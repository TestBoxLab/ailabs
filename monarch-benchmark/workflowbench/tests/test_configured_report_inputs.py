"""Configured reports must read real simulator outcomes without rewriting them."""
import hashlib
import json

from tests.test_studio_reports import studio
from wb_arms.api_loop import ArmResult
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.store import Store
from wb_studio import report_data
from wb_world.episode import load_suite
from wb_studio.app import ROOT


def test_configured_report_keeps_versioned_identity_trials_checks_and_world(studio, monkeypatch):
    from runner.arms import OracleArm
    task = load_suite(ROOT / "tasks")[0]
    studio.tasks = {task["task"]: task}
    job = studio.create(dict(request_id="configured-report", models=["oracle"],
                             tasks=[task["task"]], maximum_usd="1"), start=False)
    folder = studio.directory / job["id"]
    class Competitor:
        name = "monarch@fixture"
        provider_key = None

        def run(self, ep, deadline=None):
            if ep.episode_id.endswith("/t1"):
                OracleArm().run(ep)
            return ArmResult(cost_usd=0.25, tokens_prompt=100, tokens_output=10)

    monkeypatch.setattr("wb_orchestrator.orchestrator.build_arm", lambda key: Competitor())
    store = Store(folder / "results.sqlite3")
    try:
        orch = Orchestrator(store, ROOT / "tasks/check-collateral", ["null"], 1,
                            folder / "evidence", tasks=[task], retry_on_fail=1)
        orch.run(job["id"])
        rows = store.episodes(run=job["id"])["rows"]
    finally:
        store.close()
    assert len(rows) == 2 and [r["passed"] for r in rows] == [False, True]
    job.update(status="completed", completed=2, total=2, config_source={"commit": "frozen"},
               resolved_config={"plan": {"repetitions": 1, "retry_on_fail": 1, "baseline": "monarch"}},
               results=[dict(task=r["task_id"], model=r["arm"], episode_id=r["episode_id"],
                             passed=r["passed"], termination=r["termination"], cost_usd=r["cost_usd"]) for r in rows])
    job["settings"].update(models=["monarch"], arms=[], plan_semantics="workflowbench-configured-plan")
    studio.save(job)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder / "job.json", folder / "results.sqlite3")}
    report = report_data.run_report(studio, job["id"])
    assert report["order"] == ["monarch@fixture"]
    result = report["setups"]["monarch@fixture"]
    assert result["pass"]["attempts"] == 2 and result["pass"]["passed"] == 1
    assert result["cost"]["total"] == 0.5 and result["cost"]["tokens"]["prompt"] == 200
    assert result["time"]["median"] > 0
    assert report["method"]["repetitions"] == 1 and report["method"]["retry_on_fail"] == 1
    assert report["method"]["planned_attempts"] == 2
    assert report["method"]["fork"] == "1.0.6"
    assert report["method"]["judge"]["sha256"]
    assert not any("repaired fork" in c or "no recorded outcome" in c for c in report["caveats"])
    attempts = report["failures"]["attempts"]
    assert len(attempts[0]["checks"]) > 0 and attempts[0]["checks"] != attempts[1]["checks"]
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
