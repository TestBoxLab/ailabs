"""Genesis opens one card a day from the lab's open threads (design of record
`docs/superpowers/specs/2026-09-10-genesis-initiative-design.md`)."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio import genesis_initiative as initiative
from wb_studio.genesis import Genesis
from wb_studio.library import now_sao_paulo

ROUTE = [{'id': 'glm-5.3', 'available': True}]
HYPOTHESIS = {'claim': 'The graph arm passes more tasks', 'measure': 'pass_rate'}


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    (tmp_path / 'genesis').mkdir(exist_ok=True)
    (tmp_path / 'genesis' / 'watcher.json').write_text(json.dumps({'since': '2000-01-01T00:00:00+00:00'}), encoding='utf8')
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: ROUTE)
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', Mock())
    studio = SimpleNamespace(directory=tmp_path, create=Mock(return_value={'id': 'run-new'}), jobs=Mock(return_value=[]),
                             events=Mock(return_value=[]), ledger=BudgetLedger(tmp_path / 'budget.sqlite3'), budget=Mock(return_value={}))
    studio.job = Mock(side_effect=FileNotFoundError)
    g = Genesis(studio)
    g.autonomy.set({'initiative': 'open'})
    return SimpleNamespace(genesis=g, directory=tmp_path)


def source(genesis, identity, **fields):
    """A library record straight on disk, so a test names exactly the fields a rule reads."""
    record = {'id': identity, 'title': 'Source ' + identity, 'url': 'https://example.test/' + identity,
              'source_type': 'paper', 'topic': 'Memory', 'status': 'analyzed', 'used_in': [],
              'discovered_at': '2020-01-01', 'published_at': '2020-01-01', 'contradicts': [], **fields}
    genesis.library.root.mkdir(parents=True, exist_ok=True)
    (genesis.library.root / (identity + '.json')).write_text(json.dumps(record), encoding='utf8')
    return record


# ---- the rules ---------------------------------------------------------------------------------
def test_an_unsettled_hypothesis_is_an_open_thread(genesis):
    g = genesis.genesis
    card = g.card({'title': 'Graph beats bare', 'body': 'x', 'hypothesis': HYPOTHESIS})
    thread = initiative.open_threads(g)[0]
    assert thread['rule'] == 'unsettled-hypothesis' and thread['kind'] == 'hypothesis'
    assert thread['evidence'] == [{'kind': 'card', 'id': card['id']}]
    assert 'hypothesis_settle' in thread['question'] and card['id'] in thread['question']
    # settled: no longer open
    g.card({**card, 'revision': card['revision'], 'settlement': {'outcome': 'supported'}})
    assert initiative.open_threads(g) == []


def test_an_inconclusive_settlement_with_nothing_after_it_is_an_open_thread(genesis):
    g = genesis.genesis
    card = g.card({'title': 'Graph beats bare', 'body': 'x', 'hypothesis': HYPOTHESIS,
                   'settlement': {'outcome': 'inconclusive', 'reason': 'too few attempts'}})
    thread = initiative.open_threads(g)[0]
    assert thread['rule'] == 'inconclusive-settlement' and 'too few attempts' in thread['body']
    g.card({'title': 'The follow-up run', 'body': 'y', 'parent': card['id']})  # a plan followed it
    assert [t for t in initiative.open_threads(g) if t['rule'] == 'inconclusive-settlement'] == []


def test_a_contradicted_source_is_an_open_thread(genesis):
    """`new_evidence` is the library's own rule: a newer source on the same topic that names this
    one in `contradicts`. Being merely newer is not a disagreement."""
    g = genesis.genesis
    source(g, 'aaa', published_at='2020-01-01', discovered_at='2020-01-01')
    source(g, 'bbb', published_at='2026-01-01', discovered_at='2020-01-01', contradicts=['aaa'])
    threads = initiative.open_threads(g)
    assert threads[0]['rule'] == 'contradicted-source'
    assert threads[0]['evidence'] == [{'kind': 'library', 'id': 'aaa'}]
    # without the declaration it is only an unused source, which is a weaker thread and comes later
    source(g, 'bbb', published_at='2026-01-01', discovered_at='2020-01-01', contradicts=[])
    assert [t['rule'] for t in initiative.open_threads(g)] == ['unused-source']


def test_an_unused_source_is_open_only_after_a_week(genesis):
    g = genesis.genesis
    today = now_sao_paulo().date().isoformat()
    source(g, 'fresh', discovered_at=today)
    assert initiative.open_threads(g) == []  # read today: not an open thread yet
    source(g, 'fresh', discovered_at='2020-01-01')
    thread = initiative.open_threads(g)[0]
    assert thread['rule'] == 'unused-source' and thread['kind'] == 'source'
    source(g, 'fresh', discovered_at='2020-01-01', used_in=[{'version_id': 'v1'}])
    assert initiative.open_threads(g) == []


def test_a_record_a_card_already_points_at_is_not_filed_twice(genesis):
    g = genesis.genesis
    source(g, 'aaa', discovered_at='2020-01-01')
    assert initiative.open_threads(g)
    g.intake('source', 'Someone already asked', 'x', [{'kind': 'library', 'id': 'aaa'}])
    assert initiative.open_threads(g) == []


# ---- the job -----------------------------------------------------------------------------------
def test_the_job_files_the_first_matching_rule_and_only_one_card(genesis):
    g = genesis.genesis
    g.card({'title': 'Graph beats bare', 'body': 'x', 'hypothesis': HYPOTHESIS})   # rule 1
    source(g, 'aaa', discovered_at='2020-01-01')                                    # rule 4
    assert len(initiative.open_threads(g)) == 2
    out = initiative.initiative(genesis)
    assert out['rule'] == 'unsettled-hypothesis' and out['card'] and out['open'] == 2
    card = g.read('cards', out['card'])
    assert card['auto'] is True and card['work']['status'] == 'queued' and card['kind'] == 'hypothesis'
    assert card['question'] and card['evidence']
    assert [c['id'] for c in g.watcher._cards('queued')] == [card['id']]
    assert any(e['kind'] == 'initiative' and e['card'] == card['id'] for e in g.autonomy.tail(10))


@pytest.mark.parametrize('setup, reason', [
    (lambda g: g.autonomy.set({'initiative': 'off'}), 'Initiative dial is off'),
    (lambda g: g.autonomy.set({'paused': True}), 'paused'),
])
def test_the_dials_stop_the_job_before_it_reads_anything(genesis, setup, reason):
    g = genesis.genesis
    g.card({'title': 'Graph beats bare', 'body': 'x', 'hypothesis': HYPOTHESIS})
    setup(g)
    out = initiative.initiative(genesis)
    assert out['card'] is None and reason in out['reason']
    assert g.watcher._cards('queued') == []


def test_nothing_is_opened_while_genesis_still_has_work(genesis):
    g = genesis.genesis
    g.card({'title': 'Graph beats bare', 'body': 'x', 'hypothesis': HYPOTHESIS})
    g.intake('run', 'Something to work', 'run-1', [{'kind': 'run', 'id': 'run-1'}])
    out = initiative.initiative(genesis)
    assert out['card'] is None and 'work in hand' in out['reason']


def test_one_card_a_day_on_the_labs_clock(genesis, monkeypatch):
    g = genesis.genesis
    g.card({'title': 'Graph beats bare', 'body': 'x', 'hypothesis': HYPOTHESIS})
    source(g, 'aaa', discovered_at='2020-01-01')
    first = initiative.initiative(genesis)
    assert first['card']
    g.stop_work(first['card'])  # the card is worked and done; a thread is still open
    assert initiative.open_threads(g)
    assert initiative.initiative(genesis)['reason'] == 'Genesis already opened a card today.'
    # the record stamps UTC: an entry from this evening must still count as today in São Paulo
    now = now_sao_paulo()
    assert initiative.opened_today(g, now) is True
    assert initiative.opened_today(g, now + timedelta(days=1)) is False


def test_the_job_costs_nothing_and_says_so_when_the_record_is_quiet(genesis):
    out = initiative.initiative(genesis)
    assert out['card'] is None and out['open'] == 0 and 'Nothing in the record is open' in out['reason']


def test_the_scheduler_offers_the_job_and_the_dial_refuses_a_bad_value(genesis):
    from wb_studio import scheduler
    assert 'wb_studio.genesis_initiative' in scheduler.MODULES
    assert initiative.DAILY[0] == 'genesis-initiative' and initiative.DAILY[1] == 7
    with pytest.raises(ValueError, match='open or off'):
        genesis.genesis.autonomy.set({'initiative': 'sometimes'})
    assert genesis.genesis.autonomy.read()['words']['initiative']
