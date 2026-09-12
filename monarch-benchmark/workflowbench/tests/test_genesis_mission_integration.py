"""Mission integration uses the real Genesis card and watcher seams, offline."""
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from unittest.mock import Mock

from wb_results.evidence import write_json
from wb_studio import genesis_plugins
from wb_studio.genesis_schemas import tool_defs
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path):
    studio = SimpleNamespace(directory=tmp_path, ledger=Mock(), jobs=Mock(return_value=[]),
                             events=Mock(return_value=[]), job=Mock(side_effect=FileNotFoundError),
                             runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext()))
    return Genesis(studio)


def mission_card(genesis):
    card = genesis.card({'title': 'Improve Monarch', 'body': 'Original request', 'stage': 'research'})
    card['mission'] = {'owner': 'human:lucas', 'status': 'queued', 'model': 'claude-opus-4-8',
                       'objective': 'Improve reliability', 'turn_count': 0, 'max_turns': 8}
    card['kind'] = 'mission'
    write_json(genesis.path('cards', card['id']), card)
    return card


def test_ordinary_card_save_cannot_replace_mission_lifecycle(genesis):
    card = mission_card(genesis)
    saved = genesis.card({**card, 'mission': {'owner': 'intruder'}, 'stage': 'complete',
                          'work': {'status': 'queued'}, 'body': 'A useful note'})
    assert saved['mission'] == card['mission']
    assert saved['stage'] == 'research'
    assert saved['work'] == card['work']
    assert saved['body'] == 'A useful note'


def test_mission_tools_have_typed_schemas():
    tools = {row['name']: row for row in tool_defs()}
    assert tools['start_mission']['parameters']['required'] == ['objective', 'acceptance', 'next_action']
    assert tools['checkpoint_mission']['parameters']['properties']['status']['enum'] == ['continue', 'waiting', 'complete', 'blocked']
    assert tools['control_mission']['parameters']['properties']['action']['enum'] == ['steer', 'resume', 'stop']
    assert 'mission_status' in genesis_plugins.actions()


def test_watcher_reconciles_missions_even_when_paused(genesis, monkeypatch):
    from wb_studio import genesis_missions
    reconcile = Mock()
    monkeypatch.setattr(genesis_missions, 'reconcile', reconcile)
    monkeypatch.setattr(genesis, 'debrief', Mock())
    monkeypatch.setattr(genesis.watcher, 'triggers', Mock())
    monkeypatch.setattr(genesis.autonomy, 'read', lambda: {'paused': True, 'cards': 'act'})
    assert genesis.watcher.wake() is None
    reconcile.assert_called_once_with(genesis)


def test_mission_work_uses_durable_payload_and_preserves_owner(genesis, monkeypatch):
    from wb_studio import genesis_missions
    card = mission_card(genesis)
    monkeypatch.setattr(genesis.autonomy, 'read', lambda: {'paused': False, 'cards': 'act'})
    monkeypatch.setattr(genesis_missions, 'worker_payload', lambda g, c: {
        'message': 'Continue saved objective', 'model': 'claude-opus-4-8',
        'by': 'human:lucas', 'thread': 'conversation', 'workspace': {'route': '#genesis'},
        'purpose': 'Genesis mission', 'mission_generation': 3,
    })
    launch = Mock(side_effect=lambda payload: payload)
    monkeypatch.setattr(genesis, 'chat', launch)
    result = genesis.work(card)
    assert result['message'] == 'Continue saved objective'
    assert result['by'] == 'human:lucas'
    assert result['thread'] == 'conversation'
    assert result['mission_generation'] == 3
    assert genesis.read('cards', card['id'])['work']['turn'] == result['id']


def test_stop_card_routes_through_mission_cancellation(genesis, monkeypatch):
    from wb_studio import genesis_missions
    card = mission_card(genesis)
    stop = Mock(return_value={'stopped': True})
    monkeypatch.setattr(genesis_missions, 'trusted_control', stop)
    assert genesis.stop_work(card['id']) == {'stopped': True}
    stop.assert_called_once_with(genesis, card, 'stop')



def test_large_tool_success_keeps_a_compact_mission_receipt():
    from wb_studio.genesis_harness import mission_receipt
    assert mission_receipt('read_run', {'job': {'id': 'run1'}, 'events': ['x'*7000]}) == {'ok': True, 'run': 'run1'}
    assert mission_receipt('save_architecture', {'id': 'arch1', 'revision': 4, 'graph': {'prompt': 'x'*7000}}) == {'ok': True, 'architecture': 'arch1', 'revision': 4}
    assert mission_receipt('edit_architecture', {'saved': False, 'steps': 2, 'operation': {'type': 'add_node'}}) == {'ok': True, 'provisional': True}
    assert mission_receipt('read_run', {'error': 'missing', 'job': {'id': 'run1'}}) is None
    assert mission_receipt('save_architecture', {'error': 'conflict', 'id': 'arch1', 'revision': 4}) is None


def test_worker_payload_refusal_persists_visible_blocker(genesis, monkeypatch):
    from wb_studio import genesis_missions
    card=mission_card(genesis)
    monkeypatch.setattr(genesis_missions, 'worker_payload', Mock(side_effect=ValueError('The mission model is unavailable')))
    with pytest.raises(ValueError, match='model is unavailable'):
        genesis.work(card)
    saved=genesis.read('cards',card['id'])
    assert saved['mission']['status']=='blocked'
    assert saved['work']['status']=='failed'
    assert 'model is unavailable' in saved['work']['reason']


def test_mission_owns_analysis_without_duplicate_child_debrief(genesis, monkeypatch):
    parent=mission_card(genesis)
    child=genesis.card({'title':'Candidate comparison','body':'Frozen proposal','stage':'approval','parent':parent['id']})
    child.update(stage='running',job='job1',plan={'attempts':2},auto=False)
    write_json(genesis.path('cards',child['id']),child)
    monkeypatch.setattr(genesis.studio,'job',lambda identity: {'id':identity,'status':'completed'})
    monkeypatch.setattr(genesis.autonomy,'read',lambda:{'cards':'act'})
    assert genesis.debrief()==[child['id']]
    saved=genesis.read('cards',child['id'])
    assert saved['stage']=='review'
    assert (saved.get('work') or {}).get('status')!='queued'
    assert saved['auto'] is False
