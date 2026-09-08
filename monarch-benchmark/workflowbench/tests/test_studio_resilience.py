"""Malformed UI payloads must fail before persistence or paid dispatch."""
from decimal import Decimal
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from wb_studio.app import ROOT, Studio, handler
from wb_studio.blueprints import problems, validate_graph
from wb_world.episode import load_suite


@pytest.fixture
def studio(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('A resilience test attempted paid dispatch')
    return Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=forbidden)


@pytest.mark.parametrize('node', [None, [], 12, 'node', {'id': 'worker', 'type': []},
                                   {'id': 'worker', 'type': {}, 'config': []}])
def test_malformed_nodes_have_actionable_validation(node):
    graph = {'nodes': [node], 'edges': []}
    found = problems(graph)
    assert found and all(p['message'] for p in found)
    with pytest.raises(ValueError):
        validate_graph(graph)


@pytest.mark.parametrize('endpoint', [[], {}, None, 5])
def test_malformed_connection_endpoint_is_a_validation_problem(endpoint):
    graph = {'nodes': [{'id': 'input', 'type': 'input', 'label': 'Input', 'x': 10, 'y': 10, 'config': {}}],
             'edges': [{'from': endpoint, 'to': 'input'}]}
    assert any('existing nodes' in p['message'] for p in problems(graph))


@pytest.mark.parametrize('changes', [
    {'tasks': [{}]}, {'tasks': [[]]}, {'tasks': [None]},
    {'architectures': [{}]}, {'architectures': [[]]}, {'architectures': [None]},
    {'models': [{}]}, {'models': [[]]}, {'models': [None]},
])
def test_bad_selections_never_create_jobs_or_reservations(studio, changes):
    with pytest.raises(ValueError):
        studio.create({'models': ['oracle'], 'tasks': list(studio.tasks), 'maximum_usd': '1', **changes}, start=False)
    assert studio.jobs() == []
    assert Decimal(studio.budget()['held']) == 0


@pytest.mark.parametrize('graph', [None, {}, {'nodes': None, 'edges': []},
    {'nodes': [None], 'edges': []},
    {'nodes': [{'id': 'bad', 'type': 'agent', 'label': 'Bad', 'x': 0, 'y': 0, 'config': None}], 'edges': []}])
def test_http_graph_validation_returns_json_instead_of_dropping_connection(studio, graph):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(studio))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    try:
        connection.request('POST', '/api/blueprints/validate', json.dumps({'graph': graph}),
                           {'Content-Type': 'application/json', 'X-Studio-Token': studio.token})
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 200, body
        assert body['problems']
        assert body['capabilities'] == []
        assert studio.jobs() == []
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)

