"""Offline installed-Codex acceptance check; model completions and lab state are fake.

This verifies the native protocol boundary, not live provider SDK compatibility.
"""
import json
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_harness as harness
from wb_studio.genesis_provider import response_inputs


@pytest.mark.parametrize('model', ['gpt-5.6-sol', 'claude-opus-5', 'gemini-3.7-flash', 'kimi-k3'])
def test_installed_codex_roundtrips_scoped_mcp_tool_through_sse(tmp_path, monkeypatch, model):
    requests, events, processes, actions = [], [], [], []
    usage = dict(prompt_tokens=100, cached_tokens=0, cache_write_tokens=0, output_tokens=20)
    ledger = Mock()
    def complete(provider, body, on_text):
        requests.append(body)
        assert provider.key == model
        assert body['model'] == 'genesis-scientist'
        assert ledger.reserve.call_count == len(requests)
        assert ledger.claim.call_count == len(requests)
        system, messages, tools = response_inputs(body)
        assert system
        wire_input = json.dumps(body['input'])
        for marker in ('# AI Labs working agreement', '### Available skills', '.agents/skills', '.codex/skills'):
            assert marker not in wire_input
        names = {t['function']['name'] for t in tools}
        assert names == {'list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource', 'request_user_input', 'mcp__lab__lab_action'}
        if len(requests) == 1:
            return dict(text='', calls=[dict(id='offline_call_1', name='mcp__lab__lab_action', arguments=json.dumps(dict(action='catalog', payload={})))], usage=usage)
        assert len(requests) == 2
        calls = [m for m in messages if m.get('tool_calls')]
        assert calls[-1]['tool_calls'][0]['function']['name'] == 'mcp__lab__lab_action'
        outputs = [m for m in messages if m['role'] == 'tool']
        assert len(outputs) == 1
        assert outputs[0]['tool_call_id'] == 'offline_call_1'
        assert 'OFFLINE_CATALOG_OK' in outputs[0]['content']
        on_text('OFFLINE_PROTOCOL_OK')
        return dict(text='OFFLINE_PROTOCOL_OK', calls=[], usage=usage)
    real_popen = subprocess.Popen
    class Capture(real_popen):
        def communicate(self, input=None, timeout=None):
            output = super().communicate(input=input, timeout=min(timeout or 60, 60))
            self.captured = output
            return output
    def popen(*args, **kwargs):
        process = Capture(*args, **kwargs)
        processes.append(process)
        return process
    def tool(action, payload):
        actions.append((action, payload))
        return {'catalog': 'OFFLINE_CATALOG_OK'}
    genesis = SimpleNamespace(root=tmp_path, active={}, studio=SimpleNamespace(ledger=ledger, runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext())), event=lambda identity, kind, **data: events.append({'kind': kind, **data}), tool=tool)
    monkeypatch.setattr(harness, 'complete', complete)
    monkeypatch.setattr(harness.subprocess, 'Popen', popen)
    harness.start_turn(genesis, dict(id='offline-protocol', maximum_usd='5', model=model, message='Read the lab catalog and return OFFLINE_PROTOCOL_OK.'))
    evidence = {'requests':requests, 'events':events, 'stdout':getattr(processes[0], 'captured', ('',''))[0] if processes else '', 'stderr':getattr(processes[0], 'captured', ('',''))[1] if processes else '', 'actions':actions}
    (tmp_path / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf8')
    assert [e['kind'] for e in events][-1] == 'completed', evidence
    assert len(requests) == 2, evidence
    assert actions == [('catalog', {})]
    assert 'OFFLINE_PROTOCOL_OK' in evidence['stdout']
    assert ledger.settle.call_count == 2
    ledger.finish_run.assert_called_once_with('genesis-offline-protocol')

@pytest.mark.parametrize('incomplete', [False, True], ids=['complete', 'incomplete'])
def test_broker_rounds_cost_and_settles_receipt_before_turn_outcome(tmp_path, monkeypatch, incomplete):
    from decimal import Decimal
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    usage = {'prompt_tokens': 101, 'cached_tokens': 7, 'cache_write_tokens': 0, 'output_tokens': 19}
    timeline = []
    ledger = Mock()
    ledger.settle.side_effect = lambda identity, amount: timeline.append(('settle', identity, amount))
    result = {'text': 'partial' if incomplete else 'done', 'calls': [], 'usage': usage,
              'finish_reason': 'length' if incomplete else 'stop', 'incomplete': incomplete}
    monkeypatch.setattr(harness, 'complete', Mock(return_value=result))
    monkeypatch.setattr(harness.providers, 'cost_usd', Mock(return_value=0.012345678))
    responses = []

    class LocalBrokerClient:
        def __init__(self, command, **kwargs):
            self.env = kwargs['env']
            self.returncode = None

        def communicate(self, input=None, timeout=None):
            request = Request(self.env['GENESIS_BROKER'] + '/v1/responses',
                              data=json.dumps({'model': 'genesis-scientist', 'input': []}).encode(),
                              headers={'Authorization': 'Bearer ' + self.env['GENESIS_TOKEN'],
                                       'Content-Type': 'application/json'})
            try:
                with urlopen(request, timeout=5) as response:
                    responses.append(response.status)
                    response.read()
                self.returncode = 0
            except HTTPError as exc:
                responses.append(exc.code)
                exc.read()
                self.returncode = 1
            return '', ''

        def poll(self):
            return self.returncode

    monkeypatch.setattr(harness.subprocess, 'Popen', LocalBrokerClient)
    genesis = SimpleNamespace(root=tmp_path, active={}, studio=SimpleNamespace(
        ledger=ledger, runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext())),
        event=lambda identity, kind, **data: timeline.append(('event', kind, data)))
    harness.start_turn(genesis, {'id': 'precision', 'maximum_usd': '5', 'model': 'gpt-5.6-sol', 'effort':'high', 'message': 'offline'})

    assert harness.complete.call_args.args[1]['reasoning']=={'effort':'high'}
    ledger.settle.assert_called_once_with('genesis-precision-1', Decimal('0.012346'))
    assert type(ledger.settle.call_args.args[1]) is Decimal
    assert responses == [400 if incomplete else 200]
    receipt_position = next(i for i, entry in enumerate(timeline) if entry[:2] == ('event', 'provider_receipt'))
    settle_position = next(i for i, entry in enumerate(timeline) if entry[0] == 'settle')
    outcome = 'failed' if incomplete else 'completed'
    outcome_position = next(i for i, entry in enumerate(timeline) if entry[:2] == ('event', outcome))
    assert receipt_position < settle_position < outcome_position
    assert timeline[receipt_position][2]['usage'] == usage
    if incomplete:
        error_position = next(i for i, entry in enumerate(timeline) if entry[:2] == ('event', 'request_error'))
        assert settle_position < error_position < outcome_position
    ledger.finish_run.assert_called_once_with('genesis-precision')
