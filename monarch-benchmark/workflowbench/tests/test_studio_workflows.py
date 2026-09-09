"""Offline saved-workflow validation, references, and execution boundaries."""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import wb_studio.workflows as workflows
from wb_studio.workflows import discovery_executor, execute_workflow, resolve_arguments


def step(identity, *, tool='api_fetch', arguments=None, after=None):
    return {'id': identity, 'tool': tool,
            'arguments': {'method': 'GET', 'url': '/records'} if arguments is None else arguments,
            'after': [] if after is None else after}


def run(plan, execute, **kwargs):
    records, events = [], []
    result = execute_workflow(json.dumps(plan), execute=execute,
                              record=lambda event: records.append(deepcopy(event)),
                              emit=lambda kind, **event: events.append({'type': kind, **deepcopy(event)}),
                              **kwargs)
    return result, records, events


def test_workflow_artifact_is_saved_before_any_tool_action():
    plan = {'steps': [step('read')]}
    timeline = []
    records = []

    def record(event):
        records.append(deepcopy(event))
        timeline.append(event['type'])

    def execute(tool, arguments):
        assert records == [{'type': 'workflow_artifact', 'workflow': plan,
                            'order': ['read'], 'format': 'studio-workflow-v1'}]
        timeline.append('tool_call')
        return '{"records":[{"id":"record-1"}]}'

    result = execute_workflow(json.dumps(plan), execute=execute, record=record,
                              emit=lambda kind, **event: timeline.append(kind))
    assert timeline == ['workflow_artifact', 'workflow_recipe', 'workflow_step', 'tool_call',
                        'workflow_action', 'workflow_step']
    assert result.tool_calls == 1
    assert json.loads(result.final_text) == {'read': {'records': [{'id': 'record-1'}]}}


def test_artifact_record_failure_prevents_execution():
    execute, emit = Mock(), Mock()
    record = Mock(side_effect=OSError('disk unavailable'))
    result = execute_workflow(json.dumps({'steps': [step('read')]}), execute=execute, emit=emit, record=record)
    execute.assert_not_called()
    assert result.tool_calls == 0
    assert result.termination == 'agent_error'
    assert result.error == 'Workflow could not execute: OSError'
    emit.assert_called_once_with('attempt_error', message=result.error)


def test_dag_runs_in_dependency_order_and_resolves_transitive_nested_references():
    plan = {'steps': [
        step('write', arguments={'method': 'PATCH', 'url': '/records/r-1',
                                'body': {'owner': {'$ref': 'lookup.records.0.owner'},
                                         'labels': [{'$ref': 'transform'}]}}, after=['transform']),
        step('transform', tool='base64_encode', arguments={'text': {'$ref': 'lookup.records.0.id'}}, after=['lookup']),
        step('lookup'),
    ]}
    execute = Mock(side_effect=['{"records":[{"id":"r-1","owner":"lucas"}]}',
                                'ci0x', '{"updated":true}'])
    result, records, events = run(plan, execute)
    assert [call.args for call in execute.call_args_list] == [
        ('api_fetch', {'method': 'GET', 'url': '/records'}),
        ('base64_encode', {'text': 'r-1'}),
        ('api_fetch', {'method': 'PATCH', 'url': '/records/r-1', 'body': {'owner': 'lucas', 'labels': ['ci0x']}}),
    ]
    assert records[0]['order'] == ['lookup', 'transform', 'write']
    assert [event['id'] for event in records[1:]] == ['lookup', 'transform', 'write']
    assert [(event['node'], event['status']) for event in events if event['type'] == 'workflow_step'] == [
        ('wf:lookup', 'running'), ('wf:lookup', 'completed'),
        ('wf:transform', 'running'), ('wf:transform', 'completed'),
        ('wf:write', 'running'), ('wf:write', 'completed'),
    ]
    assert result.tool_calls == 3
    assert json.loads(result.final_text) == {'lookup': {'records': [{'id': 'r-1', 'owner': 'lucas'}]},
                                           'transform': 'ci0x', 'write': {'updated': True}}


