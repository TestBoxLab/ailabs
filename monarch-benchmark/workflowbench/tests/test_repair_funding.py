"""Remote repair grants spend one allowance held in the original shared ledger."""
from decimal import Decimal
import pytest
from wb_orchestrator.budget import BudgetLedger, BudgetExceeded
from wb_repair.grants import verify, sign, fingerprint
from wb_repair.jobs import JobStore, Conflict
from wb_studio.repair_funding import issue, reconcile

SECRET = 'test-only-signing-key-' + 'x' * 32
SPEC = {'repo': 'lab', 'commit': 'a' * 40, 'change': 'Fix page', 'verification': 'Navigate'}


def fund(ledger, job='repair_one', maximum='2.00'):
    return issue(ledger, actor='human:lucas', job=job, spec=SPEC, maximum_usd=maximum,
                 model='gpt-6-astra', effort='medium', secret=SECRET)


def claims(token, job='repair_one'):
    return verify(token, SECRET, actor='human:lucas', job=job, spec=SPEC)


def test_funding_reserves_once_and_survives_source_restart(tmp_path):
    path = tmp_path / 'budget.sqlite3'
    ledger = BudgetLedger(path, weekly_limit_usd='3')
    first = fund(ledger)
    restarted = BudgetLedger(path, weekly_limit_usd='3')
    assert fund(restarted) == first
    assert restarted.status().committed_usd == Decimal('2')
    assert claims(first)['maximum_usd'] == '2.00'
    with pytest.raises(BudgetExceeded):
        fund(restarted, 'repair_two')
    assert restarted.status().committed_usd == Decimal('2')


def test_grant_cannot_change_actor_job_spec_or_amount(tmp_path):
    token = fund(BudgetLedger(tmp_path / 'budget.sqlite3'))
    for actor, job, spec in [('human:other', 'repair_one', SPEC), ('human:lucas', 'repair_two', SPEC),
                              ('human:lucas', 'repair_one', {**SPEC, 'change': 'Different'})]:
        with pytest.raises(ValueError):
            verify(token, SECRET, actor=actor, job=job, spec=spec)
    with pytest.raises(ValueError, match='signature'):
        claims(token[:-1] + ('a' if token[-1] != 'a' else 'b'))
    expired = {**claims(token), 'expires': 0}
    with pytest.raises(ValueError, match='expired'):
        claims(sign(expired, SECRET))


def test_unknown_remote_cost_keeps_full_liability_after_terminal_receipt(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite3')
    grant = claims(fund(ledger))
    receipt = {'job': 'repair_one', 'reservation': grant['reservation'], 'status': 'interrupted', 'cost_usd': None}
    reconcile(ledger, grant, receipt)
    assert ledger.status().committed_usd == Decimal('2')
    assert grant['reservation'] in ledger.status().unknown_ids
    with pytest.raises(ValueError, match='closed'):
        fund(ledger)


def test_verified_cost_releases_only_unused_reserved_capacity(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite3')
    grant = claims(fund(ledger))
    receipt = {'job': 'repair_one', 'reservation': grant['reservation'], 'status': 'awaiting_review',
               'cost_usd': '0.70', 'usage': {'prompt_tokens': 100, 'output_tokens': 50}}
    reconcile(ledger, grant, receipt)
    assert ledger.status().committed_usd == Decimal('0.70')
    assert ledger.status().held_usd == Decimal('0')


def test_only_funded_jobs_are_claimed_and_reservation_cannot_fund_two_jobs(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite3')
    one = store.submit('human:lucas', 'one', SPEC)
    two = store.submit('human:lucas', 'two', SPEC)
    assert store.claim('worker', funded_only=True) is None
    grant = claims(fund(BudgetLedger(tmp_path / 'budget.sqlite3'), one['id']), one['id'])
    store.authorize(one['id'], 'human:lucas', grant)
    assert store.authorize(one['id'], 'human:lucas', grant) == grant
    with pytest.raises(Conflict):
        store.authorize(two['id'], 'human:lucas', {**grant, 'job': two['id']})
    assert store.claim('worker', funded_only=True)['id'] == one['id']
    assert store.claim('worker', funded_only=True) is None


def test_wrong_receipt_or_missing_usage_cannot_release_reserved_money(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite3')
    grant = claims(fund(ledger))
    for result in [
        {'job': 'another-job', 'reservation': grant['reservation'], 'status': 'failed', 'cost_usd': '0'},
        {'job': grant['job'], 'reservation': grant['reservation'], 'status': 'running', 'cost_usd': '0'},
        {'job': grant['job'], 'reservation': grant['reservation'], 'status': 'failed', 'cost_usd': '0'},
    ]:
        with pytest.raises(ValueError):
            reconcile(ledger, grant, result)
        assert ledger.status().committed_usd == Decimal('2')


def test_expired_funding_does_not_allow_a_worker_to_start(tmp_path):
    store = JobStore(tmp_path / 'jobs.sqlite3')
    job = store.submit('human:lucas', 'one', SPEC)
    grant = claims(fund(BudgetLedger(tmp_path / 'budget.sqlite3'), job['id']), job['id'])
    store.authorize(job['id'], 'human:lucas', grant)
    with store.connection() as db:
        db.execute('UPDATE funding SET expires=0')
    assert store.claim('worker', funded_only=True) is None
    assert store.read(job['id'], 'human:lucas')['state'] == 'queued'
