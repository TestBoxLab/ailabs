"""Outcome mixes retain every attempt and distinguish behavior from checker results."""
from copy import deepcopy

import pytest

from wb_studio.report_patterns import patterns


def attempt(index, *, model="a", task="sales.contact", mode="missing_action", passed=False,
            checks=(), termination="completed", run="run-1", events=None):
    return {"id": f"attempt-{index + 1}", "run": run, "task": task, "model": model,
            "passed": passed, "termination": termination, "infrastructure": termination.startswith("infra:"),
            "story": {"mode": mode, "verdict": "Recorded explanation."},
            "checks": [{"name": k, "passed": v} for k, v in checks],
            "event_ids": events if events is not None else [index + 1]}


def slices(column, field="behavior"):
    return {s["id"]: s for s in column[field]}


def test_percentage_columns_use_each_setups_all_attempts_and_round_to_one_hundred():
    rows = [attempt(0, passed=True), attempt(1), attempt(2, termination="infra:provider"),
            attempt(3, model="b"), attempt(4, model="b")]
    result = patterns(rows, {"a": "Monarch", "b": "Bare", "empty": "No results"})
    a, b, empty = result["setups"]
    assert (a["total"], b["total"], empty["total"]) == (3, 2, 0)
    assert [s["count"] for s in a["behavior"] if s["count"]] == [1, 1, 1]
    assert sum(s["percent"] for s in a["behavior"]) == 100
    assert slices(b)["missing_action"]["percent"] == 100
    assert all(s["percent"] is None for s in empty["behavior"])
    assert "infrastructure" in result["denominator"]


def test_behavior_comes_from_story_and_does_not_promote_checker_outcomes_to_causes():
    rows = [attempt(0, mode="tool_error", checks=(("allowed_changes_only", False), ("field_equals", False))),
            attempt(1, mode="unrecognized", checks=(("field_equals", False),))]
    a = patterns(rows, {"a": "Monarch"})["setups"][0]
    assert slices(a)["tool_error"]["count"] == 1
    assert slices(a)["unclassified"]["count"] == 1
    assert slices(a, "checks")["scope_and_requirements"]["count"] == 1
    assert slices(a, "checks")["requirements"]["count"] == 1
    assert slices(a)["scope_violation"]["count"] == 0


def test_checker_partition_includes_both_failure_types_normal_finish_infra_and_unknown():
    rows = [attempt(0, passed=True), attempt(1, checks=(("allowed_changes_only", False),)),
            attempt(2, checks=(("field_equals", False),)),
            attempt(3, checks=(("field_equals", False), ("allowed_changes_only", False))),
            attempt(4, termination="timeout"), attempt(5, termination="infra:network"),
            attempt(6)]
    column = patterns(rows, {"a": "Monarch"})["setups"][0]
    assert {s["id"]: s["count"] for s in column["checks"]} == {
        "passed": 1, "scope": 1, "requirements": 1, "scope_and_requirements": 1,
        "unfinished": 1, "infrastructure": 1, "unclassified": 1}
    assert sum(s["percent"] for s in column["checks"]) == pytest.approx(100)


def test_drilldowns_distinguish_repetitions_and_runs_with_same_event_ids():
    rows = [attempt(0, events=[7]), attempt(1, events=[9]), attempt(0, run="run-2", events=[7])]
    output = patterns(rows, {"a": "Monarch"})
    refs = slices(output["setups"][0])["missing_action"]["attempts"]
    assert [(a["run"], a["index"], a["event_ids"]) for a in refs] == [
        ("run-1", 0, [7]), ("run-1", 1, [9]), ("run-2", 0, [7])]
    assert len({a["key"] for a in refs}) == 3


def test_domain_slices_use_domain_denominators_and_preserve_liveness_and_inputs():
    rows = [attempt(0, passed=True), attempt(1, task="finance.invoice"),
            attempt(2, task="finance.invoice", model="b")]
    rows[1]["liveness"] = "changed"
    original = deepcopy(rows)
    output = patterns(rows, {"a": "Monarch", "b": "Bare"})
    domains = {d["id"]: d for d in output["domains"]}
    assert domains["finance"]["setups"][0]["total"] == 1
    assert slices(domains["finance"]["setups"][0])["missing_action"]["percent"] == 100
    assert slices(domains["finance"]["setups"][0])["missing_action"]["attempts"][0]["liveness"] == "changed"
    assert domains["sales"]["setups"][1]["total"] == 0
    assert rows == original


