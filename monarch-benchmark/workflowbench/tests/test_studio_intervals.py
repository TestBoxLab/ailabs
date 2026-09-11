"""One estimator behind a rank and the interval printed beside it, and no false certainty.

Feature 024, FR-016 / R6. Two problems, and they are not the ones the review first
named.

`leaderboard.uncertainty` is the *more* careful of the two estimators: with repetitions
it clusters by task rather than treating retries as independent samples, which
AI-LABS-DIRECTION.md:132 asks for in as many words. Replacing it with Wilson over
attempts — the review's suggestion — would have thrown that away and overstated
certainty on exactly the repeated runs feature 024 is adding. So it stays.

What is wrong:

1. **A zero-width 95% interval.** The clustered estimator uses the sample variance of
   the per-task shares. When every task scores the same — all pass, all fail, or every
   task passing the same fraction of its repetitions — that variance is zero and the
   interval collapses to a point. Three tasks that all passed produced "100%, 95% CI
   100 to 100". A sample variance of zero is not evidence of certainty; it is a
   degenerate estimator on a small sample, and the conservative binomial answer over
   the task count is what belongs there.
2. **Rank and interval came from different estimators.** The rank compared
   `measures.pass_rate`'s Wilson-over-attempts bounds while the row displayed
   `uncertainty`'s clustered bounds. With repetitions those disagree, so a reader saw a
   rank derived from an interval that was not the one on the page.
"""
from __future__ import annotations

import pytest

from wb_studio.leaderboard import uncertainty
from wb_studio.measures import wilson


def rows(shares, k=1):
    """One row per attempt: `shares[i]` is the fraction of task i's k repetitions that passed."""
    out = []
    for i, share in enumerate(shares):
        passes = round(share * k)
        for r in range(k):
            out.append({"task": f"t{i}", "passed": r < passes, "termination": "stop", "flags": []})
    return out


# --- 1: no interval is ever a point ----------------------------------------------------

@pytest.mark.parametrize("shares,k", [
    ([1.0, 1.0, 1.0], 2),      # every task passed every repetition
    ([0.0, 0.0, 0.0], 2),      # every task failed every repetition
    ([0.5, 0.5, 0.5], 2),      # every task passed the same half
    ([1.0] * 10, 3),
])
def test_an_interval_is_never_zero_width(shares, k):
    u = uncertainty(rows(shares, k))
    assert u["low"] is not None and u["high"] is not None
    assert u["high"] > u["low"], f"a 95% interval collapsed to a point at {u['rate']}"


def test_three_tasks_that_all_passed_do_not_claim_certainty():
    u = uncertainty(rows([1.0, 1.0, 1.0], k=2))
    assert u["rate"] == 1.0 and u["high"] == 1.0
    assert u["low"] < 0.8, "three tasks cannot support a lower bound above 80%"
    assert u["low"] == pytest.approx(wilson(3, 3)[0]), "the fallback is Wilson over tasks"


def test_the_degenerate_fallback_counts_tasks_not_attempts():
    """Ten tasks at three repetitions is ten observations, not thirty."""
    u = uncertainty(rows([1.0] * 10, k=3))
    assert u["low"] == pytest.approx(wilson(10, 10)[0])
    assert u["repetitions"] == 3 and u["tasks"] == 10


def test_a_varied_sample_keeps_the_clustered_interval():
    """The fix touches only the degenerate case; clustering is what protects repetitions."""
    u = uncertainty(rows([1.0, 0.5, 0.0], k=2))
    assert 0 <= u["low"] < u["rate"] < u["high"] <= 1


def test_one_repetition_is_still_wilson_over_attempts():
    u = uncertainty(rows([1.0, 1.0, 0.0], k=1))
    assert u["unit"] == "attempts"
    assert (u["low"], u["high"]) == pytest.approx(wilson(2, 3))


def test_a_single_task_says_it_cannot_tell_rather_than_guessing():
    """One task is not a sample. Absent bounds are honest; the defect was bounds of
    zero width, which claim certainty rather than admit ignorance."""
    u = uncertainty(rows([1.0], k=2))
    assert u["low"] is None and u["high"] is None


# --- 2: the rank and the printed interval agree ----------------------------------------

def test_the_rank_uses_the_interval_the_row_shows(tmp_path):
    """Through the real round report: every standings row is ranked on its own printed
    interval, and says so, so the two can never drift apart again unnoticed."""
    from types import SimpleNamespace
    from wb_studio import report_data
    job = {"id": "r1", "status": "completed", "created_at": "2026-09-11T00:00:00+00:00",
           "title": "A round", "settings": {"track": "agentic-request", "arms": [
               {"id": "a", "kind": "runner"}, {"id": "b", "kind": "runner"}]},
           "task_hashes": {f"t{i}": f"h{i}" for i in range(3)},
           "results": [{"task": f"t{i}", "model": m, "passed": m == "a", "termination": "stop",
                        "flags": [], "cost_usd": "0.01"}
                       for i in range(3) for m in ("a", "b")],
           "events": []}
    studio = SimpleNamespace(directory=tmp_path, jobs=lambda: [job], job=lambda i: job,
                             events=lambda i: [], tasks={})
    cohort_id = next(iter(report_data.cohorts(studio)))
    report = report_data.round_report(studio, cohort_id)
    assert report["standings"], "the round produced no standings"
    for row in report["standings"]:
        assert row["rank_basis"] == "interval"
        assert row["interval"]["low"] is not None and row["interval"]["high"] > row["interval"]["low"]
