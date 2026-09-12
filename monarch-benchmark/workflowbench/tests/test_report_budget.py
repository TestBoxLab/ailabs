"""Report preflight uses native token accounting without dispatching provider work."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms import providers
from wb_studio import genesis_harness as harness
from wb_studio import report_budget


@pytest.fixture
def setup(monkeypatch):
    adapter = Mock()
    adapter.start.side_effect = lambda system, brief, images: [{'role': 'user', 'content': brief}]
    factory = Mock(return_value=adapter)
    monkeypatch.setattr(harness, 'ADAPTERS', {'anthropic': factory})
    monkeypatch.setattr(harness, 'build_prompt', lambda genesis, turn: ('Protocol ' * 200, turn['message']))
    genesis = SimpleNamespace(studio=SimpleNamespace(ledger=Mock()), chat=Mock())
    turns = {name: {'id': name, 'model': 'claude-opus-4-8', 'purpose': 'Genesis report:run1:' + name,
                    'maximum_usd': str(amount), 'message': 'Read all retained evidence. ' * 10}
             for name, amount in [('analysis', '.30'), ('author', '.25'), ('review', '.15'),
                                  ('repair', '.20'), ('review_again', '.10')]}
    return genesis, turns, adapter, factory


def test_preflight_checks_every_turn_and_does_not_spend_or_change_allocations(setup):
    genesis, turns, adapter, factory = setup
    before = deepcopy(turns)
    result = report_budget.validate(genesis, turns, Decimal('1'))
    assert set(result['turns']) == set(turns)
    assert all(Decimal(row['first_request_minimum_usd']) > 0 for row in result['turns'].values())
    assert factory.call_count == 5
    assert adapter.start.call_count == 5
    adapter.turn.assert_not_called()
    genesis.chat.assert_not_called()
    assert genesis.studio.ledger.mock_calls == []
    assert turns == before


def test_preflight_refuses_an_underfunded_later_review_before_any_spend(setup):
    genesis, turns, adapter, _ = setup
    turns['review_again']['maximum_usd'] = '.000001'
    with pytest.raises(ValueError, match=r'review_again.*at least \$[0-9]+\.[0-9]{2}.*first request'):
        report_budget.validate(genesis, turns, Decimal('1'))
    adapter.turn.assert_not_called()
    assert genesis.studio.ledger.mock_calls == []


def test_preflight_uses_the_actual_report_prompt_and_native_token_floor(setup):
    genesis, turns, adapter, _ = setup
    result = report_budget.validate(genesis, turns, Decimal('1'))
    row = result['turns']['analysis']
    provider = providers.get('claude-opus-4-8')
    floor = Decimal(row['first_request_minimum_usd'])
    # The floor must admit exactly a minimally complete native response, and a
    # micro-dollar below it must refuse. This also catches omitted cache writes.
    output, _, _ = harness.request_bounds(provider, row['input_tokens'], floor)
    assert output >= harness.OUTPUT_FLOOR
    with pytest.raises(harness.GenesisRefused):
        harness.request_bounds(provider, row['input_tokens'], floor - Decimal('.000001'))
    assert adapter.start.call_args_list[0].args == ('Protocol ' * 200, turns['analysis']['message'], None)


def test_preflight_counts_additional_analysis_batches(setup):
    genesis, turns, adapter, _ = setup
    turns['analysis_2'] = {**turns['analysis'], 'id': 'a2', 'purpose': 'Genesis report:run1:analysis_2',
                            'maximum_usd': '.000001', 'indexes': [4, 5, 6, 7]}
    with pytest.raises(ValueError, match='analysis_2'):
        report_budget.validate(genesis, turns, Decimal('1'))
    adapter.turn.assert_not_called()


def test_preflight_requires_the_exact_prepared_dispatch_message(setup):
    genesis, turns, adapter, _ = setup
    del turns['analysis']['message']
    with pytest.raises(ValueError, match='dispatch message'):
        report_budget.validate(genesis, turns, Decimal('1'))
    adapter.turn.assert_not_called()


@pytest.mark.parametrize('model', ['claude-opus-4-8', 'glm-5.3-fireworks', 'gpt-5.6-sol', 'gemini-3.7-flash'])
def test_actual_provider_message_shapes_match_native_accounting_without_requests(monkeypatch, model):
    from wb_studio.genesis_reports import allowed_tools

    monkeypatch.setattr(providers, 'api_key', lambda provider: 'offline-test-key')
    monkeypatch.setattr(harness, 'build_prompt', lambda genesis, turn: ('System. ' * 20, 'Read evidence.'))
    provider = providers.get(model)
    cls = harness.ADAPTERS[provider.adapter]
    sent = Mock(side_effect=AssertionError('Preflight must never call a provider'))
    monkeypatch.setattr(cls, 'turn', sent)
    turn = {'id': 'analysis', 'model': model, 'purpose': 'Genesis report:run1:analysis',
            'maximum_usd': '1', 'message': 'Read evidence.'}
    tools = harness.shaped(harness.tool_defs(allowed_tools(turn)), provider.adapter)
    adapter = cls(provider, tools, harness.REQUEST_TIMEOUT)
    try:
        messages = adapter.start('System. ' * 20, 'Read evidence.', None)
        serialized = harness.canonical_json(harness._json_messages(messages))
        expected = (len('System. ' * 20) + len(serialized) + len(harness.canonical_json(tools))) // 2 + 1024
    finally:
        adapter.client.close()
    result = report_budget.validate(SimpleNamespace(), {'analysis': turn}, Decimal('1'))
    assert result['turns']['analysis']['input_tokens'] == expected
    sent.assert_not_called()
