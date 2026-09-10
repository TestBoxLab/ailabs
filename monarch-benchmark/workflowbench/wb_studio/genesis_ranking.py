"""Ranking the queue: a pairwise tournament judged by the Reviewer, an Elo score kept by
code (feature 022, design section 5).

When more than one hypothesis waits for the envelope, the Reviewer compares pairs — which
is worth testing first, given the current build, the record and the cost of the smallest
plan that would settle it — and the code keeps one score per card in `genesis/ranking.json`
(`{card_id: {'elo': 1200, 'games': 0, 'updated_at'}}`, K = 32, at most twelve pairs a
night). With one hypothesis queued no turn is spent.

The pair a turn is judging is kept in the activity record (`ranking-requested`, written
with the turn id before the turn starts, as `Genesis.work` does), so `ON_TURN` can find it
without a second store and without a field on the turn.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal

from wb_results.evidence import write_json
from wb_studio.genesis import stamp
from wb_studio.genesis_harness import model_routes
from wb_studio.library import now_sao_paulo

PURPOSE = 'Genesis ranking'
START = 1200.0
K = 32.0
LIMIT = 12
RULE = ('Which of these two hypotheses is worth testing first, given the current build, the record and '
        'the cost of the smallest plan that would settle it? Answer with one JSON object and nothing else: '
        '{"winner": "a" or "b", "reason": "one sentence"}.')


def cap() -> str:
    """The ranking step's per-turn ceiling. Per-step caps are not in `genesis/config.json` yet."""
    return os.environ.get('STUDIO_GENESIS_RANKING_USD', '0.20')


def path(genesis):
    return genesis.root / 'ranking.json'


