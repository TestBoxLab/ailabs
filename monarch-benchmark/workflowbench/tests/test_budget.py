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


# -- milestone M3: read-only views the dispatch path and reconciliation need ------

def test_reservations_are_readable_with_their_metadata_and_scope(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    ledger.reserve('a', '2', scope_id='run-1/task/arm/t0', metadata={'billing_provider': 'anthropic'}, now=MONDAY)
    ledger.reserve('b', '3', scope_id='run-1/task/arm/t1', metadata={'billing_provider': 'openai'}, now=MONDAY)
    ledger.claim('a', now=MONDAY)
    ledger.settle('a', '0.5', now=MONDAY)
    rows = ledger.reservations()
    assert [r.reservation_id for r in rows] == ['a', 'b']
    assert rows[0].metadata == {'billing_provider': 'anthropic'} and rows[0].actual_usd == Decimal('0.5')
    assert rows[1].actual_usd is None and rows[1].dispatched_at is None
    assert [r.reservation_id for r in ledger.reservations(scope_id='run-1/task/arm/t1')] == ['b']


def test_scope_committed_counts_settled_actuals_and_open_holds(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    assert ledger.scope_committed('attempt') == Decimal('0')
    ledger.reserve('r0', '0.40', scope_id='attempt', now=MONDAY)
    ledger.settle('r0', '0.05', now=MONDAY)
    ledger.reserve('r1', '0.40', scope_id='attempt', now=MONDAY)          # still held
    ledger.reserve('other', '9', scope_id='another-attempt', now=MONDAY)
    assert ledger.scope_committed('attempt') == Decimal('0.45')


def test_week_of_uses_the_ledger_calendar(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    assert ledger.week_of(MONDAY) == '2026-09-07'
    sunday_night_utc = datetime(2026, 9, 14, 2, 59, tzinfo=timezone.utc)   # still Sunday in Sao Paulo
    assert ledger.week_of(sunday_night_utc) == '2026-09-07'
    assert ledger.week_of(NEXT_MONDAY) == '2026-09-14'


def test_absent_envelope_means_zero_not_unlimited(tmp_path):
    from wb_studio.genesis_access import Envelope
    env = Envelope(tmp_path / 'genesis')
    rec = env.read(now=MONDAY)
    assert rec['amount_usd'] == '0.00'
    assert rec['per_experiment_ceiling_usd'] == '0.00'
    assert rec['is_set'] is False
    assert env.available_usd(now=MONDAY) == Decimal('0.00')


def test_envelope_set_read_and_expiration(tmp_path):
    from wb_studio.genesis_access import Envelope
    env = Envelope(tmp_path / 'genesis')
    saved = env.set(amount_usd='200.00', per_experiment_ceiling_usd='45.00', by='Lucas', now=MONDAY)
    assert saved['week_start'] == '2026-09-07'
    assert saved['amount_usd'] == '200.00'
    assert saved['per_experiment_ceiling_usd'] == '45.00'
    assert saved['set_by'] == 'human:lucas'
    assert 'T' in saved['set_at']

    # Read back in the same week
    rec = env.read(now=MONDAY)
    assert rec['is_set'] is True
    assert rec['amount_usd'] == '200.00'
    assert rec['per_experiment_ceiling_usd'] == '45.00'
    assert rec['set_by'] == 'human:lucas'

    # Next week it is expired (treated as zero)
    rec_next = env.read(now=NEXT_MONDAY)
    assert rec_next['is_set'] is False
    assert rec_next['amount_usd'] == '0.00'
    assert rec_next['per_experiment_ceiling_usd'] == '0.00'
    assert env.available_usd(now=NEXT_MONDAY) == Decimal('0.00')


def test_envelope_validation_rules(tmp_path):
    from wb_studio.genesis_access import Envelope
    env = Envelope(tmp_path / 'genesis')

    # Weekly ceiling is 300: amount must be strictly below 300
    with pytest.raises(ValueError, match='strictly below the lab weekly ceiling'):
        env.set('300.00', '50.00', by='lucas', now=MONDAY)
    with pytest.raises(ValueError, match='strictly below the lab weekly ceiling'):
        env.set('300.01', '50.00', by='lucas', now=MONDAY)

    # Non-negative
    with pytest.raises(ValueError, match='nonnegative'):
        env.set('-10.00', '5.00', by='lucas', now=MONDAY)

    # Per-experiment ceiling cannot exceed envelope amount
    with pytest.raises(ValueError, match='cannot exceed'):
        env.set('50.00', '60.00', by='lucas', now=MONDAY)

    # Must name a person
    with pytest.raises(ValueError, match='named person'):
        env.set('50.00', '10.00', by='', now=MONDAY)


def test_envelope_accounting_with_ledger(tmp_path):
    from wb_studio.genesis_access import Envelope
    genesis_dir = tmp_path / 'genesis'
    env = Envelope(genesis_dir)
    env.set('100.00', '25.00', by='lucas', now=MONDAY)

    ledger = BudgetLedger(tmp_path / 'budget.sqlite3')
    # Reserving a genesis experiment
    ledger.reserve('r1', '20.00', scope_id='genesis-exp-1', metadata={'by': 'genesis', 'purpose': 'Genesis experiment'}, now=MONDAY)
    # Available = 100 - 20 = 80
    assert env.available_usd(ledger=ledger, now=MONDAY) == Decimal('80.00')

    # Settling part of it
    ledger.settle('r1', '5.50', now=MONDAY)
    # Now settled = 5.50, held = 0, available = 100 - 5.50 = 94.50
    assert env.available_usd(ledger=ledger, now=MONDAY) == Decimal('94.50')

    # Status dictionary
    st = env.status(ledger=ledger, now=MONDAY)
    assert st['amount_usd'] == '100.00'
    assert st['settled_usd'] == '5.50'
    assert st['held_usd'] == '0.00'
    assert st['left_usd'] == '94.50'


def test_budget_envelope_cli(tmp_path, capsys):
    from wb_orchestrator.cli import main
    genesis_dir = tmp_path / 'genesis'
    ledger_path = tmp_path / 'budget.sqlite3'
    BudgetLedger(ledger_path)

    # 1. Missing arguments for set
    code = main(['budget', 'envelope', '--set', '200.00', '--genesis-dir', str(genesis_dir)])
    assert code == 2
    err = capsys.readouterr().err
    assert '--set, --per-experiment and --by are all required' in err

    # 2. Exceeding weekly ceiling (300)
    code = main(['budget', 'envelope', '--set', '300.00', '--per-experiment', '50.00', '--by', 'Lucas', '--genesis-dir', str(genesis_dir)])
    assert code == 2
    err = capsys.readouterr().err
    assert 'strictly below the lab weekly ceiling' in err

    # 3. Successful set
    code = main(['budget', 'envelope', '--set', '200.00', '--per-experiment', '45.00', '--by', 'Lucas', '--genesis-dir', str(genesis_dir)])
    assert code == 0
    out = capsys.readouterr().out
    assert 'research envelope set to $200.00 (per-experiment ceiling $45.00) by Lucas for week of' in out

    # 4. Status
    code = main(['budget', 'envelope', 'status', '--genesis-dir', str(genesis_dir), '--ledger', str(ledger_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert 'week of ' in out
    assert '(America/Sao_Paulo)' in out
    assert 'research envelope   $200.00 set by Lucas' in out
    assert 'reserved $0.00' in out
    assert 'settled $0.00' in out
    assert 'left $200.00' in out
    assert 'lab weekly ceiling  $300.00' in out
    assert 'experiments this week: 0 admitted, 0 refused' in out

    # 5. Status with empty genesis dir (not set)
    empty_genesis = tmp_path / 'empty_genesis'
    code = main(['budget', 'envelope', 'status', '--genesis-dir', str(empty_genesis), '--ledger', str(ledger_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert 'research envelope   $0.00 (not set)' in out




def test_the_envelope_gate_finds_the_shared_ledger_it_was_not_given(tmp_path, monkeypatch):
    """`background_wanted` and `may_launch` read the envelope without passing a ledger.
    Looking only beside the genesis folder found nothing in a real Studio, so the gate
    read nothing spent and reported the whole envelope available (FR-035)."""
    from wb_studio.genesis_access import Envelope
    shared = tmp_path / 'research' / 'budget.sqlite3'
    monkeypatch.setenv('STUDIO_LEDGER_PATH', str(shared))
    ledger = BudgetLedger(shared)
    ledger.reserve('genesis-held-1', '40.00', scope_id='genesis-held',
                   metadata={'purpose': 'Genesis'}, now=MONDAY)

    env = Envelope(tmp_path / 'out' / 'studio' / 'genesis')
    env.set(amount_usd='50.00', per_experiment_ceiling_usd='10.00', by='Lucas', now=MONDAY)
    assert env.available_usd(ledger=ledger, now=MONDAY) == Decimal('10.00')
    assert env.available_usd(now=MONDAY) == Decimal('10.00')      # the gate agrees

    monkeypatch.setenv('STUDIO_LEDGER_PATH', str(tmp_path / 'gone.sqlite3'))
    assert env.available_usd(now=MONDAY) == Decimal('0.00')       # no accounting: fails closed


# --- A hold whose cost the provider never reported --------------------------------------
#
# An attempt whose cost cannot be read settles with no actual and keeps its whole
# reservation held, in this week and in every week after it. That is deliberate: the
# money may well have been spent, and the ledger must not forget it. What was missing
# is the way out. Ten Monarch attempts during a Langfuse outage hold US$ 250 of a
# US$ 300 week for ever, with no cent proven spent and nothing in the CLI to release
# it — `wb budget acknowledge` answers for overruns only (found by ailabs-9c, feature
# 024 US4, 11 Sep 2026; `docs/rounds/2026-09-11-recipes.md`).
#
# The release is a person's, not a clock's: an expiry at the week boundary would drop a
# real charge nobody has read yet. So the hold survives rollover exactly as before, and
# one named person with a reason releases it — the same shape as acknowledging an overrun.

def _stale_hold(path, amount='250'):
    """One attempt that ran and whose cost the provider never reported."""
    ledger = BudgetLedger(path)
    ledger.reserve('outage-1', amount, scope_id='ep-1',
                   metadata={'harness': 'monarch', 'billing_provider': 'monarch'}, now=MONDAY)
    ledger.claim('outage-1', now=MONDAY)
    ledger.settle('outage-1', None, now=MONDAY)
    return ledger


def test_a_released_hold_stops_blocking_the_weeks_after_it(tmp_path):
    ledger = _stale_hold(tmp_path / 'budget.sqlite')
    assert ledger.status(now=NEXT_MONDAY).carried_held_usd == Decimal('250')   # the defect
    ledger.release_hold('outage-1', by='human:lucas',
                        reason='Langfuse outage; the attempt failed and no cost was ever reported.',
                        now=NEXT_MONDAY)
    after = ledger.status(now=NEXT_MONDAY)
    assert after.available_usd == Decimal('300')
    assert after.carried_held_usd == Decimal('0') and after.held_usd == Decimal('0')
    ledger.reserve('next-week', '300', scope_id='ep-2', now=NEXT_MONDAY)


def test_status_shows_unknown_holds_as_their_own_line(tmp_path):
    ledger = _stale_hold(tmp_path / 'budget.sqlite')
    blocked = ledger.status(now=NEXT_MONDAY)
    # Not spending: nothing is proven paid, and the ids say what to look at.
    assert blocked.actual_usd == Decimal('0')
    assert blocked.unknown_ids == ('outage-1',) and blocked.released_usd == Decimal('0')
    ledger.release_hold('outage-1', by='human:lucas', reason='Langfuse outage.', now=NEXT_MONDAY)
    freed = ledger.status(now=NEXT_MONDAY)
    assert freed.unknown_ids == () and freed.released_usd == Decimal('250')


def test_a_released_hold_keeps_its_unknown_cost_on_the_record(tmp_path):
    from wb_orchestrator import reconcile
    path = tmp_path / 'budget.sqlite'
    ledger = _stale_hold(path)
    ledger.release_hold('outage-1', by='human:lucas', reason='Langfuse outage.', now=NEXT_MONDAY)
    row = next(r for r in BudgetLedger(path).reservations() if r.reservation_id == 'outage-1')
    assert row.actual_usd is None and row.maximum_usd == Decimal('250')
    note = row.metadata['hold_released']
    assert note['by'] == 'human:lucas' and 'Langfuse' in note['reason'] and note['at']
    # `wb budget reconcile` still finds it against the provider's own export.
    monarch = reconcile.ledger_totals(ledger, '2026-09-07')['monarch']
    assert monarch['unsettled'] == 1 and monarch['held'] == Decimal('250')


def test_a_cost_that_arrives_after_the_release_is_still_charged(tmp_path):
    ledger = _stale_hold(tmp_path / 'budget.sqlite')
    ledger.release_hold('outage-1', by='human:lucas', reason='Langfuse outage.', now=NEXT_MONDAY)
    ledger.settle('outage-1', '31.50', now=NEXT_MONDAY)
    state = ledger.status(now=NEXT_MONDAY)
    assert state.actual_usd == Decimal('31.50') and state.released_usd == Decimal('0')
    assert state.available_usd == Decimal('268.50')


def test_a_released_hold_can_never_be_dispatched(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = BudgetLedger(path)
    ledger.reserve('pending', '25', scope_id='ep-3', now=MONDAY)
    ledger.release_hold('pending', by='human:lucas', reason='The run died before it started.', now=MONDAY)
    assert ledger.status(now=MONDAY).held_usd == Decimal('0')
    with pytest.raises(ReservationConflict, match='released'):
        ledger.claim('pending', now=MONDAY)


def test_releasing_a_hold_needs_a_person_a_reason_and_an_unsettled_hold(tmp_path):
    path = tmp_path / 'budget.sqlite'
    ledger = _stale_hold(path)
    for by, reason in (('', 'r'), ('human:lucas', ''), ('', '')):
        with pytest.raises(ValueError):
            ledger.release_hold('outage-1', by=by, reason=reason, now=NEXT_MONDAY)
    with pytest.raises(ValueError, match='no reservation'):
        ledger.release_hold('nope', by='human:lucas', reason='x', now=NEXT_MONDAY)
    ledger.reserve('paid', '10', scope_id='ep-9', now=MONDAY)
    ledger.settle('paid', '4', now=MONDAY)
    with pytest.raises(ValueError, match='settled'):
        ledger.release_hold('paid', by='human:lucas', reason='x', now=NEXT_MONDAY)
    assert ledger.status(now=NEXT_MONDAY).carried_held_usd == Decimal('250')
    ledger.release_hold('outage-1', by='human:lucas', reason='Langfuse outage.', now=NEXT_MONDAY)
    with pytest.raises(ValueError, match='already released'):
        ledger.release_hold('outage-1', by='human:carlos', reason='again', now=NEXT_MONDAY)


def test_metadata_that_cannot_be_read_never_releases_capacity(tmp_path):
    import sqlite3
    path = tmp_path / 'budget.sqlite'
    ledger = _stale_hold(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE budget_reservations SET metadata_json='not json' WHERE reservation_id='outage-1'")
    assert BudgetLedger(path).status(now=NEXT_MONDAY).carried_held_usd == Decimal('250')


def test_the_command_releases_one_hold_and_reports_the_week(tmp_path, capsys):
    from wb_orchestrator.cli import main
    path = tmp_path / 'budget.sqlite'
    _stale_hold(path)
    assert main(['--ledger', str(path), 'budget', 'release', 'outage-1',
                 '--because', 'Langfuse outage; no cost was ever reported.', '--by', 'human:lucas']) == 0
    out = capsys.readouterr().out
    assert 'released outage-1' in out and 'human:lucas' in out and '250' in out
    assert BudgetLedger(path).status(now=NEXT_MONDAY).carried_held_usd == Decimal('0')


def test_the_command_refuses_without_a_person(tmp_path, monkeypatch, capsys):
    from wb_orchestrator.cli import main
    monkeypatch.delenv('WB_OPERATOR', raising=False)
    path = tmp_path / 'budget.sqlite'
    _stale_hold(path)
    assert main(['--ledger', str(path), 'budget', 'release', 'outage-1', '--because', 'x']) == 2
    assert BudgetLedger(path).status(now=NEXT_MONDAY).carried_held_usd == Decimal('250')
