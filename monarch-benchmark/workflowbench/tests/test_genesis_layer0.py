"""Feature 022, layer 0: a Genesis request is capped by what is left of the turn; every step takes its
model from the configuration, defaulting to the cheapest available route (the strongest for review and patch)."""
import json
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms import providers
from wb_studio import genesis_harness as harness
from wb_studio.genesis_config import Config, STEPS, cheapest, list_price


OPUS = providers.get('claude-opus-4-8')


def test_request_bounds_cap_output_by_what_is_left_of_the_allowance():
    # 12,000 input tokens on Opus 4.8 with $0.50 left: the cap fits what is left.
    cap, thinking, ceiling = harness.request_bounds(OPUS, 12_048, Decimal('0.50'))
    assert harness.OUTPUT_FLOOR <= cap <= harness.OUTPUT_CAP and thinking == 0
    assert ceiling <= Decimal('0.50')
    # Plenty left: the full cap.
    assert harness.request_bounds(OPUS, 12_048, Decimal('5'))[0] == harness.OUTPUT_CAP
    # Not enough for the floor: refused in words a person can act on.
    with pytest.raises(harness.GenesisRefused) as refused:
        harness.request_bounds(OPUS, 12_048, Decimal('0.03'))
    assert "allowance is spent" in str(refused.value) and 'claude-opus-4-8' in str(refused.value)


def test_tool_events_carry_a_short_credential_free_summary():
    assert harness.summary({'id': 'run-1', 'limit': 100}) == '{"id": "run-1", "limit": 100}'
    assert '[redacted]' in harness.summary({'note': 'key sk-abcdefghijkl here'}) and 'sk-abc' not in harness.summary({'note': 'key sk-abcdefghijkl here'})
    assert harness.summary('y' * 500).endswith('...') and len(harness.summary('y' * 500)) == 243


def test_route_for_prefers_the_configured_route_then_the_cheapest_available(tmp_path):
    config = Config(tmp_path)
    routes = [{'id': 'claude-opus-4-8', 'available': True}, {'id': 'glm-5.3', 'available': True}, {'id': 'gpt-5.6-sol', 'available': False}]
    assert config.read() == {'models': {s: None for s in STEPS}, 'steps': list(STEPS)}
    assert list_price('glm-5.3') < list_price('claude-opus-4-8')
    assert config.route_for('reading', routes)['id'] == 'glm-5.3'            # cheapest available, never the first in file order
    assert cheapest([{'id': 'm', 'available': True}])['id'] == 'm'         # an unpriced route is still a route
    assert config.set({'models': {'reading': 'claude-opus-4-8'}}, routes)['models']['reading'] == 'claude-opus-4-8'
    assert config.route_for('reading', routes)['id'] == 'claude-opus-4-8'
    assert config.route_for('ranking', routes)['id'] == 'glm-5.3'            # other steps keep the default
    assert config.route_for('review', routes)['id'] == 'claude-opus-4-8'     # review and patch take the strongest route by default (Lucas, 10 Sep)
    config.set({'models': {'reading': 'gpt-5.6-sol'}}, routes)              # known but unavailable today: the cheapest stands in
    assert config.route_for('reading', routes)['id'] == 'glm-5.3'
    assert config.effective(routes)['reading'] == 'glm-5.3'
    with pytest.raises(ValueError):
        config.set({'models': {'bogus': 'glm-5.3'}}, routes)
    with pytest.raises(ValueError):
        config.set({'models': {'chat': 'no-such-route'}}, routes)
    assert Config(tmp_path).read()['models']['reading'] == 'gpt-5.6-sol'   # the choice is durable
    assert config.route_for('chat', []) is None


