import json
import sqlite3
from types import SimpleNamespace

import pytest

from wb_studio.report_state import capture, page


def test_snapshot_access_reads_exact_before_after_values_and_not_foreign_files(tmp_path):
    folder = tmp_path / 'run1'; folder.mkdir()
    before = folder / 'snapshot0.json'; before.write_text(json.dumps({'crm': {'contacts': [{'city': 'Portland'}]}}))
    after = folder / 'snapshot1.json'; after.write_text(json.dumps({'crm': {'contacts': [{'city': 'Denver'}]}}))
    foreign = tmp_path / 'not-run-data.json'; foreign.write_text('"private"')
    with sqlite3.connect(folder / 'results.sqlite3') as db:
        db.execute('CREATE TABLE episodes(episode_id,run_id,task_id,arm,trial)')
        db.execute('CREATE TABLE artifacts(episode_id,kind,uri)')
        db.executemany('INSERT INTO episodes VALUES (?,?,?,?,?)', [('e1','run1','t1','m',0),('e2','run1','t1','m',1)])
        db.executemany('INSERT INTO artifacts VALUES (?,?,?)', [('e1','snapshot0',str(before)),('e1','snapshot1',str(after)),('e2','snapshot1',str(foreign))])
    snapshots = capture(SimpleNamespace(directory=tmp_path), 'run1')
    attempt = {'task': 't1', 'model': 'm'}
    for phase, city in [('before','Portland'),('after','Denver')]:
        result = page(snapshots, attempt, {'phase': phase, 'trial': 0, 'path': ['crm','contacts','0','city'], 'limit': 100})
        assert result['text'] == city and result['next_after'] is None
    denied = page(snapshots, attempt, {'phase':'after','trial':1})
    assert denied['status'] == 'unavailable' and 'private' not in str(snapshots)
    with pytest.raises(ValueError, match='explicit recorded trial'):
        page(snapshots, attempt, {'phase':'after'})


def test_snapshot_root_lists_keys_and_missing_state_stays_unavailable():
    attempt = {'task':'t','model':'m'}
    snapshots = [{**attempt,'trial':0,'phase':'after','source':'snapshot1.json','value':{'a':1,'b':2}}]
    first = page(snapshots,attempt,{'phase':'after','limit':1})
    assert first['keys'] == ['a'] and first['next_after'] == 1
    second = page(snapshots,attempt,{'phase':'after','limit':1,'after':1})
    assert second['keys'] == ['b'] and second['next_after'] is None
    assert page([],attempt,{})['status'] == 'unavailable'


def test_report_capture_isolates_repetitions_without_opening_mutable_store(tmp_path):
    from wb_studio.genesis_reports import account_for
    job = {'id': 'repeat', 'results': [
        {'task': 't', 'model': 'm', 'passed': True, 'termination': 'completed', 'checks': []},
        {'task': 't', 'model': 'm', 'passed': False, 'termination': 'completed', 'checks': []}]}
    events = [{'id': 1, 'task': 't', 'model': 'm', 'type': 'attempt_finished'},
              {'id': 2, 'task': 't', 'model': 'm', 'type': 'attempt_finished'}]
    folder = tmp_path / 'repeat'; folder.mkdir()
    database = folder / 'results.sqlite3'; database.write_bytes(b'No database migration may open this file.')
    studio = SimpleNamespace(directory=tmp_path, tasks={}, job=lambda _: job, events=lambda _: events)
    result = account_for(studio, job, events)
    assert [a['event_ids'] for a in result['attempts']] == [[1], [2]]
    assert [a['passed'] for a in result['attempts']] == [True, False]
    assert database.read_bytes() == b'No database migration may open this file.'
