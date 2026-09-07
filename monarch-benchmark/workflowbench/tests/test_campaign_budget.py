from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from wb_orchestrator.campaign_budget import CampaignBudget, BudgetBlocked, ReservationConflict


def test_atomic_reservations_cannot_oversubscribe(tmp_path):
    path = tmp_path / 'budget.sqlite'
    CampaignBudget(path, total_limit_usd=24)
    def reserve(i):
        try:
            return CampaignBudget(path, total_limit_usd=24).reserve(str(i), 'measured').created
        except BudgetBlocked:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(20))) == 2
    assert CampaignBudget(path, total_limit_usd=24).snapshot()['reserved_usd'] == 24


def test_retries_and_reconciliation_do_not_double_count(tmp_path):
    b = CampaignBudget(tmp_path / 'b.sqlite')
    assert b.reserve('attempt', 'measured').created
    assert not b.reserve('attempt', 'measured').created
    b.reconcile('attempt', Decimal('1.23'))
    b.reconcile('attempt', Decimal('1.23'))
    assert b.snapshot()['spent_usd'] == 1.23
    assert b.snapshot()['reserved_usd'] == 0
    assert not b.reserve('attempt', 'measured').created
    with pytest.raises(ReservationConflict):
        b.reconcile('attempt', 2)


def test_unknown_usage_blocks_new_paid_work_until_resolved(tmp_path):
    b = CampaignBudget(tmp_path / 'b.sqlite')
    b.reserve('attempt', 'measured')
    b.reconcile('attempt', None)
    with pytest.raises(BudgetBlocked):
        b.reserve('next', 'measured')
    assert b.snapshot()['unknown'] == ['attempt']
    assert b.snapshot()['reserved_usd'] == 12
    b.reconcile('attempt', 5)
    assert b.reserve('next', 'measured').created


def test_development_and_campaign_ceiling_include_pending_work(tmp_path):
    b = CampaignBudget(tmp_path / 'b.sqlite')
    b.reserve('dev1', 'development', 200)
    with pytest.raises(BudgetBlocked):
        b.reserve('dev2', 'development', 1)
    b.reconcile('dev1', 200)
    for i in range(66):
        b.reserve(f'm{i}', 'measured')
    with pytest.raises(BudgetBlocked):
        b.reserve('overflow', 'measured')
    assert b.snapshot()['committed_usd'] == 992


def test_overrun_is_recorded_and_stops_later_calls(tmp_path):
    b = CampaignBudget(tmp_path / 'b.sqlite')
    b.reserve('attempt', 'measured')
    b.reconcile('attempt', 13)
    assert b.snapshot()['spent_usd'] == 13
    with pytest.raises(BudgetBlocked):
        b.reserve('next', 'measured')


def test_conflicting_reservations_and_budget_configuration_refused(tmp_path):
    path = tmp_path / 'b.sqlite'
    b = CampaignBudget(path)
    b.reserve('same', 'development', 5)
    with pytest.raises(ReservationConflict):
        b.reserve('same', 'measured')
    with pytest.raises(ReservationConflict):
        CampaignBudget(path, total_limit_usd=500)
    with pytest.raises(ValueError):
        CampaignBudget(tmp_path / 'other.sqlite', total_limit_usd=1001)
    with pytest.raises(ValueError):
        b.reserve('measured', 'measured', 13)


@pytest.mark.parametrize('amount', [-1, float('nan'), float('inf'), True])
def test_invalid_cost_cannot_change_the_ledger(tmp_path, amount):
    b = CampaignBudget(tmp_path / 'b.sqlite')
    b.reserve('attempt', 'measured')
    with pytest.raises(ValueError):
        b.reconcile('attempt', amount)
    assert b.snapshot()['reserved_usd'] == 12
