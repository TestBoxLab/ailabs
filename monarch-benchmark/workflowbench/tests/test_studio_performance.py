"""Live and permanent performance figures describe stored evidence, never guesses."""
from copy import deepcopy

import pytest

from wb_studio import measures
from wb_studio.performance import performance_report
from wb_studio.reports import outcome_report


def result(task="task-1", model="model-a", **fields):
    return {"task": task, "model": model, "passed": True, "termination": "completed",
            "seconds": 10, "cost_usd": 0.5, "tool_calls": 2, "checks": [],
            "unexpected_changes": [], "flags": [], **fields}


def job(rows=(), *, tasks=("task-1", "task-2"), models=("model-a",), repetitions=1):
    return {"id": "performance-run", "status": "running", "results": list(rows),
            "settings": {"tasks": list(tasks), "models": list(models), "repetitions": repetitions,
                         "arms": [{"id": m, "name": m.title()} for m in models]}}


def event(identity, kind, *, task="task-1", model="model-a", **fields):
    return {"id": identity, "type": kind, "task": task, "model": model, **fields}


def setup(rows, events=()):
    return performance_report(job(rows), events)["setups"]["model-a"]


def test_success_requires_normal_graded_finish_and_infrastructure_stays_in_operational_denominator():
    rows = [result(), result("failed", passed=False, seconds=40),
            result("timed-out", seconds=70, termination="timeout"),
            result("infra", seconds=100, termination="infra:harness_crash"),
            result("ungraded", seconds=200, flags=["grading=ungraded"])]
    out = setup(rows)
    assert (out["recorded"], out["passed"], out["failed"], out["infrastructure"]) == (5, 1, 2, 1)
    assert out["success_rate"] == pytest.approx(1 / 3)
    assert out["operational_success_rate"] == pytest.approx(1 / 5)
    assert out["timing"]["successful"]["values"] == [10]
    assert out["timing"]["failed"]["values"] == [40, 70]
    assert out["timing"]["all"]["values"] == [10, 40, 70, 100, 200]
    assert [a["passed"] for a in out["attempts"]] == [True, False, False, False, False]


def test_timing_interpolates_quantiles_and_reports_missing_without_inventing_zero():
    rows = [result(str(i), seconds=seconds) for i, seconds in enumerate([0, 10, 20, 30, None])]
    out = setup(rows)["timing"]["successful"]
    assert out == {"count": 4, "missing": 1, "median": 15, "p90": 27, "max": 30,
                   "values": [0, 10, 20, 30]}
    missing = result()
    del missing["seconds"]
    missing["started_at"], missing["finished_at"] = "2026-09-11T00:00:00Z", "2026-09-11T00:01:00Z"
    assert setup([missing])["timing"]["all"] == {
        "count": 0, "missing": 1, "median": None, "p90": None, "max": None, "values": []}


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf"), "invalid", True, {}])
def test_invalid_duration_is_missing_in_both_performance_and_existing_timing(invalid):
    rows = [result(seconds=invalid), result("valid", seconds=2)]
    assert setup(rows)["timing"]["all"]["values"] == [2]
    assert setup(rows)["timing"]["all"]["missing"] == 1
    assert measures.time(rows)["values"] == [2]
    assert measures.time(rows)["attempts"] == 1


def test_existing_timing_preserves_real_zero_and_skips_absent_duration():
    absent = result()
    del absent["seconds"]
    out = measures.time([absent, result(seconds=None), result(seconds=0), result(seconds=2)])
    assert out["values"] == [0, 2]
    assert out["attempts"] == 2


def test_cost_per_success_includes_failure_and_infrastructure_spend():
    out = setup([result(), result("failed", passed=False, cost_usd=1.5),
                 result("infra", termination="infra:harness_crash", cost_usd=3)])
    assert out["cost"] == {"total": 5, "known_subtotal": 5, "unknown_attempts": 0, "per_success": 5}
    assert setup([result(passed=False)])["cost"]["per_success"] is None


