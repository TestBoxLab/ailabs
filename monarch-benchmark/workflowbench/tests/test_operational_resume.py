"""Recovery keeps real interrupted world evidence and never replays completed work."""
import hashlib
import json

import pytest

from tests.test_studio_benchmark_config import workspace
from wb_studio import benchmark_config as bc
from wb_orchestrator.orchestrator import Orchestrator, RunKilled
from wb_world.episode import Episode


def interrupted(workspace):
    studio, remote = workspace
    payload = dict(commit=remote.head, product="simulated-apps", plan="free-check",
                   operator="Carlos", request_id="recover-check")
    payload["preview_id"] = bc.preview(studio, payload)["preview_id"]
    job = bc.create(studio, payload, start=False)
    folder = studio.directory / job["id"]
    store = bc.Store(folder / "results.sqlite3")
    rc = bc.config.resume_config(job["resolved_config"])
    orch = Orchestrator.from_config(store, rc, folder / "evidence", provider_concurrency=1)
    orch._stop_after = 1
    with pytest.raises(RunKilled):
        orch.run(job["id"])
    previous = store.episodes(run=job["id"])["rows"]
    task = next(t for t in rc.tasks if t["task"] != previous[0]["task_id"])
    arm = previous[0]["arm"]
    eid = f"{job['id']}/{task['task']}/{arm}/t0"
    root = folder / "evidence" / job["id"] / "episodes" / task["task"] / arm / "t0"
    ep = Episode(task, eid)
    ep.attach_journal(root / "attempt-000")
    ep.base64_encode("last observed before shutdown")
    saved = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    reservation = eid + "#attempt-000#monarch"
    studio.ledger.reserve(reservation, "0.50", scope_id=eid)
    studio.ledger.claim(reservation)
    studio.ledger.settle(reservation, "0.17")
    receipt = dict(run_id=job["id"], operator="Carlos", config_hash=job["config_hash"],
                   reason="Process terminated; backend is idle; provider usage inspected", items=[dict(
                       episode_id=eid, task_id=task["task"], arm=arm, trial=0,
                       artifacts_uri=str(root), cost_usd="0.17", reservations=[reservation],
                       billing_evidence="Retained provider receipt for this test",
                       files={n: hashlib.sha256(b).hexdigest() for n, b in saved.items()})])
    job["status"] = "interrupted"
    studio.save(job)
    store.close()
    return studio, folder, receipt, previous, root, saved


def test_recovery_preserves_world_and_completed_row_and_carries_old_spend(workspace):
    from scripts.resume_studio_run import recover
    studio, folder, receipt, previous, root, saved = interrupted(workspace)
    preview = recover(folder, receipt, studio.ledger, execute=False)
    assert preview["pending_min"] == 3 and preview["pending_max"] == 3
    assert not (folder / "recovery" / "operational.claimed").exists()
    result = recover(folder, receipt, studio.ledger, execute=True)
    assert result["status"] == "completed", result
    assert result["completed"] == 4 and result["cost_usd"] == pytest.approx(0.17)
    assert saved == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    store = bc.Store(folder / "results.sqlite3")
    rows = store.episodes(run=receipt["run_id"])["rows"]
    assert next(r for r in rows if r["episode_id"] == previous[0]["episode_id"]) == previous[0]
    recovered = next(r for r in rows if r["episode_id"] == receipt["items"][0]["episode_id"])
    assert recovered["cost_usd"] == pytest.approx(0.17)
    assert "interruption_recovered" in recovered["flags"]
    store.close()
    with pytest.raises(ValueError):
        recover(folder, receipt, studio.ledger, execute=True)


def test_recovery_refuses_tampering_before_dispatch_or_changes(workspace):
    from scripts.resume_studio_run import recover
    studio, folder, receipt, previous, root, saved = interrupted(workspace)
    (root / "attempt-000" / "events.live.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="evidence"):
        recover(folder, receipt, studio.ledger, execute=True)
    assert not (folder / "recovery" / "operational.claimed").exists()
    assert studio.job(receipt["run_id"])["status"] == "interrupted"


def test_recovery_reservation_namespace_keeps_old_dispatch_untouched(tmp_path):
    from scripts.resume_studio_run import RecoveryLedger
    from wb_orchestrator.budget import BudgetLedger
    ledger = BudgetLedger(tmp_path / "ledger.sqlite3")
    ledger.reserve("old", "1", scope_id="task")
    ledger.claim("old")
    resumed = RecoveryLedger(ledger, "recovery-1")
    resumed.reserve("old", "1", scope_id="task")
    resumed.claim("old")
    resumed.settle("old", "0.25")
    rows = {r.reservation_id: r for r in ledger.reservations()}
    assert rows["old"].actual_usd is None
    assert str(rows["old#recovery-1"].actual_usd) == "0.250000"


def test_recovery_cannot_reserve_beyond_the_original_remaining_ceiling(tmp_path):
    from scripts.resume_studio_run import RecoveryLedger
    from wb_orchestrator.budget import BudgetLedger, BudgetExceeded
    ledger = BudgetLedger(tmp_path / "ledger.sqlite3")
    ledger.reserve_run("remaining", "1")
    resumed = RecoveryLedger(ledger, "recovery-1", run_id="remaining")
    resumed.reserve("first", "0.75", scope_id="task-one")
    with pytest.raises(BudgetExceeded):
        resumed.reserve("second", "0.75", scope_id="task-two")
    assert len(ledger.reservations()) == 1
