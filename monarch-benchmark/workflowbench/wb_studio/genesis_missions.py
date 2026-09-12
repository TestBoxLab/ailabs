"""Bounded research missions on existing cards; no independent paid execution path."""
from __future__ import annotations
import json
import os
from wb_results.evidence import write_json
from wb_studio.genesis import stamp

TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted')
EVIDENCE = ('read_run', 'measures', 'failure_buckets')

def _turn(g):
    identity = getattr(g.context, 'turn', None)
    if not identity:
        raise ValueError('A mission action needs its originating conversation turn.')
    return g.read('turns', identity)

def _card(g, identity):
    card = g.read('cards', identity)
    if not card.get('mission'):
        raise ValueError('This card is not a mission.')
    return card

def _owned(g, payload):
    card = _card(g, payload.get('card'))
    turn = _turn(g)
    if turn.get('by') != card['mission']['owner']:
        raise ValueError('Only the mission owner can direct this mission.')
    if payload.get('revision') != card['revision']:
        raise ValueError('The mission changed. Read its current revision before editing.')
    return card, turn

def _save(g, card):
    old = g.read('cards', card['id'])
    archive = g.root / 'card-history' / card['id']
    archive.mkdir(parents=True, exist_ok=True)
    write_json(archive / (str(old['revision']) + '.json'), old)
    card['revision'] = old['revision'] + 1
    card['updated_at'] = stamp()
    write_json(g.path('cards', card['id']), card)
    g.autonomy.record('mission', card=card['id'], status=card['mission']['status'], revision=card['revision'], summary=card['mission'].get('summary'))
    return card

def _text(payload, key, limit=4000):
    value = str(payload.get(key) or '').strip()
    if not value or len(value) > limit:
        raise ValueError(key + ' must be non-empty text of at most ' + str(limit) + ' characters.')
    return value

def _children(g, card):
    return [c for c in g.listing('cards') if c.get('parent') == card['id']]

def start_mission(g, payload):
    turn = _turn(g)
    if turn.get('purpose') not in (None, 'Genesis conversation') or not str(turn.get('by', '')).startswith('human:'):
        raise ValueError('Start a mission from its owner conversation, not a background worker.')
    with g.lock:
        for card in g.listing('cards'):
            if (card.get('mission') or {}).get('origin_turn') == turn['id']:
                return card
        objective = _text(payload, 'objective')
        next_action = _text(payload, 'next_action')
        acceptance = payload.get('acceptance')
        if not isinstance(acceptance, list) or not acceptance or len(acceptance) > 12 or any(not isinstance(x, str) or not x.strip() or len(x) > 1000 for x in acceptance):
            raise ValueError('acceptance is a list of one to twelve concrete criteria.')
        limit = payload.get('max_turns', 8)
        if type(limit) is not int or not 1 <= limit <= 24:
            raise ValueError('max_turns is a whole number from 1 to 24.')
        card = g.card({'title': str(payload.get('title') or objective)[:140], 'body': objective, 'kind': 'mission', 'stage': 'research'})
        card['mission'] = dict(objective=objective, acceptance=acceptance, owner=turn['by'], origin_turn=turn['id'], origin_request=turn.get('message', ''), thread=turn.get('thread'), workspace=turn.get('workspace'), model=turn.get('model'), effort=turn.get('effort','default'), status='queued', max_turns=limit, turn_count=0, summary='Mission recorded.', next_action=next_action, wait_for=None, generation=0)
        card.update(auto=True, work={'status': 'queued', 'queued_at': stamp()})
        dials = g.autonomy.read()
        reason = 'Genesis is paused; the owner must resume it.' if dials['paused'] else 'The Cards dial is off; the owner must enable it.' if dials['cards'] != 'act' else None
        if reason:
            card['work']['reason'] = reason
            card['mission']['summary'] = reason
        _save(g, card)
    g.watcher.notify()
    return card

def mission_status(g, payload):
    turn = _turn(g)
    if payload.get('card'):
        card = _card(g, payload['card'])
        if turn.get('by') != card['mission']['owner']:
            raise ValueError('Only the mission owner can read this mission.')
        return card
    return {'missions': [c for c in g.listing('cards') if (c.get('mission') or {}).get('owner') == turn.get('by') and c['mission'].get('thread') == turn.get('thread')]}

