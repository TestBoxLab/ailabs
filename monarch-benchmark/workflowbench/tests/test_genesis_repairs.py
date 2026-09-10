"""The repairs of 10 Sep 2026 (deep dive, tier 0): the debrief is the watcher's, an accepted plan launches,
the envelope is a gate, the daily cap counts every turn, one run is one card, a memory tag is not doubled,
the brief hour has an effect, extraction reads the whole source."""
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio.genesis import Genesis, stamp

ROUTE = [{'id': 'glm-5.3', 'available': True}]
JOB = {'id': 'run-9', 'title': 'A run', 'status': 'completed', 'finished_at': '2030-01-01T00:00:00+00:00',
       'settings': {'models': ['gpt-5.6-sol']}, 'results': []}


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    (tmp_path / 'genesis').mkdir(exist_ok=True)
    (tmp_path / 'genesis' / 'watcher.json').write_text(json.dumps({'since': '2000-01-01T00:00:00+00:00'}), encoding='utf8')
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: ROUTE)
    studio = SimpleNamespace(directory=tmp_path, create=Mock(return_value={'id': 'run-new'}), jobs=Mock(return_value=[JOB]),
                             events=Mock(return_value=[]), ledger=BudgetLedger(tmp_path / 'budget.sqlite3'), budget=Mock(return_value={}))
    studio.job = Mock(side_effect=lambda identity: next((dict(j) for j in studio.jobs() if j['id'] == identity), None) or (_ for _ in ()).throw(FileNotFoundError(identity)))
    return Genesis(studio)


def planned_card(genesis, job='run-9', stage='running'):
    card = genesis.card({'title': 'Planned', 'body': 'x', 'stage': 'approval', 'proposal': {'tasks': ['t1'], 'maximum_usd': '1.00', 'operation': 'run'},
                         'plan': {'lines': [], 'attempts_per_competitor': 1, 'attempts': 1, 'maximum_usd': '1.00'}})
    card.update(stage=stage, job=job)
    from wb_results.evidence import write_json
    write_json(genesis.path('cards', card['id']), card)
    return card


def test_the_debrief_runs_on_the_watcher_wake_not_on_a_page_load(genesis):
    card = planned_card(genesis)
    assert genesis.state()['cards'][0]['stage'] == 'running'          # a read changes nothing
    assert genesis.read('cards', card['id'])['stage'] == 'running'
    assert genesis.debrief() == [card['id']]
    saved = genesis.read('cards', card['id'])
    assert saved['stage'] == 'review' and saved['work']['status'] == 'queued' and 'verdict' in saved['question']
    assert genesis.debrief() == []                                     # once
    assert any(e['kind'] == 'debrief' for e in genesis.autonomy.tail())


def test_a_run_genesis_launched_is_not_filed_a_second_time(genesis):
    planned_card(genesis)
    genesis.watcher.triggers()
    assert [c['kind'] for c in genesis.listing('cards')] == ['hypothesis']   # no extra run card for run-9


def test_the_daily_cap_counts_every_turn_of_today(genesis):
    from wb_results.evidence import write_json
    turn = {'id': 'n1', 'status': 'completed', 'model': 'glm-5.3', 'message': 'night', 'answer': '', 'created_at': stamp(), 'maximum_usd': '0.50',
            'card': None, 'purpose': 'Genesis nightly', 'events': [{'id': 1, 'type': 'usage', 'at': stamp(), 'cost_usd': '0.25'}]}
    write_json(genesis.path('turns', 'n1'), turn)
    assert str(genesis.watcher.today_usd()) == '0.25'


def test_the_envelope_refuses_a_turn_and_a_plan_it_cannot_cover(genesis, monkeypatch):
    genesis.access.set_settings({'envelope_usd': '1.00'})
    monkeypatch.setattr('wb_studio.usage.ledger_lines', lambda studio, now=None: {'lines': [{'who': 'Genesis', 'state': 'open', 'maximum_usd': '0.80', 'actual_usd': None}]})
    ok, reason = genesis.envelope_allows('0.50')
    assert ok is False and reason.startswith("Genesis's weekly envelope cannot cover $0.50: $0.20 left of $1.00")
    assert genesis.envelope_allows('0.10') == (True, None)
    with pytest.raises(ValueError, match='weekly envelope'):
        genesis.chat({'model': 'glm-5.3', 'message': 'hello', 'maximum_usd': '0.50'})
    assert genesis.listing('turns') == []
    genesis.autonomy.set({'runs': 'smoke'})
    card = genesis.card({'title': 'Plan', 'body': 'x', 'stage': 'approval', 'proposal': {'tasks': ['t1'], 'maximum_usd': '0.50', 'operation': 'run'},
                         'plan': {'lines': [], 'attempts_per_competitor': 1, 'attempts': 1, 'maximum_usd': '0.50'}})
    out = genesis.launch_if_allowed(card['id'])
    assert out['launched'] is False and 'envelope' in out['reason'] and genesis.studio.create.call_count == 0


