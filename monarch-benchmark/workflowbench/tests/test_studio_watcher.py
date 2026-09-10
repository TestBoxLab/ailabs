"""Offline contracts for Genesis intake and the watcher: dropped cards are classified, worked one
at a time behind the model, daily and weekly gates, and nothing is ever launched."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio.genesis import Genesis, QUESTIONS

ROUTE = [{'id': 'gemini-3.7-flash', 'available': True}]
JOBS = [{'id': 'run-7', 'title': 'Opus against Monarch', 'status': 'completed', 'created_at': '2026-09-08T10:00:00+00:00',
         'settings': {'models': ['gpt-5.6'], 'arms': [{'id': 'gpt-5.6', 'kind': 'runner'}]}},
        {'id': 'run-scripted', 'title': 'Answer key against sloppy', 'status': 'completed', 'created_at': '2026-09-08T11:00:00+00:00',
         'settings': {'models': ['oracle', 'sloppy'], 'arms': [{'id': 'oracle', 'kind': 'scripted'}, {'id': 'sloppy', 'kind': 'scripted'}]}},
        {'id': 'run-live', 'title': 'Still running', 'status': 'running', 'created_at': '2026-09-08T12:00:00+00:00',
         'settings': {'models': ['gpt-5.6'], 'arms': [{'id': 'gpt-5.6', 'kind': 'runner'}]}}]


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDIO_GENESIS_DAILY_USD', '2.00')
    monkeypatch.setenv('STUDIO_GENESIS_CARD_USD', '0.50')
    # the watcher works only what arrives after it first ran; these tests use old fixtures, so it "first ran" long ago
    (tmp_path / 'genesis').mkdir(exist_ok=True)
    (tmp_path / 'genesis' / 'watcher.json').write_text(json.dumps({'since': '2000-01-01T00:00:00+00:00'}), encoding='utf8')
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: ROUTE)
    studio = SimpleNamespace(directory=tmp_path, create=Mock(side_effect=AssertionError('The watcher must never launch')),
                             jobs=Mock(return_value=[]), events=Mock(return_value=[]),
                             ledger=BudgetLedger(tmp_path / 'budget.sqlite3'))
    studio.job = Mock(side_effect=lambda identity: next((dict(j) for j in studio.jobs() if j['id'] == identity), None) or (_ for _ in ()).throw(FileNotFoundError(identity)))
    return Genesis(studio)


class SyncThread:
    """Runs the turn inline so a wake returns after the fake turn finished."""
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def fake_turn(genesis, turn):
    card = genesis.read('cards', turn['card'])
    genesis.tool('save_research', {'id': card['id'], 'revision': card['revision'], 'title': card['title'], 'stage': 'review',
                                   'body': card['body'] + '\n\n## Genesis analysis\n\nThe failure is in run-7 event 12.'})
    genesis.event(turn['id'], 'completed', message='Genesis finished this turn.')


def test_drop_classifies_link_run_id_and_free_text(genesis, monkeypatch):
    genesis.studio.jobs.return_value = JOBS
    monkeypatch.setattr('wb_studio.genesis_ingest.fetch_source', lambda url, timeout=20: {'title': 'Attention is all you need', 'text': 'Full text', 'kind': 'paper', 'note': 'Abstract text'} if 'arxiv' in url else {'title': None, 'text': '', 'kind': 'other', 'note': ''})  # feature 022: a drop fetches the whole source, never the network in tests
    source = genesis.drop({'text': 'https://arxiv.org/abs/1706.03762'})
    record = genesis.library.read(source['evidence'][0]['id'])
    assert source['kind'] == 'source' and source['title'] == 'Attention is all you need'
    assert source['evidence'] == [{'kind': 'library', 'id': record['id']}]
    assert record['source_type'] == 'paper' and record['abstract'] == 'Abstract text' and record['url'] == 'https://arxiv.org/abs/1706.03762'
    assert genesis.drop({'text': 'https://example.com/post'})['title'] == 'https://example.com/post'
    assert genesis.library.read(genesis.drop({'text': 'https://github.com/x/y'})['evidence'][0]['id'])['source_type'] == 'repo'
    run = genesis.drop({'text': 'run-7', 'question': 'Why did task 3 fail?'})
    assert run['kind'] == 'run' and run['title'] == 'Opus against Monarch' and run['question'] == 'Why did task 3 fail?'
    assert run['evidence'] == [{'kind': 'run', 'id': 'run-7'}]
    text = genesis.drop({'text': 'Monarch fails on pagination\nbecause the graph lacks cursors', 'auto': False})
    assert text['kind'] == 'hypothesis' and text['title'] == 'Monarch fails on pagination' and text['body'].endswith('cursors')
    assert text['auto'] is False and text['evidence'] == [] and text['work'] is None  # not for Genesis: filed, never queued
    for card, kind in ((source, 'source'), (run, 'run')):
        assert card['stage'] == 'research' and card['work']['status'] == 'queued' and card['work']['queued_at']
        assert card['question'] == (QUESTIONS[kind] if card is not run else 'Why did task 3 fail?')
    assert source['auto'] is True and run['auto'] is True
    assert genesis.drop({'text': 'unknown-run'})['kind'] == 'hypothesis'
    with pytest.raises(ValueError, match='Drop a link'):
        genesis.drop({'text': '  '})
    genesis.studio.create.assert_not_called()


def test_watcher_refuses_without_a_model_route(genesis, monkeypatch):
    card = genesis.drop({'text': 'Hypothesis one'})
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'x', 'available': False}])
    assert genesis.watcher.wake() is None
    assert genesis.read('cards', card['id'])['work'] == {**card['work'], 'reason': 'Waiting: no model route is available'}
    status = genesis.watcher.status()
    assert status['queue'] == [card['id']] and status['working'] is None and status['reason'] == 'Waiting: no model route is available'
    assert genesis.listing('turns') == []


def write_turn(genesis, identity, created_at, card='card-x', maximum='0.50'):
    genesis.path('turns', identity).write_text(json.dumps({'id': identity, 'status': 'completed', 'card': card, 'maximum_usd': maximum,
                                                            'created_at': created_at.isoformat(), 'events': [{'type': 'usage', 'cost_usd': maximum}], 'answer': '', 'message': ''}), encoding='utf8')


def test_daily_tally_counts_only_today_and_gates_the_cap(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', Mock(side_effect=AssertionError('capped')))
    now = datetime.now(timezone.utc)
    write_turn(genesis, 'today-a', now)
    write_turn(genesis, 'yesterday', now - timedelta(days=1), maximum='1.00')
    write_turn(genesis, 'today-chat', now, card=None, maximum='0.10')  # a turn without a card counts too (R5)
    assert str(genesis.watcher.today_usd()) == '0.60'
    assert genesis.watcher.refusal() is None  # 0.60 + 0.50 fits under 2.00
    write_turn(genesis, 'today-b', now, maximum='1.50')
    card = genesis.drop({'text': 'Hypothesis three'})
    assert genesis.watcher.wake() is None
    assert genesis.watcher.status()['reason'] == "Waiting: today's cap of $2.00 is reached"
    assert genesis.read('cards', card['id'])['work']['status'] == 'queued'
    assert genesis.watcher.status()['today_usd'] == '2.10'
    assert any(e['kind'] == 'refused' for e in genesis.autonomy.tail(5))  # the refusal is in the record, once


def test_watcher_refuses_when_the_weekly_ledger_cannot_cover(genesis):
    genesis.studio.ledger = BudgetLedger(genesis.studio.directory / 'small.sqlite3', weekly_limit_usd='0.10')
    card = genesis.drop({'text': 'Hypothesis'})
    assert genesis.watcher.wake() is None
    assert genesis.read('cards', card['id'])['work']['reason'] == 'Waiting: the weekly ledger cannot cover $0.50'
    assert genesis.listing('turns') == []


def test_one_wake_works_one_card_and_the_next_wake_takes_the_next(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', SyncThread)
    monkeypatch.setattr('wb_studio.genesis_harness.start_turn', fake_turn)
    first = genesis.drop({'text': 'First hypothesis'})
    second = genesis.drop({'text': 'Second hypothesis'})
    turn = genesis.watcher.wake()
    assert turn['card'] == first['id'] and turn['maximum_usd'] == '0.50' and turn['model'] == 'gemini-3.7-flash'
    assert 'First hypothesis' in turn['message'] and QUESTIONS['hypothesis'] in turn['message'] and 'propose_experiment' in turn['message'] and 'Smoke scale is at most 20' in turn['message']
    reservation = genesis.studio.ledger.run_reservation('genesis-' + turn['id'])
    assert reservation.metadata['purpose'] == 'Genesis watcher' and reservation.maximum_usd == Decimal('0.50')
    done = genesis.read('cards', first['id'])
    assert done['work']['status'] == 'done' and done['work']['turn'] == turn['id'] and done['work']['finished_at'] and 'reason' not in done['work']
    assert done['stage'] == 'review' and done['analysis'] == 'The failure is in run-7 event 12.' and done['revision'] == 2
    assert done['question'] == QUESTIONS['hypothesis'] and done['auto'] is True
    assert genesis.read('cards', second['id'])['work']['status'] == 'queued'
    assert genesis.watcher.wake()['card'] == second['id']
    assert genesis.read('cards', second['id'])['work']['status'] == 'done'
    assert genesis.watcher.wake() is None and genesis.watcher.status()['queue'] == []
    genesis.studio.create.assert_not_called()


def test_turn_without_an_analysis_or_with_a_failure_is_recorded(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', SyncThread)
    monkeypatch.setattr('wb_studio.genesis_harness.start_turn', lambda g, t: g.event(t['id'], 'completed', message='Genesis finished this turn.'))
    silent = genesis.drop({'text': 'Silent'})
    genesis.watcher.wake()
    assert genesis.read('cards', silent['id'])['work']['reason'] == 'Genesis finished without writing an analysis'
    monkeypatch.setattr('wb_studio.genesis_harness.start_turn', lambda g, t: g.event(t['id'], 'failed', message='Genesis could not complete this turn. No experiment was launched.'))
    broken = genesis.drop({'text': 'Broken'})
    genesis.watcher.wake()
    work = genesis.read('cards', broken['id'])['work']
    assert work['status'] == 'failed' and work['reason'].startswith('Genesis could not complete this turn')


def test_stop_kills_the_active_process_and_marks_the_card_stopped(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', Mock())
    card = genesis.drop({'text': 'Long one'})
    turn = genesis.watcher.wake()
    process = Mock(poll=Mock(return_value=None))
    genesis.active[turn['id']] = process
    assert genesis.watcher.status()['working'] == card['id']
    stopped = genesis.stop_work(card['id'])
    process.kill.assert_called_once()
    assert stopped['work']['status'] == 'stopped' and stopped['work']['finished_at']
    genesis.event(turn['id'], 'failed', message='Codex stopped')
    assert genesis.read('cards', card['id'])['work']['status'] == 'stopped'
    assert genesis.watcher.wake() is None


def test_paused_watcher_leaves_the_queue_alone(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', Mock(side_effect=AssertionError('paused')))
    card = genesis.drop({'text': 'Wait'})
    genesis.watcher.pause(True)
    assert genesis.watcher.wake() is None and genesis.watcher.status()['paused'] is True
    assert genesis.read('cards', card['id'])['work']['status'] == 'queued'
    assert json.loads(genesis.watcher.path.read_text(encoding='utf8'))['paused'] is True


def test_triggers_create_run_and_source_cards_once_and_skip_scripted_runs(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    genesis.studio.jobs.return_value = JOBS
    full = genesis.library.add({'title': 'Read paper', 'url': 'https://arxiv.org/abs/1', 'source_type': 'paper', 'original': 'full text'})
    genesis.library.add({'title': 'Unread', 'url': 'https://example.com/b', 'source_type': 'blog'})
    genesis.watcher.wake()
    genesis.watcher.wake()
    cards = genesis.listing('cards')
    assert [(c['kind'], c['evidence']) for c in cards] == [('run', [{'kind': 'run', 'id': 'run-7'}]), ('source', [{'kind': 'library', 'id': full['id']}])]
    assert cards[0]['title'] == 'Opus against Monarch' and cards[0]['question'] == QUESTIONS['run'] and cards[0]['work']['status'] == 'queued'
    assert cards[1]['title'] == 'Read paper' and cards[1]['question'] == QUESTIONS['source']
    monkeypatch.setenv('STUDIO_GENESIS_AUTO_RUNS', '0')
    monkeypatch.setenv('STUDIO_GENESIS_AUTO_SOURCES', 'off')
    (genesis.studio.directory / 'fresh').mkdir()
    fresh = Genesis(SimpleNamespace(**{**vars(genesis.studio), 'directory': genesis.studio.directory / 'fresh'}))
    fresh.watcher.wake()
    assert fresh.listing('cards') == []


def test_watcher_thread_never_raises_and_records_its_error(genesis, monkeypatch):
    monkeypatch.setattr(genesis.watcher, 'triggers', Mock(side_effect=RuntimeError('disk gone')))
    genesis.watcher.start(interval_s=60)
    genesis.watcher.notify()
    for _ in range(50):
        if genesis.watcher._read().get('last_error'):
            break
        genesis.watcher._wake.wait(0.05)
    genesis.watcher.stop()
    assert genesis.watcher.status()['last_error'] == 'RuntimeError: disk gone'


def test_routes_drop_status_pause_and_stop(tmp_path, monkeypatch):
    from tests.test_studio_app import request, server_for
    from wb_studio.app import ROOT, Studio
    from wb_world.episode import load_suite
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    studio = Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=lambda *a, **k: pytest.fail('paid dispatch'))
    headers = {'X-Studio-Token': studio.token, 'Content-Type': 'application/json'}
    with server_for(studio) as port:
        status, _, body = request(port, 'POST', '/api/genesis/drop', json.dumps({'text': 'Dropped through the interface'}), headers)
        assert status == 201
        card = json.loads(body)
        assert card['kind'] == 'hypothesis' and card['work']['status'] == 'queued'
        status, _, body = request(port, 'GET', '/api/genesis/watcher')
        assert status == 200
        assert json.loads(body) == {'paused': False, 'queue': [card['id']], 'working': None, 'today_usd': '0', 'cap_usd': '6.00', 'last_wake': None, 'reason': None, 'last_error': None, 'interval_s': 30}
        assert json.loads(request(port, 'GET', '/api/genesis')[2])['watcher']['queue'] == [card['id']]
        status, _, body = request(port, 'POST', '/api/genesis/watcher', json.dumps({'paused': True}), headers)
        assert status == 200 and json.loads(body)['paused'] is True
        status, _, body = request(port, 'POST', f"/api/genesis/cards/{card['id']}/stop", '{}', headers)
        assert status == 200 and json.loads(body)['work']['status'] == 'stopped'
        assert json.loads(request(port, 'GET', '/api/genesis/watcher')[2])['queue'] == []
        assert request(port, 'POST', '/api/genesis/drop', json.dumps({'text': 'x'}))[0] == 403


def test_history_is_not_reworked_at_the_first_start(genesis):
    """A watcher that has never run stamps now and leaves earlier runs and sources alone."""
    (genesis.studio.directory / 'genesis' / 'watcher.json').unlink()
    old = {'id': 'run-old', 'title': 'Finished last week', 'status': 'completed', 'created_at': '2026-09-01T12:00:00+00:00',
           'finished_at': '2026-09-01T12:30:00+00:00', 'settings': {'arms': [{'id': 'gemini', 'kind': 'runner'}], 'models': ['gemini']}, 'results': []}
    genesis.studio.jobs = Mock(return_value=[old])
    genesis.watcher.triggers()
    assert [c for c in genesis.listing('cards') if c.get('kind') == 'run'] == []
    since = json.loads((genesis.studio.directory / 'genesis' / 'watcher.json').read_text(encoding='utf8'))['since']
    new = {**old, 'id': 'run-new', 'title': 'Finished just now', 'created_at': '2099-01-01T00:00:00+00:00', 'finished_at': '2099-01-01T00:10:00+00:00'}
    genesis.studio.jobs = Mock(return_value=[old, new])
    genesis.watcher.triggers()
    assert [c['evidence'][0]['id'] for c in genesis.listing('cards') if c.get('kind') == 'run'] == ['run-new'] and since

