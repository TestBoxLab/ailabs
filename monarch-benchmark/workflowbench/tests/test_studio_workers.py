"""Trusted worker coordination, scoped RPC, and real offline worker processes."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import contextmanager
from decimal import Decimal
import base64
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import uuid

import pytest

from wb_orchestrator.budget import BudgetExceeded, ReservationConflict
from wb_results.evidence import verify_manifest
from wb_results.store import Store
from wb_studio.app import ROOT, Studio, handler
from wb_studio.coordinator import Coordinator, code_identity, decode, encode
from wb_studio.worker import WorkerClient, RemoteLedger, RemoteRuntime
from wb_studio.gateways import GatewayError
from wb_world.episode import load_suite

TOKEN = 'offline-worker-test-credential-123456'


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDIO_EXECUTION_MODE', 'workers')
    monkeypatch.setenv('STUDIO_WORKER_TOKEN', TOKEN)
    monkeypatch.setenv('STUDIO_WORKER_LEASE_SECONDS', '60')
    monkeypatch.setenv('STUDIO_MAX_RUNS', '2')
    monkeypatch.setenv('STUDIO_MAX_AGENTS', '2')
    monkeypatch.delenv('STUDIO_PROVIDER_LIMITS', raising=False)
    monkeypatch.delenv('STUDIO_AUTH_USER', raising=False)
    monkeypatch.delenv('STUDIO_AUTH_PASSWORD', raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Worker test attempted a paid provider call')
    return Studio(tmp_path / 'server', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=forbidden)


def create(studio, identity='run-one', model='oracle', concurrency=1):
    return studio.create({'request_id': identity, 'models': [model], 'tasks': list(studio.tasks),
                          'maximum_usd': '1', 'concurrency': concurrency})


def claim(studio, worker='worker-one', request_id=None):
    return studio.coordinator.dispatch({'operation': 'claim', 'worker': worker, 'code_sha256': code_identity(),
                                       'request_id': request_id or uuid.uuid4().hex})


def owned(studio, bundle, operation, **payload):
    return studio.coordinator.dispatch({'operation': operation, 'job': bundle['job']['id'],
                                       'claim_token': bundle['token'], 'request_id': uuid.uuid4().hex, **payload})


@contextmanager
def server_for(studio):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(studio))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_worker_mode_enqueues_without_local_dispatch(studio, monkeypatch):
    monkeypatch.setattr('wb_studio.app.threading.Thread', lambda *args, **kwargs: pytest.fail('Local dispatch'))
    job = create(studio)
    assert job['status'] == 'queued'
    assert [event['type'] for event in studio.events(job['id'])] == ['queued']
    with pytest.raises(RuntimeError, match='authenticated worker claims'):
        studio.execute(job['id'])


def test_claim_retries_preserve_identity_and_worker_cannot_claim_two_jobs(studio):
    create(studio)
    create(studio, 'run-two')
    first = claim(studio, request_id='same-request')
    assert claim(studio, request_id='same-request') == first
    assert claim(studio) is None
    second = claim(studio, worker='worker-two')
    assert second['job']['id'] != first['job']['id']
    assert second['token'] != first['token']
    assert {row['state'] for row in studio.coordinator.snapshot()['workers']} == {'active'}


def test_concurrent_claimers_receive_each_job_at_most_once(studio):
    create(studio)
    create(studio, 'run-two')
    fingerprint = code_identity()
    def take(number):
        return studio.coordinator.dispatch({'operation': 'claim', 'worker': f'worker-{number}',
                                           'code_sha256': fingerprint, 'request_id': uuid.uuid4().hex})
    with ThreadPoolExecutor(max_workers=6) as pool:
        admitted = [result for result in pool.map(take, range(6)) if result]
    assert sorted(result['job']['id'] for result in admitted) == ['run-one', 'run-two']


def test_claim_agent_bound_accounts_for_declared_concurrent_agents(studio):
    create(studio, concurrency=2)
    create(studio, 'run-two')
    assert claim(studio)['job']['id'] == 'run-one'
    assert claim(studio, worker='worker-two') is None


def test_mismatched_worker_code_never_claims_a_job(studio):
    create(studio)
    with pytest.raises(ValueError, match='code differs'):
        studio.coordinator.dispatch({'operation': 'claim', 'worker': 'worker', 'code_sha256': 'wrong', 'request_id': 'r'})
    assert studio.coordinator.snapshot()['workers'] == []
    assert studio.job('run-one')['status'] == 'queued'


def test_live_claim_survives_coordinator_restart(studio):
    create(studio)
    bundle = claim(studio)
    running = deepcopy(bundle['job'])
    running['status'] = 'running'
    owned(studio, bundle, 'save', value=running)
    restarted = Studio(studio.directory, tasks=list(studio.tasks.values()), gateway_factory=studio.gateway_factory)
    assert restarted.job('run-one')['status'] == 'running'
    assert owned(restarted, bundle, 'heartbeat') == {'cancelled': False}
    assert claim(restarted, worker='different') is None


def test_lost_heartbeat_interrupts_without_requeue_and_preserves_unknown_admissions(studio):
    create(studio)
    bundle = claim(studio)
    studio.ledger.reserve_run('run-one', '100')
    studio.ledger.reserve('unknown', '10', scope_id='run-one')
    studio.ledger.claim('unknown')
    admission = owned(studio, bundle, 'admit', provider='test')
    with studio.coordinator.transaction() as db:
        db.execute('UPDATE claims SET heartbeat=0 WHERE job=?', ('run-one',))
    assert studio.coordinator.reap() == 1
    assert studio.job('run-one')['status'] == 'interrupted'
    assert claim(studio, worker='replacement') is None
    with pytest.raises(ValueError, match='no longer active'):
        owned(studio, bundle, 'heartbeat')
    assert studio.ledger.status().held_usd == Decimal('100')
    with studio.coordinator.transaction() as db:
        assert db.execute('SELECT released FROM admissions WHERE id=?', (admission['id'],)).fetchone()[0] == 0


def test_queued_cancellation_releases_unallocated_run_budget_without_dispatch(studio):
    create(studio)
    studio.ledger.reserve_run('run-one', '100')
    assert studio.cancel('run-one')['status'] == 'cancelled'
    assert studio.ledger.status().held_usd == Decimal('0')
    assert claim(studio) is None


def test_heartbeat_propagates_cancellation_and_prevents_provider_admission(studio):
    create(studio)
    bundle = claim(studio)
    assert studio.cancel('run-one')['status'] == 'cancelling'
    assert owned(studio, bundle, 'heartbeat') == {'cancelled': True}
    assert owned(studio, bundle, 'admit', provider='test') == {'cancelled': True, 'admitted': False}


def test_worker_cannot_change_frozen_run_settings_or_publish_early_completion(studio):
    create(studio)
    bundle = claim(studio)
    update = deepcopy(bundle['job'])
    update['settings']['maximum_usd'] = '300'
    with pytest.raises(ValueError, match='frozen'):
        owned(studio, bundle, 'save', value=update)
    update = deepcopy(bundle['job'])
    update['status'] = 'completed'
    with pytest.raises(ValueError, match='evidence upload'):
        owned(studio, bundle, 'save', value=update)
    with pytest.raises(ValueError, match='completion operation'):
        owned(studio, bundle, 'event', kind='finished', data={})
    assert studio.job('run-one')['status'] == 'queued'


def test_worker_rpc_requests_are_idempotent_and_ids_bind_payload(studio):
    create(studio)
    bundle = claim(studio)
    payload = {'operation': 'event', 'job': 'run-one', 'claim_token': bundle['token'],
               'request_id': 'event-1', 'kind': 'running', 'data': {}}
    first = studio.coordinator.dispatch(payload)
    assert studio.coordinator.dispatch(payload) == first
    assert [event['type'] for event in studio.events('run-one')] == ['queued', 'running']
    with pytest.raises(ValueError, match='different content'):
        studio.coordinator.dispatch({**payload, 'kind': 'wrong'})


def test_provider_concurrency_is_shared_between_claimed_workers(studio):
    studio.runtime.limits['test'] = {'concurrency': 1, 'requests_per_minute': 2}
    create(studio)
    create(studio, 'run-two')
    one, two = claim(studio), claim(studio, 'worker-two')
    admission = owned(studio, one, 'admit', provider='test')
    assert admission['admitted'] is True
    assert owned(studio, two, 'admit', provider='test') == {'admitted': False}
    owned(studio, one, 'release', id=admission['id'])
    next_admission = owned(studio, two, 'admit', provider='test')
    assert next_admission['admitted'] is True
    owned(studio, two, 'release', id=next_admission['id'])
    assert owned(studio, one, 'admit', provider='test') == {'admitted': False}


@pytest.mark.parametrize('path', ['../secret', '/secret', 'evidence/../../secret', 'evidence\\secret', 'C:/secret', 'results.sqlite3/nested', 'job.json'])
def test_artifact_path_escape_is_rejected(studio, path):
    create(studio)
    bundle = claim(studio)
    with pytest.raises(ValueError, match='artifact|Artifact'):
        owned(studio, bundle, 'artifact', path=path, offset=0, data='', sha256=hashlib.sha256(b'').hexdigest())
    assert studio.job('run-one')['status'] == 'queued'


def test_artifact_retries_compare_existing_bytes_and_completion_needs_inventory(studio):
    create(studio)
    bundle = claim(studio)
    data = b'offline-evidence'
    payload = {'path': 'evidence/sample.txt', 'offset': 0, 'data': base64.b64encode(data).decode(),
               'sha256': hashlib.sha256(data).hexdigest()}
    assert owned(studio, bundle, 'artifact', **payload) == {'written': len(data)}
    assert owned(studio, bundle, 'artifact', **payload) == {'written': len(data)}
    assert (studio.directory / 'run-one/evidence/sample.txt').read_bytes() == data
    with pytest.raises(ValueError, match='differs'):
        owned(studio, bundle, 'artifact', **{**payload, 'data': base64.b64encode(b'changed').decode(), 'sha256': hashlib.sha256(b'changed').hexdigest()})
    with pytest.raises(ValueError, match='inventory'):
        owned(studio, bundle, 'complete', files=[])
    assert studio.job('run-one')['status'] == 'queued'


def test_worker_bearer_auth_is_separate_from_basic_auth_and_browser_csrf(studio, monkeypatch):
    create(studio)
    monkeypatch.setenv('STUDIO_AUTH_USER', 'admin')
    monkeypatch.setenv('STUDIO_AUTH_PASSWORD', 'browser-password')
    with server_for(studio) as url:
        port = int(url.rsplit(':', 1)[1])
        for auth in ['', 'Bearer wrong', 'Basic '+base64.b64encode(b'admin:browser-password').decode()]:
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            connection.request('POST', '/api/worker', '{}', {'Authorization': auth, 'X-Studio-Token': studio.token})
            response = connection.getresponse()
            assert response.status == 401
            assert TOKEN not in response.read().decode()
            connection.close()
        client = WorkerClient(url, TOKEN)
        bundle = client.call('claim', worker='authenticated', code_sha256=code_identity())
        assert bundle['job']['id'] == 'run-one'


def test_remote_ledger_is_scoped_and_reservation_errors_preserve_type(studio):
    create(studio)
    studio.ledger.reserve_run('run-one', '10')
    studio.ledger.reserve('other-request', '1', scope_id='other')
    with server_for(studio) as url:
        client = WorkerClient(url, TOKEN)
        bundle = client.call('claim', worker='ledger-worker', code_sha256=code_identity())
        client.job, client.claim_token = 'run-one', bundle['token']
        ledger = RemoteLedger(client)
        assert ledger.status().held_usd == Decimal('11')
        assert ledger.reserve('own', '10', scope_id='run-one').maximum_usd == Decimal('10')
        with pytest.raises(BudgetExceeded):
            ledger.reserve('over', '1', scope_id='run-one')
        with pytest.raises(ValueError, match='another run'):
            ledger.claim('other-request')
        with pytest.raises(ValueError, match='scope'):
            ledger.reserve('escape', '1', scope_id='other')
        ledger.claim('own')
        with pytest.raises(ReservationConflict):
            ledger.claim('own')
        ledger.settle('own', '3')
        ledger.finish_run('run-one')
        assert studio.ledger.status().held_usd == Decimal('1')
        assert studio.ledger.status().actual_usd == Decimal('3')


@pytest.mark.parametrize('url', ['http://example.com', 'ftp://localhost', 'https://user:password@example.com', 'https://example.com/?token=abc'])
def test_worker_refuses_insecure_or_credential_bearing_urls(url):
    with pytest.raises(ValueError):
        WorkerClient(url, TOKEN)


def test_remote_runtime_timeout_never_dispatches_after_admission_deadline(monkeypatch):
    import wb_studio.worker as worker_module
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(worker_module, 'time', SimpleNamespace(monotonic=lambda: clock.now, sleep=lambda seconds: None))
    calls = []
    def call(operation, **payload):
        calls.append(operation)
        if operation == 'admit':
            clock.now = 12.0
            return {'admitted': True, 'id': 'slot'}
        return {'released': True}
    runtime = RemoteRuntime(SimpleNamespace(call=call), 1, {})
    with pytest.raises(GatewayError) as error:
        with runtime.provider('test', timeout=1):
            pytest.fail('Timed-out request was dispatched')
    assert error.value.kind == 'infra:timeout'
    assert calls == ['admit', 'release']


def test_two_real_worker_processes_finish_offline_jobs_with_portable_verified_evidence(studio, tmp_path):
    create(studio, 'run-one', 'oracle')
    create(studio, 'run-two', 'sloppy')
    work = tmp_path / 'workers'
    work.mkdir()
    processes = []
    with server_for(studio) as url:
        try:
            for number in (1, 2):
                processes.append(subprocess.Popen([sys.executable, '-m', 'wb_studio.worker', '--coordinator', url,
                    '--worker', f'process-{number}', '--once', '--work-dir', str(work)],
                    cwd=ROOT, env={**os.environ, 'STUDIO_WORKER_TOKEN': TOKEN}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=40)
                assert process.returncode == 0, stderr
                results.append(json.loads(stdout.strip().splitlines()[-1]))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
    assert {result['job'] for result in results} == {'run-one', 'run-two'}
    assert {studio.job(identity)['worker'] for identity in ('run-one', 'run-two')} == {'process-1', 'process-2'}
    assert studio.job('run-one')['results'][0]['passed'] is True
    assert studio.job('run-two')['results'][0]['passed'] is False
    for identity in ('run-one', 'run-two'):
        assert studio.job(identity)['status'] == 'completed'
        events = studio.events(identity)
        assert events[-1]['type'] == 'finished'
        assert events[-1]['job']['status'] == 'completed'
        assert len([event for event in events if event['type'] == 'attempt_started']) == 1
        store = Store(studio.directory / identity / 'results.sqlite3')
        try:
            rows = store.episodes(run=identity)['rows']
            assert len(rows) == 1
            for row in rows:
                artifacts = store.artifacts(row['episode_id'])
                assert Path(artifacts['manifest']).is_relative_to(studio.directory / identity)
                assert verify_manifest(artifacts['manifest'], episode_id=row['episode_id'], contract_sha256=row['contract_sha256']) == []
        finally:
            store.close()
    assert {row['state'] for row in studio.coordinator.snapshot()['workers']} == {'finished'}
    assert studio.ledger.reservations() == []


def paid_payload(studio, identity):
    return {'request_id': identity, 'models': ['gemini-3.7-flash'], 'tasks': list(studio.tasks), 'maximum_usd': '10'}


def test_failed_job_creation_releases_only_the_unscheduled_run_envelope(studio, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'offline-placeholder')
    def failed_save(job):
        assert studio.ledger.status().held_usd == Decimal('10')
        raise OSError('offline injected disk error')
    monkeypatch.setattr(studio, 'save', failed_save)
    with pytest.raises(OSError, match='injected'):
        studio.create(paid_payload(studio, 'failed-create'))
    assert studio.ledger.run_reservation('failed-create').closed_at is not None
    assert studio.ledger.status().held_usd == Decimal('0')
    assert studio.jobs() == []
    assert not (studio.directory / 'failed-create').exists()


def test_event_failure_after_durable_queue_save_keeps_the_run_envelope(studio, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'offline-placeholder')
    monkeypatch.setattr(studio, 'emit', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('event disk failure')))
    with pytest.raises(OSError, match='event disk'):
        studio.create(paid_payload(studio, 'queued-without-event'))
    assert studio.job('queued-without-event')['status'] == 'queued'
    assert studio.ledger.run_reservation('queued-without-event').closed_at is None
    assert studio.ledger.status().held_usd == Decimal('10')


def test_atomic_budget_conflict_returns_http_409_without_creating_a_job(studio, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'offline-placeholder')
    def conflict(*args, **kwargs):
        raise BudgetExceeded('shared weekly budget exhausted')
    monkeypatch.setattr(studio.ledger, 'reserve_run', conflict)
    with server_for(studio) as url:
        connection = http.client.HTTPConnection('127.0.0.1', int(url.rsplit(':', 1)[1]), timeout=3)
        connection.request('POST', '/api/jobs', json.dumps(paid_payload(studio, 'conflict')),
                           {'X-Studio-Token': studio.token, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        assert response.status == 409
        assert json.loads(response.read()) == {'error': 'shared weekly budget exhausted'}
        connection.close()
    assert studio.jobs() == []


def test_local_restart_releases_unused_capacity_but_retains_dispatched_unknowns(studio, tmp_path, monkeypatch):
    monkeypatch.setenv('STUDIO_EXECUTION_MODE', 'local')
    monkeypatch.setenv('GEMINI_API_KEY', 'offline-placeholder')
    app = Studio(tmp_path / 'local', tasks=list(studio.tasks.values()), gateway_factory=studio.gateway_factory)
    job = app.create(paid_payload(app, 'interrupted-local'), start=False)
    app.ledger.reserve('dispatched', '3', scope_id=job['id'])
    app.ledger.claim('dispatched')
    job['status'] = 'running'
    app.save(job)
    restarted = Studio(app.directory, tasks=list(studio.tasks.values()), gateway_factory=studio.gateway_factory)
    assert restarted.job(job['id'])['status'] == 'interrupted'
    assert restarted.ledger.run_reservation(job['id']).closed_at is not None
    assert restarted.ledger.status().held_usd == Decimal('3')
    assert restarted.ledger.reservations(scope_id=job['id'])[0].actual_usd is None


@pytest.mark.parametrize('arrival, admitted', [(159.999, False), (160.0, True), (160.001, True)])
def test_coordinator_request_rate_window_expires_at_exact_boundary(studio, monkeypatch, arrival, admitted):
    import wb_studio.coordinator as coordinator_module
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(coordinator_module, 'time', SimpleNamespace(time=lambda: clock.now))
    studio.coordinator.lease_seconds = 3600
    studio.runtime.limits['test'] = {'concurrency': 2, 'requests_per_minute': 2}
    create(studio)
    bundle = claim(studio)
    first = owned(studio, bundle, 'admit', provider='test')
    owned(studio, bundle, 'release', id=first['id'])
    clock.now = 101.0
    second = owned(studio, bundle, 'admit', provider='test')
    owned(studio, bundle, 'release', id=second['id'])
    clock.now = arrival
    assert owned(studio, bundle, 'admit', provider='test')['admitted'] is admitted


def test_expired_claim_cannot_replay_cached_dispatch_acknowledgement(studio):
    create(studio)
    bundle = claim(studio)
    studio.ledger.reserve('request', '1', scope_id='run-one')
    payload = {'operation': 'budget', 'job': 'run-one', 'claim_token': bundle['token'],
               'request_id': 'claim-request', 'method': 'claim', 'args': ['request'], 'kwargs': {}}
    assert decode(studio.coordinator.dispatch(payload)).dispatched_at is not None
    with studio.coordinator.transaction() as db:
        db.execute('UPDATE claims SET heartbeat=0 WHERE job=?', ('run-one',))
    with pytest.raises(ValueError, match='no longer active'):
        studio.coordinator.dispatch(payload)
    assert studio.job('run-one')['status'] == 'interrupted'
    assert studio.ledger.status().held_usd == Decimal('1')


def test_cancelled_run_denies_new_budget_claim_but_allows_unknown_settlement(studio):
    create(studio)
    bundle = claim(studio)
    studio.ledger.reserve('request', '1', scope_id='run-one')
    studio.cancel('run-one')
    with pytest.raises(ReservationConflict, match='cancelled'):
        owned(studio, bundle, 'budget', method='claim', args=['request'], kwargs={})
    result = decode(owned(studio, bundle, 'budget', method='settle', args=['request', None], kwargs={}))
    assert result.actual_usd is None
    assert result.dispatched_at is None
    assert studio.ledger.status().held_usd == Decimal('1')

@pytest.mark.parametrize('arrival, admitted', [(159.999, False), (160.0, True), (160.001, True)])
def test_shared_token_quota_retains_released_usage_until_exact_minute(studio, monkeypatch, arrival, admitted):
    import wb_studio.coordinator as module
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock.now))
    studio.coordinator.lease_seconds = 3600
    studio.runtime.limits['test'] = {'concurrency': 2, 'requests_per_minute': 20, 'tokens_per_minute': 100}
    create(studio)
    create(studio, 'run-two')
    first, second = claim(studio), claim(studio, 'worker-two')
    slot = owned(studio, first, 'admit', provider='test', tokens=70)
    owned(studio, first, 'release', id=slot['id'])
    clock.now = 101.0
    slot = owned(studio, second, 'admit', provider='test', tokens=30)
    assert slot['admitted'] is True
    owned(studio, second, 'release', id=slot['id'])
    assert owned(studio, second, 'admit', provider='test', tokens=1) == {'admitted': False}
    clock.now = arrival
    assert owned(studio, second, 'admit', provider='test', tokens=70)['admitted'] is admitted


@pytest.mark.parametrize('tokens', [-1, True, 1.5, '7', None])
def test_invalid_remote_token_bounds_never_create_admissions(studio, tokens):
    create(studio)
    bundle = claim(studio)
    with pytest.raises(ValueError, match='nonnegative integer'):
        owned(studio, bundle, 'admit', provider='test', tokens=tokens)
    with studio.coordinator.transaction() as db:
        assert db.execute('SELECT count(*) FROM admissions').fetchone()[0] == 0


def test_oversize_remote_request_preserves_gateway_classification_over_http(studio):
    studio.runtime.limits['test'] = {'tokens_per_minute': 100}
    create(studio)
    bundle = claim(studio)
    with server_for(studio) as url:
        client = WorkerClient(url, TOKEN, job='run-one', claim_token=bundle['token'])
        runtime = RemoteRuntime(client, 1, {})
        with pytest.raises(GatewayError) as error:
            with runtime.provider('test', tokens=101):
                pytest.fail('Oversize request dispatched')
    assert error.value.kind == 'infra:rate_limit'
    with studio.coordinator.transaction() as db:
        assert db.execute('SELECT count(*) FROM admissions').fetchone()[0] == 0


def test_simultaneous_worker_token_admissions_share_atomic_pool(studio):
    studio.runtime.limits['test'] = {'concurrency': 2, 'tokens_per_minute': 100}
    create(studio)
    create(studio, 'run-two')
    bundles = [claim(studio), claim(studio, 'worker-two')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda bundle: owned(studio, bundle, 'admit', provider='test', tokens=60), bundles))
    assert sorted(result['admitted'] for result in outcomes) == [False, True]
    with studio.coordinator.transaction() as db:
        assert db.execute('SELECT sum(tokens) FROM admissions').fetchone()[0] == 60


def test_old_admission_schema_migrates_without_refunding_live_slots(studio):
    with studio.coordinator.transaction() as db:
        db.execute('DROP TABLE admissions')
        db.execute('CREATE TABLE admissions(id TEXT PRIMARY KEY,job TEXT,provider TEXT,started REAL,released INTEGER)')
        db.execute("INSERT INTO admissions VALUES('old','old-job','test',100,0)")
    migrated = Coordinator(studio)
    with migrated.transaction() as db:
        row = dict(db.execute('SELECT * FROM admissions').fetchone())
    assert row == {'id': 'old', 'job': 'old-job', 'provider': 'test', 'started': 100, 'released': 0, 'tokens': 0}


def test_snapshot_reports_allocated_capacity_and_idle_worker_inventory(studio, monkeypatch):
    import wb_studio.coordinator as module
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock.now))
    assert claim(studio, 'idle-worker') is None
    create(studio, concurrency=2)
    bundle = claim(studio)
    owned(studio, bundle, 'admit', provider='test', tokens=75)
    state = studio.coordinator.snapshot()
    assert state['active_agents'] == state['allocated_agent_slots'] == 2
    assert state['agent_metric'] == 'allocated'
    assert state['providers'] == [{'provider': 'test', 'concurrency': 2, 'requests_per_minute': 30,
                                  'tokens_per_minute': None, 'active': 1, 'recent_requests': 1, 'reserved_tokens_last_minute': 75}]
    nodes = {node['worker']: node for node in state['worker_nodes']}
    assert nodes['idle-worker']['connected'] is True
    assert nodes['idle-worker']['active_jobs'] == []
    assert nodes['worker-one']['active_jobs'] == ['run-one']
    clock.now = 161.0
    state = studio.coordinator.snapshot()
    assert state['allocated_agent_slots'] == 0
    assert state['providers'][0]['active'] == 1  # Unknown in-flight provider work stays held.
    assert all(node['connected'] is False for node in state['worker_nodes'])

@pytest.mark.parametrize('mode', ['local', 'workers'])
def test_explicit_ledger_path_shares_weekly_budget_across_data_directories(tmp_path, monkeypatch, mode):
    monkeypatch.setenv('STUDIO_EXECUTION_MODE', mode)
    monkeypatch.setenv('STUDIO_WORKER_TOKEN', TOKEN)
    shared = tmp_path / 'canonical' / 'budget.sqlite3'
    monkeypatch.setenv('STUDIO_LEDGER_PATH', str(shared))
    monkeypatch.setenv('STUDIO_DATA_DIR', str(tmp_path / 'preview-one'))
    first = Studio(tasks=[])
    first.ledger.reserve_run('existing-other-launcher', '290')
    monkeypatch.setenv('STUDIO_DATA_DIR', str(tmp_path / 'preview-two'))
    second = Studio(tasks=[])
    assert first.ledger.path == second.ledger.path == shared.resolve()
    assert second.ledger.status().held_usd == Decimal('290')
    with pytest.raises(BudgetExceeded):
        second.ledger.reserve_run('different-launcher', '11')
    assert not (tmp_path / 'preview-two' / 'research' / 'budget.sqlite3').exists()


def test_gateway_test_hook_ignores_shared_ledger_override(tmp_path, monkeypatch):
    canonical = tmp_path / 'must-not-open.sqlite3'
    monkeypatch.setenv('STUDIO_LEDGER_PATH', str(canonical))
    app = Studio(tmp_path / 'isolated', tasks=[], gateway_factory=lambda *a, **k: pytest.fail('Paid call'))
    assert app.ledger.path == (tmp_path / 'isolated' / 'budget.sqlite3').resolve()
    assert not canonical.exists()


def test_worker_pause_gate_blocks_new_tasks_and_stale_progress_cannot_resume(studio):
    job = create(studio)
    studio.pause(job['id'])
    assert claim(studio) is None
    studio.resume(job['id'])
    bundle = claim(studio)
    assert owned(studio, bundle, 'begin_attempt')['admitted'] is True
    studio.pause(job['id'])
    assert owned(studio, bundle, 'begin_attempt') == {'admitted':False, 'cancelled':False}
    owned(studio, bundle, 'save', value=bundle['job'])
    assert studio.job(job['id'])['pause_requested'] is True
    assert studio.job(job['id'])['active_attempts'] == 1
    owned(studio, bundle, 'end_attempt')
    assert studio.job(job['id'])['active_attempts'] == 0
    studio.resume(job['id'])
    assert owned(studio, bundle, 'begin_attempt')['admitted'] is True
    studio.pause(job['id'])
    studio.cancel(job['id'])
    assert owned(studio, bundle, 'begin_attempt') == {'admitted':False, 'cancelled':True}
