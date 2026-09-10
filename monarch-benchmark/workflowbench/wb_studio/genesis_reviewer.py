"""The Reviewer, the lab's second chamber (feature 022, design section 5).

Genesis proposes; a separate turn on its own model judges. The protocol is `REVIEWER.md`
next to this file, which people edit. The Reviewer answers one JSON object, the code
validates it, and the result is written on the card as `review`. It never writes a card
itself and never launches anything.

Two rounds: a `revise` may be answered once more; a third request is refused in words.
`review_gate(card)` is what a launch consults: accepted, and accepted for *this* plan, or
the plan waits. The wiring of that gate into `propose_experiment`, `_dispatch` and
`approve` belongs to the orchestrator; the exact lines are in `.tmp/genesis-lane-c-receipt.md`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from wb_studio.genesis import stamp

PURPOSE = 'Genesis review'
VERDICTS = ('accept', 'revise', 'reject')
ISSUE_KINDS = ('confound', 'no_control', 'not_frozen', 'effect_undefined', 'cost', 'arithmetic',
               'citation_missing', 'outside_methodology')
SUBJECTS = ('hypothesis', 'plan', 'verdict', 'skill', 'patch')
ROUNDS = 2
OUTPUT = ('Answer with one JSON object and nothing else: {"verdict": "accept", "revise" or "reject", '
          '"issues": [{"kind": one of ' + ', '.join(ISSUE_KINDS) + ', "text": "one sentence"}], '
          '"reason": "one sentence"}. An empty list of issues means nothing is wrong.')


def cap() -> str:
    """The review step's per-turn ceiling. Per-step caps are not in `genesis/config.json` yet."""
    return os.environ.get('STUDIO_GENESIS_REVIEW_USD', '0.50')


def protocol_text() -> str:
    return Path(__file__).with_name('REVIEWER.md').read_text(encoding='utf8')


def json_answer(text, who='The Reviewer') -> dict:
    """The JSON object in a model's answer, tolerating code fences and prose around it."""
    body = str(text or '')
    start, end = body.find('{'), body.rfind('}')
    if start < 0 or end <= start:
        raise ValueError(who + ' did not answer with JSON.')
    try:
        data = json.loads(body[start:end + 1])
    except ValueError:
        raise ValueError(who + "'s answer was not usable JSON.") from None
    if not isinstance(data, dict):
        raise ValueError(who + ' did not answer with a JSON object.')
    return data


def read_verdict(answer) -> dict:
    """`{verdict, issues, reason}` from the Reviewer's answer; an unknown issue kind becomes
    `outside_methodology` rather than being dropped."""
    data = json_answer(answer)
    verdict = data.get('verdict')
    if verdict not in VERDICTS:
        raise ValueError('The Reviewer did not answer accept, revise or reject.')
    issues = []
    for issue in data.get('issues') or []:
        if not isinstance(issue, dict):
            issue = {'text': issue}
        kind = str(issue.get('kind') or '')
        issues.append({'kind': kind if kind in ISSUE_KINDS else 'outside_methodology', 'text': str(issue.get('text') or '')[:400]})
    return {'verdict': verdict, 'issues': issues, 'reason': str(data.get('reason') or '')[:300]}


def artifact_text(card, subject) -> str:
    """The card rendered for the Reviewer: what it carries, nothing invented."""
    parts = ['Subject: the ' + subject + ' on this card.',
             'Card ' + str(card.get('id')) + ', stage ' + str(card.get('stage')) + ', kind ' + str(card.get('kind')) + '.',
             'Title: ' + str(card.get('title') or '')]
    body = str(card.get('body') or '').strip()
    if body:
        parts.append('Body:\n' + body[:6000])
    for name, key in (('Hypothesis record', 'hypothesis'), ('Settlement', 'settlement'), ('Experiment proposal', 'proposal')):
        if card.get(key):
            parts.append(name + ':\n' + json.dumps(card[key], indent=1, default=str)[:2000])
    lines = (card.get('plan') or {}).get('lines')
    if lines:
        parts.append('Plan as the Studio computed it:\n' + '\n'.join('- ' + str(line) for line in lines))
    if card.get('analysis'):
        parts.append('Analysis:\n' + str(card['analysis'])[:3000])
    patch = card.get('patch')
    if patch:  # a patch card: the diff is what the Reviewer judges
        diff = patch.get('diff') if isinstance(patch, dict) else patch
        commit = (patch if isinstance(patch, dict) else {}).get('commit') or 'unknown'
        parts.append('Proposed diff (against commit ' + str(commit) + '):\n' + str(diff or '')[:8000])
    return '\n\n'.join(parts)


