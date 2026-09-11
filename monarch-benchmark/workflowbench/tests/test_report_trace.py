import hashlib
import json
import sqlite3
from types import SimpleNamespace

from wb_studio.report_trace import capture


def test_native_trace_keeps_full_responses_and_exact_episode_retry(tmp_path):
    folder = tmp_path / 'run'; folder.mkdir()
    first = folder / 'first.jsonl'; first.write_text(json.dumps({'kind':'tool','sequence':0,'result':'first'}))
    retry = folder / 'retry.jsonl'; retry.write_text(json.dumps({'kind':'tool','sequence':0,'arguments':{'method':'PATCH'},'result':'middle' * 15000}))
    foreign = tmp_path / 'private.jsonl'; foreign.write_text('{"secret":"foreign-sensitive-marker"}')
    with sqlite3.connect(folder / 'results.sqlite3') as db:
        db.execute('CREATE TABLE episodes(episode_id,run_id)')
        db.execute('CREATE TABLE artifacts(episode_id,kind,uri)')
        db.executemany('INSERT INTO episodes VALUES (?,?)',[('e0','run'),('e1','run'),('e2','run'),('other','different')])
        db.executemany('INSERT INTO artifacts VALUES (?,?,?)',[
            ('e0','events',str(first)),('e1','events',str(retry)),('e2','events',str(foreign)),('other','events',str(first))])
    before = hashlib.sha256((folder/'results.sqlite3').read_bytes()).hexdigest()
    rows = capture(SimpleNamespace(directory=tmp_path), {'id':'run','results':[
        {'episode_id':'e1'}, {'episode_id':'e0'}, {'episode_id':'e2'}, {'episode_id':'other'}, {}]})
    assert rows[0]['events'][0] == {'line':1,'record':{'kind':'tool','sequence':0,'arguments':{'method':'PATCH'},'result':'middle'*15000}}
    assert rows[0]['sha256'] == hashlib.sha256(retry.read_bytes()).hexdigest()
    assert rows[1]['events'][0]['record']['result'] == 'first'
    assert [r['status'] for r in rows] == ['available','available','unavailable','unavailable','unavailable']
    assert 'foreign-sensitive-marker' not in str(rows)
    assert hashlib.sha256((folder/'results.sqlite3').read_bytes()).hexdigest() == before
