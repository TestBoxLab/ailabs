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


# --- the gap list: one evidence base, three renderings (FR-031, FR-032, FR-034) ---

def gap(id, kind, confirmed=False, statement="The engine re-plans after every step."):
    return report_data.gap_item(id=id, statement=statement, evidence_kind=kind,
                                confirmed=confirmed, evidence=[{"kind": "run", "id": "run-1"}])


def test_a_code_reading_is_never_a_peer_of_a_confirmed_result():
    """FR-032. One is measured; the other is somebody reading source. Listing them
    together invites a reader to weigh them the same, which is the whole defect."""
    items = [gap("g1", "confirmed-result", confirmed=True), gap("g2", "code-reading")]
    out = report_data.gap_list(items, audience="engine-team")
    assert [i["id"] for i in out["confirmed"]] == ["g1"]
    assert [i["id"] for i in out["indications"]] == ["g2"]
    # There is no flat list to render by accident.
    assert "items" not in out
    assert out["indications"][0]["internal_only"] is True
    assert out["confirmed"][0]["internal_only"] is False


def test_an_unconfirmed_result_is_an_indication_not_a_finding():
    """FR-032. `confirmed` is true only after a held-out confirmation."""
    out = report_data.gap_list([gap("g1", "confirmed-result", confirmed=False)], audience="lab")
    assert out["confirmed"] == [] and [i["id"] for i in out["indications"]] == ["g1"]
    assert "held-out" in out["indications"][0]["caveat"]


def test_the_three_renderings_come_from_one_base_and_none_contradicts_another():
    """FR-031, SC-011. Different words for different readers, never different facts."""
    items = [gap("g1", "confirmed-result", confirmed=True), gap("g2", "code-reading")]
    views = {a: report_data.gap_list(items, audience=a)
             for a in ("engine-team", "lab", "executive")}
    # Every rendering agrees about what is confirmed and what is only indicated.
    assert {a: [i["id"] for i in v["confirmed"]] for a, v in views.items()} == {
        "engine-team": ["g1"], "lab": ["g1"], "executive": ["g1"]}
    # ...and about the evidence under each item, which is the one base.
    for view in views.values():
        assert view["confirmed"][0]["evidence"] == [{"kind": "run", "id": "run-1"}]
    # Only the wording moves.
    assert len({views[a]["confirmed"][0]["text"] for a in views}) == 3
    assert views["engine-team"]["audience"] == "engine-team"


def test_an_export_drops_code_readings_and_says_how_many():
    """Facts from Monarch's code do not leave the lab, and their absence is stated."""
    items = [gap("g1", "confirmed-result", confirmed=True), gap("g2", "code-reading")]
    out = report_data.gap_list(items, audience="executive", exported=True)
    assert out["indications"] == [] and out["withheld"] == 1
    assert "1 item" in out["withheld_note"] and "code" in out["withheld_note"]


def test_a_gap_item_refuses_an_evidence_kind_it_does_not_know():
    with pytest.raises(ValueError, match="evidence_kind"):
        report_data.gap_item(id="g", statement="s", evidence_kind="vibes")


def test_a_round_with_nothing_reusable_says_so_instead_of_drawing_an_empty_curve(studio):
    """FR-029. The scripted checks configure nothing, so there is no break-even to plot."""
    finished_run(studio)
    cohort = next(iter(report_data.cohorts(studio).values()))
    report = report_data.round_report(studio, cohort["id"])
    assert report["curve"]["available"] is False
    assert "run it again" in report["curve"]["reason"] or "again" in report["curve"]["reason"]
    assert "curves" not in report["curve"]


