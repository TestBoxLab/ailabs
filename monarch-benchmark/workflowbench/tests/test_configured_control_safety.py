"""Cancellation and live ownership survive Studio restarts without changing evidence."""
import json
import subprocess
import sys

import pytest

from tests.test_configured_controls import create, workspace
from wb_orchestrator.orchestrator import Orchestrator, RunKilled
from wb_studio import benchmark_config as bc, configured_controls as controls
from wb_studio.app import Studio


def checkpoint(workspace):
    studio, job = create(workspace, "safety-check")
    folder = studio.directory / job["id"]
    store = bc.Store(folder / "results.sqlite3")
    rc = bc.config.resume_config(job["resolved_config"])
    runner = Orchestrator.from_config(store, rc, folder / "evidence")
    runner._stop_after = 1
    with pytest.raises(RunKilled):
        runner.run(job["id"])
    store.close()
    job.update(status="running", active_attempts=1)
    studio._save_control(job)
    return studio, job, folder


def test_cancellation_during_drain_survives_restart_and_preserves_unknown_hold(workspace):
    studio, job, folder = checkpoint(workspace)
    studio.ledger.reserve("unknown-draining-call", "0.25", scope_id=job["id"] + "/unfinished")
    studio.ledger.claim("unknown-draining-call")
    assert studio.cancel(job["id"])["status"] == "cancelling"
    restored = Studio(studio.directory, gateway_factory=lambda: None)
    assert restored.job(job["id"])["status"] == "cancelled"
    assert not controls.preview(restored, job["id"])["resumable"]
    assert restored.ledger.reservations()[0].actual_usd is None
    store = bc.Store(folder / "results.sqlite3", read_only=True)
    try:
        assert store.run(job["id"])["stop_reason"] == "cancelled"
        assert len(store.episodes(run=job["id"])["rows"]) == 1
    finally:
        store.close()


def test_cancelling_paused_run_also_blocks_cli_resume_in_results_store(workspace):
    studio, job, folder = checkpoint(workspace)
    job.update(status="paused", pause_requested=True, active_attempts=0)
    studio._save_control(job)
    store = bc.Store(folder / "results.sqlite3")
    store.set_stop_reason(job["id"], "paused")
    store.close()
    assert studio.cancel(job["id"])["status"] == "cancelled"
    store = bc.Store(folder / "results.sqlite3")
    try:
        assert store.run(job["id"])["stop_reason"] == "cancelled"
        runner = Orchestrator.from_config(store, bc.config.resume_config(job["resolved_config"]),
                                          folder / "evidence")
        with pytest.raises(RunKilled, match="cancelled"):
            runner.resume(job["id"])
    finally:
        store.close()


def test_live_owner_survives_studio_reinitialization_and_other_process_preview(workspace):
    studio, job, folder = checkpoint(workspace)
    before = (folder / "job.json").read_bytes()
    code = """
import json, sys
from wb_studio.app import Studio
from wb_studio.configured_controls import preview
studio = Studio(sys.argv[1], gateway_factory=lambda: None)
print(json.dumps(dict(status=studio.job(sys.argv[2])["status"], preview=preview(studio, sys.argv[2]))))
"""
    with controls.owner(studio, job["id"]):
        restored = Studio(studio.directory, gateway_factory=lambda: None)
        assert restored.job(job["id"])["status"] == "running"
        child = subprocess.run([sys.executable, "-c", code, str(studio.directory), job["id"]],
                               capture_output=True, text=True, timeout=30)
        assert child.returncode == 0, child.stderr
        result = json.loads(child.stdout)
        assert result["status"] == "running"
        assert not result["preview"]["resumable"]
        assert any("owns" in reason for reason in result["preview"]["reasons"])
    assert (folder / "job.json").read_bytes() == before


def test_preview_reads_real_results_without_rewriting_database_or_job(workspace):
    studio, job, folder = checkpoint(workspace)
    job.update(status="interrupted", active_attempts=0)
    studio._save_control(job)
    files = [folder / "results.sqlite3", folder / "job.json"]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    preview = controls.preview(studio, job["id"])
    assert preview["resumable"] and preview["required_attempts"] == 3, preview
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}


def test_stored_cancellation_refuses_preview_even_if_job_status_was_recovered(workspace):
    studio, job, folder = checkpoint(workspace)
    store = bc.Store(folder / "results.sqlite3")
    store.set_stop_reason(job["id"], "cancelled")
    store.close()
    job.update(status="interrupted", active_attempts=0)
    studio._save_control(job)
    preview = controls.preview(studio, job["id"])
    assert not preview["resumable"], "Stored terminal cancellation overrides a stale job status"
    assert any("cancel" in reason.lower() for reason in preview["reasons"])
