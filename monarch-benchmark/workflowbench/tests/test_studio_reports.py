"""Reports read verdict first, hide lab setups from the public view, and say
what they leave out; every number comes from stored records."""
import json

import pytest

from wb_studio import caveats, report_data
from wb_studio.app import ROOT, Studio
from wb_world.episode import load_suite


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    def forbidden_gateway(*args, **kwargs):
        pytest.fail("An offline report test attempted paid dispatch")
    return Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:2], gateway_factory=forbidden_gateway)


def finished_run(studio, request_id="report-1", models=("oracle", "sloppy"), title="Answer key against sloppy"):
    job = studio.create({"request_id": request_id, "title": title, "models": list(models), "tasks": list(studio.tasks), "maximum_usd": "1.00"}, start=False)
    studio.execute(job["id"])
    return studio.job(job["id"])


def test_run_report_reads_verdict_first_with_findings_figures_caveats_and_method(studio):
    job = finished_run(studio)
    report = report_data.run_report(studio, job["id"])
    assert list(report)[:6] == ["version", "run", "title", "status", "audience", "created_at"]
    assert report["grade"]["grade"] == "Not comparable" and "Bare" in report["grade"]["reason"]
    assert report["verdict"].startswith("Scripted reference passed 2 of 2 tasks (100%")
    assert len(report["verdict"].split()) <= 120
    assert report["findings"] and all(f["evidence"] for f in report["findings"])
    assert {r["label"] for r in report["hero"]} == {"Scripted reference", "Near-miss control"}
    assert report["paired"] and set(report["paired"][0]["cells"]) == {"oracle", "sloppy"}
    assert report["failures"]["summary"]["failed_attempts"] == 2
    assert any("AutomationBench" in c and "not comparable" in c for c in report["caveats"])
    assert any(c.startswith("Each task ran once") for c in report["caveats"])
    assert report["method"]["task_count"] == 2 and report["method"]["runs"] == [job["id"]] and report["method"]["fork"]
    assert report["narrative"]["status"] == "pending"
    assert len(report["matrix"]) == 4 and all(cell["reps"] for cell in report["matrix"].values())


def test_public_view_hides_lab_setups_and_internal_shows_them(studio, tmp_path):
    job = finished_run(studio)
    # Rename one setup to a lab competitor in the stored record.
    folder = studio.directory / job["id"]
    record = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    record["settings"]["arms"] = [{"id": "oracle", "name": "oracle", "kind": "scripted"}, {"id": "sloppy", "name": "monarch-lab-sloppy", "kind": "scripted"}]
    (folder / "job.json").write_text(json.dumps(record), encoding="utf-8")
    public = report_data.run_report(studio, job["id"], audience="public")
    internal = report_data.run_report(studio, job["id"], audience="internal")
    assert public["order"] == ["oracle"] and public["hidden_setups"] == 1
    assert any("internal-only" in c for c in public["caveats"])
    assert internal["order"] == ["oracle", "sloppy"] and internal["hidden_setups"] == 0


def test_grade_rules():
    base = {"cost": {"per_attempt": 0.10}}
    def setup(wins, losses, ties=0, cost=0.10, comparable=True):
        return {"paired": {"comparable": comparable, "wins": wins, "losses": losses, "ties": ties, "reason": None if comparable else "task sets differ"}, "cost": {"per_attempt": cost}}
    assert report_data.grade(setup(3, 1), base)["grade"] == "Improvement"
    assert report_data.grade(setup(1, 3), base)["grade"] == "Regression"
    assert report_data.grade(setup(2, 2, 6), base)["grade"] == "Tie"
    assert report_data.grade(setup(3, 1, cost=0.20), base)["grade"] == "Tradeoff"
    assert report_data.grade(setup(1, 3, cost=0.05), base)["grade"] == "Tradeoff"
    assert report_data.grade(setup(3, 1, comparable=False), base)["grade"] == "Not comparable"
    assert report_data.grade(setup(3, 1), None)["grade"] == "Not comparable"


def test_caveats_come_from_data():
    m = {"setups": {"a": {"name": "Arch", "pass": {"infrastructure": 1}, "cost": {"unknown_attempts": 2, "total": None}},
                    "b": {"name": "Bare", "pass": {"infrastructure": 0}, "cost": {"unknown_attempts": 0, "total": 1.0}}},
         "unrecorded_attempts": 3, "planned_attempts": 20, "baseline": "b", "repetitions": 2}
    job = {"settings": {"arms": [{"id": "a", "runner": {"effort": "high"}}, {"id": "b", "runner": {"effort": "low"}}]}}
    out = caveats.for_run(job, m, {"status": "pending", "reason": "the weekly ledger cannot cover $0.50."}, hidden=["x"])
    text = "\n".join(out)
    assert "3 of 20 planned attempts" in text and "1 attempt stopped" in text and "Cost is unknown for Arch (2 attempts" in text
    assert "Thinking settings differ" in text and "ran 2 times" in text and "1 setup is internal-only" in text
    assert "Analysis pending: the weekly ledger cannot cover $0.50." in text and "No Bare baseline" not in text
    assert caveats.fork_version().startswith("1.0.6")


def test_rounds_group_runs_on_the_same_frozen_set_and_pool_repetitions(studio):
    first = finished_run(studio, "round-a", title="First")
    second = finished_run(studio, "round-b", title="Second")
    groups = report_data.cohorts(studio)
    assert len(groups) == 1
    cohort = next(iter(groups.values()))
    assert {r["id"] for r in cohort["runs"]} == {first["id"], second["id"]} and cohort["full_benchmark"] is False
    report = report_data.round_report(studio, cohort["id"])
    assert report["repetitions"] == 2 and report["standings"][0]["name"] == "Scripted reference" and report["standings"][0]["rank"] == 1
    assert report["standings"][0]["pass_k"]["k"] == 2 and report["standings"][1]["rank"] == 2
    assert any("not the frozen 50-task benchmark" in c for c in report["caveats"])
    index = report_data.index(studio)
    assert index["rounds"][0]["id"] == cohort["id"] and index["rounds"][0]["best"]["name"] == "Scripted reference"
    assert len(index["rounds"][0]["runs"]) == 2


def test_narrative_pending_for_scripted_runs_names_the_reason(studio):
    job = finished_run(studio)
    status = report_data.narrative_status(studio.directory / job["id"])
    assert status["status"] == "pending" and "Scripted" in status["reason"]

def test_round_standings_carry_intervals_over_tasks_pairings_and_excluded_runs(studio):
    finished_run(studio, "round-a", title="First")
    finished_run(studio, "round-b", title="Second")
    cohort = next(iter(report_data.cohorts(studio).values()))
    report = report_data.round_report(studio, cohort["id"])
    assert report["repetitions"] == 2
    assert all(s["interval"]["unit"] == "tasks" and s["interval"]["repetitions"] == 2 for s in report["standings"])
    [pair] = report["pairings"]
    assert {pair["a"], pair["b"]} == {"oracle", "sloppy"} and pair["tasks"] == 2
    assert pair["wins"] + pair["losses"] + pair["ties"] == 2
    assert sorted(e["title"] for e in report["excluded"]) == ["First", "Second"]
    assert all(e["reason"] == "not the frozen 50-task benchmark" for e in report["excluded"])

