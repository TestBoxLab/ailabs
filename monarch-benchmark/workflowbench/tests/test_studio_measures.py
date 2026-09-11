"""Report measures are pure counts over recorded results; unknown stays unknown."""
import math

import pytest

from wb_studio import measures


def result(task, model, passed, *, termination="completed", cost=0.10, checks=None, changes=(), flags=(), output="Done.", tokens=None, seconds=1.0, tool_calls=2):
    return {"task": task, "model": model, "passed": passed, "termination": termination, "cost_usd": cost,
            "checks": checks if checks is not None else [{"type": "field_equals", "passed": passed}, {"type": "allowed_changes_only", "passed": not changes}],
            "unexpected_changes": list(changes), "flags": list(flags), "output": output,
            "tokens": tokens or {"prompt": 100, "cached": 40, "cache_write": 10, "output": 20}, "seconds": seconds, "tool_calls": tool_calls}


def job(results, arms):
    tasks = sorted({r["task"] for r in results})
    return {"id": "run-1", "settings": {"tasks": tasks, "models": [a["id"] for a in arms], "arms": arms}, "results": results}


ARMS = [{"id": "arch-v1", "name": "Informed worker / v1", "kind": "version"},
        {"id": "gemini-bare", "name": "Bare Gemini", "kind": "native", "version": "without-monarch"}]

SIMPLE = [result("t1", "arch-v1", True), result("t2", "arch-v1", True), result("t3", "arch-v1", False, changes=[{"path": "x"}]),
          result("t1", "gemini-bare", True), result("t2", "gemini-bare", False), result("t3", "gemini-bare", False, output="I could not finish.")]


def test_wilson_interval_brackets_the_rate_and_handles_edges():
    low, high = measures.wilson(2, 3)
    assert low < 2 / 3 < high and 0 <= low and high <= 1
    assert measures.wilson(0, 0) == (None, None)
    assert measures.wilson(3, 3)[1] == 1.0
    assert measures.wilson(0, 3)[0] == 0.0


def test_pass_rate_excludes_infrastructure_and_counts_it():
    rows = [result("t1", "a", True), result("t2", "a", False), result("t3", "a", False, termination="infra:timeout")]
    out = measures.pass_rate(rows)
    assert (out["passed"], out["attempts"], out["infrastructure"]) == (1, 2, 1)
    assert out["rate"] == 0.5 and out["low"] < 0.5 < out["high"]


def test_pass_k_is_none_without_repetitions_and_counts_all_passed_with_them():
    assert measures.pass_k(SIMPLE[:3])["k"] is None
    rows = [result("t1", "a", True), result("t1", "a", True), result("t2", "a", True), result("t2", "a", False)]
    out = measures.pass_k(rows)
    assert (out["k"], out["tasks"], out["all_passed"], out["rate"]) == (2, 2, 1, 0.5)


def test_objective_share_averages_checks_and_ignores_the_scope_check():
    rows = [result("t1", "a", False, checks=[{"type": "x", "passed": True}, {"type": "y", "passed": False}, {"type": "allowed_changes_only", "passed": True}]),
            result("t2", "a", True, checks=[{"type": "x", "passed": True}])]
    assert measures.objective_share(rows) == {"attempts": 2, "mean": 0.75}
    assert measures.objective_share([result("t1", "a", True, checks=[])])["mean"] is None


def test_violations_and_false_completion():
    rows = [r for r in SIMPLE if r["model"] == "arch-v1"]
    assert measures.violations(rows) == {"changes": 1, "attempts_with_changes": 1, "attempts": 3, "per_attempt": 1 / 3}
    bare = [r for r in SIMPLE if r["model"] == "gemini-bare"]
    out = measures.false_completion(bare)
    # t2 failed while saying "Done."; t3 failed without a completion claim.
    assert (out["count"], out["failed"], out["rate"]) == (1, 2, 0.5)


def test_cost_stays_unknown_when_any_attempt_lacks_billing():
    rows = [result("t1", "a", True, cost=0.5), result("t2", "a", True, cost=0.25, flags=["billing=unknown"])]
    out = measures.cost(rows)
    assert out["total"] is None and out["unknown_attempts"] == 1 and out["per_pass"] is None
    known = measures.cost([result("t1", "a", True, cost=0.5), result("t2", "a", False, cost=0.25)])
    assert known["total"] == 0.75 and known["per_attempt"] == 0.375 and known["per_pass"] == 0.75
    assert known["tokens"] == {"prompt": 200, "cached": 80, "cache_write": 20, "output": 40, "uncached": 120}


def test_turns_count_model_finished_events_per_attempt():
    events = [{"type": "model_finished", "task": "t1", "model": "a"}, {"type": "model_finished", "task": "t1", "model": "a"},
              {"type": "node_finished", "task": "t1", "model": "a"}]
    out = measures.turns([result("t1", "a", True, tool_calls=3), result("t2", "a", False, tool_calls=1)], events)
    assert out == {"attempts": 2, "turns_mean": 1.0, "tool_calls_mean": 2.0, "turns_recorded": True}


