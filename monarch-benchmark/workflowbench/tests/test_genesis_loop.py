"""The Genesis loop (deep dive of 10 Sep 2026, M1 to M4): typed tools, one reservation per request,
refusals the model can read, a landing before the cap, the record keeping what the model read."""
import json
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms import providers
from wb_results.evidence import write_json
from wb_studio import genesis_harness as harness
from wb_studio.genesis import Genesis, stamp
from wb_studio.genesis_schemas import action_names, shaped, tool_defs


class FakeAdapter:
    """Plays a script of model responses; records what it was given."""
    script = []
    made = []

    def __init__(self, provider, tools, timeout):
        self.provider, self.tools, self.timeout = provider, tools, timeout
        FakeAdapter.made.append(self)

    def start(self, system, brief):
        self.system, self.brief = system, brief
        self.captured = [{'role': 'user', 'content': brief}]
        return self.captured

    def turn(self, messages, timeout=None):
        step = FakeAdapter.script.pop(0)
        if step.get('text') and getattr(self, 'on_text', None):
            self.on_text(step['text'])
        messages.append({'role': 'assistant', 'content': step.get('text'), 'calls': step.get('tool_calls')})
        return {'tool_calls': step.get('tool_calls', []), 'text': step.get('text'), 'reasoning': step.get('reasoning', []),
                'stop_reason': step.get('stop_reason', 'stop'), 'prompt_tokens': 100, 'cached_tokens': 0, 'output_tokens': 10, 'cache_write_tokens': 0}

    def append_tool_result(self, messages, call, result):
        messages.append({'role': 'tool', 'id': call['id'], 'content': result})


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    FakeAdapter.script, FakeAdapter.made = [], []
    monkeypatch.setattr(harness, 'ADAPTERS', {k: FakeAdapter for k in ('anthropic', 'openai', 'openai_responses', 'gemini')})
    monkeypatch.setattr(harness.providers, 'cost_usd', Mock(return_value=0.01))
    ledger = Mock()
    studio = SimpleNamespace(directory=tmp_path, ledger=ledger, runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext()),
                             jobs=Mock(return_value=[]), events=Mock(return_value=[]), create=Mock())
    studio.job = Mock(side_effect=FileNotFoundError)
    g = Genesis(studio)
    return g


def turn_record(genesis, identity='t1', card=None, maximum='2', model='claude-opus-4-8'):
    turn = {'id': identity, 'status': 'running', 'model': model, 'effort': 'default', 'message': 'What happened?', 'answer': '',
            'created_at': stamp(), 'events': [], 'maximum_usd': maximum, 'parent': None, 'card': card, 'purpose': 'Genesis conversation', 'thread': None, 'by': 'human:studio'}
    write_json(genesis.path('turns', identity), turn)
    return turn


def kinds(genesis, identity):
    return [e['type'] for e in genesis.read('turns', identity)['events']]


