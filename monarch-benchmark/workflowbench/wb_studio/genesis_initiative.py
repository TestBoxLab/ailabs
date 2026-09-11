"""Genesis opens one card a day from the lab's open threads (design of record
`docs/superpowers/specs/2026-09-10-genesis-initiative-design.md`).

Until now a card reached Genesis only from a person's drop, a finished run, a new source, or a
planned run's debrief. On a lab where nothing new lands, the watcher woke every 30 s, found an
empty queue and did nothing, for ever. The dials and the money gates were never the constraint:
nothing ever put a question in front of it.

This job reads stored records, applies the rules below in order, and queues the first match as an
ordinary card. **No model request is spent deciding what to ask** -- when nothing matches, the job
costs nothing, which is the same rule the rest of Genesis's loops follow. Every rule names the
record it reads, so a person can audit why a card exists.

After the card is queued nothing here is special: the watcher takes it under the usual allowances,
and its plan passes `may_launch`, the envelope and the Reviewer like any other.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from wb_studio.library import now_sao_paulo

HOUR = 7                 # after the 03:00 night and the 04:00 code index, before the 08:00 brief
UNUSED_DAYS = 7          # an Analyzed source is not an open thread the day it is read
BODY_CHARS = 2000


def _pointed(cards) -> set:
    """Every (kind, id) some card already carries as evidence, so nothing is filed twice."""
    return {(e.get('kind'), e.get('id')) for c in cards for e in (c.get('evidence') or [])
            if isinstance(e, dict) and e.get('id')}


def _thread(rule, kind, title, body, evidence, question) -> dict:
    return {'rule': rule, 'kind': kind, 'title': str(title)[:140], 'body': str(body)[:BODY_CHARS],
            'evidence': evidence, 'question': question}


def _unsettled_hypothesis(genesis, cards, sources, pointed, now):
    """A hypothesis record nobody has tried to settle against the runs already recorded."""
    for card in cards:
        if card.get('hypothesis') and not card.get('settlement') and ('card', card['id']) not in pointed:
            claim = (card.get('hypothesis') or {}).get('claim') or card['title']
            return _thread('unsettled-hypothesis', 'hypothesis', 'Is this settled: ' + str(claim),
                           'Card ' + card['id'] + ' carries a hypothesis record that has never been settled.\n\n'
                           + str(claim), [{'kind': 'card', 'id': card['id']}],
                           'Do the runs already recorded settle this? Call hypothesis_settle on card ' + card['id']
                           + '. If they do not, call hypothesis_plan and propose the smallest run that would.')
    return None


def _inconclusive_settlement(genesis, cards, sources, pointed, now):
    """A settlement that came back inconclusive and no plan followed it."""
    children = {c.get('parent') for c in cards if c.get('parent')}
    for card in cards:
        outcome = (card.get('settlement') or {}).get('outcome')
        if outcome == 'inconclusive' and card['id'] not in children and ('card', card['id']) not in pointed:
            reason = str((card.get('settlement') or {}).get('reason') or '')
            return _thread('inconclusive-settlement', 'hypothesis', 'Settle what was inconclusive: ' + card['title'],
                           'Card ' + card['id'] + ' settled inconclusive and nothing followed it.\n\n' + reason,
                           [{'kind': 'card', 'id': card['id']}],
                           'This came back inconclusive. What is the smallest run that would settle it? '
                           'Call hypothesis_plan on card ' + card['id'] + ' and propose it.')
    return None


def _contradicted_source(genesis, cards, sources, pointed, now):
    """An Analyzed source a newer source on its topic contradicts, with nobody having said so."""
    for source in sources:
        if source.get('status') == 'analyzed' and source.get('new_evidence') and ('library', source['id']) not in pointed:
            return _thread('contradicted-source', 'source', 'Newer work disagrees: ' + str(source.get('title')),
                           'Source ' + source['id'] + ' is Analyzed and a newer source on '
                           + str(source.get('topic')) + ' contradicts it.', [{'kind': 'library', 'id': source['id']}],
                           'A newer source on this topic disagrees with this one. Which of the two holds on our '
                           'evidence, and does it change a hypothesis we carry?')
    return None


def _unused_source(genesis, cards, sources, pointed, now):
    """An Analyzed source that has been read and never used anywhere."""
    cutoff = (now - timedelta(days=UNUSED_DAYS)).date().isoformat()
    for source in sources:
        if (source.get('status') == 'analyzed' and not source.get('used_in')
                and str(source.get('discovered_at') or '')[:10] <= cutoff
                and ('library', source['id']) not in pointed):
            return _thread('unused-source', 'source', 'Read and never used: ' + str(source.get('title')),
                           'Source ' + source['id'] + ' was analyzed on ' + str(source.get('discovered_at'))[:10]
                           + ' and has never been recorded as used.', [{'kind': 'library', 'id': source['id']}],
                           'This has been read and never used. Does it support or contradict a hypothesis we carry, '
                           'or should it be filed as background?')
    return None


RULES = (_unsettled_hypothesis, _inconclusive_settlement, _contradicted_source, _unused_source)


def open_threads(genesis, now=None) -> list:
    """Every open thread the rules find, in rule order. The first is the one the job files."""
    now = now or now_sao_paulo()
    cards = genesis.listing('cards')
    pointed = _pointed(cards)
    try:
        sources = genesis.library.listing()  # listing(), not records(): it computes new_evidence
    except Exception:
        sources = []
    found = [rule(genesis, cards, sources, pointed, now) for rule in RULES]
    return [thread for thread in found if thread]


def opened_today(genesis, now) -> bool:
    """Whether an initiative card was already opened on the lab's day. The activity record stamps
    UTC, so the timestamp is converted before the dates are compared."""
    for entry in genesis.autonomy.tail(200):
        if entry.get('kind') != 'initiative':
            continue
        try:
            if datetime.fromisoformat(entry['at']).astimezone(now.tzinfo).date() == now.date():
                return True
        except (KeyError, ValueError):
            continue
    return False


def initiative(studio) -> dict:
    """One card a day, or a plain reason why not. Spends nothing either way."""
    genesis, now = studio.genesis, now_sao_paulo()
    summary = {'day': now.date().isoformat(), 'card': None, 'rule': None, 'reason': None, 'open': 0}
    dials = genesis.autonomy.read()
    if dials['paused']:
        summary['reason'] = 'Genesis is paused; a person has to turn it back on.'
        return summary
    if dials.get('initiative') != 'open':
        summary['reason'] = 'The Initiative dial is off: Genesis works only the cards it is given.'
        return summary
    busy = [c for c in genesis.listing('cards')
            if (c.get('work') or {}).get('status') in ('queued', 'working') and c.get('auto')]
    if busy:
        summary['reason'] = 'Genesis already has work in hand; it opens nothing new until that is done.'
        return summary
    if opened_today(genesis, now):
        summary['reason'] = 'Genesis already opened a card today.'
        return summary
    threads = open_threads(genesis, now)
    summary['open'] = len(threads)
    if not threads:
        summary['reason'] = 'Nothing in the record is open: no unsettled hypothesis, no contradicted or unused source.'
        return summary
    thread = threads[0]
    card = genesis.intake(thread['kind'], thread['title'], thread['body'], thread['evidence'],
                          {'question': thread['question'], 'by': 'genesis:initiative'})
    genesis.autonomy.record('initiative', card=card['id'], rule=thread['rule'], title=thread['title'][:80])
    genesis.watcher.notify()
    summary.update(card=card['id'], rule=thread['rule'])
    return summary


DAILY = ('genesis-initiative', HOUR, initiative)
