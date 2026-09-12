"""Continuation capacity stays inside the original envelope and shared week."""
from decimal import Decimal

import pytest

from wb_orchestrator.budget import BudgetLedger, BudgetExceeded
from wb_studio.configured_controls import segment_budget_status


def test_own_unused_envelope_is_not_double_counted_or_available_to_other_runs(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    ledger.reserve("other-work", "260", scope_id="other")
    ledger.reserve_run("segment", "40")
    assert ledger.status().available_usd == 0
    assert segment_budget_status(ledger, "segment").available_usd == 40
    ledger.reserve("attempt", "12", scope_id="run/task/competitor/t0", run_id="segment")
    ledger.claim("attempt")
    assert segment_budget_status(ledger, "segment").available_usd == 28
    ledger.settle("attempt", "3")
    assert segment_budget_status(ledger, "segment").available_usd == 37
    with pytest.raises(BudgetExceeded):
        ledger.reserve("too-large", "38", scope_id="run/task2/competitor/t0", run_id="segment")
    assert ledger.status().available_usd == 0
    ledger.finish_run("segment")
    assert segment_budget_status(ledger, "segment") == ledger.status()
    assert ledger.status().available_usd == 37


def test_preview_rounds_remaining_capacity_down_to_ledger_precision(workspace):
    from tests.test_configured_controls import create
    from wb_studio.configured_controls import preview
    studio, remote = workspace
    remote.content["config/plans/free-check.yaml"] = remote.content["config/plans/free-check.yaml"].replace(
        "cost_ceiling_usd: 1", "cost_ceiling_usd: 0.333333333")
    remote.head = "8" * 40
    remote.commits[remote.head] = dict(remote.content)
    studio, job = create(workspace)
    studio.pause(job["id"])
    result = preview(studio, job["id"])
    assert result["resumable"], result
    assert Decimal(result["remaining_ceiling_usd"]) == Decimal("0.333333")


from tests.test_studio_benchmark_config import workspace
