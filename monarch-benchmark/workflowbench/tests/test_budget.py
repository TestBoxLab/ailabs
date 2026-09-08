"""Shared budget behavior: persistent holds, exact money, and atomic admission."""
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import multiprocessing

import pytest

from wb_orchestrator.budget import (
    BudgetLedger, BudgetExceeded, BudgetConfigurationError, ReservationConflict,
)

MONDAY = datetime(2026, 9, 7, 3, tzinfo=timezone.utc)
NEXT_MONDAY = datetime(2026, 9, 14, 3, tzinfo=timezone.utc)


def _competing_reservation(args):
    path, number = args
    ledger = BudgetLedger(path)
    try:
        ledger.reserve(str(number), '100', scope_id='parallel', now=MONDAY)
        return True
    except BudgetExceeded:
        return False


def test_concurrent_processes_cannot_overbook(tmp_path):
    path = tmp_path / 'shared.sqlite'
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
        admitted = list(pool.map(_competing_reservation, [(path, n) for n in range(8)]))
    assert sum(admitted) == 3
    assert BudgetLedger(path).status(now=MONDAY).available_usd == Decimal('0')


def test_exact_boundary_and_decimal_accounting(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite', weekly_limit_usd='0.3')
    ledger.reserve('a', Decimal('0.1'), scope_id='s', now=MONDAY)
    ledger.reserve('b', '0.199999', scope_id='s', now=MONDAY)
    assert ledger.status(now=MONDAY).available_microusd == 1
    ledger.reserve('c', '0.000001', scope_id='s', now=MONDAY)
    with pytest.raises(BudgetExceeded):
        ledger.reserve('d', '0.000001', scope_id='s', now=MONDAY)
    assert ledger.status(now=MONDAY).committed_usd == Decimal('0.3')


def test_interruption_reopen_and_unknown_cost_keep_maximum(tmp_path):
    path = tmp_path / 'budget.sqlite'
    BudgetLedger(path).reserve('a', '250', scope_id='s', now=MONDAY)
    ledger = BudgetLedger(path)
    result = ledger.settle('a', None, now=MONDAY)
    assert result.actual_microusd is None
    assert ledger.status(now=MONDAY).held_usd == Decimal('250')
    with pytest.raises(BudgetExceeded):
        ledger.reserve('b', '51', scope_id='s', now=MONDAY)


def test_verified_actual_releases_only_remainder(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('a', '300', scope_id='s', now=MONDAY)
    result = ledger.settle('a', '12.123456', now=MONDAY)
    assert result.actual_microusd == 12_123_456
    state = ledger.status(now=MONDAY)
    assert state.held_microusd == 0
    assert state.actual_usd == Decimal('12.123456')
    assert state.available_usd == Decimal('287.876544')
    assert ledger.settle('a', '12.123456', now=MONDAY) == result
    with pytest.raises(ReservationConflict):
        ledger.settle('a', '11', now=MONDAY)
    with pytest.raises(ReservationConflict):
        ledger.settle('a', None, now=MONDAY)


def test_week_boundary_no_rollover_and_unresolved_liability(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('known', '20', scope_id='s', now=MONDAY)
    ledger.settle('known', '10', now=MONDAY)
    ledger.reserve('unknown', '240', scope_id='s', now=MONDAY)
    before = datetime(2026, 9, 14, 2, 59, 59, tzinfo=timezone.utc)
    assert ledger.status(now=before).available_usd == Decimal('50')
    after = ledger.status(now=NEXT_MONDAY)
    assert after.week_start == '2026-09-14'
    assert after.carried_held_usd == Decimal('240')
    assert after.available_usd == Decimal('60')
    with pytest.raises(BudgetExceeded):
        ledger.reserve('new', '61', scope_id='s', now=NEXT_MONDAY)
    ledger.settle('unknown', '200', now=NEXT_MONDAY)
    assert ledger.status(now=NEXT_MONDAY).available_usd == Decimal('100')
    assert ledger.status(now=NEXT_MONDAY).actual_usd == Decimal('200')
    assert ledger.status(now=MONDAY).actual_usd == Decimal('210')


def test_overspend_is_recorded_and_blocks_even_after_rollover(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('a', '300', scope_id='s', now=MONDAY)
    ledger.settle('a', '301', now=MONDAY)
    state = BudgetLedger(path).status(now=MONDAY)
    assert state.actual_usd == Decimal('301')
    assert state.overrun_ids == ('a',)
    assert state.blocked is True
    assert state.available_usd == Decimal('0')
    with pytest.raises(BudgetExceeded, match='overrun'):
        ledger.reserve('b', '0', scope_id='s', now=NEXT_MONDAY)


def test_reservation_id_binds_scope_amount_and_metadata(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    metadata = {'run_id': 'run', 'attempt_id': 'try-1', 'purpose': 'experiment'}
    result = ledger.reserve('a', '20', scope_id='s', metadata=metadata, now=MONDAY)
    assert ledger.reserve('a', Decimal('20'), scope_id='s', metadata=dict(reversed(list(metadata.items()))), now=NEXT_MONDAY) == result
    for changes in ({'maximum_usd': '21'}, {'scope_id': 'other'}, {'metadata': {**metadata, 'attempt_id': 'try-2'}}):
        arguments = dict(maximum_usd='20', scope_id='s', metadata=metadata, now=MONDAY)
        arguments.update(changes)
        with pytest.raises(ReservationConflict):
            ledger.reserve('a', **arguments)
    assert ledger.status(now=MONDAY).held_usd == Decimal('20')


def test_scope_limit_is_shared_durable_and_cannot_be_raised(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('a', '30', scope_id='run', scope_limit_usd='50', now=MONDAY)
    other = BudgetLedger(path)
    with pytest.raises(BudgetExceeded, match='scope'):
        other.reserve('b', '21', scope_id='run', now=MONDAY)
    with pytest.raises(BudgetConfigurationError):
        other.reserve('b', '21', scope_id='run', scope_limit_usd='100', now=MONDAY)
    ledger.settle('a', '10', now=MONDAY)
    other.reserve('b', '40', scope_id='run', now=NEXT_MONDAY)
    assert other.status(now=NEXT_MONDAY).held_usd == Decimal('40')


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '-Infinity', '0.0000001', '1e-999999999999', '', None, True, 0.1, '1e99'])
def test_invalid_money_rejected_without_reservation(tmp_path, value):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    with pytest.raises(ValueError):
        ledger.reserve('a', value, scope_id='s', now=MONDAY)
    assert ledger.status(now=MONDAY).committed_microusd == 0


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '0.0000001', True, 1.1])
def test_invalid_settlement_keeps_hold(tmp_path, value):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('a', '100', scope_id='s', now=MONDAY)
    with pytest.raises(ValueError):
        ledger.settle('a', value, now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('100')


def test_shared_weekly_configuration_cannot_change(tmp_path):
    path = tmp_path / 'budget.sqlite'
    BudgetLedger(path)
    with pytest.raises(BudgetConfigurationError):
        BudgetLedger(path, weekly_limit_usd='301')


def test_naive_time_missing_identity_and_missing_reservation_fail(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    with pytest.raises(ValueError, match='aware'):
        ledger.status(now=datetime(2026, 9, 7))
    with pytest.raises(ValueError):
        ledger.reserve('', '1', scope_id='s', now=MONDAY)
    with pytest.raises(ValueError):
        ledger.reserve('a', '1', scope_id='', now=MONDAY)
    with pytest.raises(KeyError):
        ledger.settle('missing', '1', now=MONDAY)


def test_missing_timezone_database_fails_closed(tmp_path, monkeypatch):
    import wb_orchestrator.budget as budget
    from zoneinfo import ZoneInfoNotFoundError
    def unavailable(name):
        raise ZoneInfoNotFoundError(name)
    monkeypatch.setattr(budget, 'ZoneInfo', unavailable)
    with pytest.raises(BudgetConfigurationError, match='tzdata'):
        BudgetLedger(tmp_path / 'budget.sqlite')


def _reserve_then_crash(path):
    import os
    BudgetLedger(path).reserve('crashed', '299', scope_id='run', now=MONDAY)
    os._exit(17)


def test_process_crash_after_reservation_preserves_liability(tmp_path):
    path = tmp_path / 'budget.sqlite'
    process = multiprocessing.get_context('spawn').Process(target=_reserve_then_crash, args=(path,))
    process.start()
    process.join(timeout=20)
    try:
        assert process.exitcode == 17
        ledger = BudgetLedger(path)
        assert ledger.status(now=MONDAY).available_usd == Decimal('1')
        with pytest.raises(BudgetExceeded):
            ledger.reserve('retry', '2', scope_id='run', now=MONDAY)
    finally:
        if process.is_alive():
            process.terminate()
            process.join()


def test_decimal_context_cannot_round_budget_or_actual(tmp_path):
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 2
        ledger = BudgetLedger(tmp_path / 'budget.sqlite')
        ledger.reserve('a', '299.999999', scope_id='s', now=MONDAY)
        assert ledger.status(now=MONDAY).available_usd == Decimal('0.000001')
        ledger.settle('a', '123.456789', now=MONDAY)
        assert ledger.status(now=MONDAY).actual_usd == Decimal('123.456789')
        assert ledger.status(now=MONDAY).available_usd == Decimal('176.543211')


def test_verified_zero_frees_hold_and_failed_scope_insert_rolls_back(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    with pytest.raises(BudgetExceeded):
        ledger.reserve('a', '20', scope_id='s', scope_limit_usd='10', now=MONDAY)
    ledger.reserve('a', '20', scope_id='s', scope_limit_usd='30', now=MONDAY)
    ledger.settle('a', '0', now=MONDAY)
    assert ledger.status(now=MONDAY).committed_microusd == 0
    assert ledger.reserve('a', '20', scope_id='s', scope_limit_usd='30', now=MONDAY).actual_usd == Decimal('0')
    ledger.reserve('b', '30', scope_id='s', now=MONDAY)


@pytest.mark.parametrize('metadata', [{1: 'a'}, {'nested': {1: 'a'}}, {'a': float('nan')}, {'a': object()}, ['a']])
def test_invalid_metadata_does_not_bind_reservation(tmp_path, metadata):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    with pytest.raises(ValueError):
        ledger.reserve('a', '1', scope_id='s', metadata=metadata, now=MONDAY)
    assert ledger.status(now=MONDAY).held_microusd == 0


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', True, 0.1, '0.0000001'])
def test_invalid_policy_money_fails_closed(tmp_path, value):
    with pytest.raises(ValueError):
        BudgetLedger(tmp_path / 'invalid.sqlite', weekly_limit_usd=value)
    ledger = BudgetLedger(tmp_path / 'valid.sqlite')
    with pytest.raises(ValueError):
        ledger.reserve('a', '1', scope_id='s', scope_limit_usd=value, now=MONDAY)
    assert ledger.status(now=MONDAY).held_microusd == 0


def test_reservation_overrun_blocks_even_with_weekly_headroom(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('a', '10', scope_id='s', now=MONDAY)
    ledger.settle('a', '11', now=MONDAY)
    assert ledger.status(now=MONDAY).actual_usd == Decimal('11')
    assert ledger.status(now=MONDAY).blocked is True
    with pytest.raises(BudgetExceeded):
        ledger.reserve('b', '1', scope_id='s', now=MONDAY)


def _competing_claim(args):
    path, _ = args
    try:
        BudgetLedger(path).claim('a', now=MONDAY)
        return True
    except ReservationConflict:
        return False


def test_concurrent_claimers_dispatch_exactly_once(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('a', '100', scope_id='s', now=MONDAY)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
        claimed = list(pool.map(_competing_claim, [(path, n) for n in range(8)]))
    assert sum(claimed) == 1
    assert ledger.reserve('a', '100', scope_id='s', now=MONDAY).dispatched_at == MONDAY.isoformat()
    assert ledger.status(now=MONDAY).held_usd == Decimal('100')


def _claim_then_crash(path):
    import os
    BudgetLedger(path).claim('a', now=MONDAY)
    os._exit(19)


def test_claim_crash_never_allows_automatic_redispatch(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('a', '200', scope_id='s', now=MONDAY)
    process = multiprocessing.get_context('spawn').Process(target=_claim_then_crash, args=(path,))
    process.start()
    process.join(timeout=20)
    try:
        assert process.exitcode == 19
        with pytest.raises(ReservationConflict, match='dispatched'):
            BudgetLedger(path).claim('a', now=NEXT_MONDAY)
        assert ledger.status(now=NEXT_MONDAY).held_usd == Decimal('200')
        ledger.settle('a', None, now=NEXT_MONDAY)
        with pytest.raises(ReservationConflict):
            ledger.claim('a', now=NEXT_MONDAY)
    finally:
        if process.is_alive():
            process.terminate()
            process.join()


def test_claim_rejects_settled_missing_and_overrun(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('settled', '10', scope_id='s', now=MONDAY)
    ledger.settle('settled', '0', now=MONDAY)
    with pytest.raises(ReservationConflict, match='settled'):
        ledger.claim('settled', now=MONDAY)
    with pytest.raises(KeyError):
        ledger.claim('missing', now=MONDAY)
    ledger.reserve('a', '100', scope_id='s', now=MONDAY)
    ledger.reserve('overrun', '10', scope_id='s', now=MONDAY)
    ledger.settle('overrun', '11', now=MONDAY)
    with pytest.raises(BudgetExceeded, match='overrun'):
        ledger.claim('a', now=MONDAY)
    assert ledger.reserve('a', '100', scope_id='s', now=MONDAY).dispatched_at is None


def test_legacy_reservation_without_dispatch_evidence_cannot_redispatch(tmp_path):
    import sqlite3
    path = tmp_path / 'legacy.sqlite'
    BudgetLedger(path).reserve('legacy', '250', scope_id='s', now=MONDAY)
    with sqlite3.connect(path) as connection:
        connection.execute('ALTER TABLE budget_reservations DROP COLUMN dispatched_at')
        connection.execute('UPDATE budget_policy SET schema_version=1')
    ledger = BudgetLedger(path)
    with pytest.raises(ReservationConflict, match='dispatched'):
        ledger.claim('legacy', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('250')
    ledger.reserve('new', '50', scope_id='s', now=MONDAY)
    assert ledger.claim('new', now=MONDAY).dispatched_at == MONDAY.isoformat()
    ledger.settle('new', '20', now=MONDAY)
    assert ledger.status(now=MONDAY).available_usd == Decimal('30')
    with pytest.raises(ReservationConflict, match='settled'):
        BudgetLedger(path).claim('new', now=MONDAY)


def test_first_dispatch_in_later_week_charges_dispatch_week(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('delayed', '300', scope_id='s', now=MONDAY)
    ledger.claim('delayed', now=NEXT_MONDAY)
    ledger.settle('delayed', '300', now=NEXT_MONDAY)
    reopened = BudgetLedger(path)
    assert reopened.status(now=NEXT_MONDAY).actual_usd == Decimal('300')
    assert reopened.status(now=NEXT_MONDAY).available_usd == Decimal('0')
    assert reopened.status(now=MONDAY).actual_usd == Decimal('0')
    with pytest.raises(BudgetExceeded):
        reopened.reserve('extra', '0.000001', scope_id='s', now=NEXT_MONDAY)


def test_execution_and_billing_spanning_weeks_charge_every_relevant_week(tmp_path):
    from datetime import timedelta
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('spanning', '300', scope_id='s', now=MONDAY)
    ledger.claim('spanning', now=MONDAY)
    third_monday = NEXT_MONDAY + timedelta(days=7)
    ledger.settle('spanning', '200', now=third_monday)
    for instant in (MONDAY, NEXT_MONDAY, third_monday):
        state = ledger.status(now=instant)
        assert state.actual_usd == Decimal('200')
        assert state.available_usd == Decimal('100')
    with pytest.raises(BudgetExceeded):
        ledger.reserve('extra', '101', scope_id='s', now=third_monday)
    assert ledger.status(now=third_monday + timedelta(days=7)).available_usd == Decimal('300')


def test_claim_and_settlement_cannot_backdate_accounting(tmp_path):
    from datetime import timedelta
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('a', '100', scope_id='s', now=MONDAY)
    with pytest.raises(ValueError, match='before'):
        ledger.claim('a', now=MONDAY - timedelta(seconds=1))
    ledger.claim('a', now=NEXT_MONDAY)
    with pytest.raises(ValueError, match='before'):
        ledger.settle('a', '1', now=MONDAY)
    assert ledger.status(now=NEXT_MONDAY).held_usd == Decimal('100')


def test_claim_readmits_against_current_week_legacy_overlap(tmp_path):
    import sqlite3
    path = tmp_path / 'legacy-overlap.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('earlier', '250', scope_id='s', now=MONDAY)
    ledger.claim('earlier', now=MONDAY)
    ledger.settle('earlier', '250', now=MONDAY)
    ledger.reserve('pending', '50', scope_id='s', now=MONDAY)
    ledger.reserve('current', '250', scope_id='s', now=NEXT_MONDAY)
    ledger.claim('current', now=NEXT_MONDAY)
    ledger.settle('current', '250', now=NEXT_MONDAY)
    # Represent a ledger written under the former reservation-week attribution:
    # it could admit current spending despite earlier execution settling late.
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE budget_reservations SET settled_at=? WHERE reservation_id=?',
                           (NEXT_MONDAY.isoformat(), 'earlier'))
    reopened = BudgetLedger(path)
    assert reopened.status(now=NEXT_MONDAY).actual_usd == Decimal('500')
    assert reopened.status(now=NEXT_MONDAY).overrun_ids == ()
    with pytest.raises(BudgetExceeded, match='weekly'):
        reopened.claim('pending', now=NEXT_MONDAY)
    assert reopened.reserve('pending', '50', scope_id='s', now=NEXT_MONDAY).dispatched_at is None