def test_a_turn_calls_a_typed_tool_then_answers_and_the_record_keeps_what_it_read(genesis):
    FakeAdapter.script = [{'tool_calls': [{'id': 'c1', 'name': 'skill_list', 'args': {}}], 'reasoning': ['I should list the skills.']},
                          {'text': 'There are no skills yet.'}]
    turn = turn_record(genesis)
    harness.start_turn(genesis, turn)
    saved = genesis.read('turns', 't1')
    assert saved['status'] == 'completed' and saved['answer'] == 'There are no skills yet.'
    types = kinds(genesis, 't1')
    assert types[:2] == ['harness_started', 'model_started']
    assert types.count('model_started') == 2 and 'reasoning' in types and types[-1] == 'completed'
    started = next(e for e in saved['events'] if e['type'] == 'tool_started')
    done = next(e for e in saved['events'] if e['type'] == 'tool_completed')
    assert started['action'] == 'skill_list' and done['result'] == '[]' and done['detail'] == '[]'
    assert next(e for e in saved['events'] if e['type'] == 'harness_started')['harness'] == 'loop'
    # one reservation, claim and settlement per request, all inside the turn's scope
    ledger = genesis.studio.ledger
    assert ledger.reserve.call_count == 2 and ledger.claim.call_count == 2 and ledger.settle.call_count == 2
    assert ledger.reserve.call_args_list[0].args[0] == 'genesis-t1-1' and ledger.reserve.call_args_list[0].kwargs['scope_id'] == 'genesis-t1'
    assert ledger.reserve.call_args_list[0].kwargs['scope_limit_usd'] == Decimal('2')
    assert type(ledger.settle.call_args.args[1]) is Decimal
    ledger.finish_run.assert_called_once_with('genesis-t1')
    # the adapter saw typed tools in its provider's shape, the protocol as the system prompt, SOUL.md first
    adapter = FakeAdapter.made[0]
    assert adapter.system.startswith('Identity (SOUL.md') and '# Genesis scientist protocol' in adapter.system
    assert 'Current date and time' in adapter.brief and adapter.brief.endswith('What happened?')
    assert any(t['name'] == 'read_run' and 'input_schema' in t for t in adapter.tools)
    assert (genesis.root / 'sessions' / 't1' / 'prompt.txt').exists()


def test_a_tool_refusal_reaches_the_model_as_a_sentence(genesis):
    FakeAdapter.script = [{'tool_calls': [{'id': 'c1', 'name': 'read_run', 'args': {}}]},
                          {'tool_calls': [{'id': 'c2', 'name': 'save_research', 'args': {}}]},
                          {'text': 'Done.'}]
    turn = turn_record(genesis)
    harness.start_turn(genesis, turn)
    adapter = FakeAdapter.made[0]
    messages = [m for m in adapter.captured if m.get('role') == 'tool']
    assert json.loads(messages[0]['content']) == {'error': "Missing or wrong field 'id' for read_run."}
    assert json.loads(messages[1]['content']) == {'error': 'Give the research card a short title'}
    assert genesis.read('turns', 't1')['status'] == 'completed'


def test_the_landing_tells_the_model_when_two_requests_remain_and_a_turn_that_runs_out_keeps_its_notes(genesis, monkeypatch):
    monkeypatch.setattr(harness, 'REQUEST_LIMIT', 4)
    card = genesis.card({'title': 'A card', 'body': 'x', 'stage': 'research'})
    FakeAdapter.script = [{'tool_calls': [{'id': f'c{n}', 'name': 'skill_list', 'args': {}}], 'text': 'partial thoughts' if n == 4 else ''} for n in range(1, 5)]
    turn = turn_record(genesis, card=card['id'])
    harness.start_turn(genesis, turn)
    tool_results = [m['content'] for m in FakeAdapter.made[0].captured if m.get('role') == 'tool']
    assert 'two requests remain' in tool_results[1] and 'last request' in tool_results[2] and 'Lab:' not in tool_results[0]
    saved = genesis.read('turns', 't1')
    assert saved['status'] == 'failed'
    failed = next(e for e in saved['events'] if e['type'] == 'failed')
    assert failed['reason'] == 'Genesis reached its limit of 4 requests in one turn'
    assert 'partial thoughts' in genesis.memory.note_read(card['id']) and 'stopped' in genesis.memory.note_read(card['id'])


def test_a_person_stopping_the_turn_records_one_failure(genesis, monkeypatch):
    def stop_during_tool(name, payload):
        genesis.stop_turn('t1')
        return {'ok': True}
    monkeypatch.setattr(genesis, 'tool', stop_during_tool)
    FakeAdapter.script = [{'tool_calls': [{'id': 'c1', 'name': 'skill_list', 'args': {}}]}, {'text': 'never sent'}]
    turn = turn_record(genesis)
    harness.start_turn(genesis, turn)
    saved = genesis.read('turns', 't1')
    assert saved['status'] == 'failed' and kinds(genesis, 't1').count('failed') == 1
    assert next(e for e in saved['events'] if e['type'] == 'failed')['message'] == 'Stopped by a person'
    assert FakeAdapter.script == [{'text': 'never sent'}]  # the second request was never made
    genesis.studio.ledger.finish_run.assert_called_once_with('genesis-t1')


