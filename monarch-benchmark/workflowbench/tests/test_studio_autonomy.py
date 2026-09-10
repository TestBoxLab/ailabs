"""Genesis autonomy (feature 021): three dials, the switch, smoke-scale launches, question cards, the activity record."""
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio.genesis import Genesis
from wb_studio.genesis_autonomy import Autonomy, plan_lines


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDIO_GENESIS_CARD_USD', '2.00')
    monkeypatch.setenv('STUDIO_GENESIS_DAILY_USD', '6.00')
    ledger = Mock()
    ledger.status.return_value = SimpleNamespace(blocked=False, available_usd=Decimal('100'))
    studio = SimpleNamespace(directory=tmp_path, create=Mock(return_value={'id': 'run-accepted'}), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=ledger)
    monkeypatch.setattr('wb_studio.runtime_registry.check_launch', lambda studio, architectures, selected, track='agentic-request': [{'id': 'without-monarch', 'name': 'API control'}])
    return Genesis(studio)


SMOKE = {'title': 'Two tasks', 'tasks': ['t1', 't2'], 'models': ['gemini-3.7-flash'], 'maximum_usd': '1.00', 'track': 'agentic-request'}


def test_dials_default_validate_and_record(tmp_path):
    a = Autonomy(tmp_path)
    state = a.read()
    assert state['cards'] == 'act' and state['runs'] == 'smoke' and state['paused'] is False and state['smoke_attempts'] == 20
    with pytest.raises(ValueError):
        a.set({'runs': 'anything'})
    a.set({'runs': 'propose', 'paused': True}, by='human:lucas')
    assert a.read()['runs'] == 'propose' and a.read()['paused'] is True
    kinds = [(e['kind'], e['setting'], e['after']) for e in a.tail()]
    assert ('autonomy', 'runs', 'propose') in kinds and ('autonomy', 'paused', True) in kinds and all(e['by'] == 'human:lucas' for e in a.tail())


def test_may_launch_gates_in_order(tmp_path):
    a = Autonomy(tmp_path)
    plan = {'attempts_per_competitor': 2, 'maximum_usd': '1.00'}
    assert a.may_launch(plan, Decimal('0'), Decimal('2'), Decimal('6')) == (True, None)
    assert 'above smoke scale' in a.may_launch({'attempts_per_competitor': 21, 'maximum_usd': '1.00'}, Decimal('0'), Decimal('2'), Decimal('6'))[1]
    assert 'per-card allowance' in a.may_launch({'attempts_per_competitor': 2, 'maximum_usd': '3.00'}, Decimal('0'), Decimal('2'), Decimal('6'))[1]
    assert "Today's allowance" in a.may_launch(plan, Decimal('5.50'), Decimal('2'), Decimal('6'))[1]
    a.set({'runs': 'propose'})
    assert 'waits for a person' in a.may_launch(plan, Decimal('0'), Decimal('2'), Decimal('6'))[1]
    a.set({'runs': 'smoke', 'paused': True})
    assert 'paused' in a.may_launch(plan, Decimal('0'), Decimal('2'), Decimal('6'))[1]


def test_plan_lines_are_computed_by_the_studio(genesis):
    plan = plan_lines(genesis.studio, {**SMOKE, 'bare_models': ['gemini-3.7-flash']})
    assert plan['attempts_per_competitor'] == 2 and plan['attempts'] == 4 and plan['smoke'] is True
    assert plan['competitors'] == ['gemini-3.7-flash', 'Bare gemini-3.7-flash'] and plan['maximum_usd'] == '1.00'
    assert plan['lines'][0] == '2 tasks, each run once by every competitor' and '(smoke scale)' in plan['lines'][2]
    with pytest.raises(ValueError, match='tasks'):
        plan_lines(genesis.studio, {**SMOKE, 'tasks': []})
    with pytest.raises(ValueError, match='maximum_usd'):
        plan_lines(genesis.studio, {**SMOKE, 'maximum_usd': '0'})


