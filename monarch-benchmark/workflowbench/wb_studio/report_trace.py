"""Read retained native tool events by exact episode identity, without grading."""
import hashlib
import json
import sqlite3
from pathlib import Path


def capture(studio, job):
    folder = (Path(studio.directory) / job['id']).resolve()
    database = folder / 'results.sqlite3'
    sources = {}
    if database.exists():
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            rows = db.execute('''SELECT e.episode_id, a.uri FROM episodes e
                JOIN artifacts a ON e.episode_id=a.episode_id
                WHERE e.run_id=? AND a.kind='events' ''', (job['id'],)).fetchall()
        for episode, uri in rows:
            sources.setdefault(episode, []).append(uri)
    out = []
    for result in job['results']:
        episode = result.get('episode_id')
        paths = list(dict.fromkeys(sources.get(episode, []))) if episode else []
        item = {'episode_id': episode, 'status': 'unavailable',
                'note': 'No unique retained native event file is registered for this exact episode.'}
        if len(paths) == 1:
            path = Path(paths[0]).resolve()
            if path.is_relative_to(folder):
                item['source'] = path.relative_to(folder).as_posix()
                try:
                    raw = path.read_bytes()
                    events = [{'line': n, 'record': json.loads(line)} for n, line in
                              enumerate(raw.decode('utf8').splitlines(), 1) if line.strip()]
                    item.update(status='available', sha256=hashlib.sha256(raw).hexdigest(), events=events,
                                note='Unmodified retained native events. Cite the episode result and source line; a recorded tool response alone does not prove the requested final state.')
                except (OSError, ValueError):
                    item['note'] = 'The registered event file cannot be read as complete JSON lines.'
            else:
                item['note'] = 'The registered event file is outside this run evidence directory.'
        out.append(item)
    return out


def project(native):
    """Index every source line, preserving action metadata and marking bounded previews."""
    out = {key: value for key, value in native.items() if key != 'events'}
    out['projection'] = 'Complete native event index; result previews explicitly identify omitted characters. Read native_line for the exact retained record.'
    out['events'] = []
    for event in native.get('events', []):
        record = event['record']
        item = {'line': event['line'], 'record': {k: v for k, v in record.items() if k != 'result'}}
        if 'result' in record:
            serialized = json.dumps(record['result'], ensure_ascii=False, sort_keys=True)
            limit = 96 if record.get('tool') == 'api_search' else 1200
            complete = len(serialized) <= limit
            item['result_preview'] = {'text': serialized[:limit], 'characters': len(serialized),
                'sha256': hashlib.sha256(serialized.encode('utf8')).hexdigest(), 'complete': complete,
                'encoding': 'Canonical JSON result; preview may end inside a value.'}
            error = record.get('status') not in (None, 'completed', 'success', 'ok') or (
                isinstance(record['result'], dict) and bool(record['result'].get('error')))
            item['full_read_required'] = not complete and (record.get('tool') != 'api_search' or error)
        out['events'].append(item)
    return out


def line_page(native, line, after=0, limit=24000):
    """Lossless canonical JSON of one frozen native record; line is the source line."""
    if type(line) is not int or line < 1 or type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 24000:
        raise ValueError('Use a positive native_line, a nonnegative character offset and limit from 1 to 24000.')
    event = next((event for event in native.get('events', []) if event['line'] == line), None)
    if event is None:
        raise ValueError('That native source line is not recorded for this exact attempt.')
    serialized = json.dumps(event['record'], ensure_ascii=False, sort_keys=True)
    end = min(after + limit, len(serialized))
    return {'native_line': line, 'source': native.get('source'), 'source_sha256': native.get('sha256'),
        'fragment': serialized[after:end], 'after': after, 'next_after': end if end < len(serialized) else None,
        'total_characters': len(serialized), 'record_sha256': hashlib.sha256(serialized.encode('utf8')).hexdigest(),
        'note': 'Exact retained record encoded as canonical JSON, without clipping. Continue this native_line until next_after is null.'}