def _read_evidence(turn, run):
    pending = None
    for event in turn.get('events', []):
        receipt = event.get('receipt') or {}
        if event.get('type') == 'tool_completed' and event.get('action') in EVIDENCE and receipt.get('ok') is True and receipt.get('run') == run:
            return True
        if event.get('type') == 'tool_started':
            pending = event
        elif event.get('type') == 'tool_completed' and pending and event.get('action') == pending.get('action') and event.get('action') in EVIDENCE:
            try:
                args = json.loads(pending.get('payload') or '{}')
                result = json.loads(event.get('detail') or event.get('result') or '{}')
            except (TypeError, ValueError):
                continue
            if isinstance(result, dict) and not result.get('error') and (args.get('run') or args.get('id')) == run:
                return True
            pending = None
    return False

def checkpoint_mission(g, payload):
    with g.lock:
        card, turn = _owned(g, payload)
        state = card['mission']
        if state['status'] in ('stopped', 'completed'):
            raise ValueError('This mission is stopped or completed.')
        if (card.get('work') or {}).get('turn') != turn['id'] or turn.get('mission_generation') != state['generation']:
            raise ValueError('This worker no longer owns the mission; it changed.')
        status = payload.get('status')
        if status not in ('continue', 'waiting', 'complete', 'blocked'):
            raise ValueError('Choose continue, waiting, complete or blocked.')
        if status != 'blocked' and _unsaved_build(turn):
            raise ValueError('Call save_architecture successfully before ending this turn; the build is still provisional.')
        summary = _text(payload, 'summary')
        next_action = _text(payload, 'next_action') if status in ('continue', 'waiting') else str(payload.get('next_action') or '')
        target = payload.get('wait_for')
        if status == 'waiting':
            child = g.read('cards', target)
            if child.get('parent') != card['id']:
                raise ValueError('Wait for an experiment card belonging to this mission.')
        if status == 'complete':
            for child in _children(g, card):
                if child.get('job'):
                    job = g.studio.job(child['job'])
                    if job.get('status') not in TERMINAL:
                        raise ValueError('The linked experiment has not finished.')
                    if not _read_evidence(turn, child['job']):
                        raise ValueError('Read the linked run evidence successfully in this turn before completing.')
                elif child.get('stage') not in ('complete', 'review'):
                    raise ValueError('The linked experiment has not finished.')
        state.update(summary=summary, next_action=next_action, wait_for=target if status == 'waiting' else None, wait_kind=('question' if child.get('kind') == 'question' else 'experiment') if status == 'waiting' else None, checkpoint=status, checkpoint_turn=turn['id'], checkpoint_generation=state['generation'])
        return _save(g, card)

def worker_payload(g, card):
    from wb_studio.genesis_harness import model_routes
    with g.lock:
        card = _card(g, card['id']); state = card['mission']
        if g.autonomy.read()['paused']:
            raise ValueError('Genesis is paused.')
        if g.autonomy.read()['cards'] != 'act':
            raise ValueError('The Cards dial is off.')
        if not any(r['id'] == state['model'] and r.get('available') for r in model_routes()):
            raise ValueError('The mission model is unavailable; no substitute was selected.')
        if state['status'] != 'queued' or state['turn_count'] >= state['max_turns']:
            raise ValueError('The mission is not queued or its turn limit is reached.')
        state.update(status='working', turn_count=state['turn_count'] + 1)
        state.pop('checkpoint', None)
        _save(g, card)
        return dict(message='Continue this mission using its authoritative state. Execute the next action, save durable artifacts, then call checkpoint_mission before ending. Mission: ' + card['id'] + '. Next action: ' + state['next_action'], model=state['model'], effort=state.get('effort','default'), by=state['owner'], thread=state.get('thread'), workspace=state.get('workspace'), parent=state['origin_turn'], purpose='Genesis mission', card=card['id'], mission_generation=state['generation'], maximum_usd=os.environ.get('STUDIO_GENESIS_CARD_USD', '2.00'))