def test_the_reviewer_accepting_a_plan_launches_it(genesis, monkeypatch):
    from wb_studio import genesis_reviewer
    monkeypatch.setattr('wb_studio.genesis_plugins.MODULES', ('wb_studio.genesis_reviewer',))
    genesis.autonomy.set({'runs': 'smoke'})
    card = genesis.card({'title': 'Plan', 'body': 'x', 'stage': 'approval', 'proposal': {'tasks': ['t1'], 'maximum_usd': '0.50', 'operation': 'run'},
                         'plan': {'lines': [], 'attempts_per_competitor': 1, 'attempts': 1, 'maximum_usd': '0.50'}})
    genesis.card({**genesis.read('cards', card['id']), 'review': {'status': 'pending', 'turn': 'r1', 'subject': 'plan', 'round': 1, 'digest': card['proposal_digest']}})
    turn = {'id': 'r1', 'status': 'completed', 'purpose': genesis_reviewer.PURPOSE, 'card': card['id'], 'events': [],
            'answer': '{"verdict": "accept", "issues": [], "reason": "One factor, a control, frozen tasks."}'}
    genesis_reviewer.ON_TURN(genesis, turn)
    saved = genesis.read('cards', card['id'])
    assert saved['review']['verdict'] == 'accept' and saved['stage'] == 'running' and saved['job'] == 'run-new'
    assert genesis.studio.create.call_count == 1


def test_genesis_turns_are_attributed_to_genesis(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', Mock())
    turn = genesis.chat({'model': 'glm-5.3', 'message': 'work', 'purpose': 'Genesis watcher'})
    assert turn['by'] == 'genesis'
    turn = genesis.chat({'model': 'glm-5.3', 'message': 'hello'})
    assert turn['by'] == 'human:studio'


def test_a_memory_entry_names_its_record_once(genesis):
    out = genesis.memory.add('Monarch moved to commit 26558c83 [rec:library:e017]', 'library:e017')
    assert out['entry'].count('[rec:library:e017]') == 1 and out['entry'].startswith('Monarch moved to commit 26558c83 [rec:library:e017] ')


def test_the_brief_hour_and_several_jobs_per_module(tmp_path):
    from wb_studio.scheduler import Scheduler
    studio = SimpleNamespace(genesis=SimpleNamespace(access=SimpleNamespace(settings=lambda: {'brief_hour': 9})))
    s = Scheduler(studio, tmp_path / 'stamps.json')
    s.daily('fixed', 3, lambda studio: {'ran': True})
    s.daily('brief', lambda studio: studio.genesis.access.settings()['brief_hour'], lambda studio: {'ran': True})
    at = lambda hour: datetime(2026, 9, 10, hour, 30)
    assert [j['name'] for j in s.due(at(4))] == ['fixed']
    assert [j['name'] for j in s.due(at(9))] == ['fixed', 'brief']
    assert next(j for j in s.status() if j['name'] == 'brief')['hour'] == 9
    from wb_studio import genesis_channels
    assert [j[0] for j in genesis_channels.DAILY] == ['genesis-sweep', 'genesis-brief']


def test_extraction_reads_the_whole_source():
    from wb_studio.genesis_ingest import _message
    text = _message({'id': 'lib1', 'title': 'T', 'url': 'https://x'}, 'x' * 50_000)
    assert text.count('x' * 50_000) == 1 and 'Cut:' not in text


def test_the_state_says_who_is_asking(genesis):
    assert 'me' not in genesis.state()  # the route adds it from the person's key; the state itself does not know


def test_the_turn_route_answers_incrementally(tmp_path, monkeypatch):
    from tests.test_studio_app import request, server_for
    from wb_results.evidence import write_json
    from wb_studio.app import ROOT, Studio
    from wb_world.episode import load_suite
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    studio = Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=lambda *a, **k: pytest.fail('paid dispatch'))
    turn = {'id': 'inc1', 'status': 'running', 'model': 'glm-5.3', 'message': 'm', 'answer': 'so far', 'created_at': stamp(), 'maximum_usd': '2',
            'events': [{'id': 1, 'type': 'harness_started', 'at': stamp()}, {'id': 2, 'type': 'model_started', 'at': stamp()}, {'id': 3, 'type': 'text_delta', 'at': stamp(), 'text': 'so far'}]}
    write_json(studio.genesis.path('turns', 'inc1'), turn)
    with server_for(studio) as port:
        whole = json.loads(request(port, 'GET', '/api/genesis/turns/inc1')[2])
        assert [e['id'] for e in whole['events']] == [1, 2, 3] and 'partial' not in whole
        part = json.loads(request(port, 'GET', '/api/genesis/turns/inc1?after=2')[2])
        assert [e['id'] for e in part['events']] == [3] and part['partial'] is True and part['answer'] == 'so far' and part['status'] == 'running'