def test_a_ledger_refusal_is_shown_in_words(genesis):
    from wb_orchestrator.budget import BudgetExceeded
    genesis.studio.ledger.reserve.side_effect = BudgetExceeded('shared weekly budget exhausted')
    FakeAdapter.script = [{'text': 'unreachable'}]
    turn = turn_record(genesis)
    harness.start_turn(genesis, turn)
    saved = genesis.read('turns', 't1')
    assert saved['status'] == 'failed'
    reason = next(e for e in saved['events'] if e['type'] == 'request_error')['reason']
    assert reason == "The ledger refused the request (shared weekly budget exhausted): $2.00 left of the turn's $2.00."


def test_request_bounds_pay_for_thinking_only_when_the_turn_can(monkeypatch):
    gemini = providers.get('gemini-3.7-flash')
    cap, thinking, ceiling = harness.request_bounds(gemini, 10_000, Decimal('5'))
    assert cap == harness.OUTPUT_CAP and thinking == harness.THINKING_ALLOWANCE['gemini']
    cap, thinking, ceiling = harness.request_bounds(gemini, 10_000, Decimal('0.02'))
    assert harness.OUTPUT_FLOOR <= cap and thinking < harness.THINKING_ALLOWANCE['gemini'] and ceiling <= Decimal('0.02')
    opus = providers.get('claude-opus-4-8')
    with pytest.raises(harness.GenesisRefused, match='allowance is spent'):
        harness.request_bounds(opus, 20_000, Decimal('0.03'))


def test_every_action_has_a_typed_tool_in_every_shape():
    names = action_names()
    for expected in ('read_run', 'measures', 'hypothesis_check', 'propose_experiment', 'memory_recent', 'code_search', 'request_review'):
        assert expected in names
    defs = tool_defs()
    assert all(d['parameters']['type'] == 'object' for d in defs)
    assert next(d for d in defs if d['name'] == 'read_run')['parameters']['required'] == ['id']
    assert [t['name'] for t in shaped(defs, 'anthropic')] == names and shaped(defs, 'anthropic')[-1]['cache_control'] == {'type': 'ephemeral'}
    assert shaped(defs, 'openai')[0]['function']['name'] == names[0]
    assert shaped(defs, 'openai_responses')[0]['type'] == 'function' and 'function' not in shaped(defs, 'openai_responses')[0]
    assert shaped(defs, 'gemini')[0]['name'] == names[0]
    assert shaped([], 'anthropic') == []


def test_model_routes_need_only_a_key(monkeypatch):
    monkeypatch.setattr(harness.providers, 'api_key', lambda p: 'k' if p.key == 'claude-opus-4-8' else None)
    routes = {r['id']: r for r in harness.model_routes()}
    assert routes['claude-opus-4-8']['available'] is True and routes['claude-opus-4-8']['harness'] == 'loop'
    assert all(r['harness_ready'] for r in routes.values())


def test_sdk_message_objects_do_not_break_the_size_estimate(genesis):
    class Content:
        def __init__(self, text): self.text = text
        def model_dump(self, mode='json', exclude_none=True): return {'text': self.text}

    class ObjectAdapter(FakeAdapter):
        def start(self, system, brief):
            self.system, self.brief = system, brief
            self.captured = [Content(brief)]
            return self.captured

        def append_tool_result(self, messages, call, result):
            messages.append(Content(result))
    genesis_module = harness.ADAPTERS
    genesis_module['anthropic'] = ObjectAdapter
    FakeAdapter.script = [{'tool_calls': [{'id': 'c1', 'name': 'skill_list', 'args': {}}]}, {'text': 'Fine.'}]
    harness.start_turn(genesis, turn_record(genesis))
    assert genesis.read('turns', 't1')['status'] == 'completed'
