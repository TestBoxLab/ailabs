"""Legacy job summaries read exact saved checker receipts without regrading or writes."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from wb_studio.failure_analysis import analysis
from wb_studio.report_patterns import patterns


def saved_studio(tmp_path, rows, receipts):
    folder = tmp_path / 'run'; folder.mkdir()
    database = folder / 'results.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE episodes(episode_id, run_id, task_id, arm, row_json)')
        db.executemany('INSERT INTO episodes VALUES (?,?,?,?,?)', receipts)
    events = [{'id': i + 10, 'type': 'result', 'task': r['task'], 'model': r['model'], 'episode_id': r['episode_id']}
              for i, r in enumerate(rows)]
    studio = SimpleNamespace(directory=tmp_path, tasks={}, events=lambda _: events,
        job=lambda _: {'id': 'run', 'settings': {'tasks': ['finance.invoice'], 'models': ['monarch']}, 'results': rows})
    return studio, database


def result(episode):
    return {'task': 'finance.invoice', 'model': 'monarch', 'episode_id': episode,
            'passed': False, 'termination': 'completed'}


def receipt(episode, *, run='run', task='finance.invoice', arm='monarch', **overrides):
    data = {'episode_id': episode, 'run_id': run, 'task_id': task, 'arm': arm,
            'check_results': [{'type': 'invoice_total_equals', 'passed': False}], 'invariant_passed': False,
            'unexpected_changes': [{'service': 'invoices', 'path': 'records[id=other].total', 'before': 1, 'after': 2}],
            'count_violations': [{'table': 'invoices', 'actual': 2, 'expected': 1}], **overrides}
    return episode, run, task, arm, json.dumps(data)


def test_exact_receipt_restores_scope_and_requirements_and_retains_event_citations(tmp_path, monkeypatch):
    rows = [result('retry'), result('first')]
    original = deepcopy(rows)
    studio, database = saved_studio(tmp_path, rows, [receipt('first', invariant_passed=True, unexpected_changes=[], count_violations=[]), receipt('retry')])
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    # Patched at the source, not on `wb_studio.reports`: the read path now goes
    # through `report_inputs.saved_rows`, so naming one module would guard nothing.
    monkeypatch.setattr('wb_results.store.Store', lambda *a, **k: pytest.fail('Read-only reporting must not open Store'))
    found = analysis(studio, 'run')['attempts']
    assert [(c['name'], c['passed']) for c in found[0]['checks']] == [('invoice_total_equals', False), ('allowed_changes_only', False)]
    assert [(c['name'], c['passed']) for c in found[1]['checks']] == [('invoice_total_equals', False), ('allowed_changes_only', True)]
    assert found[0]['event_ids'] == [10] and found[1]['event_ids'] == [11]
    assert found[0]['invariant_passed'] is False
    assert found[0]['unexpected_changes'][0]['path'] == 'records[id=other].total'
    assert found[0]['count_violations'] == [{'table': 'invoices', 'actual': 2, 'expected': 1}]
    assert found[0]['receipt_source']['episode_id'] == 'retry'
    assert found[0]['receipt_source']['run_id'] == 'run'
    assert all(f['event_ids'] == [10] for f in found[0]['observed_facts'])
    column = patterns(found, {'monarch': 'Monarch'})['setups'][0]
    slices = {s['id']: s for s in column['checks']}
    assert slices['scope_and_requirements']['count'] == slices['requirements']['count'] == 1
    assert slices['scope_and_requirements']['percent'] == slices['requirements']['percent'] == 50
    assert rows == original
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('bad', ['wrong_run', 'wrong_run_json', 'wrong_episode_json', 'wrong_task', 'wrong_arm', 'malformed_json', 'malformed_blob', 'malformed_checks'])
def test_mismatched_or_malformed_receipt_never_lends_another_attempt_evidence(tmp_path, bad):
    entry = receipt('same')
    if bad == 'wrong_run': entry = receipt('same', run='different-run')
    elif bad == 'wrong_run_json': entry = (*entry[:4], json.dumps({**json.loads(entry[4]), 'run_id': 'different-run'}))
    elif bad == 'wrong_episode_json': entry = (*entry[:4], json.dumps({**json.loads(entry[4]), 'episode_id': 'different'}))
    elif bad == 'wrong_task': entry = receipt('same', task='another.task')
    elif bad == 'wrong_arm': entry = receipt('same', arm='another-version')
    elif bad == 'malformed_json': entry = (*entry[:4], '{')
    elif bad == 'malformed_blob': entry = (*entry[:4], entry[4].encode('utf8'))
    else: entry = receipt('same', check_results=[{'type': 'x', 'passed': 'false'}])
    studio, _ = saved_studio(tmp_path, [result('same'), result('missing')], [entry, receipt('unrelated')])
    attempts = analysis(studio, 'run')['attempts']
    assert [a['checks'] for a in attempts] == [[], []]
    assert [a['event_ids'] for a in attempts] == [[10], [11]]


def test_existing_job_fields_including_empty_checks_are_authoritative(tmp_path):
    row = {**result('same'), 'checks': [], 'invariant_passed': True, 'unexpected_changes': [], 'count_violations': []}
    studio, _ = saved_studio(tmp_path, [row], [receipt('same')])
    found = analysis(studio, 'run')['attempts'][0]
    assert found['checks'] == []
    assert not any(f['source'] == 'result.unexpected_changes' for f in found['observed_facts'])


def test_unreadable_database_keeps_missing_checks_unknown(tmp_path):
    studio, database = saved_studio(tmp_path, [result('same')], [])
    database.write_text('not a SQLite database', encoding='utf8')
    assert analysis(studio, 'run')['attempts'][0]['checks'] == []