def ON_TURN(g, turn):
    if turn.get('purpose') != 'Genesis mission' or not turn.get('card'):
        return
    with g.lock:
        card = _card(g, turn['card']); state = card['mission']
        if state['status'] in ('stopped', 'completed') or state.get('handled_turn') == turn['id'] or turn.get('mission_generation') != state['generation'] or (card.get('work') or {}).get('turn') != turn['id']:
            return
        checkpoint = state.get('checkpoint') if state.get('checkpoint_turn') == turn['id'] and state.get('checkpoint_generation') == state['generation'] else None
        state['handled_turn'] = turn['id']
        if turn.get('status') != 'completed' or not checkpoint:
            state.update(status='blocked', summary='The worker ended without a completed checkpoint. Inspect retained evidence before resuming.')
        elif checkpoint == 'continue':
            state['status'] = 'queued' if state['turn_count'] < state['max_turns'] else 'blocked'
            if state['status'] == 'blocked':
                state['summary'] = 'The mission turn limit is reached. ' + state['summary']
        else:
            state['status'] = {'complete': 'completed', 'waiting': 'waiting', 'blocked': 'blocked'}[checkpoint]
        card['stage'] = 'complete' if state['status'] == 'completed' else 'research' if state['status'] == 'queued' else 'review'
        card['work'] = {'status': {'completed':'done', 'blocked':'failed'}.get(state['status'], state['status']), 'turn': turn['id']}
        card['auto'] = state['status'] == 'queued'
        _save(g, card)
    g.watcher.notify()

def trusted_control(g, card, action, instruction=''):
    with g.lock:
        card = _card(g, card['id'] if isinstance(card, dict) else card); state = card['mission']
        if action not in ('steer', 'resume', 'stop'):
            raise ValueError('Choose steer, resume or stop.')
        if action != 'stop' and state['turn_count'] >= state['max_turns']:
            raise ValueError('The mission turn limit is reached; it cannot extend itself.')
        if action == 'steer' and not str(instruction).strip():
            raise ValueError('Steering needs an instruction.')
        old_turn = (card.get('work') or {}).get('turn')
        stop_turns = {old_turn} if old_turn else set()
        state['generation'] += 1
        state.update(status='stopped' if action == 'stop' else 'queued', wait_for=None)
        if action == 'steer':
            state['next_action'] = str(instruction).strip()[:4000]
            state.setdefault('steering', []).append({'at': stamp(), 'instruction': state['next_action']})
        state['summary'] = 'Stopped by the owner.' if action == 'stop' else 'The owner ' + ('updated the next action.' if action == 'steer' else 'resumed the mission.')
        card.update(stage='review' if action == 'stop' else 'research', auto=action != 'stop', work={'status': state['status']})
        _save(g, card)  # persist invalidation before cooperative cancellation
        if action == 'stop':
            for child in _children(g, card):
                stop_turns.update(t for t in ((child.get('work') or {}).get('turn'), (child.get('review') or {}).get('turn')) if t)
                child.update(auto=False, work={'status':'stopped'})
                if not child.get('job'):
                    child.update(stage='complete', decision={'outcome':'stopped','by':state['owner'],'at':stamp()})
                write_json(g.path('cards', child['id']), child)
                if child.get('job'):
                    try:
                        if g.studio.job(child['job']).get('status') not in TERMINAL:
                            g.studio.cancel(child['job'])
                    except Exception as exc:
                        g.autonomy.record('mission-cancel-error', card=card['id'], job=child['job'], error=type(exc).__name__)
    for identity in stop_turns:
        try:
            g.stop_turn(identity)
        except Exception as exc:
            g.autonomy.record('mission-cancel-error', card=card['id'], turn=identity, error=type(exc).__name__)
    g.watcher.notify()
    return g.read('cards', card['id'])

def control_mission(g, payload):
    with g.lock:
        card, turn = _owned(g, payload)
        if turn.get('purpose') == 'Genesis mission':
            raise ValueError('Only the owner conversation can control a mission.')
        return trusted_control(g, card, payload.get('action'), payload.get('instruction', ''))