def test_smoke_plan_launches_itself_and_is_recorded(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_plugins.gate_launch', lambda g, c: (True, None))  # the Reviewer chamber (feature 022) has its own tests
    out = genesis.tool('propose_experiment', {**SMOKE, 'body': 'A hypothesis.'})
    assert out['launched'] is True and out['job'] == 'run-accepted' and out['stage'] == 'running'
    card = genesis.read('cards', out['card'])
    assert card['stage'] == 'running' and card['approval']['by'] == 'genesis:smoke' and card['plan']['attempts'] == 2 and card['proposal']['operation'] == 'run'
    request = genesis.studio.create.call_args.args[0]
    assert request['tasks'] == ['t1', 't2'] and request['request_id'].startswith('genesis-' + card['id'])
    kinds = [e['kind'] for e in genesis.autonomy.tail()]
    assert kinds[:3] == ['launch', 'plan', 'card'] or set(kinds) >= {'launch', 'plan', 'card'}


def test_plan_above_smoke_or_under_propose_waits_for_a_person(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_plugins.gate_launch', lambda g, c: (True, None))  # the Reviewer chamber (feature 022) has its own tests
    big = {**SMOKE, 'tasks': [f't{i}' for i in range(21)]}
    out = genesis.tool('propose_experiment', big)
    assert out['launched'] is False and 'above smoke scale' in out['reason']
    card = genesis.read('cards', out['card'])
    assert card['stage'] == 'approval' and card['waiting'] and card.get('job') is None
    genesis.studio.create.assert_not_called()
    genesis.autonomy.set({'runs': 'propose'})
    out = genesis.tool('propose_experiment', SMOKE)
    assert out['launched'] is False and 'waits for a person' in out['reason']
    genesis.studio.create.assert_not_called()
    # a person approves it through the existing path, and the launch names the person
    card = genesis.read('cards', out['card'])
    approved = genesis.approve(card['id'], {'revision': card['revision'], 'digest': card['proposal_digest'], 'by': 'human:lucas'})
    assert approved['stage'] == 'running' and approved['approval']['by'] == 'human:lucas' and approved['waiting'] is None
    genesis.studio.create.assert_called_once()


def test_runs_off_refuses_before_any_plan(genesis):
    genesis.autonomy.set({'runs': 'off'})
    with pytest.raises(ValueError, match='Runs dial is off'):
        genesis.tool('propose_experiment', SMOKE)


def test_question_card_blocks_and_answer_resumes(genesis):
    blocked = genesis.drop({'text': 'Monarch fails more on two-app tasks.'})
    with genesis.lock:
        card = genesis.read('cards', blocked['id']); card['work'] = {'status': 'working', 'turn': 'turn-1'}
        genesis.card  # noqa: B018
        from wb_studio.genesis import write_json
        write_json(genesis.path('cards', blocked['id']), card)
    out = genesis.tool('ask_question', {'card': blocked['id'], 'question': 'Which task set: tier-medium or random-10?', 'default': 'tier-medium'})
    q = genesis.read('cards', out['card'])
    assert q['kind'] == 'question' and q['stage'] == 'approval' and q['default'] == 'tier-medium' and q['blocks'] == blocked['id'] and q['auto'] is False
    assert genesis.read('cards', blocked['id'])['work']['status'] == 'waiting'
    # the turn ends: the blocked card stays waiting, not done
    genesis.finish_card({'id': 'turn-1', 'card': blocked['id'], 'status': 'completed', 'events': []})
    assert genesis.read('cards', blocked['id'])['work']['status'] == 'waiting'
    answered = genesis.answer_question(q['id'], {})
    assert answered['answer'] == 'tier-medium' and answered['stage'] == 'complete'
    resumed = genesis.read('cards', blocked['id'])
    assert resumed['work']['status'] == 'queued' and 'Answer from the lab: tier-medium' in resumed['body'] and resumed['auto'] is True
    with pytest.raises(ValueError):
        genesis.answer_question(blocked['id'], {'answer': 'x'})
    assert [e['kind'] for e in genesis.autonomy.tail(2)] == ['answer', 'question']


def test_paused_switch_stops_the_watcher(genesis, monkeypatch):
    genesis.drop({'text': 'A hypothesis to work.'})
    genesis.autonomy.set({'paused': True})
    assert genesis.watcher.wake() is None and 'Paused by a person' in genesis.watcher.status()['reason'] and genesis.watcher.status()['paused'] is True
    with pytest.raises(ValueError):
        genesis.tool('ask_question', {'question': ''})


def test_autonomy_routes(tmp_path, monkeypatch):
    from wb_studio.app import ROOT, Studio
    from wb_world.episode import load_suite
    from tests.test_studio_app import request, server_for
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    studio = Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=lambda *a, **k: pytest.fail('paid dispatch'))
    with server_for(studio) as port:
        headers = {'X-Studio-Token': studio.token, 'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        status, _, body = request(port, 'GET', '/api/genesis/autonomy')
        assert status == 200 and json.loads(body)['runs'] == 'smoke'
        status, _, body = request(port, 'POST', '/api/genesis/autonomy', json.dumps({'runs': 'propose'}), headers)
        assert status == 200 and json.loads(body)['runs'] == 'propose'
        q = studio.genesis.ask_question({'question': 'Keep going?', 'default': 'yes'})
        status, _, body = request(port, 'POST', f"/api/genesis/cards/{q['card']}/answer", json.dumps({}), headers)
        assert status == 200 and json.loads(body)['answer'] == 'yes'
        status, _, body = request(port, 'GET', '/api/genesis/activity?limit=5')
        kinds = [e['kind'] for e in json.loads(body)['entries']]
        assert status == 200 and 'answer' in kinds and 'autonomy' in kinds
        status, _, body = request(port, 'GET', '/api/genesis')
        assert json.loads(body)['autonomy']['runs'] == 'propose'