@pytest.mark.parametrize("fields", [{"cost_usd": None}, {"cost_usd": -1}, {"cost_usd": "nan"},
                                     {"cost_usd": 0, "flags": ["billing=unknown"]},
                                     {"cost_usd": 0, "flags": ["cost_missing"]}])
def test_unknown_billing_keeps_known_subtotal_and_withholds_total_and_ratio(fields):
    out = setup([result(), result("unknown", **fields)])
    assert out["cost"] == {"total": None, "known_subtotal": 0.5, "unknown_attempts": 1, "per_success": None}
    assert out["attempts"][1]["cost_usd"] is None


def test_terminal_tool_errors_and_turns_are_observed_once_despite_event_replay():
    events = [event(1, "model_finished"), event(2, "model_finished"),
              event(3, "node_finished", node="tool-0", status="completed", output='{"ok": true}'),
              event(4, "node_finished", node="tool-1", status="completed", output='{"error": {"message": "not found"}}'),
              event(5, "node_finished", node="tool-2", status="error", output="failed"),
              event(6, "node_finished", category="builder", status="error"),
              event(7, "workflow_step", status="failed"), event(8, "node_started", node="tool-pending"),
              event(9, "model_finished", model="other"),
              event(10, "node_finished", task="not-recorded", status="error")]
    out = setup([result(tool_calls=4)], events + [events[0], events[3]])
    assert out["tools"] == {"calls": 4, "errors": 2, "observed_calls": 3, "error_rate": pytest.approx(2 / 3)}
    assert out["turns"] == {"total": 2, "observed_attempts": 1}


def test_missing_tool_telemetry_never_implies_zero_error_rate_or_known_calls():
    row = result()
    del row["tool_calls"]
    out = setup([row])
    assert out["tools"] == {"calls": None, "errors": 0, "observed_calls": 0, "error_rate": None}
    assert out["turns"] == {"total": 0, "observed_attempts": 0}
    assert out["attempts"][0]["tool_calls"] is None


def test_repeated_task_model_results_do_not_multiply_events_or_invent_attempt_attribution():
    out = setup([result(), result(passed=False)], [event(1, "model_finished"),
                event(2, "node_finished", node="tool-0", status="completed")])
    assert out["recorded"] == 2 and out["passed"] == 1
    assert out["tools"]["observed_calls"] == 1
    assert out["turns"] == {"total": 1, "observed_attempts": 0}
    assert len(out["attempts"]) == 2


def test_explicit_attempt_ids_allow_repeated_attempt_turn_coverage():
    rows = [result(attempt_id="attempt-a"), result(attempt_id="attempt-b")]
    events = [event(1, "model_finished", attempt_id="attempt-a"),
              event(2, "model_finished", attempt_id="attempt-b")]
    assert setup(rows, events)["turns"] == {"total": 2, "observed_attempts": 2}


def test_phases_preserve_missing_values_and_do_not_double_count_total_or_model_cuts():
    rows = [result(phases={"run": {"wall_clock_s": 10}, "authoring": {"wall_clock_s": 6},
                          "execution": {"wall_clock_s": 4}, "model:opus": {"wall_clock_s": 10}}),
            result("second", phases={"authoring": {"wall_clock_s": None}, "execution": {"wall_clock_s": -1}}),
            result("no-phases")]
    out = setup(rows)["phases"]
    assert set(out) == {"authoring", "execution"}
    assert out["authoring"] == {"count": 1, "missing": 1, "median": 6, "p90": 6, "max": 6, "values": [6]}
    assert out["execution"]["values"] == [4] and out["execution"]["missing"] == 1


def test_collateral_includes_excess_requested_writes_and_excludes_infrastructure():
    rows = [result(unexpected_changes=[{"path": "extra"}], count_violations=[{"want": 1, "got": 3}]),
            result("missing", passed=False, count_violations=[{"want": 3, "got": 1}]),
            result("infra", termination="infra:harness_crash", unexpected_changes=[{"path": "other"}])]
    assert setup(rows)["collateral"] == {"attempts": 1, "changes": 3, "complete_attempts": 2, "missing_attempts": 0}


def test_empty_and_partial_runs_keep_planned_setups_without_fabricating_completion():
    planned = job(models=("model-b", "model-a"), repetitions=3)
    empty = performance_report(planned, [])
    assert empty["order"] == ["model-b", "model-a"]
    assert (empty["planned_attempts"], empty["recorded_attempts"]) == (12, 0)
    out = empty["setups"]["model-b"]
    assert (out["planned"], out["recorded"], out["name"]) == (6, 0, "Model-B")
    assert out["success_rate"] is None and out["operational_success_rate"] is None
    assert out["timing"]["all"]["median"] is None
    assert out["cost"]["per_success"] is None
    partial = performance_report({**planned, "results": [result()]}, [])
    assert (partial["recorded_attempts"], partial["setups"]["model-a"]["passed"]) == (1, 1)
    assert "performance-run" in partial["source"] and "1 recorded" in partial["source"]


def test_unlisted_recorded_model_is_retained_and_inputs_are_unchanged():
    original = job([result(model="unlisted")])
    events = [event(1, "model_finished", model="unlisted")]
    saved = deepcopy((original, events))
    out = performance_report(original, events)
    assert out["order"] == ["model-a", "unlisted"]
    assert out["setups"]["unlisted"]["recorded"] == 1
    assert out["setups"]["unlisted"]["planned"] == 0
    assert (original, events) == saved


def test_outcome_report_uses_the_shared_performance_projection():
    stored = job([result()])
    events = [event(1, "model_finished")]
    out = outcome_report(stored, events, {})
    assert out["performance"] == performance_report(stored, events)
    assert out["performance"]["setups"]["model-a"]["timing"]["successful"]["median"] == 10


def test_permanent_report_keeps_original_spend_when_task_hash_is_stale(tmp_path, monkeypatch):
    from tests.test_studio_report_baseline import arm, write_run
    from wb_studio.app import Studio
    from wb_studio.report_data import run_report

    task = {"task": "simple.local", "prompt": [{"role": "system", "content": "sys"},
            {"role": "user", "content": "local task"}], "info": {"initial_state": {}, "assertions": []}}
    studio = Studio(tmp_path / "studio", tasks=[task])
    stored = write_run(studio, "performance-run", [arm("model-a", "scripted", {})],
                       [result("simple.local", seconds=10, cost_usd=3)])
    studio.tasks["simple.local"]["prompt"][1]["content"] = "Different current task"
    out = run_report(studio, "performance-run")
    assert out["method"]["live_task_count"] == 0
    assert out["performance"] == performance_report(stored, [])
    assert out["performance"]["setups"]["model-a"]["cost"]["known_subtotal"] == 3


def test_mixed_attempt_identity_coverage_keeps_other_tasks_and_rejects_wrong_explicit_ids():
    rows = [result(attempt_id="attempt-a"), result("task-2")]
    events = [event(1, "model_finished", attempt_id="attempt-a"),
              event(2, "model_finished", task="task-2", attempt_id="older-format"),
              event(3, "model_finished", attempt_id="wrong-attempt")]
    assert setup(rows, events)["turns"] == {"total": 2, "observed_attempts": 2}


def test_events_without_ids_are_not_silently_collapsed_as_duplicate_delivery():
    events = [event(None, "model_finished"), event(None, "model_finished"),
              event(0, "tool_completed", status="failed"),
              event("0", "tool_completed", status="failed")]
    out = setup([result()], events)
    assert out["turns"] == {"total": 2, "observed_attempts": 1}
    assert out["tools"] == {"calls": 2, "errors": 1, "observed_calls": 1, "error_rate": 1}

def test_missing_collateral_detail_marks_known_counts_as_incomplete():
    rows = [result(unexpected_changes=[{"path": "extra"}]),
            result("complete", count_violations=[]),
            result("infra", termination="infra:harness_crash")]
    out = performance_report(job(rows), [])
    assert out["setups"]["model-a"]["collateral"] == {
        "attempts": 1, "changes": 1, "complete_attempts": 1, "missing_attempts": 1}
    assert "Collateral counts are a lower bound" in out["source"]
    missing = result(count_violations=[])
    del missing["unexpected_changes"]
    assert setup([missing])["collateral"]["missing_attempts"] == 1