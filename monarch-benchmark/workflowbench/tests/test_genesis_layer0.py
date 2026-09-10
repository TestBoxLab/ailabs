"""Feature 022, layer 0: a Genesis turn spends its allowance across requests and stops in words;
every step takes its model from the configuration, defaulting to the cheapest available route."""
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
    # A 20 KB request on Opus 4.8 with $0.50 left: the old rule reserved above $0.50; now the cap fits.
    tokens, cap, ceiling = harness.request_bounds(OPUS, 20_000, Decimal('0.50'))
    assert tokens == 20_000 // 2 + 2048
    assert harness.OUTPUT_FLOOR <= cap <= harness.OUTPUT_CAP
    assert ceiling <= Decimal('0.50')
    # Plenty left: the full cap.
    assert harness.request_bounds(OPUS, 20_000, Decimal('5'))[1] == harness.OUTPUT_CAP
    # Not enough for the floor: refused in words a person can act on.
    with pytest.raises(harness.GenesisRefused) as refused:
        harness.request_bounds(OPUS, 20_000, Decimal('0.03'))
    assert "allowance is spent" in str(refused.value) and 'claude-opus-4-8' in str(refused.value)


def test_broker_spends_the_allowance_across_requests_and_stops_with_the_reason(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    usage = {'prompt_tokens': 12_000, 'cached_tokens': 0, 'cache_write_tokens': 0, 'output_tokens': 4_000}
    bodies, statuses, timeline = [], [], []
    ledger = Mock()
    ledger.reserve.side_effect = lambda identity, ceiling, **kw: timeline.append(('reserve', Decimal(ceiling)))
    ledger.settle.side_effect = lambda identity, amount, **details: timeline.append(('settle', Decimal(amount)))

    def complete(provider, body, on_text):
        bodies.append(body)
        return {'text': 'ok', 'calls': [], 'usage': usage, 'finish_reason': 'end_turn', 'incomplete': False}
    monkeypatch.setattr(harness, 'complete', complete)
    monkeypatch.setattr(harness.providers, 'cost_usd', Mock(return_value=0.20))   # every request settles at $0.20

    class Client:
        def __init__(self, command, **kwargs):
            self.env = kwargs['env']
            self.returncode = None

        def communicate(self, input=None, timeout=None):
            payload = json.dumps({'model': 'genesis-scientist', 'input': [{'role': 'user', 'content': 'x' * 20_000}]}).encode()
            for _ in range(6):
                request = Request(self.env['GENESIS_BROKER'] + '/v1/responses', data=payload,
                                  headers={'Authorization': 'Bearer ' + self.env['GENESIS_TOKEN'], 'Content-Type': 'application/json'})
                try:
                    with urlopen(request, timeout=5) as response:
                        statuses.append(response.status)
                        response.read()
                except HTTPError as exc:
                    statuses.append(exc.code)
                    exc.read()
                    self.returncode = 1
                    return '', ''
            self.returncode = 0
            return '', ''

        def poll(self):
            return self.returncode

    monkeypatch.setattr(harness.subprocess, 'Popen', Client)
    events = []
    genesis = SimpleNamespace(root=tmp_path, active={}, studio=SimpleNamespace(ledger=ledger, runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext())),
                              event=lambda identity, kind, **data: events.append({'kind': kind, **data}))
    harness.start_turn(genesis, {'id': 'allowance', 'maximum_usd': '0.50', 'model': 'claude-opus-4-8', 'message': 'offline'})

    # Two requests fit a $0.50 allowance at $0.20 each; the third cannot afford the floor and is refused.
    assert statuses == [200, 200, 400]
    reserves = [amount for kind, amount in timeline if kind == 'reserve']
    assert len(reserves) == 2 and reserves[0] <= Decimal('0.50') and reserves[1] <= Decimal('0.30')
    caps = [b['_max_output'] for b in bodies]
    assert caps[0] == harness.OUTPUT_CAP and harness.OUTPUT_FLOOR <= caps[1] < caps[0]
    started = [e for e in events if e['kind'] == 'model_started']
    assert [e['max_output'] for e in started] == caps
    refusal = [e for e in events if e['kind'] == 'request_error'][-1]
    assert refusal['reason'].startswith("The turn's allowance is spent")
    failed = [e for e in events if e['kind'] == 'failed'][-1]
    assert failed['reason'] == refusal['reason']
    ledger.finish_run.assert_called_once_with('genesis-allowance')


