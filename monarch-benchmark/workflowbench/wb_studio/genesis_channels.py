"""Channels: Slack and the weekly digest data, plus the Monday sweep (feature 022,
design section 11 and section 5's sweep).

Slack: one webhook named in `SLACK_WEBHOOK_AILABS`, links built from `STUDIO_PUBLIC_URL`.
The nightly brief posts after it is written (a step in `genesis_sleep.nightly`), and a
question card or a waiting plan posts when it appears. Every post is written to the
activity record as `slack` with its status, and each card is posted once. With no webhook
nothing is sent and the brief carries one line saying so. A post is not a paid request,
so it reserves nothing; it is still recorded.

`digest(genesis, week)` is the data behind the weekly digest page (the page is lane B's).

The sweep is here because a module offers the scheduler one daily job and this is the
weekly-cadence module the scheduler already knows; `genesis_memory_suite` carries the
weekly evaluation. Moving it to its own module means adding that module to
`scheduler.MODULES`, which this lane does not own.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.request import Request, urlopen

from wb_studio.library import TOPICS, now_sao_paulo

WEBHOOK = 'SLACK_WEBHOOK_AILABS'
NO_WEBHOOK = 'No Slack webhook is configured, so nothing was posted.'
SWEEP_PURPOSE = 'Genesis sweep'
SWEEP = ('Weekly sweep of the topic "{topic}". The library holds {count} sources under it; the newest are: {newest}.\n\n'
         'Search for work published since the newest of those with search_research, and file what is worth keeping '
         'with library_save (title, url, source_type, abstract, topic "{topic}"). When a new source contradicts an '
         'Analyzed card, say so on that card with save_research and name both records. When a finding is worth '
         'testing, drop at most one hypothesis card for it with save_research: stage "research", kind "hypothesis", '
         'a one-sentence claim as the title, and the record tags it rests on in the body. Do not propose a run and '
         'do not spend anything beyond this turn.')


# ---- Slack -------------------------------------------------------------------------
def link(path='') -> str:
    """A link into the Studio, from the public host in the environment."""
    base = str(os.environ.get('STUDIO_PUBLIC_URL') or '').rstrip('/')
    return (base + '/' + str(path or '').lstrip('/')) if base else ''


def post(text, blocks=None) -> dict:
    """Post to the webhook. No webhook, no post: the reason comes back in words."""
    url = os.environ.get(WEBHOOK)
    if not url:
        return {'posted': False, 'reason': NO_WEBHOOK}
    body = json.dumps({'text': str(text or '')[:3000], **({'blocks': blocks} if blocks else {})}).encode()
    request = Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            return {'posted': True, 'status': getattr(response, 'status', None) or response.getcode()}
    except Exception as exc:  # a channel never fails the work it reports on
        return {'posted': False, 'reason': f'{type(exc).__name__}: {exc}'}


def announce(genesis, text, blocks=None, **data) -> dict:
    """Post and write the result to the activity record, whatever it was."""
    result = post(text, blocks)
    genesis.autonomy.record('slack', text=text[:200], posted=result['posted'],
                            status=result.get('status'), reason=result.get('reason'), **data)
    return result


def _posted(genesis, kind) -> set:
    return {e.get('card') for e in genesis.autonomy.tail(500) if e.get('kind') == 'slack' and e.get('about') == kind}


def post_brief(genesis, card) -> dict:
    """The nightly brief, after it is written."""
    counts = (card.get('brief') or {}).get('allowance') or {}
    text = 'Nightly brief ' + str(card.get('title') or card.get('id')) + '\n' + str(card.get('body') or '')
    if counts.get('week_usd') is not None:
        text += '\nWeekly allowance left: $' + str(counts['week_usd']) + '.'
    where = link('genesis?card=' + str(card.get('id')))
    if where:
        text += '\n' + where
    return announce(genesis, text, card=card.get('id'), about='brief')


def post_waiting(genesis) -> list:
    """Question cards with no answer and plans waiting for a person, each posted once."""
    out = []
    seen = _posted(genesis, 'question') | _posted(genesis, 'waiting')
    for card in genesis.listing('cards'):
        if card['id'] in seen:
            continue
        if card.get('kind') == 'question' and not card.get('answer'):
            text = 'Genesis is asking: ' + str(card.get('title'))
            if card.get('default'):
                text += '\nIts suggested default: ' + str(card['default'])
            about = 'question'
        elif card.get('stage') == 'approval' and card.get('plan') and (card.get('review') or {}).get('status') != 'pending':
            text = 'A plan is waiting for a person: ' + str(card.get('title'))
            if card.get('waiting'):
                text += '\n' + str(card['waiting'])
            about = 'waiting'
        else:
            continue
        where = link('genesis?card=' + card['id'])
        out.append(announce(genesis, text + ('\n' + where if where else ''), card=card['id'], about=about))
    return out


def ON_TURN(genesis, turn):
    if turn.get('status') in ('completed', 'failed'):
        post_waiting(genesis)


# ---- the weekly digest data ---------------------------------------------------------
def _week_range(week):
    year, _, number = str(week).partition('-W')
    start = datetime.fromisocalendar(int(year), int(number or 1), 1)
    return start.date().isoformat(), (start + timedelta(days=7)).date().isoformat()


def digest(genesis, week) -> dict:
    """What the weekly digest page reads: what ran, what is done, what settled, the track line."""
    start, end = _week_range(week)
    inside = lambda value: start <= str(value or '')[:10] < end
    jobs = [j for j in genesis.studio.jobs() if inside(j.get('finished_at') or j.get('created_at'))]
    cards = genesis.listing('cards')
    done = [c for c in cards if c.get('stage') == 'complete']
    hypotheses = []
    for card in cards:
        outcome = (card.get('settlement') or {}).get('outcome')
        if outcome in ('supported', 'not_supported'):
            hypotheses.append({'id': card['id'], 'title': card['title'], 'outcome': outcome,
                               'tag': '[rec:card:' + card['id'] + ']',
                               'reason': str((card.get('settlement') or {}).get('reason') or '')[:300]})
    try:
        track = [l for l in (genesis.memory.root / 'TRACK.md').read_text(encoding='utf8').splitlines() if l.startswith('Calibration')]
    except OSError:
        track = []
    gates = {'reviews': {}, 'questions': 0, 'answers': 0, 'defaults_taken': 0, 'launches': 0, 'held': 0,
             'refused_turns': 0, 'opened': 0}
    defaults = {c['id']: c.get('default') for c in cards if c.get('kind') == 'question'}
    for e in genesis.autonomy.tail(2000):
        if not inside(e.get('at')):
            continue
        kind = e.get('kind')
        if kind == 'review' and e.get('verdict'):
            gates['reviews'][e['verdict']] = gates['reviews'].get(e['verdict'], 0) + 1
        elif kind == 'question':
            gates['questions'] += 1
        elif kind == 'answer':
            gates['answers'] += 1
            if defaults.get(e.get('card')) and e.get('answer') == defaults.get(e.get('card')):
                gates['defaults_taken'] += 1
        elif kind == 'launch':
            gates['launches'] += 1
        elif kind == 'waiting':
            gates['held'] += 1
        elif kind == 'refused':
            gates['refused_turns'] += 1
        elif kind == 'initiative':
            gates['opened'] += 1  # cards Genesis opened for itself
    return {'week': week, 'from': start, 'to': end, 'gates': gates,
            'ran': [{'id': j['id'], 'title': j.get('title') or j['id'], 'status': j.get('status')} for j in jobs][:20],
            'done': [{'id': c['id'], 'title': c['title'], 'tag': '[rec:card:' + c['id'] + ']'} for c in done][:20],
            'supported': [h for h in hypotheses if h['outcome'] == 'supported'],
            'refuted': [h for h in hypotheses if h['outcome'] == 'not_supported'],
            'standings': link('leaderboard') or '/leaderboard',
            'track': track[0] if track else 'No calibration line yet.'}


# ---- the weekly sweep ---------------------------------------------------------------
def sweep_cap() -> str:
    return os.environ.get('STUDIO_GENESIS_SWEEP_USD', '0.50')


def topics(genesis) -> list:
    """The library topics that hold at least one source, with their newest titles."""
    out = []
    records = genesis.library.records()
    for topic in TOPICS:
        held = [r for r in records if r.get('topic') == topic]
        if held:
            held.sort(key=lambda r: (str(r.get('published_at') or ''), str(r.get('discovered_at') or '')), reverse=True)
            out.append({'topic': topic, 'count': len(held), 'newest': '; '.join(str(r.get('title'))[:80] for r in held[:3])})
    return out


def weekly(studio) -> dict:
    """`genesis-sweep`, 06:00, Mondays only: one turn per topic, as far as the ledger reaches."""
    from wb_studio.genesis_harness import model_routes
    genesis, now = studio.genesis, now_sao_paulo()
    summary = {'day': now.date().isoformat(), 'topics': [], 'turns': [], 'reason': None, 'errors': []}
    if now.weekday() != 0:
        summary['reason'] = 'The sweep runs on Mondays; today is not one.'
        return summary
    held = topics(genesis)
    if not held:
        summary['reason'] = 'No library topic holds a source yet, so no sweep turn was spent.'
        return summary
    route = genesis.config.route_for('sweep', routes=model_routes())
    if not route:
        summary['reason'] = 'No model route is available for the sweep.'
        return summary
    ceiling = Decimal(sweep_cap())
    try:
        affordable = int(Decimal(str(studio.ledger.status(now=now).available_usd)) / ceiling)
    except Exception as exc:  # the job reports and finishes; it never takes the server down
        summary['errors'].append(f'ledger: {type(exc).__name__}: {exc}')
        return summary
    if affordable < 1:
        summary['reason'] = f'The weekly ledger cannot cover ${ceiling:.2f} for one topic.'
        return summary
    if affordable < len(held):
        summary['reason'] = f'The ledger covered {affordable} of the {len(held)} topics with sources.'
    for row in held[:affordable]:
        try:
            turn = genesis.chat({'message': SWEEP.format(**row), 'model': route['id'],
                                 'maximum_usd': sweep_cap(), 'purpose': SWEEP_PURPOSE})
            summary['turns'].append(turn['id'])
            summary['topics'].append(row['topic'])
        except Exception as exc:
            summary['errors'].append(f"{row['topic']}: {type(exc).__name__}: {exc}")
    return summary


def brief_hour(studio) -> int:
    """The hour a person set under Settings, Genesis (R10: the setting now has an effect)."""
    return int(studio.genesis.access.settings()['brief_hour'])


def post_latest_brief(studio) -> dict:
    """The newest brief card, posted once. Without a webhook nothing is sent and the reason is the summary."""
    genesis = studio.genesis
    briefs = [c for c in genesis.listing('cards') if c.get('kind') == 'brief']
    if not briefs:
        return {'posted': False, 'reason': 'No brief has been written yet.'}
    card = briefs[-1]
    if card['id'] in _posted(genesis, 'brief'):
        return {'posted': False, 'reason': 'Already posted.', 'card': card['id']}
    if not os.environ.get(WEBHOOK):
        return {'posted': False, 'reason': NO_WEBHOOK, 'card': card['id']}
    return {**post_brief(genesis, card), 'card': card['id']}


DAILY = (('genesis-sweep', 6, weekly), ('genesis-brief', brief_hour, post_latest_brief))

PROTOCOL = ('Once a week the Studio spends one sweep turn per library topic that holds a source: search for new '
            'work, file it with library_save, say on an Analyzed card when a new source contradicts it, and drop '
            'at most one hypothesis card per finding worth testing. The nightly brief, the questions you ask and '
            'the plans waiting for a person are posted to Slack by the Studio with a link to the card; you do not '
            'post, and nothing private goes into a post.')
