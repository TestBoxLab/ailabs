"""Independent durable repair acceptance and worker ownership."""
from concurrent.futures import ThreadPoolExecutor
import pytest
import hashlib
from wb_repair.jobs import JobStore, Conflict


def test_duplicate_submission_survives_restart_and_conflicting_reuse_refuses(tmp_path):
    path = tmp_path / 'jobs.sqlite3'
    first = JobStore(path).submit('lucas', 'request-1', {'change': 'Repair navigation'})
    restarted = JobStore(path)
    assert restarted.submit('lucas', 'request-1', {'change': 'Repair navigation'}) == first
    with pytest.raises(Conflict):
        restarted.submit('lucas', 'request-1', {'change': 'Another change'})
    with pytest.raises(KeyError):
        restarted.read(first['id'], 'other-person')
    assert restarted.read(first['id'], 'lucas')['payload'] == {'change': 'Repair navigation'}


def test_concurrent_acceptance_and_claim_execute_a_request_once(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite3')
    with ThreadPoolExecutor(max_workers=6) as pool:
        accepted = list(pool.map(lambda _: store.submit('lucas', 'same', {'change': 'Fix UI'}), range(12)))
        claimed = list(pool.map(lambda i: store.claim(str(i)), range(12)))
    assert len({job['id'] for job in accepted}) == 1
    assert len([job for job in claimed if job]) == 1
    assert store.read(accepted[0]['id'], 'lucas')['state'] == 'running'


def test_running_job_survives_restart_and_old_heartbeat_without_replay(tmp_path):
    path = tmp_path / 'jobs.sqlite3'
    store = JobStore(path)
    job = store.submit('lucas', 'key', {'change': 'Fix UI'})
    store.claim('worker-1')
    with store.connection() as db:
        db.execute('UPDATE jobs SET heartbeat=0 WHERE id=?', (job['id'],))
    restarted = JobStore(path)
    assert restarted.claim('worker-2') is None
    assert restarted.read(job['id'], 'lucas')['state'] == 'running'
    restarted.mark_interrupted(job['id'], 'worker-1', 'Supervisor observed process exit 137')
    assert restarted.claim('worker-2') is None
    assert restarted.read(job['id'], 'lucas')['result']['replay'] is False


def test_only_claiming_worker_can_finish_and_receipt_never_means_published(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite3')
    job = store.submit('lucas', 'key', {'change': 'Fix UI'})
    store.claim('worker-1')
    with pytest.raises(Conflict):
        store.finish(job['id'], 'worker-2', 'awaiting_review', {'verified': True})
    with pytest.raises(ValueError):
        store.finish(job['id'], 'worker-1', 'published', {})
    store.heartbeat(job['id'], 'worker-1')
    content = b'complete patch\n'
    digest = hashlib.sha256(content).hexdigest()
    store.put_patch(job['id'], 'worker-1', content, digest)
    store.finish(job['id'], 'worker-1', 'awaiting_review', {'verified': True, 'commit': 'abc', 'diff_sha256': digest})
    result = store.read(job['id'], 'lucas')
    assert result['state'] == 'awaiting_review' and result['result'] == {'verified': True, 'commit': 'abc', 'diff_sha256': digest}
    with pytest.raises(Conflict):
        store.heartbeat(job['id'], 'worker-1')
    with pytest.raises(Conflict):
        store.finish(job['id'], 'worker-1', 'failed', {})
