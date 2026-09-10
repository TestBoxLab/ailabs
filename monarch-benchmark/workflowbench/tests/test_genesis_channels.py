"""Slack, the digest data and the Monday sweep, offline. Nothing is sent and no model is
called: `urlopen` is a stub, `genesis.chat` is a fake and the ledger is a mock."""
import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_channels as channels
from wb_studio import genesis_harness as harness
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.delenv(channels.WEBHOOK, raising=False)
    monkeypatch.delenv('STUDIO_PUBLIC_URL', raising=False)
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    return studio.genesis


@pytest.fixture
def sent(monkeypatch):
    posted = []

    class Response:
        status = 200

        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(request, timeout=None):
        posted.append({'url': request.full_url, 'body': request.data.decode()})
        return Response()
    monkeypatch.setattr(channels, 'urlopen', urlopen)
    return posted


def test_a_post_is_recorded_and_skipped_without_a_webhook(genesis, sent, monkeypatch):
    result = channels.announce(genesis, 'Nothing goes out')
    assert result == {'posted': False, 'reason': channels.NO_WEBHOOK} and sent == []
    logged = genesis.autonomy.tail(1)[0]
    assert logged['kind'] == 'slack' and logged['posted'] is False and logged['reason'] == channels.NO_WEBHOOK

    monkeypatch.setenv(channels.WEBHOOK, 'https://hooks.example/T/B/X')
    monkeypatch.setenv('STUDIO_PUBLIC_URL', 'https://studio.example/')
    assert channels.link('genesis?card=c1') == 'https://studio.example/genesis?card=c1'
    assert channels.announce(genesis, 'The brief', card='brief-1', about='brief') == {'posted': True, 'status': 200}
    assert sent[0]['url'] == 'https://hooks.example/T/B/X' and 'The brief' in sent[0]['body']
    assert genesis.autonomy.tail(1)[0]['posted'] is True


def test_questions_and_waiting_plans_are_posted_once_each_from_a_finished_turn(genesis, sent, monkeypatch):
    monkeypatch.setenv(channels.WEBHOOK, 'https://hooks.example/T/B/X')
    genesis.card({'id': 'q1', 'kind': 'question', 'title': 'Which task set?', 'stage': 'research', 'default': 'the frozen one'})
    genesis.card({'id': 'p1', 'title': 'Retry caps at smoke scale', 'stage': 'approval',
                  'plan': {'lines': ['3 attempts'], 'maximum_usd': '1.00'}, 'waiting': 'Above the daily allowance.'})
    genesis.card({'id': 'a1', 'kind': 'question', 'title': 'Already answered', 'stage': 'research', 'answer': 'yes'})
    channels.ON_TURN(genesis, {'id': 't1', 'status': 'completed'})
    assert [p['body'].count('Genesis is asking') for p in sent].count(1) == 1
    assert len(sent) == 2 and 'A plan is waiting for a person' in sent[1]['body']
    assert 'the frozen one' in sent[0]['body'] and 'Already answered' not in sent[0]['body'] + sent[1]['body']
    channels.ON_TURN(genesis, {'id': 't2', 'status': 'completed'})
    assert len(sent) == 2   # each card is posted once
    assert [e['about'] for e in genesis.autonomy.tail(5) if e['kind'] == 'slack'] == ['waiting', 'question']


def test_the_nightly_brief_posts_after_it_is_written(genesis, sent, monkeypatch):
    monkeypatch.setenv(channels.WEBHOOK, 'https://hooks.example/T/B/X')
    monkeypatch.setenv('STUDIO_PUBLIC_URL', 'https://studio.example')
    card = genesis.card({'id': 'brief-2026-09-10', 'kind': 'brief', 'title': 'Daily brief 2026-09-10', 'stage': 'research',
                         'body': 'Since yesterday: 2 turns.', 'brief': {'allowance': {'week_usd': '12.50'}}})
    assert channels.post_brief(genesis, card)['posted'] is True
    assert 'Since yesterday: 2 turns.' in sent[0]['body'] and 'Weekly allowance left: $12.50' in sent[0]['body']
    assert 'https://studio.example/genesis?card=brief-2026-09-10' in sent[0]['body']


