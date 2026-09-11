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