def test_time_quantiles():
    rows = [result(f"t{i}", "a", True, seconds=s) for i, s in enumerate([5, 1, 3, 2, 4])]
    out = measures.time(rows)
    assert (out["median"], out["max"], out["attempts"]) == (3, 5, 5)
    assert measures.time([])["median"] is None


def test_overlap_jaccard_of_solved_sets():
    out = measures.overlap(measures.by_setup(SIMPLE))
    assert out == [{"a": "arch-v1", "b": "gemini-bare", "both": 1, "either": 2, "only_a": 1, "only_b": 0, "jaccard": 0.5}]


def test_sign_test_two_sided():
    assert measures.sign_test(0, 0) is None
    assert measures.sign_test(5, 0) == pytest.approx(2 / 32)
    assert measures.sign_test(2, 2) == 1.0


def test_paired_delta_only_on_identical_task_sets():
    mine = [r for r in SIMPLE if r["model"] == "arch-v1"]
    theirs = [r for r in SIMPLE if r["model"] == "gemini-bare"]
    out = measures.paired(mine, theirs)
    assert out["comparable"] and (out["wins"], out["losses"], out["ties"]) == (1, 0, 2)
    assert out["delta"] == pytest.approx(1 / 3)
    assert out["p_value"] == 1.0
    partial = measures.paired(mine[:2], theirs)
    assert not partial["comparable"] and partial["reason"] == "task sets differ"
    hashed = measures.paired(mine, theirs, {"t1": "a", "t2": "b", "t3": "c"}, {"t1": "a", "t2": "b", "t3": "changed"})
    assert not hashed["comparable"] and hashed["reason"] == "task definitions differ"


def test_baseline_detection_prefers_native_bare_then_hint_then_control():
    assert measures.baseline_id(job([], ARMS)) == "gemini-bare"
    assert measures.baseline_id(job([], [{"id": "x", "name": "Opus bare", "kind": "runner"}])) == "x"
    assert measures.baseline_id(job([], [{"id": "without-monarch", "name": "API control", "kind": "runner"}])) == "without-monarch"
    assert measures.baseline_id(job([], [{"id": "a", "name": "Arch", "kind": "version"}])) is None


def test_run_measures_assembles_every_setup_and_pairs_against_bare():
    out = measures.run_measures(job(SIMPLE, ARMS), [])
    assert out["baseline"] == "gemini-bare" and out["order"] == ["arch-v1", "gemini-bare"]
    arch = out["setups"]["arch-v1"]
    assert arch["name"] == "Informed worker / v1" and arch["pass"]["passed"] == 2 and arch["paired"]["comparable"]
    assert out["setups"]["gemini-bare"]["paired"] is None and out["setups"]["gemini-bare"]["is_baseline"]
    assert (out["planned_attempts"], out["recorded_attempts"], out["unrecorded_attempts"], out["repetitions"]) == (6, 6, 0, 1)


def test_run_measures_reports_unrecorded_attempts_and_infrastructure():
    rows = SIMPLE[:2] + [result("t3", "arch-v1", False, termination="infra:attempt_cap", flags=["billing=unknown"])]
    out = measures.run_measures(job(rows, ARMS[:1]), [])
    setup = out["setups"]["arch-v1"]
    assert setup["pass"]["infrastructure"] == 1 and setup["pass"]["attempts"] == 2
    assert setup["cost"]["total"] is None and setup["cost"]["unknown_attempts"] == 1
    assert out["unrecorded_attempts"] == 0
    missing = measures.run_measures({"id": "r", "settings": {"tasks": ["t1", "t2", "t3", "t4"], "models": ["arch-v1"], "arms": ARMS[:1]}, "results": rows}, [])
    assert missing["unrecorded_attempts"] == 1


def test_sentinels_are_mutually_distinguishable():
    """T004: not_applicable is distinct from unknown, from None, and from zero."""
    assert measures.not_applicable is not measures.unknown
    assert measures.not_applicable != measures.unknown
    assert measures.not_applicable != 0
    assert measures.unknown != 0
    assert measures.not_applicable is not None
    assert measures.unknown is not None
    assert measures.is_not_applicable(measures.not_applicable)
    assert measures.is_unknown(measures.unknown)
    assert not measures.is_not_applicable(measures.unknown)
    assert not measures.is_unknown(measures.not_applicable)


def test_agent_error_turn_limit_attempts_produce_no_completion_claim(stored_run):
    agent_error_rows = [r for r in stored_run.job["results"] if r.get("termination") == "agent_error"]
    assert len(agent_error_rows) == 4, f"Expected 4 agent_error attempts, got {len(agent_error_rows)}"
    for r in agent_error_rows:
        claim = measures.false_completion([r])
        assert claim["count"] == 0, f"Attempt {r['task']} produced a completion claim: {r.get('output')}"
    assert measures.false_completion(agent_error_rows)["count"] == 0

