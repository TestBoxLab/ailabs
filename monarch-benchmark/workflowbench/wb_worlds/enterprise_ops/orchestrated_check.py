"""Free EnterpriseOps setup controls through orchestration, storage, regrade and reports."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from wb_arms.api_loop import ArmResult
from wb_orchestrator.config import load_product
from wb_orchestrator.orchestrator import Orchestrator, regrade
from wb_report.report import build_report, write_report
from wb_results.evidence import verify_manifest
from wb_results.store import Store
from wb_world.episode import contract_hash, load_suite
from wb_worlds.enterprise_ops.adapter import EnterpriseOpsWorld
from wb_worlds.enterprise_ops.smoke_check import _complete


class SetupControl:
    provider_key = None
    message_evidence = "setup-validation-script"
    model_label = "deterministic setup validation; no model"

    def __init__(self, correct):
        self.correct = correct
        self.name = "setup-validation-correct" if correct else "setup-validation-null"

    def run(self, ep, deadline=None):
        ep.record_agent_event({"type": "setup_validation", "control": self.name, "provider_calls": 0})
        if self.correct:
            _complete(ep)
        return ArmResult(termination="completed", cost_usd=0, tool_calls=len(ep.tool_calls),
                         flags=["setup_validation", "provider_calls=0"],
                         final_text="Deterministic setup control finished; this is not a competitor score.",
                         turn_log=[{"source": "setup_validation", "control": self.name, "provider_calls": 0}])


def main():
    os.environ.setdefault("WB_EOG_URL", "http://127.0.0.1:18005")
    source_tasks = Path("tasks/eog-itsm-smoke-2").resolve()
    tasks = load_suite(source_tasks)
    assert len(tasks) == 2
    assert all(task["contract_sha256"] == contract_hash(task) for task in tasks)
    product = load_product("config/products/enterprise-ops-gym.yaml")
    controls = [SetupControl(True), SetupControl(False)]
    root = Path("out") / ("eog-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    run_id = "eog-ctl"
    source_paths = [Path(__file__), Path(__file__).with_name("smoke_check.py")]
    frozen = {"product": asdict(product), "plan": "free-eog-setup-validation", "mode": "create-run",
              "n_tasks": 2, "k": 1, "arms": [arm.name for arm in controls], "attempts_total": 4,
              "tasks": [task["contract_sha256"] for task in tasks],
              "qualification": "Free deterministic setup controls; no model calls, no Monarch or native-agent score.",
              "control_source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}}
    config_hash = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    store = Store(root / "results.sqlite3")
    engine = Orchestrator(store, source_tasks, [], 1, root / "e", tasks=tasks,
                          timeout_s=120, provider_concurrency=1, operator="Lucas")
    engine.world = EnterpriseOpsWorld
    engine.arm_keys = [arm.name for arm in controls]
    engine.run_config = SimpleNamespace(product=product, native_runtimes={}, hash=config_hash,
        config_json=frozen, plan=SimpleNamespace(mode="create-run", cost_ceiling_usd=0))
    engine._arms = lambda: controls
    engine.run(run_id)
    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 4, rows
    for row in rows:
        assert row["termination"] == "completed", row
        assert row["passed"] == (row["arm"] == "setup-validation-correct"), row
        assert row["cost_usd"] == 0
        artifacts = store.artifacts(row["episode_id"])
        assert not verify_manifest(artifacts["manifest"], episode_id=row["episode_id"], contract_sha256=row["contract_sha256"])
        folder = Path(row["artifacts_uri"])
        assert (folder / "world-gym-itsm-mcp.sqlite").is_file()
        assert (folder / "attempt-000" / "world-gym-itsm-mcp.sqlite").is_file()
        grade = json.loads((folder / "grading.json").read_text(encoding="utf-8"))
        assert grade["positive_source"] == "EnterpriseOps-Gym SQL verifiers"
        assert len(grade["positive"]["verifiers"]) == 2
        assert not grade["ungraded"]
    # All source worlds have now closed. Regrade uses only preserved databases.
    replay = regrade(store, run_id, source_tasks)
    assert replay["regraded"] == 4 and replay["changed"] == 0, replay
    report = build_report(store, run_id, baseline_arm="setup-validation-null")
    assert report["product"]["name"] == "enterprise-ops-gym"
    assert report["size"]["prompts"] == 2 and report["size"]["total"] == 4
    assert len(report["grading_evidence"]) == 4
    assert any("SQL" in caveat for caveat in report["caveats"]), report["caveats"]
    files = write_report(store, run_id, root / "report", baseline_arm="setup-validation-null", tasks_dir=source_tasks)
    for name in ("md", "html"):
        assert Path(files[name]).is_file() and Path(files[name]).stat().st_size > 1000
    (root / "report-data.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {"run_id": run_id, "qualification": frozen["qualification"], "provider_calls": 0,
               "attempts": 4, "correct_control_passes": sum(row["passed"] for row in rows),
               "null_control_failures": sum(not row["passed"] for row in rows), "regrade": replay,
               "reports": files, "results_database": str(root / "results.sqlite3"),
               "task_hashes": frozen["tasks"], "config_hash": config_hash}
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"summary": str(root / "summary.json"), **summary}))


if __name__ == "__main__":
    main()
