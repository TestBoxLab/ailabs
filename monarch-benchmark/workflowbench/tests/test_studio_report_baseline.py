"""A run without a Bare setup borrows the Bare rows of an earlier finished run on
the same frozen tasks with the same model and thinking setting, and says so.
Nothing is re-run; a run with a different model, tasks or thinking is ignored."""
import json

from tests.test_studio_reports import studio  # noqa: F401  (fixture)
from wb_results.evidence import write_json
from wb_studio import report_data
from wb_world.episode import contract_hash

MODEL = "gemini-3.7-flash"


def arm(identity, kind, runner, **extra):
    return {"id": identity, "name": extra.pop("name", identity), "kind": kind, "runner": runner, **extra}


def write_run(studio, identity, arms, results, *, title=None, finished_at="2026-09-08T12:00:00+00:00", tasks=None, track="agentic-request"):
    tasks = tasks or list(studio.tasks)
    job = {"id": identity, "title": title or identity, "status": "completed", "created_at": finished_at, "finished_at": finished_at,
           "settings": {"tasks": tasks, "models": [a["id"] for a in arms], "arms": arms, "track": track, "concurrency": 1, "maximum_usd": "1.00"},
           "task_hashes": {t: contract_hash(studio.tasks[t]) for t in tasks}, "results": results, "completed": len(results), "total": len(results)}
    (studio.directory / identity).mkdir(parents=True, exist_ok=True)
    write_json(studio.directory / identity / "job.json", job)
    (studio.directory / identity / "events.jsonl").write_text("", encoding="utf-8")
    return job


def rows(model, verdicts):
    return [{"task": task, "model": model, "passed": passed, "termination": "completed", "cost_usd": "0.10", "tokens": {}, "checks": [], "unexpected_changes": [], "flags": []}
            for task, passed in verdicts.items()]


def test_a_matching_bare_run_becomes_the_baseline_and_is_named(studio):
    tasks = list(studio.tasks)
    bare = arm("without-monarch", "native", {"model": MODEL, "effort": "default"}, version="without-monarch", name="Bare Gemini 3.7 Flash")
    write_run(studio, "bare-earlier", [bare], rows("without-monarch", {tasks[0]: False, tasks[1]: False}), title="Bare, 8 Sep", finished_at="2026-09-08T10:00:00+00:00")
    write_run(studio, "bare-latest", [bare], rows("without-monarch", {tasks[0]: True, tasks[1]: False}), title="Bare, 9 Sep", finished_at="2026-09-09T10:00:00+00:00")
    subject = arm("arch-v3", "version", {"model": MODEL, "effort": "default"}, name="Architecture v3")
    write_run(studio, "subject", [subject], rows("arch-v3", {tasks[0]: True, tasks[1]: True}), title="Architecture v3 alone", finished_at="2026-09-09T12:00:00+00:00")

    report = report_data.run_report(studio, "subject")
    assert report["baseline"] == "without-monarch"
    assert report["baseline_source"] == {"run": "bare-latest", "title": "Bare, 9 Sep", "finished_at": "2026-09-09T10:00:00+00:00"}
    # one task differs out of two: a direction the sign test cannot support is not a grade
    assert report["grade"]["grade"] == "Undecided" and "better than Bare on 1 task" in report["grade"]["reason"]
    assert "Bare, 9 Sep" in report["verdict"] and "recorded earlier" in report["verdict"]
    assert any("reused from the run \"Bare, 9 Sep\"" in c for c in report["caveats"])
    assert "without-monarch" in report["order"] and report["setups"]["without-monarch"]["is_baseline"]
    # the borrowed rows are the newest matching run's, untouched
    assert report["setups"]["without-monarch"]["pass"]["passed"] == 1
    assert json.loads((studio.directory / "subject" / "job.json").read_text(encoding="utf-8"))["settings"]["arms"] == [subject]


