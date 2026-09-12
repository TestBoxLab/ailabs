"""An experiment is sized for the test that decides it.

Feature 024, FR-021 / R11. Two functions in one module disagreed about the statistics:

  genesis_hypotheses.smallest_plan   n = ceil(4·p·(1−p)/d²), floored at 10 tasks
                                     — a two-proportion normal approximation for
                                       INDEPENDENT samples
  genesis_hypotheses.settle          measures.paired -> measures.sign_test
                                     — a two-sided sign test with ties DROPPED

A paired sign test's power depends on how many tasks the two setups actually disagree
on, not on how many tasks were run. Below six discordant pairs no win count reaches
p < 0.05 — not a perfect sweep, not anything. Ten tasks typically yield three or four.
So the lab's sizing function recommended, and its floor enforced, experiments that its
own settling function could never conclude, and every tier set in the repository is ten
tasks.

This is the arithmetic, from sign_test itself:

    discordant pairs   2  3  4  5   6  7  8  9 10 11 12 13 14 15
    wins for p<0.05    -  -  -  -   6  7  8  8  9 10 10 11 12 12

The fix sizes against the sign test and refuses what it cannot settle, before any money
is reserved. No new statistics: both functions already exist.
"""
from __future__ import annotations

import pytest

from wb_studio.measures import minimum_discordant_pairs, sign_test, wins_needed


def test_below_six_pairs_no_win_count_can_reach_significance():
    for n in range(0, 6):
        assert wins_needed(n) is None, f"{n} discordant pairs should be unsettleable"
        for w in range(n + 1):
            assert sign_test(w, n - w) is None or sign_test(w, n - w) >= 0.05


def test_six_is_the_floor_and_it_needs_a_clean_sweep():
    assert minimum_discordant_pairs() == 6
    assert wins_needed(6) == 6
    assert sign_test(6, 0) < 0.05


@pytest.mark.parametrize("pairs,wins", [(7, 7), (8, 8), (9, 8), (10, 9), (12, 10), (15, 12), (20, 15)])
def test_the_table_matches_the_test_that_settles_it(pairs, wins):
    assert wins_needed(pairs) == wins
    assert sign_test(wins, pairs - wins) < 0.05
    assert sign_test(wins - 1, pairs - wins + 1) >= 0.05


def test_wins_needed_never_exceeds_the_pairs_available():
    for n in range(6, 40):
        assert wins_needed(n) <= n


# --- turning a task count into an expected number of discordant pairs ------------------

def test_ten_tasks_at_one_repetition_cannot_be_settled():
    from wb_studio.measures import settleable
    verdict = settleable(tasks=10, repetitions=1)
    assert verdict["ok"] is False
    assert verdict["expected_pairs"] < 6
    reason = verdict["reason"].lower()
    assert ("6" in reason or "six" in reason) and "10 tasks" in reason


def test_the_development_slate_at_three_repetitions_can_be():
    from wb_studio.measures import settleable
    verdict = settleable(tasks=50, repetitions=3)
    assert verdict["ok"] is True
    assert verdict["expected_pairs"] >= 6
    assert verdict["wins_needed"] <= verdict["expected_pairs"]


def test_the_refusal_says_what_would_be_enough():
    from wb_studio.measures import settleable
    verdict = settleable(tasks=10, repetitions=1)
    assert verdict["sufficient_tasks"] is not None
    assert settleable(tasks=verdict["sufficient_tasks"], repetitions=1)["ok"] is True


def test_the_assumed_flip_rate_is_stated_not_hidden():
    from wb_studio.measures import settleable
    verdict = settleable(tasks=10, repetitions=1)
    assert 0 < verdict["flip_rate"] <= 1
    assert str(verdict["flip_rate"]) in verdict["reason"] or "flip" in verdict["reason"].lower()


def test_a_caller_may_state_its_own_flip_rate():
    from wb_studio.measures import settleable
    optimistic = settleable(tasks=10, repetitions=1, flip_rate=0.9)
    assert optimistic["ok"] is True and optimistic["expected_pairs"] >= 6
