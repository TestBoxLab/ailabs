"""An overrun must be answerable by a person, not only by editing the database.

Feature 024, FR-006. The ledger's own docstring says an actual above its reserved
maximum "permanently blocks new admissions" and that request reservations have "no
override, expiry, or cancellation path". Blocking is the right instinct — a provider
that charged more than it promised is exactly when work should stop — but the only
recovery was hand-editing `research/budget.sqlite3`, which the same docstring puts out
of scope. So one under-estimated request could stop every run, every Genesis turn and
`wb run` itself, for good.

This does not weaken the gate. The overrun still blocks until a named person
acknowledges it, and the acknowledgement is recorded with who, when and why. What
changes is that the recovery is auditable instead of invisible.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from wb_orchestrator.budget import BudgetExceeded, BudgetLedger

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ledger(tmp_path):
    return BudgetLedger(tmp_path / 'budget.sqlite3')


def overrun(ledger):
    """One reservation that settles above its maximum, the way a provider overcharge lands."""
    ledger.reserve('r1', '0.10', scope_id='s1', metadata={'purpose': 'test'}, now=NOW)
    ledger.claim('r1', now=NOW)
    ledger.settle('r1', '0.50', now=NOW)
    return ledger.status(now=NOW)


def test_an_overrun_blocks_until_someone_answers_for_it(ledger):
    status = overrun(ledger)
    assert status.overrun_ids == ('r1',) and status.blocked is True
    with pytest.raises(BudgetExceeded, match='overrun'):
        ledger.reserve('r2', '0.01', scope_id='s2', metadata={}, now=NOW)


def test_a_person_can_acknowledge_it_and_work_resumes(ledger):
    overrun(ledger)
    ledger.acknowledge_overrun('r1', by='human:lucas',
                               reason='Provider billed above the quoted rate; raised with them.', now=NOW)
    status = ledger.status(now=NOW)
    assert status.overrun_ids == () and status.blocked is False
    ledger.reserve('r2', '0.01', scope_id='s2', metadata={}, now=NOW)


def test_the_acknowledgement_keeps_the_overrun_on_the_record(ledger):
    overrun(ledger)
    ledger.acknowledge_overrun('r1', by='human:lucas', reason='Known provider overcharge.', now=NOW)
    row = next(r for r in ledger.reservations() if r.reservation_id == 'r1')
    assert row.actual_usd > row.maximum_usd          # the money is still what it was
    assert row.metadata['overrun_acknowledged']['by'] == 'human:lucas'
    assert 'overcharge' in row.metadata['overrun_acknowledged']['reason']
    assert row.metadata['overrun_acknowledged']['at']


def test_an_acknowledgement_needs_a_person_and_a_reason(ledger):
    overrun(ledger)
    for by, reason in (('', 'r'), ('human:lucas', ''), ('', '')):
        with pytest.raises(ValueError):
            ledger.acknowledge_overrun('r1', by=by, reason=reason, now=NOW)
    assert ledger.status(now=NOW).blocked is True


def test_acknowledging_one_overrun_does_not_clear_another(ledger):
    overrun(ledger)
    ledger.acknowledge_overrun('r1', by='human:lucas', reason='first', now=NOW)
    ledger.reserve('r3', '0.10', scope_id='s3', metadata={}, now=NOW)
    ledger.claim('r3', now=NOW)
    ledger.settle('r3', '0.90', now=NOW)
    assert ledger.status(now=NOW).overrun_ids == ('r3',)


def test_an_unknown_reservation_cannot_be_acknowledged(ledger):
    overrun(ledger)
    with pytest.raises(ValueError, match='no reservation'):
        ledger.acknowledge_overrun('nope', by='human:lucas', reason='x', now=NOW)


def test_a_reservation_that_did_not_overrun_cannot_be_acknowledged(ledger):
    ledger.reserve('ok', '1.00', scope_id='s9', metadata={}, now=NOW)
    ledger.claim('ok', now=NOW)
    ledger.settle('ok', '0.10', now=NOW)
    with pytest.raises(ValueError, match='did not overrun'):
        ledger.acknowledge_overrun('ok', by='human:lucas', reason='x', now=NOW)


# --- T026: the same recovery from the command line ------------------------------------

def test_the_command_acknowledges_and_reports_what_is_left(tmp_path, capsys, monkeypatch):
    from types import SimpleNamespace
    from wb_orchestrator.cli import cmd_budget_acknowledge
    path = tmp_path / 'budget.sqlite3'
    overrun(BudgetLedger(path))
    args = SimpleNamespace(ledger=str(path), reservation_id='r1',
                           reason='Provider billed above the quoted rate.', by='human:lucas')
    assert cmd_budget_acknowledge(args) == 0
    out = capsys.readouterr().out
    assert 'acknowledged r1' in out and 'human:lucas' in out and 'overruns still blocking: none' in out
    assert BudgetLedger(path).status().blocked is False


def test_the_command_refuses_without_a_person(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from wb_orchestrator.cli import cmd_budget_acknowledge
    monkeypatch.delenv('WB_OPERATOR', raising=False)
    path = tmp_path / 'budget.sqlite3'
    overrun(BudgetLedger(path))
    args = SimpleNamespace(ledger=str(path), reservation_id='r1', reason='x', by=None)
    assert cmd_budget_acknowledge(args) == 2
    assert BudgetLedger(path).status().blocked is True
