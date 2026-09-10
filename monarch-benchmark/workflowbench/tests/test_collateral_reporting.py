"""Collateral damage must reach the row and the report, not stop at the grader.

A competitor that finishes more prompts by writing things nobody asked for and
one that takes the safe path can have the same pass rate. The report has to be
able to tell them apart, so the per-attempt number is aggregated per competitor.
"""
from __future__ import annotations

from runner.schema import EpisodeRow
from wb_report.metrics import competitor_metrics


def _row(arm, passed, unexpected=0, violations=0, termination="completed"):
    return EpisodeRow(
        episode_id=f"e{arm}{passed}{unexpected}{violations}", run_id="r", task_id="t",
        suite="s", contract_sha256="h", arm=arm, passed=passed,
        assertions_passed=passed, invariant_passed=passed, invariant_declared=True,
        unexpected_changes=[{"path": f"p{i}"} for i in range(unexpected)],
        count_violations=[{"want": 1, "got": 1 + violations}] if violations else [],
        termination=termination,
    ).model_dump()


def test_the_row_carries_count_violations():
    row = _row("a", False, violations=200)
    assert row["count_violations"] == [{"want": 1, "got": 201}]


def test_a_clean_competitor_reports_no_collateral():
    m = competitor_metrics([_row("safe", True), _row("safe", True)], k=1)
    assert m["collateral_attempts"] == 0
    assert m["collateral_changes"] == 0


def test_a_messy_competitor_is_told_apart_from_a_safe_one():
    """Same pass rate, very different blast radius."""
    safe = competitor_metrics([_row("safe", True), _row("safe", False)], k=1)
    messy = competitor_metrics(
        [_row("messy", True, unexpected=3), _row("messy", False, violations=200)], k=1)
    assert safe["strict_pass"]["mean"] == messy["strict_pass"]["mean"]
    assert safe["collateral_changes"] == 0
    assert messy["collateral_changes"] == 203, "3 unexpected + 200 extra writes"
    assert messy["collateral_attempts"] == 2


def test_infrastructure_attempts_do_not_count_as_collateral():
    rows = [_row("a", False, unexpected=5, termination="infra:rate_limit")]
    assert competitor_metrics(rows, k=1)["collateral_attempts"] == 0
