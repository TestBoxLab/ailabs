"""Out-of-process grading: the source's own check + our approval rule.

Nothing here touches a live episode; input is (task, snapshot0, snapshot1). That is
what "nothing grades itself" means in code, and it is why the positive check is a
class method on the world rather than a method on the attempt.

The verdict has two halves and needs both (T0 spec, Deliverable 3; `PLAN.md` §1):

  positive    "the expected result is present" -- the product's own checker, run as
              shipped. AutomationBench's assertion registry for the simulated API
              set; an external benchmark's own verifiers, unit tests or reward for
              the worlds added in feature 026.
  collateral  "and nothing else changed" -- ours, always, computed from our own
              before-and-after snapshots through `grader/invariant.py`, which is
              world-agnostic.

Where a source has its own side-effect finding (AppWorld does), it is recorded
beside ours and a disagreement is named rather than resolved.
"""
from __future__ import annotations

from typing import Any

from grader.invariant import check_invariant
from wb_world.snapshot import diff_snapshots


def grade(task: dict[str, Any], snapshot0: dict[str, Any], snapshot1: dict[str, Any],
          world: type | None = None, artifacts: Any = None) -> dict[str, Any]:
    """`world` is the adapter class of the product under test; the AutomationBench
    world when unnamed, which is every caller that predates feature 026."""
    if world is None:
        from wb_world.episode import Episode
        world = Episode
    info = task["info"]

    # A checker that cannot answer leaves the attempt ungraded, with the error kept.
    # It is never turned into a pass, and never into a fail: a broken verifier is a
    # fact about our run, not about the competitor.
    ungraded, error = False, None
    try:
        positive = world.positive_check(task, snapshot0, snapshot1, artifacts=artifacts)
    except Exception as exc:
        from wb_world.adapter import PositiveResult
        ungraded, error = True, f"{type(exc).__name__}: {exc}"
        positive = PositiveResult(passed=False, detail={}, source=getattr(world, "__name__", "?"),
                                  side_effects=None)

    from wb_world.episode import is_external
    external = is_external(task)
    reviewed = bool(info.get("approval_rule_reviewed"))
    changes = diff_snapshots(snapshot0, snapshot1)
    expected = info.get("expected_changes", [])
    if not expected and not external:
        expected = [{"service": "*", "path": "*", "op": "*"}]
    inv = check_invariant(
        changes,
        expected=expected,
        allowed=info.get("allowed_changes", []),
    )
    # Tasks without declared expected_changes fall back to positive-only strictness;
    # the wildcard above makes the invariant vacuous there, and we flag it.
    #
    # On an external world the key itself is the declaration, because a reviewed
    # empty list is the decision that nothing may change -- but only once someone
    # has reviewed it. The importers write `approval_rule_reviewed` for exactly this
    # reason, and tau2's writes the empty list either way, so without the flag an
    # unreviewed row would report a rule a person never read. The invariant stays
    # strict there, deliberately (an undeclared external rule accepts no change);
    # what this decides is only whether the record may call that rule declared.
    invariant_declared = (reviewed and "expected_changes" in info) if external else bool(info.get("expected_changes"))

    # How much this attempt touched that it was not asked to touch. Reported as a
    # number, not folded into pass/fail: a competitor that finishes more tasks by
    # making a bigger mess should be visible next to one that takes the safe path.
    collateral = len(inv["unexpected_changes"]) + sum(
        max(0, v["got"] - v["want"]) for v in inv.get("count_violations", []))

    # Two opinions about side effects, where the source has one. We do not reconcile
    # them: a disagreement is a finding, and hiding it would make the quieter of the
    # two checkers look authoritative.
    source_collateral = positive.side_effects
    disagreement = bool(source_collateral is not None
                        and _reads_clean(source_collateral) != (collateral == 0))

    return {
        "passed": positive.passed and inv["passed"] and not ungraded,
        "assertions_passed": positive.passed,
        "assertion_results": positive.detail.get("assertion_results", [])
                             if isinstance(positive.detail, dict) else [],
        "positive": positive.detail,
        "positive_source": positive.source,
        "source_collateral": source_collateral,
        "disagreement": disagreement,
        "ungraded": ungraded,
        "error": error,
        "invariant": inv,
        "invariant_declared": invariant_declared,
        "n_changes": inv["n_changes"],
        "collateral_damage": collateral,
    }


def _reads_clean(finding: Any) -> bool:
    """Whether a source's own side-effect finding says "nothing extra was touched".

    Sources spell it differently; the shapes we have seen are a list of collateral
    items, or a mapping holding one. Anything unrecognized is read as clean, because
    inventing a violation out of a shape we do not understand would be worse than
    missing one -- ours is the finding the verdict rests on either way.
    """
    if isinstance(finding, (list, tuple)):
        return not finding
    if isinstance(finding, dict):
        if type(finding.get("passed")) is bool:
            return finding["passed"]
        for key in ("collateral", "collateral_damage", "unexpected_changes", "fails", "failures"):
            if key in finding:
                return not finding[key]
    return True
