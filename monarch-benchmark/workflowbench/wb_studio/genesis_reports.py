"""Genesis owns report analysis, authorship, review and internal publication.

Each stage is a normal, separately recorded Genesis turn with only report tools.
Bounded reservations cover analysis batches, author, review and one repair/re-review.
No model can publish directly. A matching review of complete, unchanged evidence
publishes one version; failed/interrupted work retains its draft and receipts.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path

from wb_results.evidence import write_json

PREFIX = 'Genesis report:'
STAGES = ('analysis', 'author', 'review', 'repair', 'review_again')
WEIGHTS = (Decimal('.30'), Decimal('.25'), Decimal('.15'), Decimal('.20'), Decimal('.10'))
READ_TOOLS = ('report_evidence', 'read_report_state', 'read_report_draft', 'report_status')
TEXT_FIELDS = ('summary', 'what_went_right', 'what_went_wrong', 'why', 'next_experiment', 'limitations')
ATTEMPT_FIELDS = ('expected', 'observed', 'explanation', 'mechanism', 'alternatives', 'confidence', 'missing_evidence')
PROTOCOL = '''You own Studio reports. author_report starts a paid, bounded analysis subagent,
authoring, separate review and at most one repair/re-review; it publishes the accepted
revision inside Studio. report_status gives progress, child turns and the reason for
unfinished work. read_report_draft reads the complete work by section; report_evidence
pages the source. A pending response is not a published report. Use these tools for
report requests, then show #report/<run>. Existing generic record_analysis records do
not publish reports. Report interpretation cannot override grades or prove causation.
No external posting, benchmark launch or repository change is part of this workflow.'''


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _folder(studio, identity):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(identity or '')):
        raise ValueError('Name a recorded run.')
    return Path(studio.directory) / identity


def _read(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except FileNotFoundError:
        return default


def _state(genesis, identity):
    return _read(_folder(genesis.studio, identity) / 'report-work.json')


def _save(genesis, state):
    write_json(_folder(genesis.studio, state['run']) / 'report-work.json', state)
    write_json(_workdir(genesis, state) / 'state.json', state)


def _workdir(genesis, state):
    return _folder(genesis.studio, state['run']) / 'report-work' / state['id']


def account_for(studio, job, events):
    from wb_studio.reports import outcome_report
    # Job rows retain the checks. Do not open Store (which may migrate the DB)
    # or borrow the last repetition's state for every result with this task/setup.
    account = outcome_report(job, events, studio.tasks)
    from wb_studio.failure_analysis import analysis
    segmented = analysis(studio, job['id'])['attempts']
    account['attempts'] = [{**a, **s, 'index': i} for i, (a, s) in enumerate(zip(account['attempts'], segmented))]
    return account


def measures_for(studio, job, events):
    from wb_studio.measures import run_measures
    return run_measures(job, events)


def _capture(studio, identity):
    job, events = studio.job(identity), studio.events(identity)
    if job['status'] not in ('completed', 'failed', 'cancelled', 'interrupted'):
        raise ValueError('Wait for the run to finish before writing its report.')
    account = account_for(studio, job, events)
    from wb_studio.report_trace import capture as capture_trace
    for attempt, result, native in zip(account['attempts'], job['results'], capture_trace(studio, job)):
        attempt.update(episode_id=result.get('episode_id'), trial=result.get('trial'), retained_trace=native)
    briefs = {t: studio.tasks.get(t, {}).get('prompt') for t in job['settings']['tasks']}
    from wb_studio.report_state import capture as capture_state
    from wb_studio.report_patterns import patterns, compact
    names = {a['id']: a.get('name', a['id']) for a in job['settings'].get('arms', [])}
    if not names:
        names = {a: a for a in job['settings'].get('models', [])}
    return {'job': job, 'events': events, 'checked': account, 'briefs': briefs,
            'patterns': compact(patterns(account['attempts'], names, identity)),
            'snapshots': capture_state(studio, identity), 'measures': measures_for(studio, job, events)}


def _fingerprint(capture):
    # Job metadata includes transient UI fields in some callers; the facts of the
    # comparison, the complete trace, briefs and deterministic checks are the input.
    job = capture['job']
    return _hash({k: capture[k] for k in ('events', 'checked', 'briefs', 'snapshots', 'patterns')} |
                 {'settings': job['settings'], 'results': job['results'], 'hashes': job.get('task_hashes'),
                  'status': job['status']})


def _snapshot(genesis, state):
    return _read(_workdir(genesis, state) / 'evidence.json')


def published(studio, identity):
    # A read, so it answers like one: a studio with nowhere to keep reports has
    # published none. round_report works over stored job records alone and is called
    # with no directory; only the writers below may treat that as an error.
    if getattr(studio, 'directory', None) is None:
        return None
    return _read(_folder(studio, identity) / 'report-publication.json')


def status(genesis, payload):
    _scope_read(genesis, payload.get('run'))
    state = _state(genesis, payload.get('run'))
    if not state:
        return {'run': payload.get('run'), 'stage': 'none', 'reason': 'Genesis has not authored this report yet.'}
    out = {k: v for k, v in state.items() if k not in ('reads',)}
    if state['stage'] in STAGES:
        tid = _entry(state, state['stage'])['id']
        reader = getattr(genesis, 'read', None)
        if reader:
            try:
                turn = reader('turns', tid)
                if turn.get('status') in ('failed', 'interrupted', 'cancelled'):
                    out['stage'] = 'failed'
                    out['reason'] = 'The report turn stopped; retained work is available. Retry explicitly after inspecting billing.'
            except FileNotFoundError:
                out['reason'] = 'A reserved stage has no recorded turn. Inspect billing before retrying.'
    out['source'] = '#report/' + state['run']
    return out


def _entry(state, stage):
    key = state.get('analysis_keys', ['analysis'])[state.get('analysis_cursor', 0)] if stage == 'analysis' else stage
    return state['turns'][key]


def _batches(capture):
    """Fresh analyst contexts, bounded by attempt count and retained trace size."""
    sizes = {e['id']: len(json.dumps(e, ensure_ascii=False, default=str)) for e in capture['events']}
    groups, group, size = [], [], 0
    for index, attempt in enumerate(capture['checked']['attempts']):
        weight = sum(sizes.get(e, 0) for e in attempt['event_ids']) + len(json.dumps(attempt, default=str))
        if group and (len(group) >= 8 or size + weight > 100000):
            groups.append(group); group, size = [], 0
        group.append(index); size += weight
    if group:
        groups.append(group)
    return groups


def _release_unused(genesis, state):
    for entry in state['turns'].values():
        if not entry.get('started'):
            genesis.studio.ledger.finish_run('genesis-' + entry['id'])


def _fail(genesis, state, reason):
    state.update(stage='failed', reason=str(reason)[:1200])
    _save(genesis, state)
    _release_unused(genesis, state)
    genesis.autonomy.record('report-failed', run=state['run'], report=state['id'], reason=state['reason'])


def start(genesis, payload):
    identity = payload.get('run')
    with genesis.lock:
        existing = _state(genesis, identity)
        if existing:
            # Never silently replay a failed/interrupted paid stage or re-author
            # unchanged published evidence. Explicit retry creates a new history.
            if not payload.get('retry') or status(genesis, payload)['stage'] != 'failed':
                return status(genesis, payload)
            for entry in existing['turns'].values():
                if entry.get('started'):
                    try:
                        if genesis.read('turns', entry['id']).get('status') == 'running':
                            raise ValueError('A report turn is still running; stop it before retrying.')
                    except FileNotFoundError:
                        raise ValueError('A dispatched report turn is missing; inspect billing before retrying.') from None
            _release_unused(genesis, existing)
        if genesis.autonomy.read()['paused']:
            raise ValueError('Genesis is paused; resume before authoring a report.')
        capture = _capture(genesis.studio, identity)
        if not capture['checked']['attempts']:
            raise ValueError('This run has no recorded attempts to analyze.')
        maximum = Decimal(str(payload.get('maximum_usd', genesis.studio.analysis_ceiling)))
        if not maximum.is_finite() or maximum <= 0:
            raise ValueError('Choose a positive report budget.')
        # Legacy readings used their own envelope; unknown receipts still count.
        previous_spend = genesis.studio.ledger.scope_committed(identity + '-analysis-v1')
        for saved in (_folder(genesis.studio, identity) / 'report-work').glob('*/state.json'):
            for entry in _read(saved)['turns'].values():
                previous_spend += genesis.studio.ledger.scope_committed('genesis-' + entry['id'])
        execution_spend = sum((r.maximum_usd if r.actual_usd is None else r.actual_usd
                               for r in genesis.studio.ledger.reservations(run_id=identity)), Decimal('0'))
        remaining = Decimal(capture['job']['settings']['maximum_usd']) - execution_spend - previous_spend
        if maximum > remaining:
            raise ValueError('The report ceiling exceeds the run\'s remaining analysis budget.')
        ok, reason = genesis.allowance_allows(maximum)
        if not ok:
            raise ValueError(reason)
        routes = {role: genesis.config.route_for('report_analysis' if role == 'analysis' else 'review' if role.startswith('review') else 'report_author') for role in STAGES}
        if not all(routes.values()):
            raise ValueError('Configure available Genesis report analysis, author and review routes.')
        state = {'id': uuid.uuid4().hex, 'run': identity, 'stage': 'analysis', 'revision': 0,
                 'evidence_sha256': _fingerprint(capture), 'maximum_usd': str(maximum),
                 'attempt_count': len(capture['checked']['attempts']), 'covered': 0,
                 'reads': {}, 'turns': {}, 'processed': [], 'reason': 'The analysis subagent is reading the recorded attempts.'}
        batches = _batches(capture)
        state.update(analysis_keys=['analysis' if i == 0 else 'analysis_' + str(i + 1) for i in range(len(batches))], analysis_cursor=0)
        allocated = Decimal('0')
        for i, stage in enumerate(STAGES):
            amount = (maximum * WEIGHTS[i]).quantize(Decimal('.000001')) if i < 4 else maximum - allocated
            allocated += amount
            groups = list(zip(state['analysis_keys'], batches)) if stage == 'analysis' else [(stage, None)]
            subtotal = Decimal('0')
            for position, (key, indexes) in enumerate(groups):
                share = (amount / len(groups)).quantize(Decimal('.000001')) if position < len(groups) - 1 else amount - subtotal
                subtotal += share
                entry = {'id': uuid.uuid4().hex, 'maximum_usd': str(share),
                         'model': routes[stage]['id'], 'purpose': PREFIX + identity + ':' + stage}
                if indexes is not None:
                    entry['indexes'] = indexes
                state['turns'][key] = entry
                entry['message'] = _message(state, stage, entry)
        from wb_studio.report_budget import validate
        state['budget_preflight'] = validate(genesis, state['turns'], maximum)
        held = []
        try:
            for entry in state['turns'].values():
                scope = 'genesis-' + entry['id']
                genesis.studio.ledger.reserve_run(scope, entry['maximum_usd'],
                    metadata={'purpose': entry['purpose'], 'model': entry['model'], 'by': 'genesis'})
                held.append(scope)
        except Exception:
            for scope in held:
                genesis.studio.ledger.finish_run(scope)
            raise
        try:
            folder = _workdir(genesis, state)
            folder.mkdir(parents=True, exist_ok=True)
            write_json(folder / 'evidence.json', capture)
            write_json(folder / 'attempts.json', {})
            _save(genesis, state)
            _dispatch(genesis, state, 'analysis')
        except Exception as exc:
            _fail(genesis, state, exc)
            raise
        return status(genesis, {'run': identity})


def _dispatch(genesis, state, stage):
    state['stage'] = stage
    state['reason'] = {'analysis': 'The analysis subagent is reading every attempt.', 'author': 'Genesis is writing the explanation.',
                       'review': 'A separate reviewer is checking the draft and evidence.', 'repair': 'Genesis is addressing the review findings.',
                       'review_again': 'The revised draft is being reviewed.'}[stage]
    entry = _entry(state, stage)
    entry['started'] = True
    entry['message'] = _message(state, stage, entry)
    _save(genesis, state)  # persist the identity before a fast child can complete
    step = 'report_analysis' if stage == 'analysis' else 'review' if stage.startswith('review') else 'report_author'
    payload = dict(entry)
    effort = genesis.config.effort_for(step, entry['model'])
    if effort:
        payload['effort'] = effort
    try:
        genesis.chat(payload, reserved=True)
    except Exception:
        entry['started'] = False  # no child was admitted; its unused hold can close
        _save(genesis, state)
        raise
    genesis.autonomy.record('report-stage', run=state['run'], stage=stage, turn=entry['id'])


def _message(state, stage, entry):
    message = ('Report run ' + state['run'] + '. Your role is ' + stage + '. '
               'Read the versioned report procedure in your system prompt. Read report_evidence overview and '
               'read_report_draft, then perform your assigned work. All tool arguments name run "' + state['run'] + '". '
               'The report has ' + str(state['attempt_count']) + ' recorded attempts. '
               'Draft SHA: ' + state.get('draft_sha256', '0' * 64) + '. Evidence SHA: ' + state['evidence_sha256'] + '.')
    if stage == 'analysis':
        message += (' Your assigned attempt indexes are ' + json.dumps(entry['indexes']) +
                    '. Read and record every assigned index. Other batches analyze the rest; compare other attempts as needed, but do not record their analysis. '
                    'Batch independent tool calls in one response; the turn has at most 24 provider requests.')
    if stage in ('review', 'review_again'):
        message += (' Return only JSON {"verdict":"accept|revise|reject","issues":["specific correction"],'
                    '"reason":"evidence-based judgment","draft_sha256":"the exact SHA","evidence_sha256":"the exact SHA"}.')
    return message


def role(turn):
    purpose = str((turn or {}).get('purpose') or '')
    return purpose.rsplit(':', 1)[-1] if purpose.startswith(PREFIX) else None


def allowed_tools(turn):
    stage = role(turn)
    if stage is None:
        return None
    return READ_TOOLS + (('record_report_attempt',) if stage == 'analysis' else ('write_report_draft',) if stage in ('author', 'repair') else ())


def _worker(genesis, identity, stages=None):
    state = _state(genesis, identity)
    tid = getattr(getattr(genesis, 'context', None), 'turn', None)
    if not state or state['stage'] not in STAGES or _entry(state, state['stage'])['id'] != tid:
        raise ValueError('Only the current report worker may change this draft.')
    if stages and state['stage'] not in stages:
        raise ValueError('This report role cannot perform that operation.')
    return state


def _scope_read(genesis, identity):
    tid = getattr(getattr(genesis, 'context', None), 'turn', None)
    if tid and getattr(genesis, 'read', None):
        turn = genesis.read('turns', tid)
        if role(turn) and turn['purpose'].split(':')[1] != identity:
            raise ValueError('Report workers may read only their assigned run.')


def _bounded(value):
    if len(json.dumps(value, ensure_ascii=False, default=str)) > 55000:
        raise ValueError('This page exceeds the report tool limit. Request a smaller limit or an individual attempt; no evidence was truncated.')
    return value


def _packet_page(genesis, state, index, packet, payload):
    """Lossless escape hatch for long events, briefs or check explanations."""
    serialized = json.dumps(packet, ensure_ascii=False, default=str)
    after, limit = payload.get('after', 0), payload.get('limit', 24000)
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 24000:
        raise ValueError('For packet pages use a nonnegative character offset and limit from 1 to 24000.')
    end = min(after + limit, len(serialized))
    result = _bounded({'run': state['run'], 'index': index, 'part': 'packet',
                       'fragment': serialized[after:end], 'after': after,
                       'next_after': end if end < len(serialized) else None,
                       'total_characters': len(serialized),
                       'note': 'Lossless JSON text. Continue with part=packet and next_after as after. Read every fragment before recording analysis.'})
    with genesis.lock:
        current = _state(genesis, state['run'])
        if current['id'] == state['id'] and current['stage'] == 'analysis' and _entry(current, 'analysis')['id'] == getattr(genesis.context, 'turn', None):
            spans = current.setdefault('packet_reads', {}).setdefault(str(index), [])
            spans.append([after, end])
            covered = 0
            for left, right in sorted(spans):
                if left > covered:
                    break
                covered = max(covered, right)
            if covered >= len(serialized):
                current['reads'][str(index)] = packet['checked']['event_ids']
            _save(genesis, current)
    return result


def evidence(genesis, payload):
    identity = payload.get('run'); _scope_read(genesis, identity)
    state = _state(genesis, identity)
    if not state:
        raise ValueError('Start author_report before reading its frozen evidence packet.')
    capture = _snapshot(genesis, state)
    attempts = capture['checked']['attempts']
    if payload.get('section') == 'patterns':
        data = capture['patterns']
        domain = payload.get('domain')
        selected = next((d for d in data['domains'] if d['id'] == domain), None) if domain else data
        if selected is None:
            raise ValueError('Choose a domain from the pattern summary.')
        columns = selected['setups']
        if payload.get('setup'):
            columns = [c for c in columns if c['id'] == payload['setup']]
            if not columns:
                raise ValueError('Choose a recorded setup.')
        return _bounded({k: data[k] for k in ('denominator', 'behavior_basis', 'checks_basis')} |
                        {'domain': domain, 'setups': columns, 'domains': [{'id': d['id'], 'label': d['label']} for d in data['domains']],
                         'source': '#report/' + identity, 'note': 'Counts and percentages are computed by the same code as the chart. attempt_keys are run:index; read that index with report_evidence.'})
    if payload.get('section') is not None:
        raise ValueError('The optional section is patterns.')
    index = payload.get('attempt')
    if index is None:
        return _bounded({'run': identity, 'evidence_sha256': state['evidence_sha256'], 'attempt_count': len(attempts),
                         'attempts': [{'index': i, 'task': a['task'], 'model': a['model'], 'passed': a['passed']} for i, a in enumerate(attempts)],
                         'measures': capture['measures'], 'settings': capture['job']['settings'],
                         'task_hashes': capture['job'].get('task_hashes'),
                         'source': '#report/' + identity, 'patterns': 'Read section=patterns, optionally selecting domain and setup, for the chart counts and percentages.', 'note': 'Read every attempt page, including successes; never infer a cause from the failed checker alone.'})
    if type(index) is not int or not 0 <= index < len(attempts):
        raise ValueError('Choose an attempt index from the overview.')
    attempt = attempts[index]
    event_ids = set(attempt['event_ids'])
    events = [e for e in capture['events'] if e.get('id') in event_ids]
    checked = {k: v for k, v in attempt.items() if k not in ('actions', 'story')}
    checked['story'] = {k: v for k, v in attempt.get('story', {}).items() if k != 'timeline'}
    packet = {'checked': checked, 'brief': capture['briefs'].get(attempt['task']), 'events': events}
    if payload.get('part') == 'packet':
        return _packet_page(genesis, state, index, packet, payload)
    if payload.get('part') is not None:
        raise ValueError('Use part=packet only for lossless JSON character pages.')
    after, limit = payload.get('after', 0), payload.get('limit', 20)
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Use a nonnegative after offset and a limit from 1 to 50.')
    page = events[after:after + limit]
    # The trace is paged separately. Do not repeat a full timeline/actions array
    # on every page or a large attempt becomes impossible to inspect.
    result = {'run': identity, 'index': index, 'checked': checked, 'brief': capture['briefs'].get(attempt['task']),
                      'events': page, 'next_after': after + len(page) if after + len(page) < len(events) else None,
                      'total_events': len(events), 'source': '#run/' + identity,
                      'note': 'Events are matched by the recorded task/setup. If repetition IDs are absent, individual repetitions cannot be causally isolated.'}
    if len(json.dumps(result, ensure_ascii=False, default=str)) > 55000:
        return _packet_page(genesis, state, index, packet, {})
    with genesis.lock:
        current = _state(genesis, identity)
        if current['id'] == state['id'] and current['stage'] == 'analysis' and _entry(current, 'analysis')['id'] == getattr(genesis.context, 'turn', None):
            read = current['reads'].setdefault(str(index), [])
            current['reads'][str(index)] = sorted(set(read) | {e['id'] for e in page})
            _save(genesis, current)
    return result


def read_state(genesis, payload):
    identity = payload.get('run'); _scope_read(genesis, identity)
    state = _state(genesis, identity)
    if not state:
        raise ValueError('Start author_report before reading its frozen world state.')
    packet = _snapshot(genesis, state)
    index = payload.get('attempt')
    if type(index) is not int or not 0 <= index < state['attempt_count']:
        raise ValueError('Choose an attempt index from the overview.')
    from wb_studio.report_state import page
    return _bounded(page(packet.get('snapshots', []), packet['checked']['attempts'][index], payload))


def _text(payload, fields, max_chars=14000):
    out = {}
    for key in fields:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > max_chars:
            raise ValueError(key + ' must contain a complete, nonempty explanation within ' + str(max_chars) + ' characters.')
        out[key] = value.strip()
    return out


def _citations(ids, valid, allow_empty=False):
    if not isinstance(ids, list) or (not ids and not allow_empty) or any(type(i) is not int or i not in valid for i in ids):
        raise ValueError('Citations must belong to the assigned evidence and include the basis for the claim.')
    return list(dict.fromkeys(ids))


def record_attempt(genesis, payload):
    with genesis.lock:
        state = _worker(genesis, payload.get('run'), ('analysis',))
        attempts = _snapshot(genesis, state)['checked']['attempts']; index = payload.get('index')
        if type(index) is not int or not 0 <= index < len(attempts):
            raise ValueError('Choose an attempt index from the evidence packet.')
        if index not in _entry(state, 'analysis').get('indexes', range(len(attempts))):
            raise ValueError('This attempt belongs to another analysis batch.')
        original = attempts[index]
        if str(index) not in state['reads'] or set(original['event_ids']) - set(state['reads'][str(index)]):
            raise ValueError('Read every event page for this attempt before recording its analysis.')
        item = _text(payload, ATTEMPT_FIELDS)
        if item['confidence'] not in ('limited', 'moderate', 'strong'):
            raise ValueError('Confidence is limited, moderate or strong; it describes the evidence, not causal proof.')
        if len(json.dumps(item, ensure_ascii=False)) > 30000:
            raise ValueError('Keep this attempt analysis within 30,000 characters so it can be reviewed as one page.')
        item.update(index=index, task=original['task'], model=original['model'], passed=original['passed'],
                    event_ids=_citations(payload.get('event_ids'), set(original['event_ids']), allow_empty=not original['event_ids']))
        path = _workdir(genesis, state) / 'attempts.json'
        rows = _read(path, {}); rows[str(index)] = item; write_json(path, rows)
        state['covered'] = len(rows); _save(genesis, state)
        return item


def read_draft(genesis, payload):
    identity = payload.get('run'); _scope_read(genesis, identity)
    state = _state(genesis, identity)
    if not state:
        return {'run': identity, 'stage': 'none', 'published': published(genesis.studio, identity)}
    folder = _workdir(genesis, state)
    rows = _read(folder / 'attempts.json', {})
    offset, limit = payload.get('after', 0), payload.get('limit', 20)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('Use a nonnegative after offset and limit from 1 to 20.')
    items = [rows[k] for k in sorted(rows, key=int)]
    selected = items[offset:offset + limit]
    result = {'run': identity, 'stage': state['stage'], 'draft': _read(folder / 'draft.json'),
              'draft_sha256': state.get('draft_sha256'), 'evidence_sha256': state['evidence_sha256'],
              'review': state.get('review'), 'attempts': selected, 'total_attempts': len(items)}
    while len(selected) > 1 and len(json.dumps(result, ensure_ascii=False, default=str)) > 54500:
        selected.pop()
    result['next_after'] = offset + len(selected) if offset + len(selected) < len(items) else None
    result = _bounded(result)
    with genesis.lock:
        current = _state(genesis, identity)
        stage = current['stage']
        if stage in STAGES and _entry(current, stage)['id'] == getattr(genesis.context, 'turn', None):
            reads = current.setdefault('draft_reads', {}).setdefault(stage, [])
            current['draft_reads'][stage] = sorted(set(reads) | {a['index'] for a in selected})
            _save(genesis, current)
    return result


def write_draft(genesis, payload):
    with genesis.lock:
        state = _worker(genesis, payload.get('run'), ('author', 'repair'))
        if set(state.get('draft_reads', {}).get(state['stage'], [])) != set(range(state['attempt_count'])):
            raise ValueError('Read every page of the attempt analysis before writing the report.')
        data = _text(payload, TEXT_FIELDS)
        if len(data['summary']) > 1200:
            raise ValueError('Keep the opening within 1,200 characters; put full analysis in why and the findings.')
        findings = payload.get('findings')
        if not isinstance(findings, list) or not 1 <= len(findings) <= 12:
            raise ValueError('Provide one to twelve prioritized, cited findings.')
        valid = {e['id'] for e in _snapshot(genesis, state)['events']}
        checked = []
        for f in findings:
            if not isinstance(f, dict): raise ValueError('A finding is an object.')
            item = _text(f, ('title', 'explanation'))
            if f.get('kind') not in ('fact', 'hypothesis'):
                raise ValueError('Label each finding fact or hypothesis.')
            item.update(kind=f['kind'], event_ids=_citations(f.get('event_ids'), valid, allow_empty=not valid))
            checked.append(item)
        data['findings'] = checked
        if len(json.dumps(data, ensure_ascii=False)) > 20000:
            raise ValueError('Keep the report synthesis within 20,000 characters; detailed attempt analysis is already retained separately.')
        state['revision'] += 1
        state['draft_sha256'] = _hash({'draft': data, 'analysis': _read(_workdir(genesis, state) / 'attempts.json')})
        folder = _workdir(genesis, state)
        write_json(folder / ('draft-' + str(state['revision']) + '.json'), data)
        write_json(folder / 'draft.json', data); _save(genesis, state)
        return data


def ON_TURN(genesis, turn):
    stage = role(turn)
    if stage not in STAGES:
        return
    identity = turn['purpose'].split(':')[1]
    with genesis.lock:
        state = _state(genesis, identity)
        if not state or state['stage'] != stage or _entry(state, stage)['id'] != turn['id'] or turn['id'] in state['processed']:
            return
        state['processed'].append(turn['id'])
        try:
            if turn['status'] != 'completed':
                raise ValueError('The ' + stage + ' turn did not finish; inspect its retained response and billing.')
            if _fingerprint(_capture(genesis.studio, identity)) != state['evidence_sha256']:
                raise ValueError('The evidence changed during authoring; the draft cannot publish.')
            folder = _workdir(genesis, state)
            if stage == 'analysis':
                rows = _read(folder / 'attempts.json', {})
                assigned = _entry(state, 'analysis').get('indexes', range(state['attempt_count']))
                if any(str(i) not in rows for i in assigned):
                    raise ValueError('Attempt coverage is incomplete; every assigned success and failure must be analyzed.')
                if state.get('analysis_cursor', 0) + 1 < len(state.get('analysis_keys', ['analysis'])):
                    state['analysis_cursor'] += 1
                    _dispatch(genesis, state, 'analysis')
                else:
                    if set(rows) != {str(i) for i in range(state['attempt_count'])}:
                        raise ValueError('Attempt coverage is incomplete; all batches must finish.')
                    _dispatch(genesis, state, 'author')
            elif stage in ('author', 'repair'):
                data = _read(folder / 'draft.json')
                if not data or _hash({'draft': data, 'analysis': _read(folder / 'attempts.json')}) != state.get('draft_sha256'):
                    raise ValueError('Genesis did not save a complete report draft.')
                if stage == 'repair' and state['revision'] <= state.get('review_revision', 0):
                    raise ValueError('Genesis did not save a revised draft after review.')
                _dispatch(genesis, state, 'review' if stage == 'author' else 'review_again')
            else:
                if set(state.get('draft_reads', {}).get(stage, [])) != set(range(state['attempt_count'])):
                    raise ValueError('The reviewer did not read every page of the complete analysis.')
                judged = json.loads(turn.get('answer') or '')
                if len(json.dumps(judged, ensure_ascii=False)) > 4000:
                    raise ValueError('Keep review feedback within 4,000 characters so every draft page remains readable.')
                if (not isinstance(judged, dict) or judged.get('verdict') not in ('accept', 'revise', 'reject') or
                    not isinstance(judged.get('issues'), list) or any(not isinstance(i, str) or not i.strip() for i in judged['issues']) or
                    not isinstance(judged.get('reason'), str) or not judged['reason'].strip()):
                    raise ValueError('The reviewer did not return a complete review.')
                if judged.get('draft_sha256') != state.get('draft_sha256') or judged.get('evidence_sha256') != state['evidence_sha256']:
                    raise ValueError('The review does not match this draft and evidence.')
                data = _read(folder / 'draft.json')
                if _hash({'draft': data, 'analysis': _read(folder / 'attempts.json')}) != state['draft_sha256']:
                    raise ValueError('The draft changed after it was sent for review.')
                state['review'] = judged; state['review_revision'] = state['revision']
                write_json(folder / (stage + '.json'), judged)
                if judged['verdict'] == 'revise' and stage == 'review':
                    _dispatch(genesis, state, 'repair')
                elif judged['verdict'] != 'accept' or judged['issues']:
                    raise ValueError('Report review is unresolved: ' + judged['reason'])
                else:
                    rows = _read(folder / 'attempts.json')
                    publication = {**data, 'status': 'completed', 'run': identity, 'revision': state['revision'],
                                   'attempts': [rows[k] for k in sorted(rows, key=int)], 'review': judged,
                                   'draft_sha256': state['draft_sha256'], 'evidence_sha256': state['evidence_sha256'],
                                   'turns': state['turns'], 'workflow': state['id'], 'source': '#report/' + identity,
                                   'basis': 'Genesis interpretation, separately reviewed; deterministic verdicts remain authoritative.'}
                    write_json(folder / 'publication.json', publication)
                    write_json(_folder(genesis.studio, identity) / 'report-publication.json', publication)
                    state.update(stage='published', reason='Genesis published the reviewed report inside Studio.')
                    _save(genesis, state); _release_unused(genesis, state)
                    genesis.autonomy.record('report-published', run=identity, report=state['id'], revision=state['revision'])
                    genesis._index([{'kind': 'report', 'id': identity, 'title': data['summary'],
                                     'body': data['why'] + '\n' + data['limitations']}])
        except Exception as exc:
            _fail(genesis, state, str(exc))


def PROMPT(genesis, turn):
    stage = role(turn)
    if stage not in STAGES:
        return ''
    procedure = Path(__file__).with_name('report_procedures') / ('analysis.md' if stage == 'analysis' else 'review.md' if stage.startswith('review') else 'author.md')
    text = '\n\n' + procedure.read_text(encoding='utf8')
    if stage != 'analysis':
        for name in ('editorial.md', 'figures.md'):
            text += '\n\n' + (procedure.parent / name).read_text(encoding='utf8')
    return text


TOOLS = {'author_report': start, 'report_status': status, 'report_evidence': evidence, 'read_report_state': read_state,
         'read_report_draft': read_draft, 'record_report_attempt': record_attempt, 'write_report_draft': write_draft}
