"""Compact, source-addressed evidence for one assigned report analysis batch.

This is a projection, never a new grade. Successful check prose is omitted;
failed checks, exact native action metadata and required full results remain.
Every omission is explicit and the frozen original remains available by index.
"""
import hashlib
import json


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf8')).hexdigest()


def attempt(capture, index, include_required=True):
    source = capture['checked']['attempts'][index]
    out = {key: source[key] for key in (
        'task', 'model', 'episode_id', 'trial', 'passed', 'termination', 'infrastructure',
        'scope_respected', 'invariant_passed', 'unexpected_changes', 'count_violations',
        'error', 'flags', 'receipt_source', 'event_ids') if key in source}
    out.update(index=index, checked_sha256=digest(source))
    checks = source.get('checks') or source.get('requirements', [])
    requirements = {r.get('check_index'): r for r in source.get('requirements', [])}
    out['checks'] = {'total': len(checks), 'passed_indexes': [c.get('check_index', n)
        for n, c in enumerate(checks) if c.get('passed') is True],
        'failed_or_unknown': [{**requirements.get(c.get('check_index'), {}), **c}
            for c in checks if c.get('passed') is not True],
        'source_sha256': digest(checks), 'success_detail': 'Omitted; full checked evidence is available by attempt index.'}
    # Some historic receipts carry structured scope changes only in changes.
    if source.get('changes') and source['changes'] != source.get('unexpected_changes'):
        out['changes'] = source['changes']
    out['events'] = []
    for event in capture['events']:
        if event.get('id') not in source['event_ids']:
            continue
        # Completion receipts duplicate the check projection above. Preserve
        # all other fields, and identify exactly which repeated fields were cut.
        omitted = [k for k in ('checks', 'check_results', 'requirements') if k in event]
        out['events'].append({'record': {k: v for k, v in event.items() if k not in omitted},
                              'sha256': digest(event), 'omitted_check_fields': omitted})
    native = capture.get('native_traces', [])
    native = native[index] if index < len(native) else {}
    projection = source.get('retained_trace', {})
    out['native'] = {key: projection[key] for key in ('status', 'source', 'sha256', 'note') if key in projection}
    out['native']['events'] = []
    exact = {event['line']: event['record'] for event in native.get('events', [])}
    for event in projection.get('events', []):
        line = event['line']
        raw = exact.get(line)
        if raw is None:
            raise ValueError('The frozen native event index has no exact source record at line ' + str(line) + '.')
        item = {'line': line, 'record_sha256': digest(raw)}
        preview = event.get('result_preview')
        full = not preview or preview.get('complete') or (include_required and event.get('full_read_required'))
        if full:
            item['record'] = raw
            item['complete'] = True
        else:
            item['record'] = event['record']
            item['result_preview'] = {k: preview[k] for k in ('text', 'characters', 'sha256', 'complete')}
            item['complete'] = False
        item['full_read_required'] = bool(event.get('full_read_required'))
        out['native']['events'].append(item)
    out['snapshots'] = [{k: row[k] for k in ('phase', 'trial', 'source') if k in row} |
        {'sha256': digest(row.get('value')), 'contents_read': False}
        for row in capture.get('snapshots', [])
        if source.get('episode_id') and row.get('episode_id') == source['episode_id']]
    return out


def packet(capture, indexes, include_required=True):
    tasks = dict.fromkeys(capture['checked']['attempts'][i]['task'] for i in indexes)
    return {'indexes': indexes,
        'briefs': {task: {'value': capture['briefs'].get(task), 'sha256': digest(capture['briefs'].get(task))} for task in tasks},
        'attempts': [attempt(capture, i, include_required) for i in indexes],
        'projection': 'Task briefs are shared by task. Successful check details and duplicate narratives are omitted. '
            'Every assigned receipt and native action is indexed; required full native records are inline. '
            'Incomplete catalogue previews do not establish absence. Use report_evidence for exact originals or '
            'native_line and read_report_state for snapshot contents; uninspected state remains unknown.'}
