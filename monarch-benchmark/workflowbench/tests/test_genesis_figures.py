"""Figures in a card (feature 023 §5.9): Genesis names a kind and a run, the Studio computes every
number from the same report the reader sees, and the chart kit draws it. The model writes the
caption and nothing else."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio import figures
from wb_studio.genesis import Genesis

REPORT = {
    'run': 'run-9', 'finished_at': '2026-09-11T10:00:00+00:00',
    'order': ['a', 'b'], 'baseline': 'b',
    'hero': [{'id': 'a', 'label': 'GPT-5.6 Sol', 'value': 0.9, 'low': 0.6, 'high': 0.98, 'detail': '9 / 10', 'baseline': False},
             {'id': 'b', 'label': 'Bare', 'value': 0.5, 'low': 0.2, 'high': 0.8, 'detail': '5 / 10', 'baseline': True}],
    'setups': {'a': {'name': 'GPT-5.6 Sol', 'short_name': 'GPT-5.6 Sol', 'is_baseline': False,
                     'pass': {'rate': 0.9, 'low': 0.6, 'high': 0.98}, 'cost': {'per_attempt': 0.02}},
               'b': {'name': 'Bare', 'short_name': 'Bare', 'is_baseline': True,
                     'pass': {'rate': 0.5, 'low': 0.2, 'high': 0.8}, 'cost': {'per_attempt': 0.01}}},
    'failures': {'summary': {'failed_attempts': 6, 'recorded_attempts': 20},
                 'buckets': [{'id': 'wrong-field', 'label': 'Wrote a field nobody asked for', 'count': 6}]},
    'tasks': [{'id': 't1'}, {'id': 't2'}], 'matrix': {'t1': {}},
    'method': {'task_count': 10, 'repetitions': 2},
}


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    (tmp_path / 'genesis').mkdir(exist_ok=True)
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'glm-5.3', 'available': True}])
    monkeypatch.setattr('wb_studio.report_data.run_report', lambda studio, run: dict(REPORT))
    studio = SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), events=Mock(return_value=[]),
                             job=Mock(), create=Mock(), budget=Mock(return_value={}),
                             ledger=BudgetLedger(tmp_path / 'budget.sqlite3'))
    made = Genesis(studio)
    studio.genesis = made
    return made


# -- the catalogue -------------------------------------------------------------------

def test_the_kinds_the_model_sees_are_the_kinds_that_exist():
    from wb_studio.genesis_schemas import SCHEMAS, action_names
    assert [k['kind'] for k in figures.catalogue()] == list(figures.KINDS)
    assert SCHEMAS['figure'][1]['properties']['kind']['enum'] == list(figures.KINDS)
    assert 'figure' in action_names()
    assert all(shows.endswith('.') for shows, _ in figures.KINDS.values())


@pytest.mark.parametrize('kind, chart', [('pass_rate', 'dotWhisker'), ('failures', 'failureColumns'),
                                         ('cost_against_pass_rate', 'scatter'), ('tasks', 'matrix')])
def test_every_kind_builds_from_the_report_the_reader_sees(genesis, kind, chart):
    figure = figures.build(genesis.studio, kind, 'run-9')
    assert figure['chart'] == chart and figure['kind'] == kind and figure['run'] == 'run-9'
    assert figure['source'].startswith('Run run-9') and figure['source'].endswith('.')
    assert '10 tasks × 2 setups' in figure['source'] and '2 repetitions' in figure['source']   # F6
    assert figure['options'] and 'title' in figure['options'] or chart == 'matrix'


def test_the_numbers_are_the_reports_own(genesis):
    rows = figures.build(genesis.studio, 'pass_rate', 'run-9')['options']['rows']
    assert [r['value'] for r in rows] == [0.9, 0.5] and [r['low'] for r in rows] == [0.6, 0.2]
    points = figures.build(genesis.studio, 'cost_against_pass_rate', 'run-9')['options']['points']
    assert [(p['x'], p['y']) for p in points] == [(0.02, 0.9), (0.01, 0.5)]


def test_a_run_that_cannot_carry_the_figure_is_refused_in_a_sentence(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.report_data.run_report',
                        lambda studio, run: {**REPORT, 'hero': [], 'failures': {'summary': {}, 'buckets': []},
                                             'setups': {}, 'order': [], 'tasks': []})
    for kind, message in [('pass_rate', 'no evaluated attempts'), ('failures', 'Nothing failed'),
                          ('cost_against_pass_rate', 'no setup in this run has a known cost'),
                          ('tasks', 'records no tasks')]:
        with pytest.raises(ValueError, match='(?i)' + message):
            figures.build(genesis.studio, kind, 'run-9')
    with pytest.raises(ValueError, match='Figure kinds are'):
        figures.build(genesis.studio, 'a pie chart', 'run-9')
    with pytest.raises(ValueError, match='Name the run'):
        figures.build(genesis.studio, 'pass_rate', '')


# -- what the model may and may not put in one ----------------------------------------

def test_the_model_writes_the_caption_and_nothing_else(genesis):
    answer = figures.tool(genesis, {'kind': 'pass_rate', 'run': 'run-9', 'caption': 'Sol is ahead of Bare.',
                                    'options': {'rows': [{'label': 'Invented', 'value': 1.0}]},
                                    'chart': 'somethingElse', 'source': 'made up', 'audience': 'public'})
    stored = figures.read(genesis, answer['figure'])
    assert stored['caption'] == 'Sol is ahead of Bare.'
    assert stored['chart'] == 'dotWhisker'                       # not the model's 'somethingElse'
    assert [r['label'] for r in stored['options']['rows']] == ['GPT-5.6 Sol', 'Bare']   # not 'Invented'
    assert stored['source'].startswith('Run run-9')              # not 'made up'
    assert '[figure:' + answer['figure'] + ']' in answer['note']


def test_a_figure_id_is_read_only_and_a_bad_one_is_refused(genesis):
    figure = figures.save(genesis, figures.build(genesis.studio, 'failures', 'run-9'))
    assert figures.read(genesis, figure['id'])['kind'] == 'failures'
    for bad in ('../../etc/passwd', 'nope', 'a b', ''):
        with pytest.raises(ValueError, match='No figure is called'):
            figures.read(genesis, bad)


def test_the_figure_is_served_read_only_over_http(genesis):
    import http.client
    import threading
    from contextlib import contextmanager
    from http.server import ThreadingHTTPServer
    from wb_studio.app import handler

    figure = figures.save(genesis, figures.build(genesis.studio, 'pass_rate', 'run-9'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(genesis.studio))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        def get(path):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                return response.status, response.read().decode()
            finally:
                connection.close()

        status, body = get('/api/genesis/figures/' + figure['id'])
        assert status == 200 and json.loads(body)['chart'] == 'dotWhisker'
        assert json.loads(body)['options']['rows'][0]['value'] == 0.9
        assert get('/api/genesis/figures/deadbeef')[0] == 404
        assert get('/api/genesis/figures/..%2F..%2Fsecrets')[0] in (400, 404)
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)


# -- the card the reader sees ---------------------------------------------------------

def test_a_finding_card_is_short_and_carries_its_figure():
    from wb_studio import genesis_critic as critic
    found = {'analysis': 'lowest_contrast records 4.1 on the 11px "3 runs" line; F12 wants 4.5.',
             'rubric': 'figures:F12', 'where': 'Runs, light', 'what': 'Contrast is 4.1 on 11px text.',
             'why_it_matters': 'A reader cannot read the run count.', 'fix': 'Darken the muted ink.',
             'figure': '[figure:abc123]'}
    body = critic.body_of(found, None)
    assert body.startswith('Contrast is 4.1 on 11px text.\n\n')      # the claim first
    assert '| Fails | figures:F12 |' in body and '| Where | Runs, light |' in body
    assert body.rstrip().endswith('[figure:abc123]')
    assert len(body) < 900 and body.count('\n\n') <= 4               # fifteen seconds, not three paragraphs

    checked = critic.check_finding({**found, 'figure': 'draw me a pie chart'}, critic.rubric_lines())
    assert checked['figure'] == ''                                   # only a real tag survives
    assert critic.check_finding(found, critic.rubric_lines())['figure'] == '[figure:abc123]'
    assert 'figure' in critic.OUTPUT and 'never a figure for a finding about prose' in critic.OUTPUT