def test_the_digest_reads_from_the_cards(genesis):
    genesis.studio.jobs.return_value = [{'id': 'run-1', 'title': 'Smoke run', 'status': 'completed', 'finished_at': '2026-09-08T10:00:00'},
                                        {'id': 'run-0', 'title': 'Older run', 'status': 'completed', 'finished_at': '2026-08-01T10:00:00'}]
    genesis.card({'id': 'c1', 'title': 'Retry caps help', 'kind': 'hypothesis', 'stage': 'complete',
                  'settlement': {'outcome': 'supported', 'reason': 'The run says so.'}})
    genesis.card({'id': 'c2', 'title': 'Bigger context helps', 'kind': 'hypothesis', 'stage': 'review',
                  'settlement': {'outcome': 'not_supported', 'reason': 'No gain.'}})
    genesis.card({'id': 'c3', 'title': 'Untested', 'kind': 'hypothesis', 'stage': 'hypothesis'})
    (genesis.memory.root / 'TRACK.md').write_text('# Track record\n\nCalibration: Brier score 0.10 on 2.\n', encoding='utf8')
    out = channels.digest(genesis, '2026-W37')
    assert (out['from'], out['to']) == ('2026-09-07', '2026-09-14')
    assert [j['id'] for j in out['ran']] == ['run-1']
    assert [c['tag'] for c in out['done']] == ['[rec:card:c1]']
    assert [h['id'] for h in out['supported']] == ['c1'] and [h['tag'] for h in out['refuted']] == ['[rec:card:c2]']
    assert out['track'].startswith('Calibration: Brier score 0.10')
    assert out['standings'] == '/leaderboard'


def _sources(genesis):
    genesis.library.add({'title': 'Sleep-time compute', 'url': 'https://example.org/sleep', 'source_type': 'paper',
                         'abstract': 'consolidation between sessions', 'topic': 'Agentic memory'})
    genesis.library.add({'title': 'A grader study', 'url': 'https://example.org/grader', 'source_type': 'paper',
                         'abstract': 'benchmark eval grading', 'topic': 'Evaluation and benchmarks'})


def monday(monkeypatch, day=7):
    monkeypatch.setattr(channels, 'now_sao_paulo', lambda: datetime.datetime(2026, 9, day, 6, 0))


def test_the_sweep_spends_one_turn_per_topic_and_none_when_the_ledger_cannot_cover(genesis, monkeypatch):
    monkeypatch.setattr(harness, 'model_routes', lambda: [{'id': 'fake-route', 'available': True}])
    calls = []
    genesis.chat = lambda payload: (calls.append(payload), {'id': 'turn-' + str(len(calls))})[1]
    studio = genesis.studio
    studio.ledger.status.return_value = SimpleNamespace(available_usd='10.00')

    monday(monkeypatch, day=8)   # a Tuesday
    assert 'Mondays' in channels.weekly(studio)['reason'] and calls == []
    monday(monkeypatch)
    assert channels.weekly(studio)['reason'].startswith('No library topic holds a source')
    _sources(genesis)
    assert channels.topics(genesis) == [{'topic': 'Agentic memory', 'count': 1, 'newest': 'Sleep-time compute'},
                                        {'topic': 'Evaluation and benchmarks', 'count': 1, 'newest': 'A grader study'}]
    summary = channels.weekly(studio)
    assert summary['topics'] == ['Agentic memory', 'Evaluation and benchmarks'] and len(summary['turns']) == 2
    assert calls[0]['purpose'] == 'Genesis sweep' and calls[0]['maximum_usd'] == '0.50'
    assert 'Agentic memory' in calls[0]['message'] and 'library_save' in calls[0]['message']

    studio.ledger.status.return_value = SimpleNamespace(available_usd='0.60')
    trimmed = channels.weekly(studio)
    assert trimmed['topics'] == ['Agentic memory'] and 'covered 1 of the 2 topics' in trimmed['reason']
    studio.ledger.status.return_value = SimpleNamespace(available_usd='0.10')
    assert channels.weekly(studio)['reason'] == 'The weekly ledger cannot cover $0.50 for one topic.'
    assert len(calls) == 3
    assert channels.DAILY[0][0] == 'genesis-sweep' and channels.DAILY[0][1] == 6
