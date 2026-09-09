"""Full-run envelopes reserve shared capacity before any request can dispatch."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

import pytest

from wb_orchestrator.budget import BudgetLedger, BudgetExceeded, BudgetConfigurationError, ReservationConflict

MONDAY = datetime(2026, 9, 7, 3, tzinfo=timezone.utc)
NEXT_MONDAY = MONDAY + timedelta(days=7)


def test_full_run_maximum_is_durable_before_any_request(tmp_path):
    path = tmp_path / 'budget.sqlite'
    reservation = BudgetLedger(path).reserve_run('run', '250', metadata={'purpose': 'comparison'}, now=MONDAY)
    reopened = BudgetLedger(path)
    assert reservation.maximum_usd == Decimal('250')
    assert reopened.run_reservation('run') == reservation
    assert reopened.reservations(scope_id='run') == []
    assert reopened.status(now=MONDAY).held_usd == Decimal('250')
    with pytest.raises(BudgetExceeded, match='weekly'):
        reopened.reserve_run('another', '51', now=MONDAY)
    assert reopened.run_reservation('another') is None
    assert reopened.status(now=MONDAY).available_usd == Decimal('50')


def test_cross_ledger_concurrent_runs_cannot_overbook(tmp_path):
    path = tmp_path / 'budget.sqlite'
    BudgetLedger(path)

    def launch(number):
        try:
            BudgetLedger(path).reserve_run(f'run-{number}', '75', now=MONDAY)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted = list(pool.map(launch, range(12)))
    assert sum(admitted) == 4
    assert BudgetLedger(path).status(now=MONDAY).held_usd == Decimal('300')


def test_nested_requests_replace_envelope_hold_and_reuse_only_verified_savings(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve_run('run', '300', now=MONDAY)
    ledger.reserve('first', '100', scope_id='run', scope_limit_usd='300', now=MONDAY)
    ledger.claim('first', now=MONDAY)
    state = ledger.status(now=MONDAY)
    assert (state.held_usd, state.actual_usd, state.available_usd) == (Decimal('300'), Decimal('0'), Decimal('0'))
    ledger.settle('first', '20', now=MONDAY)
    assert ledger.scope_committed('run') == Decimal('20')
    assert ledger.status(now=MONDAY).held_usd == Decimal('280')
    ledger.reserve('retry', '280', scope_id='run', now=MONDAY)
    assert ledger.status(now=MONDAY).committed_usd == Decimal('300')
    with pytest.raises(BudgetExceeded, match='run budget'):
        ledger.reserve('too-large', '.000001', scope_id='run', now=MONDAY)
    ledger.claim('retry', now=MONDAY)
    ledger.settle('retry', None, now=MONDAY)
    assert ledger.status(now=MONDAY).committed_usd == Decimal('300')


def test_cross_ledger_nested_requests_share_run_cap_without_double_counting(tmp_path):
    path = tmp_path / 'budget.sqlite'
    BudgetLedger(path).reserve_run('run', '100', now=MONDAY)
    BudgetLedger(path).reserve_run('other-run', '200', now=MONDAY)

    def request(number):
        try:
            BudgetLedger(path).reserve(f'request-{number}', '25', scope_id='run', now=MONDAY)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted = list(pool.map(request, range(12)))
    assert sum(admitted) == 4
    reopened = BudgetLedger(path)
    assert len(reopened.reservations(scope_id='run')) == 4
    assert reopened.scope_committed('run') == Decimal('100')
    assert reopened.status(now=MONDAY).held_usd == Decimal('300')


def test_finish_releases_only_unused_capacity_and_preserves_unknown_and_unclaimed_requests(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve_run('run', '200', now=MONDAY)
    ledger.reserve('known', '80', scope_id='run', now=MONDAY)
    ledger.claim('known', now=MONDAY)
    ledger.settle('known', '20', now=MONDAY)
    ledger.reserve('unknown', '60', scope_id='run', now=MONDAY)
    ledger.claim('unknown', now=MONDAY)
    ledger.settle('unknown', None, now=MONDAY)
    ledger.reserve('unclaimed', '30', scope_id='run', now=MONDAY)
    closed = ledger.finish_run('run', now=MONDAY)
    assert closed.closed_at == MONDAY.isoformat()
    assert ledger.finish_run('run', now=NEXT_MONDAY) == closed
    state = BudgetLedger(path).status(now=MONDAY)
    assert (state.actual_usd, state.held_usd, state.available_usd) == (Decimal('20'), Decimal('90'), Decimal('190'))
    with pytest.raises(ReservationConflict, match='closed'):
        ledger.claim('unclaimed', now=MONDAY)
    with pytest.raises(ReservationConflict, match='closed'):
        ledger.reserve('new', '1', scope_id='run', now=MONDAY)
    ledger.settle('unknown', '50', now=MONDAY)
    ledger.settle('unclaimed', '0', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('0')
    assert ledger.status(now=MONDAY).actual_usd == Decimal('70')


def test_cancelled_run_with_no_requests_releases_entire_hold_and_cannot_reopen(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve_run('cancelled', '300', now=MONDAY)
    closed = ledger.finish_run('cancelled', now=MONDAY)
    assert ledger.status(now=MONDAY).available_usd == Decimal('300')
    assert ledger.reserve_run('cancelled', '300', now=MONDAY) == closed
    with pytest.raises(ReservationConflict, match='closed'):
        ledger.reserve('late', '1', scope_id='cancelled', now=MONDAY)


def test_run_identity_is_immutable_and_duplicate_requests_cannot_move_between_envelopes(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    first = ledger.reserve_run('run', '100', metadata={'version': 'a'}, now=MONDAY)
    assert ledger.reserve_run('run', '100', metadata={'version': 'a'}, now=NEXT_MONDAY) == first
    for amount, metadata in [('101', {'version': 'a'}), ('100', {'version': 'b'})]:
        with pytest.raises(ReservationConflict):
            ledger.reserve_run('run', amount, metadata=metadata, now=MONDAY)
    ledger.reserve_run('other', '100', now=MONDAY)
    child = ledger.reserve('child', '10', scope_id='attempt', run_id='run', now=MONDAY)
    assert ledger.reserve('child', '10', scope_id='attempt', run_id='run', now=MONDAY) == child
    with pytest.raises(ReservationConflict, match='different run'):
        ledger.reserve('child', '10', scope_id='attempt', run_id='other', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('200')


def test_explicit_nested_scopes_share_parent_cap_and_keep_their_own_caps(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    with pytest.raises(BudgetConfigurationError, match='before'):
        ledger.reserve('early', '1', scope_id='attempt', run_id='missing', now=MONDAY)
    ledger.reserve_run('run', '100', now=MONDAY)
    ledger.reserve('a', '60', scope_id='attempt-a', run_id='run', scope_limit_usd='70', now=MONDAY)
    with pytest.raises(BudgetExceeded, match='scope'):
        ledger.reserve('scope-overflow', '11', scope_id='attempt-a', run_id='run', now=MONDAY)
    with pytest.raises(BudgetExceeded, match='run'):
        ledger.reserve('run-overflow', '41', scope_id='attempt-b', run_id='run', now=MONDAY)
    ledger.reserve('b', '40', scope_id='attempt-b', run_id='run', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('100')
    assert ledger.scope_committed('run') == Decimal('100')
    assert ledger.scope_committed('attempt-a') == Decimal('60')


def test_weekly_rollover_carries_unused_and_unknown_liability_without_carrying_spent_capacity(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve_run('run', '200', now=MONDAY)
    ledger.reserve('known', '100', scope_id='run', now=MONDAY)
    ledger.claim('known', now=MONDAY)
    ledger.settle('known', '50', now=MONDAY)
    ledger.reserve('unknown', '70', scope_id='run', now=MONDAY)
    ledger.claim('unknown', now=MONDAY)
    ledger.settle('unknown', None, now=MONDAY)
    state = ledger.status(now=NEXT_MONDAY)
    assert (state.actual_usd, state.held_usd, state.carried_held_usd) == (Decimal('0'), Decimal('150'), Decimal('150'))
    assert state.available_usd == Decimal('150')
    ledger.finish_run('run', now=NEXT_MONDAY)
    assert ledger.status(now=NEXT_MONDAY).held_usd == Decimal('70')
    ledger.settle('unknown', '60', now=NEXT_MONDAY)
    assert ledger.status(now=MONDAY).actual_usd == Decimal('110')
    assert ledger.status(now=NEXT_MONDAY).actual_usd == Decimal('60')
    assert ledger.status(now=NEXT_MONDAY + timedelta(days=7)).available_usd == Decimal('300')


def test_first_request_after_rollover_uses_already_reserved_run_capacity(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve_run('delayed', '300', now=MONDAY)
    ledger.reserve('request', '300', scope_id='delayed', now=NEXT_MONDAY)
    ledger.claim('request', now=NEXT_MONDAY)
    ledger.settle('request', '90', now=NEXT_MONDAY)
    ledger.finish_run('delayed', now=NEXT_MONDAY)
    assert ledger.status(now=MONDAY).actual_usd == Decimal('0')
    assert ledger.status(now=NEXT_MONDAY).actual_usd == Decimal('90')


def test_child_overrun_remains_recorded_and_blocks_all_new_admission_after_close(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve_run('run', '100', now=MONDAY)
    ledger.reserve('request', '10', scope_id='run', now=MONDAY)
    ledger.claim('request', now=MONDAY)
    ledger.settle('request', '11', now=MONDAY)
    ledger.finish_run('run', now=MONDAY)
    assert ledger.status(now=NEXT_MONDAY).overrun_ids == ('request',)
    with pytest.raises(BudgetExceeded, match='overrun'):
        ledger.reserve_run('another', '1', now=NEXT_MONDAY)
    with pytest.raises(BudgetExceeded, match='overrun'):
        ledger.reserve('legacy', '1', scope_id='legacy', now=NEXT_MONDAY)


def test_run_adopts_existing_exact_scope_holds_without_double_counting(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('prior', '80', scope_id='run', scope_limit_usd='100', now=MONDAY)
    ledger.reserve_run('run', '100', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('100')
    ledger.finish_run('run', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('80')
    with pytest.raises(ReservationConflict, match='closed'):
        ledger.claim('prior', now=MONDAY)


def test_schema_upgrade_preserves_legacy_requests_and_marks_envelope_accounting_version(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('legacy', '70', scope_id='legacy', now=MONDAY)
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TABLE budget_run_requests')
        connection.execute('DROP TABLE budget_run_reservations')
        connection.execute('UPDATE budget_policy SET schema_version=2')
    reopened = BudgetLedger(path)
    reopened.reserve_run('new-run', '230', now=MONDAY)
    assert reopened.status(now=MONDAY).held_usd == Decimal('300')
    assert reopened.reservations()[0].reservation_id == 'legacy'
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT schema_version FROM budget_policy').fetchone()[0] == 3


@pytest.mark.parametrize('value', ['-1', 'NaN', '0.0000001', True, 0.1, None])
def test_invalid_run_maximum_never_creates_envelope(tmp_path, value):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    with pytest.raises(ValueError):
        ledger.reserve_run('run', value, now=MONDAY)
    assert ledger.run_reservation('run') is None
    assert ledger.status(now=MONDAY).held_usd == Decimal('0')


def test_envelope_actions_cannot_backdate_creation(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve_run('run', '10', now=NEXT_MONDAY)
    with pytest.raises(ValueError, match='before'):
        ledger.reserve('child', '1', scope_id='run', now=MONDAY)
    with pytest.raises(ValueError, match='before'):
        ledger.finish_run('run', now=MONDAY)
    assert ledger.run_reservation('run').closed_at is None
    assert ledger.status(now=NEXT_MONDAY).held_usd == Decimal('10')



def test_concurrent_close_and_claim_preserve_request_liability(tmp_path):
    import threading
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve_run('run', '100', now=MONDAY)
    ledger.reserve('request', '10', scope_id='run', now=MONDAY)
    ready = threading.Barrier(2)

    def claim():
        client = BudgetLedger(path)
        ready.wait(timeout=3)
        try:
            client.claim('request', now=MONDAY)
            return True
        except ReservationConflict:
            return False

    def close():
        client = BudgetLedger(path)
        ready.wait(timeout=3)
        return client.finish_run('run', now=MONDAY)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = pool.submit(claim)
        closed = pool.submit(close)
        assert closed.result(timeout=5).closed_at == MONDAY.isoformat()
        did_claim = claimed.result(timeout=5)
    row = ledger.reservations(scope_id='run')[0]
    assert row.dispatched_at == (MONDAY.isoformat() if did_claim else None)
    assert ledger.status(now=MONDAY).held_usd == Decimal('10')
    with pytest.raises(ReservationConflict):
        ledger.claim('request', now=MONDAY)
