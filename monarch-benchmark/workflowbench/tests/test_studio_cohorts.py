"""Runs are pooled into one round only when the whole evaluation contract agrees.

Feature 024, FR-016 / R5. Two functions partitioned the same records by different
rules, and the weaker one was the one a person opened:

  report_data.cohorts   task hashes + track
  leaderboard.rank_records   task hashes + track + judge + assistance
                             + world manifest + workflow contract, and a stamped
                             note when the judge is not pinned

So a round report could pool a run graded by one judge with a run graded by another,
or a run on one world revision with a run on a different one, and rank them against
each other as though they were one measurement. PLAN.md §1.1 exists to stop exactly
that: nothing grades itself, and a config hash is recorded per run so two runs are
only comparable when the contract behind them is identical.

The stricter key was already written and tested. The fix is to call it, and to delete
the weaker one rather than leave a third rule in the codebase.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from wb_studio import report_data


def job(identity, *, judge="judge-v1", world="world-1", track="agentic-request",
        assistance="unattended", hashes=None):
    hashes = hashes or {f"t{i}": f"h{i}" for i in range(3)}
    return {"id": identity, "status": "completed", "created_at": "2026-09-11T00:00:00+00:00",
            "title": identity, "task_hashes": hashes,
            "component_manifest": {"judge": judge} if judge else {},
            "world_manifest": world,
            "settings": {"track": track, "assistance": assistance, "tasks": list(hashes),
                         "arms": [{"id": "a", "kind": "runner"}]},
            "results": [{"task": t, "model": "a", "passed": True, "termination": "stop",
                         "flags": [], "cost_usd": "0.01"} for t in hashes],
            "events": []}


def studio_of(*jobs):
    by_id = {j["id"]: j for j in jobs}
    return SimpleNamespace(directory=None, jobs=lambda: list(jobs),
                           job=lambda i: by_id[i], events=lambda i: [], tasks={})


def test_the_same_contract_pools_into_one_round():
    groups = report_data.cohorts(studio_of(job("a"), job("b")))
    assert len(groups) == 1
    assert {r["id"] for r in next(iter(groups.values()))["runs"]} == {"a", "b"}


@pytest.mark.parametrize("differs", [
    {"judge": "judge-v2"},
    {"world": "world-2"},
    {"assistance": "clarifying"},
    {"track": "create-and-run"},
])
def test_a_different_contract_is_a_different_round(differs):
    groups = report_data.cohorts(studio_of(job("a"), job("b", **differs)))
    assert len(groups) == 2, f"runs differing in {list(differs)} were pooled"


def test_a_round_with_no_pinned_judge_says_it_is_provisional():
    groups = report_data.cohorts(studio_of(job("a", judge=None), job("b", judge=None)))
    cohort = next(iter(groups.values()))
    assert "provisional" in (cohort.get("note") or "").lower()


def test_a_pinned_round_is_not_marked_provisional():
    cohort = next(iter(report_data.cohorts(studio_of(job("a"))).values()))
    assert "provisional" not in (cohort.get("note") or "").lower()


def test_pinned_and_unpinned_runs_are_never_pooled():
    groups = report_data.cohorts(studio_of(job("a"), job("b", judge=None)))
    assert len(groups) == 2


def test_one_rule_not_two():
    """The contract both surfaces partition on comes from one function."""
    from wb_studio.leaderboard import evaluation_contract
    assert callable(evaluation_contract)
