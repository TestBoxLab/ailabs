"""Free source integration checks; these are not model scores or an answer-key ceiling.

Run with: uv run python -m wb_worlds.enterprise_ops.smoke_check
Requires the pinned source container and acquired seed files, no provider keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from grader.grade import grade
from wb_world.episode import load_suite
from wb_worlds.enterprise_ops.adapter import EnterpriseOpsWorld


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _send(world, fields):
    reply = json.loads(world.api_fetch("POST", "/api/notifications/", body=json.dumps({**fields, "type": "alert", "status": "sent"})))
    if "error" in reply:
        raise RuntimeError(reply)
    return reply


def _complete(world):
    """Reviewed development probes use only the task's published application calls."""
    if world.task["task"].endswith("be0bd794"):
        reply = json.loads(world.api_fetch("PUT", "/incidents/INC_004", body=json.dumps({"service": "SVC_002"})))
        if "error" in reply:
            raise RuntimeError(reply)
        _send(world, {"incident_id": "INC_004", "email": "elena.petrov@techcorp.com",
                      "subject": "Service Association Updated for Assigned Incident",
                      "message": "The service association for your assigned network connectivity incident INC0000004 has been updated and is now aligned to the service owned by Priya. Continue work using the corrected service relationship."})
    elif world.task["task"].endswith("8fd400d1"):
        for incident, email, summary, date in (
            ("INC_003", "carlos.rodriguez@techcorp.com", "printer connectivity", "19 February 2024"),
            ("INC_004", "elena.petrov@techcorp.com", "network connectivity", "18 February 2024"),
        ):
            _send(world, {"incident_id": incident, "email": email,
                          "subject": "Priority Escalation for Aging Incidents",
                          "message": f"This {summary} incident created on {date} has been escalated as top-priority work because it remains unresolved. Handle it ahead of other tasks and drive resolution as quickly as possible."})
    else:
        raise ValueError("the free check is reviewed only for the frozen two-task smoke set")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default="tasks/eog-itsm-smoke-2")
    parser.add_argument("--out", default="out/external-checks/enterprise-ops")
    args = parser.parse_args()
    directory = Path(args.out) / uuid.uuid4().hex
    directory.mkdir(parents=True)
    summary = {"kind": "free deterministic source integration checks", "provider_calls": 0,
               "competitor_score": False, "evidence": []}
    for task in load_suite(args.tasks):
        for variant in ("positive", "null", "stray-write"):
            output = directory / task["task"] / variant
            output.mkdir(parents=True)
            world = EnterpriseOpsWorld(task, f"eog-check-{uuid.uuid4().hex}")
            try:
                world.artifacts_dir = output
                world.attach_journal(output / "attempt-0")
                _write(output / "snapshot0.json", world.snapshot0)
                assert world.snapshot() == world.snapshot0, "untouched snapshots must be stable"
                if variant != "null":
                    _complete(world)
                if variant == "stray-write":
                    _send(world, {"incident_id": "INC_002", "email": "benjamin.chen@techcorp.com",
                                  "subject": "Unrequested alert", "message": "This alert was not requested by the task."})
                after = world.finish()
                _write(output / "snapshot1.json", after)
                _write(output / "termination.json", {"status": "completed", "normal_finish": True, "provider_calls": 0})
            finally:
                world.close()
            # Deliberately grade only once the remote source database has closed.
            verdict = grade(task, world.snapshot0, after, world=EnterpriseOpsWorld, artifacts=output)
            _write(output / "grading.json", verdict)
            assert not verdict["ungraded"], verdict["error"]
            assert verdict["passed"] == (variant == "positive"), verdict
            assert verdict["assertions_passed"] == (variant != "null"), verdict
            assert verdict["collateral_damage"] == (1 if variant == "stray-write" else 0), verdict
            manifest = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob("*") if p.is_file()}
            _write(output / "artifact-sha256.json", manifest)
            summary["evidence"].append({"task": task["task"], "case": variant,
                "task_hash": task["contract_sha256"], "passed": verdict["passed"],
                "source_positive": verdict["assertions_passed"], "collateral_damage": verdict["collateral_damage"],
                "changes": verdict["n_changes"], "directory": str(output)})
    _write(directory / "summary.json", summary)
    print(json.dumps({"summary": str(directory / "summary.json"), "checks": len(summary["evidence"]), "provider_calls": 0}))


if __name__ == "__main__":
    main()