@pytest.mark.parametrize('plan', [
    None, [], {}, {'steps': []}, {'steps': [step('read')], 'unexpected': True},
    {'steps': [None]}, {'steps': [step('bad id')]},
    {'steps': [step('read', tool='shell')]}, {'steps': [step('read', arguments=[])]},
    {'steps': [step('same'), step('same')]},
    {'steps': [step('self', after=['self'])]},
    {'steps': [step('first', after=['second']), step('second', after=['first'])]},
    {'steps': [step('first', after=['absent'])]},
    {'steps': [step('first'), step('second', after=['first', 'first'])]},
    {'steps': [step('first', after=[None])]},
    {'steps': [step('first', after='other')]},
    {'steps': [step(str(index)) for index in range(101)]},
])
def test_invalid_plan_is_rejected_before_artifact_or_tool_execution(plan):
    execute = Mock()
    result, records, events = run(plan, execute)
    execute.assert_not_called()
    assert records == []
    assert result.tool_calls == 0
    assert result.termination == 'agent_error'
    assert events == [{'type': 'attempt_error', 'message': result.error}]


def test_invalid_json_is_rejected_without_execution():
    execute, record, emit = Mock(), Mock(), Mock()
    result = execute_workflow('{"steps":', execute=execute, record=record, emit=emit)
    execute.assert_not_called()
    record.assert_not_called()
    assert result.termination == 'agent_error'
    assert result.error == 'Workflow could not execute: JSONDecodeError'


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', None, ''])
def test_authoring_fetch_write_guard_rejects_every_non_get_method(method):
    execute = Mock()
    args = {'url': '/records/one', 'method': method, 'body': {'status': 'changed'}}
    value = json.loads(discovery_executor(execute)('api_fetch', args))
    assert value == {'error': 'Workflow authoring permits reads only. Put writes in the workflow artifact.'}
    execute.assert_not_called()


@pytest.mark.parametrize('method', ['GET', 'get', 'GeT'])
def test_authoring_allows_get_and_preserves_request_arguments(method):
    execute = Mock(return_value='{"records":[]}')
    args = {'method': method, 'url': '/records?owner=lucas'}
    assert discovery_executor(execute)('api_fetch', args) == '{"records":[]}'
    execute.assert_called_once_with('api_fetch', args)


@pytest.mark.parametrize('tool, args, output', [
    ('api_search', {'query': 'records'}, '{"tools":[]}'),
    ('base64_encode', {'text': 'hello'}, 'aGVsbG8='),
])
def test_authoring_allows_catalog_search_and_local_encoding(tool, args, output):
    execute = Mock(return_value=output)
    assert discovery_executor(execute)(tool, args) == output
    execute.assert_called_once_with(tool, args)


def test_action_error_is_retained_and_stops_downstream_execution():
    plan = {'steps': [step('read'), step('write', arguments={'method': 'POST', 'url': '/records'}, after=['read'])]}
    execute = Mock(return_value='{"error":"permission denied","status":403}')
    result, records, events = run(plan, execute)
    execute.assert_called_once_with('api_fetch', {'method': 'GET', 'url': '/records'})
    assert result.tool_calls == 1
    assert result.termination == 'agent_error'
    assert result.error == 'Workflow action read returned an error'
    assert records[-1] == {'type': 'workflow_action', 'id': 'read', 'tool': 'api_fetch',
                           'arguments': {'method': 'GET', 'url': '/records'},
                           'output': {'error': 'permission denied', 'status': 403}}
    assert events[-1]['node'] == 'wf:read'
    assert events[-1]['status'] == 'error'
    assert json.loads(result.final_text) == {'read': {'error': 'permission denied', 'status': 403}}


