"""Grading a world we did not write (feature 026, decision D1).

The source benchmark's own checker answers "is the expected result present?".
WorkflowBench answers "and nothing else changed", from its own snapshot diff. Both
are required; neither alone is a pass. These tests pin that split, and the three
ways it is allowed to go wrong.

Offline: no containers, no downloads, no network, no keys.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from grader.grade import grade
from wb_orchestrator import orchestrator as orch
from wb_world.adapter import PositiveResult
from wb_world.episode import Episode, load_task_file

TASKS = Path(__file__).resolve().parents[1] / "tasks" / "tier-simple"


def a_task() -> dict:
    return load_task_file(sorted(TASKS.glob("*.json"))[0])


def a_world(passed=True, detail=None, side_effects=None, raises=None, source="toy checker"):
    """A world that answers the positive half however the test needs."""

    class _World:
        artifacts_dir = None
        snapshot0 = None
        tool_calls = ()
        events = ()

        @classmethod
        def prerequisites(cls):
            return []

        @classmethod
        def positive_check(cls, task, snapshot0, snapshot1, artifacts=None):
            if raises is not None:
                raise raises
            return PositiveResult(passed=passed, detail=detail if detail is not None else {"checks": 1},
                                  source=source, side_effects=side_effects)

    return _World


# A world with one service and one row, so a change is easy to make and to name.
BEFORE = {"notes": {"rows": [{"id": 1, "text": "one"}]}}


def world_pair(after_rows):
    return copy.deepcopy(BEFORE), {"notes": {"rows": after_rows}}


def task_expecting_a_new_note() -> dict:
    return {"task": "toy.add_note", "prompt": "add a note",
            "info": {"assertions": [],
                     "expected_changes": [{"service": "notes", "op": "added", "path": "*"}],
                     "allowed_changes": []}}


# --- the positive half comes from the product -----------------------------------

def test_grade_uses_the_products_own_positive_check():
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1, world=a_world(passed=True))
    assert g["passed"] is True
    assert g["positive_source"] == "toy checker"
    assert g["ungraded"] is False


def test_a_failing_source_check_fails_the_attempt_even_with_a_clean_world():
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1, world=a_world(passed=False))
    assert g["passed"] is False
    assert g["invariant"]["passed"] is True, "the collateral half was satisfied; only the source's was not"


def test_a_task_with_no_positive_check_does_not_pass():
    """Preserved deliberately from before this feature: an imported row whose
    approval rule was never declared must not read as a success because there was
    nothing to check."""
    task = a_task()
    task["info"]["assertions"] = []
    ep = Episode(task, episode_id="no-checks")
    s0, s1 = ep.snapshot0, ep.finish()
    assert grade(task, s0, s1)["passed"] is False


# --- the collateral half is ours, on every world ---------------------------------

def test_the_right_result_plus_one_stray_change_is_a_failure():
    s0, s1 = world_pair([{"id": 1, "text": "EDITED"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1, world=a_world(passed=True))
    assert g["passed"] is False
    stray = g["invariant"]["unexpected_changes"]
    assert len(stray) == 1
    assert stray[0]["service"] == "notes" and stray[0]["after"] == "EDITED"


# --- a checker that cannot answer -------------------------------------------------

def test_a_checker_that_raises_leaves_the_attempt_ungraded():
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1,
              world=a_world(raises=RuntimeError("the verifier database was gone")))
    assert g["ungraded"] is True
    assert g["passed"] is False
    assert "verifier database was gone" in g["error"]
    assert g["assertions_passed"] is False


# --- an approval rule nobody reviewed ---------------------------------------------
#
# An undeclared external rule accepts no change, deliberately: see
# test_external_undeclared_collateral_rule_cannot_accept_changes. These pin the other
# half of that decision -- that the record must not call such a rule declared, since
# tau2's importer writes the empty list whether or not a person ever read one.

def an_external_task(info_extra) -> dict:
    """A task pinned to a world we did not write, the way the importers write one."""
    return {"task": "appworld.1", "prompt": "add a note",
            "info": {"world": {"package": "appworld", "version": "1"}, **info_extra}}


def test_an_unreviewed_external_rule_is_not_reported_as_declared():
    """The empty list alone is not a decision; `approval_rule_reviewed` is."""
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(an_external_task({"expected_changes": [], "approval_rule_reviewed": False}),
              s0, s1, world=a_world(passed=True))
    assert g["invariant_declared"] is False
    assert g["passed"] is False, "the strict rule still refuses the change"


def test_an_external_task_with_no_rule_at_all_is_not_declared():
    """AppWorld's importer writes no expected_changes unless a rule was reviewed."""
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    assert grade(an_external_task({}), s0, s1, world=a_world(passed=True))["invariant_declared"] is False


