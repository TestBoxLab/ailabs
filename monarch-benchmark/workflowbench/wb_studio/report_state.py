"""Frozen before/after state for report analysis, read only from this run's artifacts."""
import json
import sqlite3
from pathlib import Path


def capture(studio, identity):
    folder = (Path(studio.directory) / identity).resolve()
    database = folder / 'results.sqlite3'
    if not database.exists():
        return []
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute('''SELECT e.task_id, e.arm, e.trial, a.kind, a.uri, e.episode_id
            FROM episodes e JOIN artifacts a ON e.episode_id=a.episode_id
            WHERE e.run_id=? AND a.kind IN ('snapshot0','snapshot1')
            ORDER BY e.task_id,e.arm,e.trial,a.kind''', (identity,)).fetchall()
    out = []
    for task, model, trial, kind, uri, episode in rows:
        item = {'episode_id': episode, 'task': task, 'model': model, 'trial': trial, 'phase': 'before' if kind == 'snapshot0' else 'after'}
        path = Path(uri)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        if not path.is_relative_to(folder):
            item['unavailable'] = 'The snapshot reference is outside this run evidence directory.'
        else:
            item['source'] = path.relative_to(folder).as_posix()
            try:
                item['value'] = json.loads(path.read_text(encoding='utf8'))
            except (ValueError, OSError):
                item['unavailable'] = 'The recorded snapshot cannot be read as JSON.'
        out.append(item)
    return out


def page(snapshots, attempt, payload):
    matches = [s for s in snapshots if s['task'] == attempt['task'] and s['model'] == attempt['model']]
    if attempt.get('episode_id'):
        matches = [s for s in matches if s.get('episode_id') == attempt['episode_id']]
    phase = payload.get('phase')
    if phase is None:
        return {'snapshots': [{k: v for k, v in s.items() if k != 'value'} for s in matches],
                'status': 'available' if any('value' in s for s in matches) else 'unavailable',
                'note': 'Choose a phase and the recorded trial. A result without a trial ID cannot identify a repetition by guesswork.'}
    if phase not in ('before', 'after'):
        raise ValueError('Snapshot phase is before or after.')
    candidates = [s for s in matches if s['phase'] == phase and (payload.get('trial') is None or s['trial'] == payload['trial'])]
    if not candidates:
        return {'status': 'unavailable', 'reason': 'No matching snapshot was retained.'}
    if len(candidates) != 1:
        raise ValueError('Several repetitions have snapshots; choose an explicit recorded trial.')
    chosen = candidates[0]
    if 'value' not in chosen:
        return {'status': 'unavailable', 'reason': chosen['unavailable']}
    value = chosen['value']; path = payload.get('path', [])
    if not isinstance(path, list) or any(not isinstance(k, str) for k in path):
        raise ValueError('Path is a list of JSON keys or list indexes, never a filesystem path.')
    for key in path:
        try:
            value = value[int(key)] if isinstance(value, list) else value[key]
        except (IndexError, KeyError, TypeError, ValueError):
            raise ValueError('That JSON path is absent from the recorded snapshot.') from None
    after, limit = payload.get('after', 0), payload.get('limit', 10)
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Use a nonnegative offset and a limit from 1 to 100.')
    if isinstance(value, dict):
        # Return keys first: asking for the root must not dump every service.
        keys = list(value)
        content = {'keys': keys[after:after + limit]}; length = len(keys)
    elif isinstance(value, (list, str)):
        content = {'items' if isinstance(value, list) else 'text': value[after:after + limit]}; length = len(value)
    else:
        content = {'value': value}; length = 1
    return {'status': 'available', 'phase': phase, 'trial': chosen['trial'], 'source': chosen['source'],
            'path': path, **content, 'next_after': after + limit if after + limit < length else None,
            'total': length, 'basis': 'Stored world state; interpretation does not change its verdict.'}
