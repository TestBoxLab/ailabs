"""Report headroom includes legacy episode scopes and unresolved billing exactly once."""
from decimal import Decimal

import pytest

from wb_orchestrator.budget import BudgetLedger


def test_run_reservations_union_episode_ids_exact_scopes_and_envelope_links(tmp_path):
    ledger = BudgetLedger(tmp_path / 'ledger.sqlite3')
    ledger.reserve_run('run_1', '20')
    ledger.reserve('run_1/request', '2', scope_id='run_1')
    ledger.settle('run_1/request', '1')
    ledger.reserve('linked', '3', scope_id='episode-a', run_id='run_1')
    ledger.settle('linked', '2')
    ledger.reserve('run_1/legacy', '4', scope_id='episode-b')
    ledger.claim('run_1/legacy')
    ledger.settle('run_1/legacy', None, outcome='interrupted')
    ledger.reserve('run_10/wrong', '5', scope_id='episode-c')
    ledger.reserve('runX1/wildcard', '6', scope_id='episode-d')
    found = ledger.reservations(run_id='run_1')
    assert {r.reservation_id for r in found} == {'run_1/request', 'linked', 'run_1/legacy'}
    assert len(found) == 3  # The exact-scope request is also linked and prefix-matched.
    assert sum(r.maximum_usd if r.actual_usd is None else r.actual_usd for r in found) == Decimal('7')
    assert next(r for r in found if r.reservation_id == 'run_1/legacy').actual_usd is None
    assert {r.reservation_id for r in ledger.reservations(scope_id='episode-b')} == {'run_1/legacy'}
    with pytest.raises(ValueError, match='Choose scope_id or run_id'):
        ledger.reservations(scope_id='episode-b', run_id='run_1')


def test_legacy_run_without_an_envelope_retains_known_and_unknown_episode_costs(tmp_path):
    ledger = BudgetLedger(tmp_path / 'legacy.sqlite3')
    ledger.reserve('historical/episode-a/request-1', '2', scope_id='episode-a')
    ledger.settle('historical/episode-a/request-1', '1')
    ledger.reserve('historical/episode-b/request-1', '3', scope_id='episode-b')
    ledger.settle('historical/episode-b/request-1', None, outcome='error')
    assert ledger.scope_committed('historical') == 0
    found = ledger.reservations(run_id='historical')
    assert len(found) == 2
    assert sum(r.maximum_usd if r.actual_usd is None else r.actual_usd for r in found) == Decimal('4')
