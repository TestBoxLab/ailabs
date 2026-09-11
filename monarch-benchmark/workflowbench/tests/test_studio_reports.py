"""Reports read verdict first, show every setup that ran, and say what they
leave out; every number comes from stored records."""
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
    assert list(report)[:5] == ["version", "run", "title", "status", "created_at"]
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


def test_one_report_shows_every_setup_including_lab_ones(studio, tmp_path):
    """There is one report: a lab competitor is a setup like any other."""
    job = finished_run(studio)
    # Rename one setup to a lab competitor in the stored record.
    folder = studio.directory / job["id"]
    record = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    record["settings"]["arms"] = [{"id": "oracle", "name": "oracle", "kind": "scripted"}, {"id": "sloppy", "name": "monarch-lab-sloppy", "kind": "lab"}]
    (folder / "job.json").write_text(json.dumps(record), encoding="utf-8")
    report = report_data.run_report(studio, job["id"])
    assert report["order"] == ["oracle", "sloppy"]
    assert report["setups"]["sloppy"]["name"] == "monarch-lab-sloppy"
    assert not any("internal" in c for c in report["caveats"])


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
    # with a recorded sign test the word carries the same certainty as the sentence
    weak = setup(3, 1); weak["paired"]["p_value"] = 0.625
    assert report_data.grade(weak, base)["grade"] == "Undecided" and "p = 0.62" in report_data.grade(weak, base)["reason"]
    strong = setup(9, 0); strong["paired"]["p_value"] = 0.004
    assert report_data.grade(strong, base)["grade"] == "Improvement"
    # with a recorded sign test the word carries the same certainty as the sentence
    weak = setup(3, 1); weak["paired"]["p_value"] = 0.625
    assert report_data.grade(weak, base)["grade"] == "Undecided" and "p = 0.62" in report_data.grade(weak, base)["reason"]
    strong = setup(9, 0); strong["paired"]["p_value"] = 0.004
    assert report_data.grade(strong, base)["grade"] == "Improvement"
    assert report_data.grade(setup(3, 1), None)["grade"] == "Not comparable"


def test_caveats_come_from_data():
    m = {"setups": {"a": {"name": "Arch", "pass": {"infrastructure": 1}, "cost": {"unknown_attempts": 2, "total": None}},
                    "b": {"name": "Bare", "pass": {"infrastructure": 0}, "cost": {"unknown_attempts": 0, "total": 1.0}}},
         "unrecorded_attempts": 3, "planned_attempts": 20, "baseline": "b", "repetitions": 2}
    job = {"settings": {"arms": [{"id": "a", "runner": {"effort": "high"}}, {"id": "b", "runner": {"effort": "low"}}]}}
    out = caveats.for_run(job, m, {"status": "pending", "reason": "the weekly ledger cannot cover $0.50."})
    text = "\n".join(out)
    assert "3 of 20 planned attempts" in text and "1 attempt stopped" in text and "Cost is unknown for Arch (2 attempts" in text
    assert "Thinking settings differ" in text and "ran 2 times" in text
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
    # Both rank 1, with a spread of 2. Two tasks cannot separate a setup that passed
    # both from one that failed both: Wilson over tasks gives [0.34, 1.0] against
    # [0.0, 0.66], which overlap. This asserted rank 2 while the rank came from a
    # Wilson interval over *attempts*, counting two repetitions of two tasks as four
    # independent samples — the narrowing feature 024 removed (FR-016).
    assert report["standings"][0]["pass_k"]["k"] == 2
    assert [s["rank"] for s in report["standings"]] == [1, 1]
    assert all(s["rank_high"] == 2 for s in report["standings"])
    assert all(s["rank_basis"] == "interval" for s in report["standings"])
    assert any("not the frozen benchmark of 50 tasks" in c for c in report["caveats"])
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



def test_the_report_keeps_the_timeline_and_the_reasoning(studio):
    job = finished_run(studio)
    task = list(studio.tasks)[0]
    # Slip one model turn with a reasoning summary into the sloppy attempt's record, before it finished.
    log = studio.directory / job["id"] / "events.jsonl"
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    at = next(i for i, e in enumerate(events) if e["type"] == "attempt_finished" and e["task"] == task and e["model"] == "sloppy")
    events.insert(at, {"type": "model_finished", "at": events[at]["at"], "task": task, "model": "sloppy", "output": "I changed it.",
                       "reasoning": ["Private plan: patch the phone field."], "stop_reason": "end_turn"})
    log.write_text("".join(json.dumps({**e, "id": i + 1}) + "\n" for i, e in enumerate(events)), encoding="utf-8")
    report = report_data.run_report(studio, job["id"])
    turns = [t for a in report["failures"]["attempts"] if a["story"] for t in a["story"]["timeline"]]
    assert turns and any("Private plan" in t["reasoning"] for t in turns)
    assert any("Private plan" in t["sentence"] for t in turns)


def test_googleads_write_does_not_render_as_gmail(stored_run):
    from wb_studio.reports import outcome_report
    events = stored_run.studio.events(stored_run.run_id)
    report = outcome_report(stored_run.job, events, stored_run.studio.tasks)
    ad_audit = next(a for a in report["attempts"] if a["task"] == "marketing.ad_platform_audit")
    googleads_writes = [
        act for act in ad_audit["actions"]
        if "googleads.googleapis.com" in (act.get("url") or "") and act.get("method") == "POST"
    ]
    assert googleads_writes, "Expected at least one googleads POST write in stored run"
    for write_action in googleads_writes:
        assert "Gmail" not in write_action["title"], f"googleads write rendered as Gmail: {write_action['title']}"
        assert "Google Ads" in write_action["title"], f"googleads write did not name Google Ads: {write_action['title']}"