def test_run_and_round_project_patterns_and_scope_authored_analysis_to_its_run(tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    from wb_studio.app import ROOT, Studio
    from wb_studio import report_data
    from wb_world.episode import load_suite

    def forbidden(*args, **kwargs):
        pytest.fail("Reading a report must not start paid work")
    studio = Studio(tmp_path / "studio", tasks=[t for t in load_suite(ROOT / "tasks") if t.get("task")][:1], gateway_factory=forbidden)
    jobs = []
    for number in range(2):
        job = studio.create({"request_id": f"patterns-{number}", "title": f"Run {number}",
                             "models": ["oracle", "sloppy"], "tasks": list(studio.tasks), "maximum_usd": "1"}, start=False)
        studio.execute(job["id"])
        jobs.append(job)
    publication = {"status": "completed", "summary": "Requested change succeeds; extra writes fail.",
                   "revision": 3, "attempts": [{"index": 0, "explanation": "Full analysis remains available."}]}
    plugin = ModuleType("wb_studio.genesis_reports")
    plugin.published = lambda s, identity: publication if identity == jobs[0]["id"] else None
    plugin.status = lambda g, payload: {"stage": "published" if payload["run"] == jobs[0]["id"] else "analysis"}
    monkeypatch.setitem(sys.modules, plugin.__name__, plugin)
    monkeypatch.setattr("wb_studio.genesis_reports", plugin, raising=False)
    single = report_data.run_report(studio, jobs[0]["id"])
    assert single["authored"] == publication
    assert single["report_work"] == {"stage": "published"}
    assert single["narrative"]["status"] == "pending"
    assert sum(s["total"] for s in single["patterns"]["setups"]) == 2
    cohort = next(iter(report_data.cohorts(studio)))
    pooled = report_data.round_report(studio, cohort)
    assert sum(s["total"] for s in pooled["patterns"]["setups"]) == 4
    assert len(pooled["run_analyses"]) == 2
    records = {a["run"]: a for a in pooled["run_analyses"]}
    assert records[jobs[0]["id"]]["authored"] == publication
    assert records[jobs[1]["id"]]["authored"] is None
    assert "authored" not in pooled, "A run interpretation must not become a cross-run synthesis"
    refs = [a for s in pooled["patterns"]["setups"] for sl in s["behavior"] for a in sl["attempts"]]
    assert {a["run"] for a in refs} == {j["id"] for j in jobs}


def test_narrative_status_prefers_published_genesis_and_preserves_legacy_file(tmp_path):
    import json
    from wb_studio.report_data import narrative_status
    legacy = {'status': 'failed', 'error': 'Old provider unavailable'}
    (tmp_path / 'analysis.json').write_text(json.dumps(legacy), encoding='utf8')
    publication = {'status': 'completed', 'summary': 'Reviewed report', 'revision': 2, 'attempts': [{'index': 0}], 'basis': 'Reviewed interpretation'}
    (tmp_path / 'report-publication.json').write_text(json.dumps(publication), encoding='utf8')
    result = narrative_status(tmp_path)
    assert result == {**publication, 'model': 'Genesis'}
    assert json.loads((tmp_path / 'analysis.json').read_text(encoding='utf8')) == legacy


@pytest.mark.parametrize('stage,expected', [('analysis', 'pending'), ('repair', 'pending'), ('failed', 'failed')])
def test_narrative_status_exposes_report_work_before_legacy(tmp_path, stage, expected):
    import json
    from wb_studio.report_data import narrative_status
    (tmp_path / 'analysis.pending.json').write_text(json.dumps({'reason': 'Old Gemini missing'}), encoding='utf8')
    (tmp_path / 'report-work.json').write_text(json.dumps({'stage': stage, 'reason': 'Current report state'}), encoding='utf8')
    result = narrative_status(tmp_path)
    assert result['status'] == expected
    assert result['reason'] == 'Current report state'
    assert result['model'] == 'Genesis'


def test_compact_pattern_summary_preserves_numbers_and_unique_source_refs():
    from wb_studio.report_patterns import compact
    source = patterns([attempt(0, passed=True), attempt(1, checks=(("field_equals", False),))], {"a": "Monarch"})
    result = compact(source)
    for field in ("behavior", "checks"):
        for original, brief in zip(source["setups"][0][field], result["setups"][0][field]):
            assert (brief["count"], brief["percent"]) == (original["count"], original["percent"])
            assert brief["attempt_keys"] == [r["key"] for r in original["attempts"]]
    assert set(result["attempts"]) == {"run-1:0", "run-1:1"}
    assert result["attempts"]["run-1:1"]["event_ids"] == [2]
    assert "explanation" not in result["attempts"]["run-1:1"]


def test_pattern_names_do_not_exclude_recorded_setup_versions():
    version = 'monarch@0cf63a74e+feat/railway-dev-deploy*'
    rows = [attempt(i, model=version, passed=i < 4) for i in range(17)]
    names = {'monarch': 'Planned Monarch'}
    result = patterns(rows, names)
    assert [c['id'] for c in result['setups']] == ['monarch', version]
    assert result['setups'][0]['total'] == 0
    assert result['setups'][1]['total'] == 17
    assert slices(result['setups'][1])['passed']['count'] == 4
    assert slices(result['setups'][1])['passed']['percent'] == 23.53
    assert names == {'monarch': 'Planned Monarch'}