def scores(genesis) -> dict:
    try:
        data = json.loads(path(genesis).read_text(encoding='utf8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def with_scores(genesis, cards) -> list:
    """The cards with their `elo` and `games` merged in, for `pairs` and `order`."""
    table = scores(genesis)
    return [{**c, 'elo': START, 'games': 0, **table.get(c['id'], {})} for c in cards]


def queued(cards) -> list:
    return [c for c in cards if c.get('kind') == 'hypothesis' and (c.get('work') or {}).get('status') == 'queued']


def pairs(cards, night=()) -> list:
    """Up to twelve pairs of queued hypothesis cards for one night.

    Cards with the fewest games come first, then the oldest. Neighbours are paired before
    distant ones, so every card gets a comparison before any card gets a second. A pair
    already judged tonight (`night`, the pairs from the activity record) is never repeated.
    """
    ranked = sorted(queued(cards), key=lambda c: (int(c.get('games') or 0), str(c.get('created_at') or ''), c['id']))
    done = {frozenset(p) for p in night}
    out = []
    for gap in range(1, len(ranked)):
        for i in range(len(ranked) - gap):
            pair = (ranked[i]['id'], ranked[i + gap]['id'])
            if frozenset(pair) in done:
                continue
            done.add(frozenset(pair))
            out.append(pair)
            if len(out) >= LIMIT:
                return out
    return out


def order(cards) -> list:
    """The queue, best first: Elo descending, then created_at.

    Every card keeps its place in the list; a card with no score (a run or source card, a
    hypothesis never compared) sits at 1200, so the old oldest-first order holds among them.
    """
    return sorted(cards, key=lambda c: (-float(c.get('elo') or START), str(c.get('created_at') or '')))


def why_first(card) -> str:
    """One sentence for the board."""
    elo, games = float(card.get('elo') or START), int(card.get('games') or 0)
    if not games:
        return 'Not compared yet: it starts at 1200 and the queue takes it in the order it arrived.'
    stands = 'above' if elo > START else ('below' if elo < START else 'at')
    return (f'Elo {elo:.0f} after {games} comparison(s), {stands} the 1200 every hypothesis starts at. The Reviewer '
            'compares which is worth testing first, given the build, the record and the cost of settling it.')


def _card(genesis, value):
    return value if isinstance(value, dict) else genesis.read('cards', str(value))


def _side(letter, card) -> str:
    record = card.get('hypothesis') or {}
    lines = ['Card ' + letter + ': ' + str(card.get('id')),
             'Claim: ' + str(record.get('claim') or card.get('title') or '')]
    if record:
        lines.append('Record: ' + json.dumps(record, default=str)[:800])
        if record.get('prior') is not None:
            lines.append("Genesis's prior that the claim holds: " + str(record['prior']))
    settlement = card.get('settlement')
    if settlement:
        lines.append('What the record says so far: ' + str(settlement.get('outcome')) + '. ' + str(settlement.get('reason') or '')[:300])
    body = str(card.get('body') or '').strip()
    if body:
        lines.append('Body: ' + body[:1200])
    return '\n'.join(lines)


def judge(genesis, a, b) -> dict:
    """One comparison turn on the ranking route. The pair is recorded before the turn starts."""
    first, second = _card(genesis, a), _card(genesis, b)
    route = genesis.config.route_for('ranking', routes=model_routes())
    if not route:
        raise ValueError('No model route is available for ranking.')
    message = (_side('a', first) + '\n\n' + _side('b', second) + '\n\n' + RULE)[:15000]
    identity = uuid.uuid4().hex
    genesis.autonomy.record('ranking-requested', card=first['id'], turn=identity, a=first['id'], b=second['id'])
    return genesis.chat({'id': identity, 'message': message, 'model': route['id'], 'maximum_usd': cap(), 'purpose': PURPOSE})


def update(genesis, winner, loser) -> dict:
    """The Elo move, K = 32: what the winner gains the loser loses, so the table sums to itself."""
    with genesis.lock:
        table = scores(genesis)
        won = {'elo': START, 'games': 0, **table.get(winner, {})}
        lost = {'elo': START, 'games': 0, **table.get(loser, {})}
        expected = 1 / (1 + 10 ** ((float(lost['elo']) - float(won['elo'])) / 400))
        move = round(K * (1 - expected), 2)
        now = stamp()
        table[winner] = {'elo': round(float(won['elo']) + move, 2), 'games': int(won['games']) + 1, 'updated_at': now}
        table[loser] = {'elo': round(float(lost['elo']) - move, 2), 'games': int(lost['games']) + 1, 'updated_at': now}
        write_json(path(genesis), table)
    return {'winner': winner, 'loser': loser, 'move': move, 'elo': {winner: table[winner]['elo'], loser: table[loser]['elo']}}


def judged_tonight(genesis, now=None) -> list:
    """The pairs already sent out tonight, from the activity record."""
    now = now or now_sao_paulo()
    today, out = now.date().isoformat(), []
    for entry in genesis.autonomy.tail(500):
        if entry.get('kind') != 'ranking-requested' or not entry.get('a'):
            continue
        try:
            day = datetime.fromisoformat(entry.get('at') or '').astimezone(now.tzinfo).date().isoformat()
        except ValueError:
            continue
        if day == today:
            out.append((entry['a'], entry['b']))
    return out


def ON_TURN(genesis, turn):
    """A finished comparison moves both scores. A failed turn or an unusable answer moves nothing."""
    if turn.get('purpose') != PURPOSE:
        return
    pair = next((e for e in genesis.autonomy.tail(500) if e.get('kind') == 'ranking-requested' and e.get('turn') == turn['id']), None)
    if not pair:
        return
    from wb_studio.genesis_reviewer import json_answer
    try:
        if turn.get('status') != 'completed':
            raise ValueError('The comparison turn did not finish.')
        data = json_answer(turn.get('answer'), 'The Reviewer')
        if data.get('winner') not in ('a', 'b'):
            raise ValueError('The Reviewer did not name a or b as the winner.')
    except ValueError as exc:
        genesis.autonomy.record('ranking-failed', card=pair['a'], turn=turn['id'], a=pair['a'], b=pair['b'], reason=str(exc))
        return
    winner = pair['a'] if data['winner'] == 'a' else pair['b']
    loser = pair['b'] if winner == pair['a'] else pair['a']
    moved = update(genesis, winner, loser)
    genesis.autonomy.record('ranked', card=winner, turn=turn['id'], a=pair['a'], b=pair['b'], winner=winner,
                            reason=str(data.get('reason') or '')[:300], elo=moved['elo'])


def nightly(studio):
    """At 03:00: compare the queued hypotheses in pairs, within the ledger and the step's cap."""
    genesis, now = studio.genesis, now_sao_paulo()
    summary = {'day': now.date().isoformat(), 'pairs': [], 'turns': [], 'errors': [], 'reason': None}
    cards = with_scores(genesis, genesis.listing('cards'))
    chosen = pairs(cards, judged_tonight(genesis, now))
    if not chosen:
        summary['reason'] = ('Fewer than two hypotheses are queued, or every pair was already compared tonight; '
                             'no ranking turn was spent.')
        return summary
    ceiling = Decimal(cap())
    try:
        affordable = int(Decimal(str(studio.ledger.status(now=now).available_usd)) / ceiling)
    except Exception as exc:  # the job reports and finishes; it never takes the server down
        summary['errors'].append(f'ledger: {type(exc).__name__}: {exc}')
        return summary
    if affordable < 1:
        summary['reason'] = f'The weekly ledger cannot cover ${ceiling:.2f} for one comparison.'
        return summary
    if affordable < len(chosen):
        summary['reason'] = f'The ledger covered {affordable} of the {len(chosen)} comparisons waiting tonight.'
    for a, b in chosen[:affordable]:
        try:
            summary['turns'].append(judge(genesis, a, b)['id'])
            summary['pairs'].append([a, b])
        except Exception as exc:
            summary['errors'].append(f'{a} against {b}: {type(exc).__name__}: {exc}')
    return summary


DAILY = ('genesis-ranking', 3, nightly)

PROTOCOL = ('When more than one hypothesis is queued, the Reviewer compares them in pairs at night and the '
            'Studio keeps an Elo score per hypothesis card, starting at 1200. The queue is worked best score '
            'first, not oldest first, and the board shows the score with one sentence saying why a card is '
            'first. You do not write these scores and you do not ask for a comparison: the nightly job runs '
            'it, and with a single queued hypothesis no turn is spent.')