def test_the_curve_is_drawn_only_for_a_competitor_that_configures_something_once():
    """A bare model pays per request by construction; giving it a configure step would
    invent the very asymmetry the figure exists to measure."""
    def row(task, model, passed, cost, phases=None):
        out = {"task": task, "model": model, "passed": passed, "termination": "completed",
               "cost_usd": cost, "seconds": 1.0, "tool_calls": 1, "checks": [], "flags": [],
               "unexpected_changes": [], "tokens": {}, "output": ""}
        if phases:
            out["phases"] = phases
        return out
    built = {"run": {"cost_usd": 0.30, "wall_clock_s": 3.0},
             "authoring": {"cost_usd": 0.20, "wall_clock_s": 2.0},
             "execution": {"cost_usd": 0.10, "wall_clock_s": 1.0}}
    groups = {
        "monarch": [row("t1", "monarch", True, 0.30, built), row("t2", "monarch", True, 0.30, built)],
        "bare": [row("t1", "bare", True, 0.50, {"run": {"cost_usd": 0.50, "wall_clock_s": 3.0}}),
                 row("t2", "bare", True, 0.50, {"run": {"cost_usd": 0.50, "wall_clock_s": 3.0}})],
    }
    out = report_data.break_even_block(groups, ["monarch", "bare"], "bare",
                                       {"monarch": "Monarch", "bare": "Bare Gemini"})
    assert out["available"] is True and len(out["curves"]) == 1
    curve = out["curves"][0]
    assert curve["id"] == "monarch" and curve["crossing"] == 1
    assert curve["configure_usd"] == pytest.approx(0.20)
    assert "Monarch" in curve["title"] and curve["comparator_name"] == "Bare Gemini"


@pytest.mark.parametrize('with_winner', [False, True])
def test_recorded_setup_versions_remain_separate_in_every_report_view(studio, with_winner):
    job = finished_run(studio, models=('sloppy',))
    folder = studio.directory / job['id']
    record = json.loads((folder / 'job.json').read_text(encoding='utf8'))
    version = 'monarch@0cf63a74e+feat/railway-dev-deploy*'
    other_version = 'monarch@different-build+feat/railway-dev-deploy*'
    template = record['results'][0]
    for index in range(18):
        passed = index < 4
        record['results'].append({**template, 'episode_id': 'versioned-' + str(index),
            'model': version if index < 17 else other_version, 'passed': passed,
            'checks': [{'type': 'field_equals', 'passed': passed}, {'type': 'allowed_changes_only', 'passed': True}],
            'unexpected_changes': []})
    if with_winner:
        record['results'].extend({**template, 'episode_id': 'winner-' + str(i), 'model': 'glm-5.3-fireworks/api',
                                  'passed': i < 7} for i in range(13))
    (folder / 'job.json').write_text(json.dumps(record), encoding='utf8')
    report = report_data.run_report(studio, job['id'])
    expected_order = ['sloppy', version, other_version] + (['glm-5.3-fireworks/api'] if with_winner else [])
    assert report_data.setup_ids(record) == report['order'] == expected_order
    assert report['setups'][version]['pass']['attempts'] == 17
    assert report['setups'][version]['pass']['passed'] == 4
    assert report['setups'][other_version]['pass']['attempts'] == 1
    heroes = {row['id']: row for row in report['hero']}
    assert (heroes[version]['passed'], heroes[version]['attempts'], heroes[version]['value']) == (4, 17, 4 / 17)
    attempts = [row for row in report['failures']['attempts'] if row['model'] == version]
    assert len(attempts) == 17 and sum(row['passed'] for row in attempts) == 4
    column = next(row for row in report['patterns']['setups'] if row['id'] == version)
    assert column['total'] == 17
    assert next(row for row in column['checks'] if row['id'] == 'passed')['percent'] == 23.53
    if with_winner:
        assert report['subject'] == 'glm-5.3-fireworks/api'
        assert report['verdict'].startswith('GLM 5.3 (Fireworks) passed 7 of 13 tasks')
        assert 'Monarch (build 0cf63a74e) passed 4 of 17 attempts (23.53%).' in report['verdict']
        assert 'Monarch (build different-build) passed 0 of 1 attempt (0.00%).' in report['verdict']
    else:
        assert report['subject'] == version and 'passed 4 of 17 tasks' in report['verdict']
    assert report['method']['planned_attempts'] == len(record['settings']['tasks'])
    assert report['method']['recorded_attempts'] == len(record['results'])