def test_resolve_service_distinguishes_google_and_other_services():
    from wb_studio.reports import resolve_service
    assert resolve_service("https://googleads.googleapis.com/v19/customers/123/campaigns") == "Google Ads"
    assert resolve_service("https://sheets.googleapis.com/v4/spreadsheets/123") == "Google Sheets"
    assert resolve_service("https://www.googleapis.com/calendar/v3/calendars/primary") == "Google Calendar"
    assert resolve_service("https://calendar.googleapis.com/calendar/v3/events") == "Google Calendar"
    assert resolve_service("https://www.googleapis.com/drive/v3/files") == "Google Drive"
    assert resolve_service("https://drive.googleapis.com/drive/v3/files") == "Google Drive"
    assert resolve_service("https://gmail.googleapis.com/gmail/v1/users/me/messages") == "Gmail"
    assert resolve_service("https://my-instance.salesforce.com/services/data/v61.0/sobjects") == "Salesforce"
    assert resolve_service("https://api.airtable.com/v0/app123/Table") == "Airtable"
    assert resolve_service("https://slack.com/api/conversations.history") == "Slack"
    assert resolve_service("https://us1.api.mailchimp.com/3.0/campaigns") == "Mailchimp"
    assert resolve_service("https://subdomain.freshdesk.com/api/v2/tickets") == "Freshdesk"


def test_false_completion_finding_labels_signal_as_inferred_from_wording():
    from wb_studio import report_data
    from wb_studio.app import ROOT
    m = {
        "setups": {
            "a": {
                "id": "a",
                "name": "Model A",
                "pass": {"attempts": 10, "passed": 5, "rate": 0.5, "low": 0.2, "high": 0.8},
                "violations": {"attempts_with_changes": 0, "attempts": 10, "per_attempt": 0},
                "false_completion": {"count": 2, "failed": 5, "rate": 0.4},
                "cost": {"per_attempt": 0.1, "per_pass": 0.2},
            }
        }
    }
    findings = report_data.code_findings(m, ["a"], None, {})
    fc = next((f for f in findings if f["kind"] == "false_completion"), None)
    assert fc is not None
    assert "inferred from wording" in fc["text"]

    reports_js = (ROOT / "wb_studio" / "static" / "reports.js").read_text(encoding="utf-8")
    assert "inferred from wording" in reports_js


def test_no_finding_cites_a_bucket_the_narrative_contradicts(stored_run):
    from wb_studio.narrative import MODES
    studio, job = stored_run
    report = report_data.run_report(studio, stored_run.run_id)
    findings = report.get("findings", [])
    bucket_findings = [f for f in findings if (f.get("evidence") or {}).get("kind") == "bucket"]
    assert bucket_findings, "Expected at least one finding citing a failure bucket"
    mode_keys = set(MODES.keys())
    failure_bucket_ids = {b["id"] for b in report["failures"]["buckets"]}
    for f in bucket_findings:
        ref = f["evidence"]["ref"]
        assert ref in mode_keys, f"Finding evidence ref '{ref}' is not in MODES: {f}"
        assert ref in failure_bucket_ids, f"Finding evidence ref '{ref}' is not in failure_analysis buckets: {f}"
        matching_attempts = [
            a for a in report["failures"]["attempts"]
            if (a.get("story") or {}).get("mode") == ref or a.get("bucket") == ref
        ]
        assert len(matching_attempts) > 0, f"Finding cites bucket '{ref}', but no attempt narrative has that mode"


def test_trend_over_cohort_with_no_monarch_is_not_titled_monarch_pass_rate_by_run(studio):
    finished_run(studio, "round-a", title="First")
    finished_run(studio, "round-b", title="Second")
    cohort = next(iter(report_data.cohorts(studio).values()))
    report = report_data.round_report(studio, cohort["id"])
    assert len(report["trend"]) > 1
    assert not any("monarch" in t["series"].lower() for t in report["trend"])
    assert "Monarch" not in report.get("trend_title", "")
    assert "Scripted reference" in report.get("trend_title", "")

    reports_js = (ROOT / "wb_studio" / "static" / "reports.js").read_text(encoding="utf-8")
    assert "title: 'Monarch pass rate by run'" not in reports_js
    assert "family: 'monarch'" not in reports_js


def test_provisional_sentence_surfaced_in_round_report_when_judge_unpinned(studio):
    first = finished_run(studio, "round-a", title="First")
    second = finished_run(studio, "round-b", title="Second")
    for run_id in (first["id"], second["id"]):
        folder = studio.directory / run_id
        job_data = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        job_data["component_manifest"] = {}
        (folder / "job.json").write_text(json.dumps(job_data), encoding="utf-8")

    cohort = next(iter(report_data.cohorts(studio).values()))
    report = report_data.round_report(studio, cohort["id"])
    provisional_sentence = "Historical records lack a pinned judge; rankings are provisional."
    assert any(provisional_sentence in c for c in report["caveats"])
    assert provisional_sentence in report.get("note", "")

    reports_js = (ROOT / "wb_studio" / "static" / "reports.js").read_text(encoding="utf-8")
    assert "r.note" in reports_js
