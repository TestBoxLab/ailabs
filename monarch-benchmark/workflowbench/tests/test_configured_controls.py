"""Configured runs keep their frozen inputs and evidence across explicit controls."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from tests.test_studio_benchmark_config import workspace
from wb_studio import benchmark_config as bc
from wb_studio.app import Studio
from wb_orchestrator.orchestrator import Orchestrator


def create(workspace, identity="controlled"):
    studio, remote = workspace
    payload = dict(commit=remote.head, product="simulated-apps", plan="free-check",
                   operator="Carlos", request_id=identity)
    payload["preview_id"] = bc.preview(studio, payload)["preview_id"]
    return studio, bc.create(studio, payload, start=False)


def test_queued_pause_survives_restart_and_requires_preview(workspace):
    studio, job = create(workspace)
    studio.pause(job["id"])
    studio.execute(job["id"])
    restored = Studio(studio.directory, gateway_factory=lambda: None)
    assert restored.job(job["id"])["status"] == "paused"
    from wb_studio import configured_controls as controls
    with pytest.raises(ValueError, match="preview"):
        controls.resume(restored, job["id"], start=False)
    preview = controls.preview(restored, job["id"])
    assert preview["resumable"] and preview["required_attempts"] == 4
    controls.resume(restored, job["id"], preview_id=preview["preview_id"], start=False)
    restored.execute(job["id"])
    assert restored.job(job["id"])["status"] == "completed"
    assert restored.job(job["id"])["completed"] == 4


def test_pause_drains_without_replaying_and_cancel_is_terminal(workspace, monkeypatch):
    studio, job = create(workspace)
    entered, release = threading.Event(), threading.Event()
    original = Orchestrator._run_episode
    calls = []
    def blocked(self, identity, arm, task, trial):
        calls.append(task["task"])
        entered.set()
        assert release.wait(5)
        return original(self, identity, arm, task, trial)
    monkeypatch.setattr(Orchestrator, "_run_episode", blocked)
    thread = threading.Thread(target=studio.execute, args=(job["id"],))
    thread.start()
    try:
        assert entered.wait(5)
        paused = studio.pause(job["id"])
        assert paused["status"] == "pausing" and paused["active_attempts"] == 1
        release.set()
        thread.join(10)
        assert not thread.is_alive()
        paused = studio.job(job["id"])
        assert paused["status"] == "paused" and paused["completed"] == 1
        assert len(calls) == 1
        studio.cancel(job["id"])
        assert studio.job(job["id"])["status"] == "cancelled"
        with pytest.raises(ValueError):
            studio.resume(job["id"])
    finally:
        release.set()
        thread.join(10)


def test_process_death_and_concurrent_resume_preserve_completed_rows(workspace):
    studio, job = create(workspace, "crash-control")
    folder = studio.directory / job["id"]
    code = '''
import os, sys
from wb_studio.app import Studio
from wb_orchestrator.orchestrator import Orchestrator
from wb_world.episode import Episode
original = Orchestrator._run_episode
calls = 0
def crash(self, identity, arm, task, trial):
    global calls
    calls += 1
    if calls == 2:
        ep = Episode(task, f"{identity}/{task['task']}/{arm.name}/t{trial}")
        ep.attach_journal(self._run_dir(identity) / 'episodes' / task['task'] / arm.name / f't{trial}' / 'attempt-000')
        ep.base64_encode('partial observation')
        os._exit(73)
    return original(self, identity, arm, task, trial)
Orchestrator._run_episode = crash
Studio(sys.argv[1], gateway_factory=lambda: None).execute(sys.argv[2])
'''
    child = subprocess.run([sys.executable, "-c", code, str(studio.directory), job["id"]],
                           capture_output=True, text=True, timeout=30)
    assert child.returncode == 73, child.stderr
    evidence = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file() and "evidence" in p.parts}
    store = bc.Store(folder / "results.sqlite3")
    before = store.episodes(run=job["id"])["rows"]
    store.close()
    assert len(before) == 1
    restored = Studio(studio.directory, gateway_factory=lambda: None)
    assert restored.job(job["id"])["status"] == "interrupted"
    from wb_studio import configured_controls as controls
    preview = controls.preview(restored, job["id"])
    assert preview["resumable"], preview
    assert preview["required_attempts"] == 3
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: controls.resume(restored, job["id"],
            preview_id=preview["preview_id"], start=False), range(2)))
    assert all(r["status"] == "queued" for r in responses)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: restored.execute(job["id"]), range(2)))
    done = restored.job(job["id"])
    assert done["status"] == "completed" and done["completed"] == 4, done
    assert len(done["execution_segments"]) == 2
    store = bc.Store(folder / "results.sqlite3")
    after = store.episodes(run=job["id"])["rows"]
    store.close()
    assert before[0] == next(r for r in after if r["episode_id"] == before[0]["episode_id"])
    assert all(Path(p).read_bytes() == contents for p, contents in evidence.items())
    # The real frozen reference can fail a task: compare with an uninterrupted
    # control rather than inventing a perfect answer key for these inputs.
    control_studio, control = create(workspace, "uninterrupted-control")
    control_studio.execute(control["id"])
    baseline = control_studio.job(control["id"])["results"]
    assert sorted((r["task_id"], r["passed"], r["termination"]) for r in after) == sorted(
        (r["task_id"], r["passed"], r["termination"]) for r in baseline)


def test_preview_refuses_unknown_billing_without_mutation(workspace):
    studio, job = create(workspace)
    studio.pause(job["id"])
    ledger = studio.ledger
    ledger.reserve("lost", "0.50", scope_id=job["id"] + "/task/oracle/t0")
    ledger.claim("lost")
    file = studio.directory / job["id"] / "job.json"
    before = file.read_bytes()
    from wb_studio import configured_controls as controls
    preview = controls.preview(studio, job["id"])
    assert not preview["resumable"] and preview["unresolved_usd"] == "0.500000"
    assert any("billing" in reason.lower() for reason in preview["reasons"])
    assert file.read_bytes() == before
    assert ledger.reservations()[0].actual_usd is None


def test_resume_rechecks_configuration_and_rejects_stale_preview(workspace):
    studio, job = create(workspace)
    studio.pause(job["id"])
    from wb_studio import configured_controls as controls
    preview = controls.preview(studio, job["id"])
    file = studio.directory / job["id"] / "job.json"
    changed = json.loads(file.read_text())
    changed["config_hash"] = "changed"
    file.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="(?i)changed|drift|configuration"):
        controls.resume(studio, job["id"], preview_id=preview["preview_id"], start=False)
    assert studio.job(job["id"])["status"] == "paused"


def test_initial_preview_refuses_installed_world_drift(workspace, monkeypatch):
    from wb_world import episode
    studio, remote = workspace
    monkeypatch.setattr(episode, "installed_world_version", lambda: "different-world")
    result = bc.preview(studio, dict(commit=remote.head, product="simulated-apps", plan="free-check"))
    assert not result["launchable"]
    assert any("world" in reason.lower() for reason in result["reasons"])
    assert not studio.jobs()


def test_http_configured_controls_reuse_person_permissions(workspace):
    from tests.test_studio_app import server_for, request
    studio, job = create(workspace)
    person = studio.genesis.access.add("Carlos", "admin")
    with server_for(studio) as port:
        headers = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json",
                   "X-Studio-Token": studio.token}
        status, _, _ = request(port, "POST", f"/api/jobs/{job['id']}/pause", body="{}", headers=headers)
        assert status == 403
        assert studio.job(job["id"])["status"] == "queued"
        headers["X-Person-Key"] = person["key"]
        status, _, body = request(port, "POST", f"/api/jobs/{job['id']}/pause", body="{}", headers=headers)
        assert status == 200 and json.loads(body)["status"] == "paused"


def test_recovery_preview_reports_world_drift_over_http(workspace, monkeypatch):
    from tests.test_studio_app import server_for, request
    from wb_world import episode
    studio, job = create(workspace)
    studio.pause(job["id"])
    file = studio.directory / job["id"] / "job.json"
    before = file.read_bytes()
    monkeypatch.setattr(episode, "installed_world_version", lambda: "different-world")
    with server_for(studio) as port:
        status, _, body = request(port, "GET", f"/api/jobs/{job['id']}/resume-preview")
    assert status == 200
    result = json.loads(body)
    assert not result["resumable"] and any("world" in r for r in result["reasons"])
    assert file.read_bytes() == before
