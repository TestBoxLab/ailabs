"""Pilot runner: tasks x arms x k, in-process, emitting episodes.jsonl + summary.

In-process arms exercise the identical Episode surface the MCP server exposes;
CLI arms attach later via wb_world.server with zero grader changes.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grader.grade import grade
from grader.noop import validate_task
from runner.arms import NullArm, OracleArm, SloppyArm
from runner.schema import EpisodeRow, PhaseMetrics
from wb_world.episode import Episode


def _contract_hash(task: dict[str, Any]) -> str:
    blob = json.dumps(
        {"task": task.get("task"), "prompt": task.get("prompt"), "info": task.get("info")},
        sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def run_pilot(tasks: list[dict[str, Any]], out_dir: Path, k: int = 2,
              arms=None, run_id: str | None = None) -> dict[str, Any]:
    arms = arms or [OracleArm(), SloppyArm(), NullArm()]
    run_id = run_id or f"pilot-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[EpisodeRow] = []

    noop_report = [validate_task(t) for t in tasks]

    for task in tasks:
        chash = _contract_hash(task)
        for arm in arms:
            for trial in range(k):
                eid = f"{run_id}/{task['task']}/{arm.name.replace('/', '_')}/t{trial}"
                t0 = time.monotonic()
                ep = Episode(task, episode_id=eid)
                error = None
                termination = "completed"
                try:
                    arm.run(ep)
                except Exception as e:  # agent-side failure, not infra
                    error, termination = str(e), "agent_error"
                snap1 = ep.finish()
                g = grade(task, ep.snapshot0, snap1)
                rows.append(EpisodeRow(
                    episode_id=eid, run_id=run_id, task_id=task["task"],
                    contract_sha256=chash, arm=arm.name, trial=trial,
                    passed=g["passed"], assertions_passed=g["assertions_passed"],
                    invariant_passed=g["invariant"]["passed"],
                    invariant_declared=g["invariant_declared"],
                    check_results=[{k2: r[k2] for k2 in ("type", "passed")} for r in g["assertion_results"]],
                    unexpected_changes=g["invariant"]["unexpected_changes"],
                    n_changes=g["n_changes"], tool_calls=len(ep.tool_calls),
                    phases={"run": PhaseMetrics(tool_calls=len(ep.tool_calls),
                                                wall_clock_s=round(time.monotonic() - t0, 4))},
                    termination=termination, error=error,
                    finished_at=datetime.now(timezone.utc),
                ))

    (out_dir / "episodes.jsonl").write_text(
        "\n".join(r.model_dump_json() for r in rows) + "\n")
    (out_dir / "noop_validation.json").write_text(json.dumps(noop_report, indent=1, default=str))

    summary: dict[str, Any] = {"run_id": run_id, "n_tasks": len(tasks), "k": k, "arms": {}}
    for arm in arms:
        sub = [r for r in rows if r.arm == arm.name]
        summary["arms"][arm.name] = {
            "episodes": len(sub),
            "strict_pass_rate": round(sum(r.passed for r in sub) / len(sub), 4) if sub else None,
            "assertion_pass_rate": round(sum(r.assertions_passed for r in sub) / len(sub), 4) if sub else None,
            "invariant_fail_count": sum(not r.invariant_passed for r in sub),
        }
    summary["noop_vacuous_tasks"] = [r["task"] for r in noop_report if not r["ok"]]
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary
