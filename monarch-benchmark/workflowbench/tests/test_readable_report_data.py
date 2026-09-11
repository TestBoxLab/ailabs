"""Readable report data keeps task/retry units and evidence scope explicit."""
import json

import pytest

from wb_studio import measures, report_data
from tests.test_studio_measures import result
from tests.test_studio_reports import studio, finished_run


def test_task_progress_uses_trial_identity_not_completion_order():
    rows = [{**result("a", "m", True, cost=.3), "trial": 2},
            {**result("a", "m", False, cost=.1), "trial": 0},
            {**result("a", "m", False, cost=.2), "trial": 1},
            {**result("b", "m", True), "trial": 0},
            {**result("c", "m", False, termination="infra:timeout"), "trial": 0}]
    progress = measures.task_progress(rows, ["a", "b", "c", "d"], repetitions=2)
    assert (progress["tasks"], progress["initial_solved"], progress["solved"]) == (4, 1, 2)
    assert (progress["evaluated_tasks"], progress["missing_tasks"], progress["infrastructure_tasks"]) == (2, 1, 1)
    assert progress["retries"] == 1 and progress["retry_cost"] == pytest.approx(.3)
    assert progress["states"] == {"a": "retry_pass", "b": "initial_pass", "c": "infrastructure", "d": "missing"}


def test_flagged_retries_keep_unknown_billing_and_time_unknown():
    rows = [result("a", "m", False, seconds=None), result("a", "m", True, flags=["retry", "billing=unknown"], seconds=None)]
    progress = measures.task_progress(rows, ["a"])
    assert progress["initial_solved"] == 0 and progress["solved"] == 1
    assert progress["retries"] == 1 and progress["retry_cost"] is None and progress["retry_unknown_costs"] == 1
    assert measures.time(rows)["median"] is None and measures.time(rows)["unknown_attempts"] == 2


def test_typical_duration_is_the_median_for_even_samples():
    assert measures.time([result("a", "m", True, seconds=2), result("b", "m", True, seconds=10)])["median"] == 6


def subject_run(studio):
    job = finished_run(studio)
    folder = studio.directory / job["id"]
    record = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    record["settings"]["arms"] = [{"id": "oracle", "name": "Scripted reference", "kind": "scripted"},
                                   {"id": "sloppy", "name": "Monarch", "kind": "monarch"}]
    (folder / "job.json").write_text(json.dumps(record), encoding="utf-8")
    return job, folder


def test_reading_subject_is_configured_monarch_not_highest_scoring_control(studio):
    job, folder = subject_run(studio)
    report = report_data.run_report(studio, job["id"])
    reading = report["reading"]
    assert reading["subject"] == report["subject"] == "sloppy"
    assert reading["status"] == "pending" and "Analysis pending" in reading["why"]
    assert len(reading["summary"].split()) <= 100
    assert reading["comparison"][0]["kind"] == "scripted"
    assert sum(b["count"] for b in reading["buckets"]) == 2
    assert sum(c["failed_attempts"] for c in reading["cases"]) == 2
    assert all(c["responsibility"] == "undetermined" and c["event_ids"] for c in reading["cases"])
    assert reading["actions"] == []
    assert all(c["state"] in ("initial_pass", "failed") for c in report["matrix"].values())


def test_reading_accepts_cited_diagnosis_and_retains_analysis_revision(studio):
    job, folder = subject_run(studio)
    event = next(e for e in studio.events(job["id"]) if e.get("model") == "sloppy" and e["type"] == "attempt_finished")
    data = {"status": "completed", "summary": "The cited attempt changed a field outside the request.",
            "headline": "An extra write failed the scope check", "why": "The cited scope check rejected an extra write.",
            "opening_event_ids": [event["id"]], "model": "Offline reviewer", "input_sha256": "revision-a",
            "aliases": {"sloppy": "Setup 2"}, "attempts": [{"task": event["task"], "model": "Setup 2",
            "diagnosis": "The attempt changed a field outside the request.", "responsibility": "Monarch", "failure_mode": "scope_violation", "event_ids": [event["id"]]}],
            "next_actions": [{"text": "Check write scope", "acceptance": "No extra field changes", "event_ids": [event["id"]]}]}
    (folder / "analysis.json").write_text(json.dumps(data), encoding="utf-8")
    reading = report_data.run_report(studio, job["id"])["reading"]
    assert reading["headline"] == data["headline"] and reading["summary"] == data["summary"]
    case = next(c for c in reading["cases"] if c["task"] == event["task"])
    assert case["responsibility"] == "Monarch" and case["diagnosis"] == data["attempts"][0]["diagnosis"]
    assert case["event_ids"] == [event["id"]]
    bucket = next(b for b in reading["buckets"] if b["id"] == "reviewed_scope_violation")
    assert bucket["count"] == 1 and bucket["basis"] == "Model interpretation"
    assert sum(b["count"] for b in reading["buckets"]) == sum(c["failed_attempts"] for c in reading["cases"])
    assert reading["analysis"]["input_sha256"] == "revision-a" and reading["actions"] == data["next_actions"]
    revision = reading["analysis"]["revision"]
    data["headline"] = "A revised finding on the same evidence"
    data["attempts"][0]["responsibility"] = "undetermined"
    data.pop("opening_event_ids")
    (folder / "analysis.json").write_text(json.dumps(data), encoding="utf-8")
    revised = report_data.run_report(studio, job["id"])["reading"]
    assert revised["analysis"]["revision"] != revision
    assert revised["status"] == "completed"


def test_hidden_competitors_cannot_leak_through_new_reading(studio):
    job, folder = subject_run(studio)
    record = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    record["settings"]["arms"][0]["name"] = "monarch-lab-secret"
    (folder / "job.json").write_text(json.dumps(record), encoding="utf-8")
    (folder / "analysis.json").write_text(json.dumps({"status": "completed", "summary": "SECRET hidden findings",
        "headline": "SECRET", "why": "SECRET", "limitations": "SECRET", "next_actions": [{"text": "SECRET"}]}), encoding="utf-8")
    report = report_data.run_report(studio, job["id"])
    reading = report["reading"]
    assert "SECRET" not in json.dumps(reading) and "monarch-lab-secret" not in json.dumps(reading)
    assert [r["id"] for r in reading["comparison"]] == ["sloppy"]
    assert reading["status"] == "pending" and reading["actions"] == []
    assert "SECRET" not in json.dumps(report["narrative"])
    assert report["failures"]["summary"]["recorded_attempts"] == 2
    assert report["method"]["recorded_attempts"] == report["method"]["planned_attempts"] == 2


def test_invalid_citations_never_become_a_diagnosis(studio):
    job, folder = subject_run(studio)
    event = next(e for e in studio.events(job["id"]) if e.get("model") == "oracle" and e["type"] == "attempt_finished")
    (folder / "analysis.json").write_text(json.dumps({"status": "completed", "headline": "Unsupported claim",
        "why": "Unsupported claim", "opening_event_ids": [999999], "attempts": [{"task": event["task"], "model": "sloppy",
        "diagnosis": "Unsupported claim", "responsibility": "Monarch", "event_ids": [event["id"]]}]}), encoding="utf-8")
    reading = report_data.run_report(studio, job["id"])["reading"]
    assert "Unsupported claim" not in json.dumps(reading)
    assert reading["status"] == "pending" and all(c["responsibility"] == "undetermined" for c in reading["cases"])
    own = next(e for e in studio.events(job["id"]) if e.get("model") == "sloppy" and e["type"] == "attempt_finished")
    (folder / "analysis.json").write_text(json.dumps({"status": "completed", "attempts": [{"task": own["task"], "model": "sloppy",
        "diagnosis": "Unsupported turning point", "event_ids": [own["id"]], "turning_point_event_id": event["id"]}]}), encoding="utf-8")
    assert "Unsupported turning point" not in json.dumps(report_data.run_report(studio, job["id"])["reading"])


def test_partial_run_preserves_retry_cost_missing_tasks_and_bucket_reconciliation(studio, monkeypatch):
    job, folder = subject_run(studio)
    job = studio.job(job["id"])
    task = job["settings"]["tasks"][0]
    initial = next(r for r in job["results"] if r["model"] == "sloppy" and r["task"] == task)
    job["results"] = [{**initial, "trial": 0, "cost_usd": None, "seconds": None},
                      {**initial, "trial": 1, "passed": True, "flags": ["retry"], "cost_usd": .4, "seconds": 4}]
    job["settings"].update(plan_semantics=True, repetitions=1, retry_on_fail=2)
    monkeypatch.setattr(studio, "job", lambda identity: job)
    report = report_data.run_report(studio, job["id"])
    reading = report["reading"]
    row = next(r for r in reading["comparison"] if r["id"] == "sloppy")
    assert (row["tasks"], row["initial_solved"], row["solved"], row["missing_tasks"], row["attempts"], row["retries"]) == (2, 0, 1, 1, 2, 1)
    assert row["retry_cost"] == .4 and row["cost"] is None and row["unknown_costs"] == row["unknown_times"] == 1
    assert row["median_seconds"] == 4 and reading["buckets"][0]["unknown_costs"] == 1
    assert reading["cases"][0]["cost"] is None and reading["buckets"][0]["count"] == 1
    assert "attempts" in report["verdict"] and "passed 1 of 2 tasks" not in report["verdict"]
    assert report["matrix"][f"{task} sloppy"]["state"] == "retry_pass"
    missing_task = job["settings"]["tasks"][1]
    assert report["matrix"][f"{missing_task} sloppy"]["state"] == "missing"


def test_script_only_success_and_failed_analysis_have_honest_empty_states(studio):
    job = finished_run(studio, models=("oracle",))
    reading = report_data.run_report(studio, job["id"])["reading"]
    assert reading["cases"] == reading["buckets"] == reading["actions"] == []
    assert "No failed attempts" in reading["why"]
    (studio.directory / job["id"] / "analysis.json").write_text('{"status":"failed"}', encoding="utf-8")
    assert report_data.run_report(studio, job["id"])["reading"]["status"] == "failed"


def test_configured_harness_identity_and_monarch_subject_survive_empty_arms(studio, monkeypatch):
    job = finished_run(studio)
    job["settings"]["arms"] = []
    job["settings"]["models"] = ["gpt/codex", "monarch@build"]
    job["resolved_config"] = {"plan": {"competitors": [{"model": "gpt", "harness": "codex"}]},
                              "harnesses": {"codex": {"kind": "cli"}}}
    job["results"] = [{**r, "model": "gpt/codex" if r["model"] == "oracle" else "monarch@build"} for r in job["results"]]
    monkeypatch.setattr(studio, "job", lambda identity: job)
    report = report_data.run_report(studio, job["id"])
    assert report["subject"] == "monarch@build"
    assert [r["kind"] for r in report["reading"]["comparison"]] == ["native", "monarch"]


def test_reused_baseline_keeps_its_own_initial_repetition_count(studio):
    from tests.test_studio_report_baseline import arm, write_run, MODEL
    task = next(iter(studio.tasks))
    bare = arm("without-monarch", "native", {"model": MODEL, "effort": "default"}, version="without-monarch")
    previous = write_run(studio, "bare-earlier", [bare], [{**result(task, "without-monarch", False), "trial": 0},
                                                        {**result(task, "without-monarch", True), "trial": 1}])
    previous["settings"]["repetitions"] = 2
    (studio.directory / "bare-earlier" / "job.json").write_text(json.dumps(previous), encoding="utf-8")
    subject = arm("arch", "version", {"model": MODEL, "effort": "default"})
    write_run(studio, "subject", [subject], [result(task, "arch", True)])
    report = report_data.run_report(studio, "subject")
    row = next(r for r in report["reading"]["comparison"] if r["id"] == "without-monarch")
    assert row["initial_solved"] == row["solved"] == 1 and row["retries"] == 0 and row["retry_cost"] == 0
    assert report["matrix"][f"{task} without-monarch"]["state"] == "initial_pass"