def test_raised_action_exception_stops_downstream_execution():
    execute = Mock(side_effect=OSError('connection lost'))
    result, records, events = run({'steps': [step('read'), step('write', after=['read'])]}, execute)
    assert execute.call_count == 1
    assert result.termination == 'agent_error'
    assert result.error == 'Workflow could not execute: OSError'
    assert events[-1] == {'type': 'attempt_error', 'message': result.error}
    assert result.tool_calls == 1
    assert [record['type'] for record in records] == ['workflow_artifact', 'workflow_action']
    assert records[-1] == {'type': 'workflow_action', 'id': 'read', 'tool': 'api_fetch',
                           'arguments': {'method': 'GET', 'url': '/records'}, 'error': 'OSError'}
    assert events[-2] == {'type': 'workflow_step', 'node': 'wf:read', 'label': 'api_fetch',
                          'status': 'error', 'output': 'Tool execution raised OSError'}


@pytest.mark.parametrize('stop', ['cancel', 'timeout'])
@pytest.mark.parametrize('before_start', [False, True])
def test_cancellation_or_deadline_stops_before_the_next_action(monkeypatch, stop, before_start):
    cancel = threading.Event()
    clock = SimpleNamespace(now=99.0)
    monkeypatch.setattr(workflows, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    if before_start:
        if stop == 'cancel':
            cancel.set()
        else:
            clock.now = 100.0

    def execute(tool, arguments):
        if stop == 'cancel':
            cancel.set()
        else:
            clock.now = 100.0
        return '{"read":true}'

    execute = Mock(side_effect=execute)
    result, records, events = run({'steps': [step('read'), step('write', after=['read'])]},
                                  execute, cancel=cancel, deadline=100.0)
    assert execute.call_count == (0 if before_start else 1)
    assert result.tool_calls == execute.call_count
    assert result.termination == 'timeout'
    assert result.error == 'Workflow stopped before the next action'
    assert json.loads(result.final_text) == ({} if before_start else {'read': {'read': True}})
    assert records[0]['type'] == 'workflow_artifact'
    assert [event['id'] for event in records[1:]] == ([] if before_start else ['read'])
    assert not any(event.get('node') == 'wf:write' for event in events)


def test_argument_references_preserve_zero_false_null_and_nested_literals():
    outputs = {'lookup': {'count': 0, 'enabled': False, 'optional': None, 'rows': [{'id': 'r-0'}]}}
    arguments = {'body': {'count': {'$ref': 'lookup.count'}, 'enabled': {'$ref': 'lookup.enabled'},
                          'optional': {'$ref': 'lookup.optional'},
                          'values': [0, False, {'$ref': 'lookup.rows.0.id'}]}}
    resolved = resolve_arguments(arguments, outputs, {'lookup'})
    assert resolved == {'body': {'count': 0, 'enabled': False, 'optional': None, 'values': [0, False, 'r-0']}}
    assert type(resolved['body']['count']) is int
    assert resolved['body']['enabled'] is False
    assert resolved['body']['optional'] is None
    assert arguments['body']['count'] == {'$ref': 'lookup.count'}


@pytest.mark.parametrize('reference, dependencies', [
    ('lookup.missing', ['lookup']), ('lookup.rows.5.id', ['lookup']),
    ('missing.rows.0.id', ['lookup']), ('lookup.rows.0.id', []),
    (None, ['lookup']),
])
def test_missing_or_undeclared_reference_prevents_dependent_tool_execution(reference, dependencies):
    execute = Mock(return_value='{"rows":[{"id":"r-1"}]}')
    plan = {'steps': [step('lookup'), step('write', arguments={'method': 'PATCH', 'url': {'$ref': reference}}, after=dependencies)]}
    result, records, events = run(plan, execute)
    execute.assert_called_once_with('api_fetch', {'method': 'GET', 'url': '/records'})
    assert result.tool_calls == 1
    assert result.termination == 'agent_error'
    assert [record['id'] for record in records if record['type'] == 'workflow_action'] == ['lookup']
    assert not any(event.get('node') == 'wf:write' for event in events)
    assert events[-1]['type'] == 'attempt_error'
