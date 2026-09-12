"""Fill absent legacy summary fields from exact saved episode receipts, read only."""
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def enrich(studio, identity, results):
    directory = getattr(studio, 'directory', None)
    if not isinstance(directory, (str, Path)):
        return results
    database = (Path(directory) / identity / 'results.sqlite3').resolve()
    receipts = defaultdict(list)
    try:
        if not database.is_file():
            return results
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            for episode, task, arm, raw in db.execute(
                    'SELECT episode_id, task_id, arm, row_json FROM episodes WHERE run_id=?', (identity,)):
                receipts[episode].append((task, arm, raw))
    except (OSError, sqlite3.Error):
        return results
    enriched = []
    for original in results:
        row = dict(original)
        enriched.append(row)
        episode = row.get('episode_id')
        matches = receipts.get(episode, []) if episode else []
        if len(matches) != 1:
            continue
        task, arm, raw = matches[0]
        if not isinstance(raw, str):
            continue
        try:
            saved = json.loads(raw)
            if (task, arm) != (row['task'], row['model']) or not isinstance(saved, dict):
                continue
            if any(saved.get(key) != value for key, value in (
                    ('episode_id', episode), ('run_id', identity), ('task_id', task), ('arm', arm))):
                continue
            checks = saved.get('check_results', [])
            if not isinstance(checks, list) or any(not isinstance(c, dict) or not isinstance(c.get('type'), str)
                    or not c['type'] or type(c.get('passed')) is not bool for c in checks):
                continue
            if 'invariant_passed' in saved and type(saved['invariant_passed']) is not bool:
                continue
            if any(not isinstance(saved[key], list) or any(not isinstance(v, dict) for v in saved[key])
                   for key in ('unexpected_changes', 'count_violations') if key in saved):
                continue
        except (ValueError, TypeError):
            continue
        filled = []
        for key in ('invariant_passed', 'unexpected_changes', 'count_violations'):
            if key not in row and key in saved:
                row[key] = saved[key]
                filled.append(key)
        if 'checks' not in row and ('check_results' in saved or 'invariant_passed' in row):
            row['checks'] = [dict(check) for check in checks]
            if type(row.get('invariant_passed')) is bool and not any(c['type'] == 'allowed_changes_only' for c in checks):
                row['checks'].append({'type': 'allowed_changes_only', 'passed': row['invariant_passed']})
            filled.append('checks')
        if filled:
            row['receipt_source'] = {'database': 'results.sqlite3', 'run_id': identity, 'episode_id': episode,
                                     'row_sha256': hashlib.sha256(raw.encode('utf8')).hexdigest(), 'filled': filled}
    return enriched
