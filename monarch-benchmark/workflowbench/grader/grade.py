"""Out-of-process grading: assertions + dual invariant from snapshot files.

Nothing here touches a live episode; input is (task, snapshot0, snapshot1).
The AB assertion registry supplies the positive checks; the invariant supplies
the collateral guard. (T0 spec, Deliverable 3.)
"""
from __future__ import annotations

from typing import Any

import automationbench.rubric.assertions  # noqa: F401  (registers handlers)
from automationbench.rubric.registry import AssertionRegistry
from automationbench.runner import strip_none_values
from automationbench.schema.world import WorldState

from grader.invariant import check_invariant
from wb_world.snapshot import diff_snapshots


def _world_from_snapshot(snap: dict[str, Any]) -> WorldState:
    return WorldState(**strip_none_values({k: v for k, v in snap.items() if k != "meta"}))


def grade(task: dict[str, Any], snapshot0: dict[str, Any], snapshot1: dict[str, Any]) -> dict[str, Any]:
    info = task["info"]
    world1 = _world_from_snapshot(snapshot1)

    assertion_results = []
    for a in info.get("assertions", []):
        ok = bool(AssertionRegistry.check(world1, a))
        assertion_results.append({"type": a.get("type"), "passed": ok, "assertion": a})
    assertions_passed = all(r["passed"] for r in assertion_results) if assertion_results else False

    changes = diff_snapshots(snapshot0, snapshot1)
    inv = check_invariant(
        changes,
        expected=info.get("expected_changes", []) or [{"service": "*", "path": "*", "op": "*"}],
        allowed=info.get("allowed_changes", []),
    )
    # Tasks without declared expected_changes fall back to assertion-only strictness;
    # the wildcard above makes the invariant vacuous there, and we flag it.
    invariant_declared = bool(info.get("expected_changes"))

    # How much this attempt touched that it was not asked to touch. Reported as a
    # number, not folded into pass/fail: a competitor that finishes more tasks by
    # making a bigger mess should be visible next to one that takes the safe path.
    collateral = len(inv["unexpected_changes"]) + sum(
        max(0, v["got"] - v["want"]) for v in inv.get("count_violations", []))

    return {
        "passed": assertions_passed and inv["passed"],
        "assertions_passed": assertions_passed,
        "assertion_results": assertion_results,
        "invariant": inv,
        "invariant_declared": invariant_declared,
        "n_changes": inv["n_changes"],
        "collateral_damage": collateral,
    }