def _write(genesis, card_id, review):
    """The review onto the card through `Genesis.card`, so revisions and history hold.
    Returns the refusal sentence when the card could not be written, else None."""
    with genesis.lock:
        try:
            genesis.card({**genesis.read('cards', card_id), 'review': review})
        except (ValueError, OSError) as exc:
            return str(exc)
    return None


def request_review(genesis, card_id, subject='plan') -> dict:
    """Start a review turn for one artifact on this card and mark the card pending."""
    if not card_id:
        raise ValueError('Name the card by its id.')
    subject = str(subject or 'plan')
    if subject not in SUBJECTS:
        raise ValueError('The subject is one of ' + ', '.join(SUBJECTS) + '.')
    card = genesis.read('cards', str(card_id))
    round_number = int((card.get('review') or {}).get('round') or 0) + 1
    if round_number > ROUNDS:
        raise ValueError('The Reviewer has judged this card twice already; the second answer is the last one.')
    route = genesis.config.route_for('review')
    if not route:
        raise ValueError('No model route is available for the Reviewer.')
    message = (protocol_text() + '\n\nThe artifact to judge:\n\n' + artifact_text(card, subject))[:15000] + '\n\n' + OUTPUT
    turn = genesis.chat({'message': message, 'model': route['id'], 'maximum_usd': cap(), 'purpose': PURPOSE, 'card': card['id']})
    genesis.autonomy.record('review-requested', card=card['id'], turn=turn['id'], subject=subject, round=round_number)
    review = {'status': 'pending', 'turn': turn['id'], 'subject': subject, 'round': round_number,
              'digest': card.get('proposal_digest'), 'at': stamp()}
    problem = _write(genesis, card['id'], review)
    return {'card': card['id'], 'turn': turn['id'], 'round': round_number, 'status': 'pending',
            'note': problem or 'The Reviewer is reading the ' + subject + '. Read it back with read_review.'}


def read_review(genesis, card_id) -> dict:
    if not card_id:
        raise ValueError('Name the card by its id.')
    card = genesis.read('cards', str(card_id))
    review = card.get('review')
    if not review:
        return {'card': card['id'], 'status': 'none', 'note': 'No review has been requested for this card.'}
    ok, reason = review_gate(card)
    return {'card': card['id'], **review, 'accepted_for_this_plan': ok, 'gate': reason}


def review_gate(card) -> tuple[bool, str | None]:
    """Whether a launch may go ahead on this card, and the plain reason when it may not."""
    review = (card or {}).get('review') or {}
    if review.get('status') != 'done':
        return False, 'The Reviewer has not accepted this plan.'
    if review.get('verdict') != 'accept':
        return False, 'The Reviewer answered ' + str(review.get('verdict')) + ': ' + str(review.get('reason') or '')
    if review.get('digest') != (card or {}).get('proposal_digest'):
        return False, 'The plan changed after the Reviewer accepted it; ask for a new review.'
    return True, None


def ON_TURN(genesis, turn):
    """A finished review turn becomes the card's review. A failed turn or an answer that is
    not usable JSON is recorded as failed with its reason and never yields a verdict."""
    if turn.get('purpose') != PURPOSE or not turn.get('card'):
        return
    try:
        card = genesis.read('cards', turn['card'])
    except (ValueError, OSError):
        return
    review = dict(card.get('review') or {})
    if review.get('turn') != turn['id']:
        return  # a later review owns this card
    for key in ('verdict', 'issues', 'reason'):
        review.pop(key, None)
    review['at'] = stamp()
    if turn.get('status') != 'completed':
        review['status'] = 'failed'
        review['reason'] = next((e.get('message') for e in reversed(turn.get('events') or []) if e.get('type') == 'failed'),
                                'The review turn did not finish.')
    else:
        try:
            review.update(status='done', **read_verdict(turn.get('answer')))
        except ValueError as exc:
            review.update(status='failed', reason=str(exc))
    problem = _write(genesis, card['id'], review)
    genesis.autonomy.record('review', card=card['id'], turn=turn['id'], status=review['status'],
                            verdict=review.get('verdict'), reason=review.get('reason'),
                            round=review.get('round'), note=problem)


TOOLS = {'request_review': lambda genesis, payload: request_review(genesis, payload.get('card'), payload.get('subject', 'plan')),
         'read_review': lambda genesis, payload: read_review(genesis, payload.get('card'))}

PROTOCOL = ('The Reviewer is the lab\'s second chamber: a separate turn on its own model that judges one '
            'artifact against the methodology and answers accept, revise or reject with its issues. Call '
            'request_review with the card and a subject (hypothesis, plan, verdict, skill or patch) before you '
            'propose a launch and again after you write a verdict, then read_review to read it back. A plan does '
            'not launch without an accepted review of that exact plan; if the plan changes, ask again. You may '
            'answer one revise; the second review is the last, so fix everything it named.')