def test_plugins_add_tools_protocol_and_prompt_without_touching_shared_files(tmp_path, monkeypatch):
    import sys
    from wb_studio import genesis_plugins
    (tmp_path / 'fake_plugin.py').write_text(
        "TOOLS={'fake_tool': lambda genesis, payload: {'echo': payload, 'who': genesis.name},"
        " 'fake_refusal': lambda genesis, payload: (_ for _ in ()).throw(ValueError('Name the run.'))}\n"
        "PROTOCOL='Use fake_tool to echo.'\n"
        "def PROMPT(genesis, turn): return '\\n\\nFake block for ' + turn['id']\n", encoding='utf8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(genesis_plugins, 'MODULES', ('fake_plugin', 'wb_studio.no_such_module_today'))
    genesis = SimpleNamespace(name='g')
    assert genesis_plugins.actions() == ['fake_tool', 'fake_refusal']
    assert genesis_plugins.dispatch(genesis, 'fake_tool', {'a': 1}) == (True, {'echo': {'a': 1}, 'who': 'g'})
    assert genesis_plugins.dispatch(genesis, 'fake_refusal', {}) == (True, {'error': 'Name the run.'})
    assert genesis_plugins.dispatch(genesis, 'unknown', {}) == (False, None)
    assert genesis_plugins.protocol() == '\n\nUse fake_tool to echo.'
    assert genesis_plugins.prompt(genesis, {'id': 't1'}) == '\n\nFake block for t1'
    # The plugin actions become typed tools beside the built-in list.
    from wb_studio import genesis_schemas
    assert set(genesis_schemas.action_names()) >= {"fake_tool", "read_run"}


def test_a_plugin_gate_holds_a_smoke_launch_and_a_persons_approval(tmp_path, monkeypatch):
    from wb_studio import genesis_plugins
    from wb_studio.genesis import Genesis
    (tmp_path / 'gate_plugin.py').write_text(
        "STATE={'ok': False}\n"
        "def review_gate(card): return (True, None) if STATE['ok'] else (False, 'The Reviewer has not accepted this plan.')\n", encoding='utf8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(genesis_plugins, 'MODULES', ('gate_plugin',))
    monkeypatch.setattr('wb_studio.runtime_registry.check_launch', lambda studio, architectures, selected, track='agentic-request': [{'id': 'without-monarch', 'name': 'API control'}])
    studio = SimpleNamespace(directory=tmp_path / 'studio', create=Mock(return_value={'id': 'run-1'}), jobs=Mock(return_value=[]), job=Mock(), events=Mock(return_value=[]), ledger=Mock())
    (tmp_path / 'studio').mkdir()
    genesis = Genesis(studio)
    proposal = {'title': 'Smoke', 'tasks': ['t1', 't2'], 'models': ['gpt-5.6-sol'], 'maximum_usd': '1.00', 'track': 'agentic-request'}
    # Within every allowance, so the autonomy gate says yes; the plugin gate holds it in Plan with the reason.
    result = genesis.propose_experiment(proposal)
    assert result['launched'] is False and result['reason'] == 'The Reviewer has not accepted this plan.'
    card = genesis.read('cards', result['card'])
    assert card['stage'] == 'approval' and card['waiting'] == result['reason'] and studio.create.call_count == 0
    # A person's approval waits for the same gate.
    with pytest.raises(ValueError, match='has not accepted'):
        genesis.approve(card['id'], {'revision': card['revision'], 'digest': card['proposal_digest']})
    assert studio.create.call_count == 0
    # Once the gate agrees, the same approval launches.
    import gate_plugin
    gate_plugin.STATE['ok'] = True
    launched = genesis.approve(card['id'], {'revision': card['revision'], 'digest': card['proposal_digest']})
    assert launched['stage'] == 'running' and launched['job'] == 'run-1' and studio.create.call_count == 1
    # A gate that breaks refuses and is recorded; it never waves a launch through.
    (tmp_path / 'gate_plugin.py').write_text("def review_gate(card): raise RuntimeError('disk gone')\n", encoding='utf8')
    import importlib
    importlib.reload(gate_plugin)
    ok, reason = genesis_plugins.gate_launch(genesis, {'id': 'x'})
    assert ok is False and 'RuntimeError' in reason
    assert genesis.autonomy.tail(1)[0]['kind'] == 'plugin-error'
