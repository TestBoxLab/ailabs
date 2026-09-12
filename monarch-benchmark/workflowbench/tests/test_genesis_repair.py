"""Repair tools bind remote authentication to the stored turn, never model arguments."""
import io
import json
from types import SimpleNamespace
from urllib.error import URLError
import pytest
from wb_studio import genesis_repair


SPEC = {'repo': 'lab', 'commit': 'a' * 40, 'change': 'Fix navigation', 'verification': 'Open each page'}


@pytest.fixture
def repair(monkeypatch):
    calls = []
    g = SimpleNamespace(context=SimpleNamespace(turn='turn-1'), read=lambda *args: {'by': 'human:lucas'})
    monkeypatch.setenv('GENESIS_REPAIR_URL', 'https://recovery.example')
    monkeypatch.setenv('GENESIS_REPAIR_ACTOR_KEYS', json.dumps({'human:lucas': 'x' * 40}))
    def open_request(request, timeout):
        calls.append(request)
        return io.BytesIO(json.dumps({'id': 'repair_' + 'a' * 32, 'state': 'queued'}).encode())
    monkeypatch.setattr(genesis_repair, 'build_opener', lambda *args: SimpleNamespace(open=open_request))
    return g, calls


def test_same_repair_uses_same_idempotency_key_and_authenticated_actor(repair):
    g, calls = repair
    first = genesis_repair.request_repair(g, SPEC)
    second = genesis_repair.request_repair(g, SPEC)
    assert first == second and first['state'] == 'queued'
    assert calls[0].get_header('Idempotency-key') == calls[1].get_header('Idempotency-key')
    assert calls[0].get_header('Authorization') == 'Bearer ' + 'x' * 40
    assert json.loads(calls[0].data) == {'spec': SPEC}
    genesis_repair.repair_status(g, {'job': first['id']})
    assert calls[-1].full_url == 'https://recovery.example/jobs/' + first['id']
    assert calls[-1].data is None


def test_actor_override_unknown_person_and_arbitrary_job_url_refuse(repair):
    g, calls = repair
    with pytest.raises(ValueError, match='Unsupported'):
        genesis_repair.request_repair(g, {**SPEC, 'actor': 'human:other'})
    g.read = lambda *args: {'by': 'human:other'}
    with pytest.raises(ValueError, match='this person'):
        genesis_repair.request_repair(g, SPEC)
    with pytest.raises(ValueError, match='job ID'):
        genesis_repair.repair_status(g, {'job': 'https://attacker.example'})
    assert calls == []


def test_unknown_acceptance_retains_retry_identity(repair, monkeypatch):
    g, calls = repair
    def unavailable(request, timeout):
        calls.append(request)
        raise URLError('socket closed')
    monkeypatch.setattr(genesis_repair, 'build_opener', lambda *args: SimpleNamespace(open=unavailable))
    for _ in range(2):
        with pytest.raises(ValueError, match='Acceptance is unknown'):
            genesis_repair.request_repair(g, SPEC)
    assert calls[0].get_header('Idempotency-key') == calls[1].get_header('Idempotency-key')


def test_genesis_dispatch_and_terminal_status_share_one_original_reservation(tmp_path, monkeypatch):
    import threading
    import hashlib
    from decimal import Decimal
    from wb_repair.jobs import JobStore
    from wb_repair.grants import verify
    from wb_orchestrator.budget import BudgetLedger
    store = JobStore(tmp_path / 'remote.sqlite3')
    ledger = BudgetLedger(tmp_path / 'shared-budget.sqlite3', weekly_limit_usd='3')
    secret = 'funding-secret-for-test-' + 'z' * 32
    monkeypatch.setenv('GENESIS_REPAIR_FUNDING_KEY', secret)
    monkeypatch.setenv('STUDIO_GENESIS_CODEX_USD', '1.00')
    g = SimpleNamespace(root=tmp_path / 'genesis', lock=threading.RLock(), studio=SimpleNamespace(ledger=ledger),
        autonomy=SimpleNamespace(read=lambda: {'paused': False, 'engineer': 'propose'}),
        config=SimpleNamespace(route_for=lambda _: {'id': 'gpt-5.6-sol'}, effort_for=lambda _: 'medium'),
        allowance_allows=lambda cap: (True, None))
    job = store.submit('human:lucas', 'accepted', SPEC)
    def remote(g, path, payload=None, request_key=None):
        if path == '/health':
            return {'execution_enabled': True}
        if path.endswith('/funding'):
            grant = verify(payload['grant'], secret, actor=job['actor'], job=job['id'], spec=SPEC)
            return {'job': job['id'], 'funding': store.authorize(job['id'], job['actor'], grant)}
        return store.read(job['id'], job['actor'])
    monkeypatch.setattr(genesis_repair, 'call', remote)
    one = genesis_repair.start_repair(g, {'job': job['id']})
    two = genesis_repair.start_repair(g, {'job': job['id']})
    assert one == two and ledger.status().committed_usd == Decimal('1')
    assert store.claim('remote-worker', funded_only=True)['id'] == job['id']
    result = {'job': job['id'], 'reservation': one['funding']['reservation'], 'status': 'awaiting_review',
              'changed': True, 'verified': True, 'cost_usd': '0.20',
              'usage': {'prompt_tokens': 20, 'output_tokens': 10}}
    content = b'complete patch\n'
    result['diff_sha256'] = hashlib.sha256(content).hexdigest()
    store.put_patch(job['id'], 'remote-worker', content, result['diff_sha256'])
    store.finish(job['id'], 'remote-worker', 'awaiting_review', result)
    assert genesis_repair.repair_status(g, {'job': job['id']})['result'] == result
    assert genesis_repair.repair_status(g, {'job': job['id']})['result'] == result
    assert ledger.status().committed_usd == Decimal('0.20')


def test_disabled_engineering_does_not_reserve_or_dispatch_repair(tmp_path, monkeypatch):
    from wb_orchestrator.budget import BudgetLedger
    ledger = BudgetLedger(tmp_path / 'budget.sqlite3')
    job = {'id': 'repair_' + 'a' * 32, 'state': 'queued'}
    calls = []
    def remote(*args):
        calls.append(args[1])
        return job
    monkeypatch.setattr(genesis_repair, 'call', remote)
    g = SimpleNamespace(autonomy=SimpleNamespace(read=lambda: {'engineer': 'off'}), studio=SimpleNamespace(ledger=ledger))
    with pytest.raises(ValueError, match='Enable Genesis engineering'):
        genesis_repair.start_repair(g, {'job': job['id']})
    assert calls == ['/jobs/' + job['id']]
    assert ledger.status().committed_microusd == 0
