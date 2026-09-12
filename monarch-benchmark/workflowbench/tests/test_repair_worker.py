"""Actual subprocess and HTTP worker behavior, without paid provider calls."""
import json
import os
import sys
import time
from pathlib import Path
import pytest
from tests.test_repair_server import recovery, WORKER, SPEC
from wb_repair.worker import Client, Worker, executor_environment
from wb_repair.grants import fingerprint

SCRIPT = r"""
import hashlib, json, os, sys
from pathlib import Path
job = json.load(sys.stdin)
root = Path(os.environ['GENESIS_REPAIR_JOB_DIR'])
with (root.parent / 'calls.txt').open('a') as out: out.write('called\n')
result = {'job': job['id'], 'reservation': job['funding']['reservation'], 'status': 'awaiting_review',
          'verified': True, 'changed': True, 'cost_usd': '0.10', 'usage': {'prompt_tokens': 10, 'output_tokens': 10}}
patch = b'full patch with more than a preview\n' * 3000
(root / 'artifacts').mkdir()
(root / 'artifacts' / 'change.patch').write_bytes(patch)
result['diff_sha256'] = hashlib.sha256(patch).hexdigest()
(root / 'result.json').write_text(json.dumps(result))
"""


def queued(recovery):
    request, store = recovery
    _, job = request('/jobs', {'spec': SPEC})
    grant = {'version': 1, 'actor': 'lucas', 'job': job['id'], 'spec_sha256': fingerprint(SPEC),
             'scope': 'source-scope', 'reservation': 'source-reservation', 'model': 'gpt-6-astra',
             'effort': 'medium', 'maximum_usd': '2', 'expires': int(time.time()) + 600}
    store.authorize(job['id'], 'lucas', grant)
    return job


def test_worker_runs_subprocess_and_retries_lost_finish_ack_without_reexecution(recovery, tmp_path):
    job = queued(recovery)
    client = Client(recovery[0].root, WORKER)
    original = client.call
    lost = [False]
    def call(operation, payload):
        answer = original(operation, payload)
        if operation == 'finish' and not lost[0]:
            lost[0] = True
            raise ConnectionError('acknowledgement lost after server accepted result')
        return answer
    client.call = call
    worker = Worker(tmp_path, client, command=[sys.executable, '-c', SCRIPT], heartbeat_seconds=.02)
    with pytest.raises(ConnectionError):
        worker.once()
    assert recovery[1].read(job['id'], 'lucas')['state'] == 'awaiting_review'
    assert worker.once() == 'awaiting_review'
    assert (tmp_path / 'calls.txt').read_text().splitlines() == ['called']
    content, digest = recovery[1].patch(job['id'], 'lucas')
    assert content == b'full patch with more than a preview\n' * 3000
    assert digest == recovery[1].read(job['id'], 'lucas')['result']['diff_sha256']
    assert not worker.current.exists()
    assert json.loads((tmp_path / (job['id'] + '.receipt.json')).read_text())['cost_usd'] == '0.10'


def test_lost_claim_response_recovers_same_job_and_token(recovery, tmp_path):
    job = queued(recovery)
    client = Client(recovery[0].root, WORKER)
    original = client.call
    lost = [False]
    claimed = []
    def call(operation, payload):
        response = original(operation, payload)
        if operation == 'claim':
            claimed.append(response['job'])
            if not lost[0]:
                lost[0] = True
                raise ConnectionError('claim response lost')
        return response
    client.call = call
    worker = Worker(tmp_path, client, command=[sys.executable, '-c', SCRIPT], heartbeat_seconds=.02)
    with pytest.raises(ConnectionError):
        worker.once()
    assert worker.once() == 'awaiting_review'
    assert claimed[0] == claimed[1] and claimed[0]['id'] == job['id']
    assert (tmp_path / 'calls.txt').read_text().splitlines() == ['called']


def test_restart_does_not_replay_an_executor_whose_status_is_unknown(recovery, tmp_path):
    queued(recovery)
    client = Client(recovery[0].root, WORKER)
    job = client.call('claim', {'request_key': 'restart-claim'})['job']
    (tmp_path / 'current.json').write_text(json.dumps({'job': job, 'phase': 'dispatching', 'pid': 12345}))
    worker = Worker(tmp_path, client, command=[sys.executable, '-c', 'raise AssertionError("must not restart")'])
    assert worker.once() == 'needs_attention'
    assert recovery[1].read(job['id'], 'lucas')['state'] == 'running'
    assert worker.current.exists()


def test_control_credentials_do_not_cross_executor_environment(monkeypatch, tmp_path):
    for name in ('GENESIS_REPAIR_WORKER_KEY', 'GENESIS_REPAIR_FUNDING_KEY', 'GENESIS_GITHUB_PRIVATE_KEY_FILE', 'GITHUB_TOKEN'):
        monkeypatch.setenv(name, 'must-not-reach-executor')
    monkeypatch.setenv('GENESIS_REPAIR_REPO_LAB', str(tmp_path))
    environment = executor_environment(tmp_path)
    assert 'must-not-reach-executor' not in environment.values()
    assert environment['GENESIS_REPAIR_REPO_LAB'] == str(tmp_path)
    assert environment['GENESIS_REPAIR_JOB_DIR'] == str(tmp_path)


def test_only_one_worker_can_own_a_recovery_directory(tmp_path):
    from wb_repair.worker import exclusive_worker
    with exclusive_worker(tmp_path):
        with pytest.raises(RuntimeError, match='Another worker'):
            with exclusive_worker(tmp_path):
                pytest.fail('concurrent owner entered')
    with exclusive_worker(tmp_path):
        assert (tmp_path / 'worker.lock').exists()