def test_a_reviewed_external_rule_grades_normally():
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(an_external_task({"expected_changes": [{"service": "notes", "op": "added", "path": "*"}],
                                "approval_rule_reviewed": {"reviewed_by": "Lucas"}}),
              s0, s1, world=a_world(passed=True))
    assert g["passed"] is True
    assert g["invariant_declared"] is True


def test_a_reviewed_empty_rule_means_nothing_may_change():
    """An explicitly empty list a person reviewed is a decision, not a missing one."""
    reviewed = {"expected_changes": [], "approval_rule_reviewed": True}
    assert grade(an_external_task(reviewed), copy.deepcopy(BEFORE), copy.deepcopy(BEFORE),
                 world=a_world(passed=True))["passed"] is True
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(an_external_task(reviewed), s0, s1, world=a_world(passed=True))
    assert g["passed"] is False
    assert g["invariant_declared"] is True


# --- two opinions about side effects ----------------------------------------------

def test_a_sources_own_side_effect_finding_is_recorded_beside_ours():
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1,
              world=a_world(passed=True, side_effects={"collateral": []}))
    assert g["source_collateral"] == {"collateral": []}
    assert g["disagreement"] is False


def test_a_disagreement_about_side_effects_is_visible_not_resolved():
    """Their check says clean, ours saw a stray edit. Both are kept and the
    disagreement is named; the verdict is a fail, because both halves are required."""
    s0, s1 = world_pair([{"id": 1, "text": "EDITED"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1,
              world=a_world(passed=True, side_effects={"collateral": []}))
    assert g["disagreement"] is True
    assert g["source_collateral"] == {"collateral": []}
    assert g["invariant"]["unexpected_changes"]
    assert g["passed"] is False


def test_no_source_finding_means_no_disagreement():
    s0, s1 = world_pair([{"id": 1, "text": "EDITED"}])
    g = grade(task_expecting_a_new_note(), s0, s1, world=a_world(passed=True))
    assert g["source_collateral"] is None
    assert g["disagreement"] is False


# --- the world comes from the product ---------------------------------------------

class _Plan:
    mode = "create-run"


class _Product:
    def __init__(self, world):
        self.world = world
        self.name = "p"


class _RunConfig:
    def __init__(self, world):
        self.product = _Product(world)
        self.plan = _Plan()


def test_the_orchestrator_builds_the_world_named_by_the_product():
    assert orch.world_for(_RunConfig("automation-bench")) is Episode
    assert orch.world_for(_RunConfig(None)) is Episode, "unnamed means the world we always had"
    assert orch.world_for(None) is Episode, "a run with no product file is the old path"


def test_the_orchestrator_refuses_an_unknown_world_by_name():
    from wb_world.registry import UnknownWorld

    with pytest.raises(UnknownWorld) as e:
        orch.world_for(_RunConfig("no-such-world"))
    assert "no-such-world" in str(e.value)


# --- nothing grades itself ---------------------------------------------------------

def test_grading_needs_only_the_stored_snapshots():
    """No live attempt, no live world: the inputs are two dictionaries and a task."""
    s0, s1 = world_pair([{"id": 1, "text": "one"}, {"id": 2, "text": "two"}])
    g = grade(task_expecting_a_new_note(), s0, s1, world=a_world(passed=True))
    assert g["passed"] is True