def test_no_match_means_not_comparable_with_the_reason(studio):
    tasks = list(studio.tasks)
    other_model = arm("without-monarch", "native", {"model": "gpt-5.6-sol", "effort": "default"}, version="without-monarch", name="Bare GPT")
    write_run(studio, "bare-other-model", [other_model], rows("without-monarch", {tasks[0]: True, tasks[1]: True}))
    other_thinking = arm("without-monarch", "native", {"model": MODEL, "effort": "high"}, version="without-monarch", name="Bare high")
    write_run(studio, "bare-other-thinking", [other_thinking], rows("without-monarch", {tasks[0]: True, tasks[1]: True}))
    fewer_tasks = arm("without-monarch", "native", {"model": MODEL, "effort": "default"}, version="without-monarch", name="Bare partial")
    write_run(studio, "bare-partial", [fewer_tasks], rows("without-monarch", {tasks[0]: True}), tasks=tasks[:1])
    subject = arm("arch-v3", "version", {"model": MODEL, "effort": "default"}, name="Architecture v3")
    write_run(studio, "subject", [subject], rows("arch-v3", {tasks[0]: True, tasks[1]: True}))

    report = report_data.run_report(studio, "subject")
    assert report["baseline"] is None and report["baseline_source"] is None
    assert report["grade"]["grade"] == "Not comparable"
    assert any("no earlier run recorded one" in c for c in report["caveats"])


def test_a_bare_only_run_is_not_compared_with_itself(studio):
    tasks = list(studio.tasks)
    bare = arm("without-monarch", "native", {"model": MODEL, "effort": "default"}, version="without-monarch", name="Bare Gemini 3.7 Flash")
    write_run(studio, "bare-only", [bare], rows("without-monarch", {tasks[0]: False}), title="Bare alone")

    report = report_data.run_report(studio, "bare-only")
    assert report["grade"] == {"grade": "Not comparable", "reason": "only the Bare baseline ran"}
    assert report["verdict"].count("Bare Gemini 3.7 Flash") == 1 and "against" not in report["verdict"]


def test_attempts_on_moved_hashes_are_marked_non_comparable(stored_run):
    studio, job = stored_run
    report = report_data.run_report(studio, stored_run.run_id)
    moved_tasks = {
        "operations.access_request_validation",
        "simple.airtable_create_contact",
        "support.freshdesk_auto_merge",
        "finance.annual_budget_prep",
    }
    by_id = {t["id"]: t for t in report["tasks"]}
    for task_id in moved_tasks:
        assert by_id[task_id]["comparable"] is False
        assert by_id[task_id]["liveness"] == "superseded"
    live_tasks = set(by_id) - moved_tasks
    assert len(live_tasks) == 6
    for task_id in live_tasks:
        assert by_id[task_id]["comparable"] is True
        assert by_id[task_id]["liveness"] == "live"

    for key, cell in report["matrix"].items():
        task = key.split()[0]
        if task in moved_tasks:
            assert cell["comparable"] is False
            assert cell["liveness"] == "superseded"
        else:
            assert cell["comparable"] is True
            assert cell["liveness"] == "live"

    for attempt in report["failures"]["attempts"]:
        if attempt["task"] in moved_tasks:
            assert attempt["comparable"] is False
            assert attempt["liveness"] == "superseded"
        else:
            assert attempt["comparable"] is True
            assert attempt["liveness"] == "live"


def test_superseded_attempts_excluded_from_headline_figures(stored_run):
    studio, job = stored_run
    report = report_data.run_report(studio, stored_run.run_id)
    assert "passed 1 of 6 tasks" in report["verdict"]
    assert "2 of 10 tasks" not in report["verdict"]

    hero = report["hero"][0]
    assert hero["attempts"] == 6
    assert hero["passed"] == 1
    assert "1 / 6" in hero["detail"]

    count_findings = [f for f in report["findings"] if f["kind"] == "count"]
    if count_findings:
        assert "1 of 6 tasks" in count_findings[0]["text"]