def reconcile(g):
    for listed in g.listing('cards'):
        if not listed.get('mission'):
            continue
        with g.lock:
            card = _card(g, listed['id']); state = card['mission']
            if state['status'] == 'working':
                identity = (card.get('work') or {}).get('turn')
                try:
                    turn = g.read('turns', identity)
                except (ValueError, FileNotFoundError):
                    turn = {}
                if turn.get('status') == 'running':
                    continue
                state.update(status='blocked', summary='The worker was interrupted. Inspect retained evidence and uncertain charges before resuming.')
                card.update(stage='review', auto=False, work={'status':'failed', 'turn':identity})
                _save(g, card)
            elif state['status'] == 'waiting' and state.get('wait_for'):
                try:
                    child = g.read('cards', state['wait_for'])
                    finished = g.studio.job(child['job']).get('status') in TERMINAL if child.get('job') else child.get('stage') in ('complete','review')
                except (ValueError, FileNotFoundError):
                    state['summary'] = 'Waiting for a linked experiment record that is unavailable.'
                    if card != listed:
                        _save(g, card)
                    continue
                if not finished:
                    continue
                if child.get('kind') == 'question':
                    state['summary'] = ('Answer from the owner: ' + str(child.get('answer') or 'Question closed.'))[:4000]
                state.update(status='queued' if state['turn_count'] < state['max_turns'] else 'blocked', wait_for=None, wait_kind=None)
                card.update(stage='research' if state['status']=='queued' else 'review', auto=state['status']=='queued', work={'status':'queued' if state['status']=='queued' else 'failed'})
                _save(g, card)

def PROMPT(g, turn):
    if not callable(getattr(g, 'listing', None)):
        return ''
    cards = [c for c in g.listing('cards') if c.get('mission') and c['mission'].get('owner') == turn.get('by') and (c['id'] == turn.get('card') or c['mission'].get('thread') == turn.get('thread'))]
    return '\nAuthoritative mission records (status comes from persisted work, not a promise):\n' + json.dumps([_projection(c) for c in cards], ensure_ascii=False) if cards else ''

PROTOCOL = '''For a substantial user objective that requires work beyond one turn, start_mission records the objective, acceptance criteria and next action on the existing board. Mission workers must checkpoint_mission explicitly: continue with concrete next work, waiting with a linked child experiment card, blocked with the blocker, or complete with evidence. Build and save durable architecture revisions before ending a turn; provisional edits do not survive continuation. Propose each experiment on an independent child card, request review, then wait without paid polling. Read successful evidence results before claiming completion. Retain frozen tasks, held-out separation, native harness and raw control identities, and all existing spending and approval gates. A mission is an attempt at the user's objective, never a guarantee of beating a baseline. Use mission_status to discuss progress and control_mission from the owner conversation to steer, resume or stop.'''
TOOLS = {'start_mission': start_mission, 'mission_status': mission_status, 'checkpoint_mission': checkpoint_mission, 'control_mission': control_mission}


def _unsaved_build(turn):
    pending = False
    for event in turn.get('events', []):
        if event.get('type') != 'tool_completed' or event.get('action') not in ('edit_architecture','save_architecture'):
            continue
        receipt = event.get('receipt') or {}
        if receipt.get('ok') is True:
            if event['action'] == 'edit_architecture' and receipt.get('provisional') is True:
                pending = True
                continue
            if event['action'] == 'save_architecture' and receipt.get('architecture') and type(receipt.get('revision')) is int and receipt['revision'] > 0:
                pending = False
                continue
        try:
            result = json.loads(event.get('detail') or event.get('result') or '{}')
        except (TypeError, ValueError):
            continue
        if not isinstance(result, dict) or result.get('error'):
            continue
        if event['action'] == 'edit_architecture' and isinstance(result.get('operation'), dict):
            pending = True
        elif event['action'] == 'save_architecture' and result.get('id') and result.get('revision'):
            pending = False
    return pending

def _projection(card):
    state = card['mission']
    return {'id':card['id'], 'revision':card['revision'], 'mission':{
        key: state.get(key) for key in ('objective','acceptance','status','model','effort','next_action','summary','wait_for','wait_kind','turn_count','max_turns')
    }}

