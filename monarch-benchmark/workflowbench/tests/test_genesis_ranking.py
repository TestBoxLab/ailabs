"""The pairwise tournament and its Elo, offline: pairs never repeat within a night, a
comparison moves both scores by the same amount, and a single queued hypothesis spends
nothing. Every model turn here is a fake `genesis.chat`."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_ranking as ranking
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setattr(ranking, 'model_routes', lambda: [{'id': 'cheap', 'available': True}])
    ledger = Mock()
    ledger.status.return_value = SimpleNamespace(available_usd=Decimal('10'))
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=ledger)
    studio.genesis = Genesis(studio)
    studio.genesis.chat = Mock(side_effect=lambda payload: {'id': payload['id'], **payload})
    return studio.genesis


def hypothesis(genesis, name, queued=True, prior=0.6):
    return genesis.card({'id': name, 'title': 'Hypothesis ' + name, 'kind': 'hypothesis', 'stage': 'hypothesis',
                         'body': 'A claim about retries.', 'hypothesis': {'claim': 'Retries help on ' + name, 'prior': prior},
                         'work': {'status': 'queued'} if queued else None})


def finished(turn_id, answer, status='completed'):
    return {'id': turn_id, 'purpose': 'Genesis ranking', 'status': status, 'answer': answer, 'events': []}


def test_elo_moves_are_symmetric_and_bounded_by_k(genesis):
    moved = ranking.update(genesis, 'winner-card', 'loser-card')
    table = ranking.scores(genesis)
    assert table['winner-card']['elo'] == 1216 and table['loser-card']['elo'] == 1184   # equal scores: half of K
    assert moved['move'] == 16 and table['winner-card']['games'] == table['loser-card']['games'] == 1
    for _ in range(6):
        ranking.update(genesis, 'winner-card', 'loser-card')
    table = ranking.scores(genesis)
    assert table['winner-card']['elo'] + table['loser-card']['elo'] == pytest.approx(2 * ranking.START)  # what one gains the other loses
    assert 0 < table['winner-card']['elo'] - 1216 < 7 * ranking.K                                        # every move is under K
    assert table['winner-card']['games'] == 7


def test_pairs_prefer_the_least_played_and_never_repeat_within_a_night(genesis):
    for name in ('a', 'b', 'c'):
        hypothesis(genesis, name)
    hypothesis(genesis, 'd', queued=False)                      # not queued: never compared
    genesis.card({'id': 'r', 'title': 'A run card', 'kind': 'run', 'stage': 'research', 'work': {'status': 'queued'}})
    cards = ranking.with_scores(genesis, genesis.listing('cards'))
    tonight = ranking.pairs(cards, [])
    assert tonight == [('a', 'b'), ('b', 'c'), ('a', 'c')]
    assert ranking.pairs(cards, tonight) == []
    assert ranking.pairs(cards, [('a', 'b')]) == [('b', 'c'), ('a', 'c')]
    assert len(ranking.pairs([{'id': str(i), 'kind': 'hypothesis', 'work': {'status': 'queued'}} for i in range(20)], [])) == ranking.LIMIT
    # a card with games already played waits behind the untried ones
    ranking.update(genesis, 'a', 'b')
    played = ranking.with_scores(genesis, genesis.listing('cards'))
    assert ranking.pairs(played, [])[0] == ('c', 'a')


def test_one_queued_hypothesis_spends_nothing(genesis):
    hypothesis(genesis, 'only')
    summary = ranking.nightly(genesis.studio)
    assert summary['pairs'] == [] and summary['turns'] == [] and 'no ranking turn was spent' in summary['reason']
    genesis.chat.assert_not_called()


def test_a_night_of_comparisons_moves_the_queue(genesis):
    for name in ('a', 'b'):
        hypothesis(genesis, name)
    summary = ranking.nightly(genesis.studio)
    assert summary['pairs'] == [['a', 'b']] and summary['errors'] == []
    payload = genesis.chat.call_args.args[0]
    assert payload['purpose'] == 'Genesis ranking' and payload['maximum_usd'] == '0.20' and payload['model'] == 'cheap'
    assert 'Retries help on a' in payload['message'] and "Genesis's prior" in payload['message'] and 'worth testing first' in payload['message']
    assert ranking.nightly(genesis.studio)['pairs'] == []      # the same pair is not judged twice in one night

    ranking.ON_TURN(genesis, finished(summary['turns'][0], '{"winner": "b", "reason": "Its plan is a tenth of the cost."}'))
    assert ranking.scores(genesis)['b']['elo'] == 1216
    logged = genesis.autonomy.tail(1)[0]
    assert logged['kind'] == 'ranked' and logged['winner'] == 'b' and logged['a'] == 'a' and 'tenth of the cost' in logged['reason']
    ranked = ranking.order(ranking.with_scores(genesis, genesis.listing('cards')))
    assert [c['id'] for c in ranked] == ['b', 'a']
    assert ranking.why_first(ranked[0]).startswith('Elo 1216 after 1 comparison(s), above the 1200')
    assert ranking.why_first(ranked[1]).startswith('Elo 1184 after 1 comparison(s), below the 1200')
    assert ranking.why_first({'id': 'fresh'}).startswith('Not compared yet')


def test_a_failed_comparison_moves_nothing(genesis):
    for name in ('a', 'b'):
        hypothesis(genesis, name)
    summary = ranking.nightly(genesis.studio)
    ranking.ON_TURN(genesis, finished(summary['turns'][0], '', status='failed'))
    assert ranking.scores(genesis) == {}
    ranking.ON_TURN(genesis, finished(summary['turns'][0], 'I prefer the first one.'))
    assert ranking.scores(genesis) == {}
    assert genesis.autonomy.tail(1)[0]['kind'] == 'ranking-failed'
    ranking.ON_TURN(genesis, finished('a-turn-nobody-recorded', '{"winner": "a"}'))
    assert ranking.scores(genesis) == {}


def test_the_ledger_bounds_the_night(genesis):
    for name in ('a', 'b', 'c'):
        hypothesis(genesis, name)
    genesis.studio.ledger.status.return_value = SimpleNamespace(available_usd=Decimal('0.45'))
    summary = ranking.nightly(genesis.studio)
    assert len(summary['pairs']) == 2 and summary['reason'] == 'The ledger covered 2 of the 3 comparisons waiting tonight.'
    genesis.studio.ledger.status.return_value = SimpleNamespace(available_usd=Decimal('0.05'))
    assert ranking.nightly(genesis.studio)['reason'] == 'The weekly ledger cannot cover $0.20 for one comparison.'


def test_the_scheduler_offers_the_ranking_job(tmp_path):
    from wb_studio.scheduler import Scheduler
    scheduler = Scheduler(SimpleNamespace(directory=tmp_path), tmp_path / 'schedule.json')
    scheduler.discover()
    assert ('genesis-ranking', 3) in [(j['name'], j['hour']) for j in scheduler.jobs]