def test_ledger_refusals_are_shown_in_words(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from wb_orchestrator.budget import BudgetExceeded

    ledger = Mock()
    ledger.reserve.side_effect = BudgetExceeded('shared weekly budget exhausted')
    monkeypatch.setattr(harness, 'complete', Mock())
    events = []

    class Client:
        def __init__(self, command, **kwargs):
            self.env = kwargs['env']
            self.returncode = None

        def communicate(self, input=None, timeout=None):
            request = Request(self.env['GENESIS_BROKER'] + '/v1/responses', data=json.dumps({'model': 'genesis-scientist', 'input': []}).encode(),
                              headers={'Authorization': 'Bearer ' + self.env['GENESIS_TOKEN'], 'Content-Type': 'application/json'})
            try:
                with urlopen(request, timeout=5) as response:
                    response.read()
            except HTTPError as exc:
                exc.read()
            self.returncode = 1
            return '', ''

        def poll(self):
            return self.returncode

    monkeypatch.setattr(harness.subprocess, 'Popen', Client)
    genesis = SimpleNamespace(root=tmp_path, active={}, studio=SimpleNamespace(ledger=ledger, runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext())),
                              event=lambda identity, kind, **data: events.append({'kind': kind, **data}))
    harness.start_turn(genesis, {'id': 'weekly', 'maximum_usd': '2', 'model': 'gpt-5.6-sol', 'message': 'offline'})
    reason = [e for e in events if e['kind'] == 'request_error'][-1]['reason']
    assert reason == "The ledger refused the request (shared weekly budget exhausted): $2.00 left of the turn's $2.00."
    assert harness.complete.call_count == 0


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
    assert config.route_for('verdict', routes)['id'] == 'glm-5.3'            # other steps keep the default
    config.set({'models': {'reading': 'gpt-5.6-sol'}}, routes)              # known but unavailable today: the cheapest stands in
    assert config.route_for('reading', routes)['id'] == 'glm-5.3'
    assert config.effective(routes)['reading'] == 'glm-5.3'
    with pytest.raises(ValueError):
        config.set({'models': {'bogus': 'glm-5.3'}}, routes)
    with pytest.raises(ValueError):
        config.set({'models': {'chat': 'no-such-route'}}, routes)
    assert Config(tmp_path).read()['models']['reading'] == 'gpt-5.6-sol'   # the choice is durable
    assert config.route_for('chat', []) is None


def test_chat_completions_adapter_sends_the_output_cap(monkeypatch):
    import openai
    from wb_studio import genesis_provider
    sent = {}

    class Chunk:
        def __init__(self, usage=None, content=None, finish=None):
            self.usage = usage
            delta = SimpleNamespace(content=content, tool_calls=None)
            self.choices = [SimpleNamespace(finish_reason=finish, delta=delta)]

    class Completions:
        def create(self, **kwargs):
            sent.update(kwargs)
            return iter([Chunk(content='hi'), Chunk(finish='stop', usage=SimpleNamespace(model_dump=lambda: {'prompt_tokens': 3, 'completion_tokens': 1}))])

    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    monkeypatch.setattr(genesis_provider.providers, 'api_key', lambda p: 'k')
    monkeypatch.setattr(genesis_provider.providers, 'extract_cached_tokens', lambda meta, headers, p: (0, None))
    provider = providers.Provider(key='cheap', model_id='cheap', key_env='X', adapter='openai', price_in=0.1, price_cached=0.01, price_out=0.2, base_url='http://x')
    result = genesis_provider.complete(provider, {'instructions': 's', 'input': [{'role': 'user', 'content': 'q'}], '_max_output': 2048}, lambda t: None)
    assert sent['max_tokens'] == 2048 and result['text'] == 'hi'


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
    # The harness names the plugin actions to the MCP adapter, which admits them beside the built-in list.
    monkeypatch.setenv('GENESIS_ACTIONS', ','.join(genesis_plugins.actions()))
    source = (harness.Path(harness.__file__).with_name('genesis_mcp.py')).read_text(encoding='utf8')
    namespace = {}
    exec(source.split('def respond')[0], namespace)
    assert 'fake_tool' in namespace['ACTIONS'] and 'read_run' in namespace['ACTIONS']


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
