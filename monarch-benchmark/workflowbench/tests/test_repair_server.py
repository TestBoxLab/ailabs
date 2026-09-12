"""Recovery API remains independent of Studio and binds jobs to authenticated actors."""
import hashlib
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from wb_repair.jobs import JobStore
from wb_repair.server import handler

KEY = 'local-test-recovery-key-' + 'x' * 32
OTHER = 'another-test-recovery-key-' + 'y' * 32
WORKER = 'worker-test-only-key-' + 'z' * 32
SPEC = {'repo': 'lab', 'commit': 'a' * 40, 'change': 'Repair navigation', 'verification': 'Check page navigation in Chrome'}


@pytest.fixture
def recovery(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite3')
    hashes = {actor: hashlib.sha256(key.encode()).hexdigest() for actor, key in [('lucas', KEY), ('other', OTHER)]}
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(store, hashes, 'tested-revision', funding_secret='f' * 40, worker_hash=hashlib.sha256(WORKER.encode()).hexdigest()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, body=None, key=KEY, request_key='request-1'):
        headers = {'Authorization': 'Bearer ' + key, 'Idempotency-Key': request_key, 'Content-Type': 'application/json'}
        req = Request(f'http://127.0.0.1:{server.server_port}' + path,
                      data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)
    request.root = f'http://127.0.0.1:{server.server_port}'
    yield request, store
    server.shutdown()
    server.server_close()
    thread.join(5)


def test_health_and_repair_roundtrip_work_without_studio(recovery):
    request, store = recovery
    status, health = request('/health', key='')
    assert status == 200 and health['revision'] == 'tested-revision'
    status, job = request('/jobs', {'spec': SPEC})
    assert status == 202 and job['state'] == 'queued' and job['actor'] == 'lucas'
    assert request('/jobs', {'spec': SPEC})[1]['id'] == job['id']
    assert request('/jobs/' + job['id'])[1]['payload'] == SPEC
    assert request('/jobs/' + job['id'], key=OTHER)[0] == 404
    assert request('/jobs', {'spec': {**SPEC, 'change': 'Other change'}})[0] == 409
    assert store.claim('worker')['id'] == job['id']


def test_unauthorized_or_forged_actor_cannot_submit(recovery):
    request, store = recovery
    assert request('/jobs', {'spec': SPEC}, key='wrong')[0] == 401
    assert request('/jobs', {'spec': SPEC, 'actor': 'other'})[0] == 400
    assert request('/jobs', {'spec': {**SPEC, 'repo': 'other-owner/secret'}})[0] == 400
    assert request('/jobs', {'spec': {**SPEC, 'commit': 'main'}})[0] == 400
    assert store.claim('worker') is None


def test_recovery_refuses_unconfigured_or_ambiguous_access_keys(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite3')
    for hashes in ({}, {'lucas': 'plaintext'}, {'lucas': 'a' * 64, 'other': 'a' * 64}):
        with pytest.raises(ValueError):
            handler(store, hashes)


def test_funding_endpoint_requires_signed_owner_and_job_specific_allowance(recovery):
    from wb_repair.grants import sign, fingerprint
    import time
    request, store = recovery
    _, job = request('/jobs', {'spec': SPEC})
    claims = {'version': 1, 'actor': 'lucas', 'job': job['id'], 'spec_sha256': fingerprint(SPEC),
              'scope': 'source-scope', 'reservation': 'source-reservation', 'model': 'gpt-6-astra',
              'effort': 'medium', 'maximum_usd': '2.00', 'expires': int(time.time()) + 600}
    path = '/jobs/' + job['id'] + '/funding'
    assert request(path, {'grant': sign(claims, 'wrong-key-' + 'x' * 32)})[0] == 400
    assert store.claim('worker', funded_only=True) is None
    assert request(path, {'grant': sign(claims, 'f' * 40)}, key=OTHER)[0] == 404
    status, receipt = request(path, {'grant': sign(claims, 'f' * 40)})
    assert status == 200 and receipt['funding']['reservation'] == 'source-reservation'
    assert request(path, {'grant': sign(claims, 'f' * 40)})[0] == 200
    assert store.claim('worker', funded_only=True)['id'] == job['id']
    assert store.claim('another-worker', funded_only=True) is None


def test_patch_download_requires_owner_and_exact_immutable_upload(recovery):
    import base64
    request, store = recovery
    _, job = request('/jobs', {'spec': SPEC})
    store.claim('claim-token')
    content = b'diff --git a/file b/file\n' * 5000
    digest = hashlib.sha256(content).hexdigest()
    body = {'job': job['id'], 'claim_token': 'claim-token', 'content': base64.b64encode(content).decode(), 'sha256': digest}
    assert request('/workers/patch', {'job': job['id']}, key=KEY)[0] == 401
    assert request('/workers/patch', {**body, 'claim_token': 'wrong'}, key=WORKER)[0] == 409
    assert request('/workers/patch', {**body, 'sha256': '0' * 64}, key=WORKER)[0] == 400
    assert request('/workers/patch', body, key=WORKER)[0] == 200
    assert request('/workers/patch', body, key=WORKER)[0] == 200
    changed = b'replacement'
    assert request('/workers/patch', {**body, 'content': base64.b64encode(changed).decode(), 'sha256': hashlib.sha256(changed).hexdigest()}, key=WORKER)[0] == 409
    path = '/jobs/' + job['id'] + '/patch'
    assert request(path, key=OTHER)[0] == 404
    with urlopen(Request(request.root + path, headers={'Authorization': 'Bearer ' + KEY}), timeout=5) as response:
        assert response.read() == content
        assert response.headers['Content-Disposition'] == 'attachment; filename="' + job['id'] + '.patch"'
    assert request('/jobs', key=OTHER)[1]['jobs'] == []
    assert [item['id'] for item in request('/jobs')[1]['jobs']] == [job['id']]


def test_review_requires_complete_patch_matching_receipt(recovery):
    request, store = recovery
    _, job = request('/jobs', {'spec': SPEC})
    store.claim('worker')
    with pytest.raises(ValueError, match='complete patch'):
        store.finish(job['id'], 'worker', 'awaiting_review', {'diff_sha256': '0' * 64})
    assert store.read(job['id'], 'lucas')['state'] == 'running'


def test_recovery_page_and_assets_work_without_studio_or_auth(recovery):
    request, _ = recovery
    for path, content_type in [('/', 'text/html'), ('/recovery.js', 'text/javascript'), ('/recovery.css', 'text/css'), ('/regular.woff2', 'font/woff2')]:
        with urlopen(request.root + path, timeout=5) as response:
            assert response.headers.get_content_type() == content_type
            assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
            content = response.read()
            if path == '/':
                assert b'id="repair"' in content and b'Download complete patch' in content
    assert request('/../server.py')[0] == 404
