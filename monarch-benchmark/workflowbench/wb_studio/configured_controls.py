"""Explicit configured-run recovery, using frozen inputs and existing execution."""
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
import json
import os
from pathlib import Path
import threading
import uuid

from wb_arms.runtime_manifest import sha256_json
from wb_orchestrator import approvals, config, reconcile
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.evidence import verify_manifest, write_json
from wb_results.store import Store
from wb_studio.runtime import single_host_owner
from wb_world.episode import installed_world_version, recorded_world_version


def read_job(studio, identity):
    from wb_studio.app import ID
    if not isinstance(identity, str) or not ID.fullmatch(identity):
        raise ValueError("Invalid run ID")
    with studio.lock:
        return json.loads((studio.directory / identity / "job.json").read_text(encoding="utf-8"))


@contextmanager
def owner(studio, identity):
    # OS ownership covers the entire segment, including drain and final writes.
    # The OS releases it after process death; an old marker alone proves nothing.
    with single_host_owner(studio.directory / identity / "execution"):
        yield


def names(rc):
    result = []
    for competitor in rc.competitors:
        if competitor.harness.kind == "monarch":
            from wb_arms.monarch import monarch_version
            repo = config.from_workflowbench(competitor.harness.monarch_repo, rc.config_dir, rc.runtime_root)
            result.append(monarch_version(repo, os.environ.get("MONARCH_BUILD")))
        else:
            result.append(competitor.name)
    return result


def inspect(studio, job):
    """Read stored outcomes and liabilities; never build a paid adapter or regrade."""
    identity = job["id"]
    folder = studio.directory / identity
    rc = config.resume_config(job["resolved_config"])
    if rc.hash != job["config_hash"]:
        raise ValueError("Frozen configuration changed; refusing continuation")
    if installed_world_version() != recorded_world_version(rc.tasks):
        raise ValueError("Installed world revision differs from the frozen run")
    competitors = names(rc)
    if job.get("competitor_identities") and competitors != job["competitor_identities"]:
        raise ValueError("Recorded competitor version differs from the available runtime")
    rows, recorded = [], None
    db = folder / "results.sqlite3"
    if db.exists():
        store = Store(db, read_only=True)
        try:
            recorded = store.run(identity)
            rows = store.episodes(run=identity)["rows"]
            if recorded and (recorded["config_hash"] != rc.hash or
                             json.loads(recorded["config_json"]).get("config_source") != rc.config_source):
                raise ValueError("Stored configuration differs from the original run")
            pending = Orchestrator.from_config(store, rc, folder / "evidence").pending_work(
                identity, competitor_names=competitors)
            if job.get("approval_request_id"):
                approval = store.approval_request(job["approval_request_id"])
                if (not approval or approval["status"] != "approved" or approval["config_hash"] != rc.hash
                        or approval.get("run_id") not in (None, identity)):
                    raise ValueError("Original approval is unavailable or does not match this run")
        finally:
            store.close()
    else:
        initial = rc.attempts_per_competitor_min * len(competitors)
        pending = dict(required_initial=initial, earned_retries=0, required_attempts=initial,
                       conditional_retries=rc.attempts_total-initial, maximum_attempts=rc.attempts_total)
    if any(row["arm"] not in competitors for row in rows):
        raise ValueError("Recorded competitor version differs from the available runtime")
    reasons = []
    if recorded and recorded.get("stop_reason") == "cancelled":
        reasons.append("The stored run was cancelled and cannot be resumed")
    if recorded and not job.get("competitor_identities"):
        for competitor, runtime_name in zip(rc.competitors, competitors):
            if competitor.harness.kind == "monarch" and not any(r["arm"] == runtime_name for r in rows):
                reasons.append("Legacy run has no recorded Monarch version; operator verification is required")
    costs = defaultdict(lambda: Decimal("0"))
    for row in rows:
        if row.get("cost_usd") is None or {"billing=unknown", "cost_missing"}.intersection(row.get("flags", [])):
            reasons.append("Unknown attempt billing requires reconciliation")
        costs[row["episode_id"]] = Decimal(str(row.get("cost_usd") or 0))
        root = Path(row.get("artifacts_uri") or "").resolve()
        if (not root.is_relative_to(folder.resolve()) or verify_manifest(root / "manifest.json",
                episode_id=row["episode_id"], contract_sha256=row["contract_sha256"])):
            reasons.append("Stored attempt evidence requires reconciliation")
    bills = [r for r in studio.ledger.reservations()
             if r.scope_id == identity or r.scope_id.startswith(identity + "/")]
    actuals = defaultdict(lambda: Decimal("0"))
    unresolved = Decimal("0")
    for bill in bills:
        if bill.actual_usd is None:
            unresolved += bill.maximum_usd
        else:
            actuals[bill.scope_id] += bill.actual_usd
    if any(bill.actual_usd is None for bill in bills):
        reasons.append("Unresolved request billing must be reconciled before continuation")
    known = sum((max(costs[scope], actuals[scope]) for scope in costs.keys() | actuals.keys()), Decimal("0"))
    remaining = max(Decimal("0"), Decimal(str(rc.plan.cost_ceiling_usd)) - known - unresolved).quantize(
        Decimal("0.000001"), rounding=ROUND_DOWN)
    envelopes = [r for r in studio.ledger.run_reservations()
                 if r.scope_id == identity or r.metadata.get("run_id") == identity]
    reserved = sum((max(Decimal("0"), r.maximum_usd - studio.ledger.scope_committed(r.scope_id))
                    for r in envelopes if r.closed_at is None), Decimal("0"))
    if approvals.is_paid(rc):
        env = {**os.environ, "WB_OPERATOR": job["operator"]}
        reasons.extend(approvals.launch_readiness(rc, env))
        if rc.attempts_per_competitor > approvals.SMOKE_SCALE_ATTEMPTS and not job.get("approval_request_id"):
            reasons.append("The original paid approval record is missing")
        status = studio.ledger.status()
        verified = reconcile.summaries(reconcile.default_dir(studio.ledger)).get(status.week_start, {})
        if not verified.get("historical_billing_verified"):
            reasons.append("This week's historical billing is not verified")
        if status.blocked or remaining > status.available_usd + reserved:
            reasons.append("This week's available budget cannot cover the remaining original ceiling")
        if remaining <= 0 and pending["required_attempts"]:
            reasons.append("The original run ceiling has been reached")
        committed = {Path(r.get("artifacts_uri") or "").resolve() for r in rows}
        for path in (folder / "segments").glob("*/prior-results.json"):
            for old in json.loads(path.read_text(encoding="utf-8")):
                root = Path(old.get("artifacts_uri") or "").resolve()
                if root.is_relative_to(folder.resolve()) and not verify_manifest(root / "manifest.json",
                        episode_id=old["episode_id"], contract_sha256=old["contract_sha256"]):
                    committed.add(root)
        partials = {p.parent.parent.resolve() for p in folder.rglob("attempt.json")} - committed
        if partials:
            reasons.append("Unfinished paid work needs an operator recovery receipt confirming external completion and billing")
    if studio.coordinator is not None:
        reasons.append("Configured continuation requires the local Studio runtime")
    return rc, rows, {**pending, "competitor_identities": competitors,
        "known_cost_usd": str(known), "unresolved_usd": str(unresolved.quantize(Decimal("0.000001"))),
        "reserved_usd": str(reserved), "remaining_ceiling_usd": str(remaining),
        "config_commit": (rc.config_source or {}).get("commit"), "reasons": list(dict.fromkeys(reasons))}


def preview(studio, identity, *, locked=False):
    job = read_job(studio, identity)
    result = dict(resumable=False, reasons=[], required_attempts=0, conditional_retries=0,
                  maximum_attempts=0, known_cost_usd=None, unresolved_usd=None,
                  reserved_usd=None, remaining_ceiling_usd=None, config_commit=None)
    try:
        if not locked:
            with owner(studio, identity):
                return preview(studio, identity, locked=True)
        _, rows, values = inspect(studio, job)
        result.update(values)
        if job.get("cancel_requested") or job["status"] not in ("paused", "interrupted", "failed"):
            result["reasons"].append("Only paused, interrupted or recoverable failed runs can continue")
        if not result["required_attempts"]:
            result["reasons"].append("No required attempts remain")
        result["resumable"] = not result["reasons"]
        result["preview_id"] = sha256_json({"run": identity, "status": job["status"],
            "config_hash": job["config_hash"], "rows": rows, "preview": result,
            "segments": job.get("execution_segments", [])})
    except (config.ConfigError, ValueError, RuntimeError, OSError) as exc:
        result["reasons"] = [str(exc)]
    return result


def resume(studio, identity, *, preview_id=None, start=True):
    from wb_studio.app import now
    with studio.lock:
        job = read_job(studio, identity)
        if preview_id and job.get("resume_preview_id") == preview_id and job["status"] in ("queued", "running", "completed"):
            return studio.job(identity)
        if not preview_id:
            raise ValueError("Review a current continuation preview before resuming")
        with owner(studio, identity):
            current = preview(studio, identity, locked=True)
            if not current["resumable"]:
                raise ValueError("; ".join(current["reasons"]))
            if current["preview_id"] != preview_id:
                raise ValueError("Run or billing changed after preview; review continuation again")
            job.update(status="queued", pause_requested=False, active_attempts=0,
                       resumed_at=now(), resume_preview_id=preview_id)
            job.pop("finished_at", None)
            job.pop("error", None)
            studio.cancelled[identity] = threading.Event()
            write_json(studio.directory / identity / "job.json", job)
            studio.emit(identity, "run_control", status="queued", pause_requested=False,
                        active_attempts=0, resumed_at=job["resumed_at"])
    if start:
        threading.Thread(target=studio.execute, args=(identity,), daemon=True).start()
    return studio.job(identity)


def pause(studio, identity):
    with studio.lock:
        job = read_job(studio, identity)
        if job["status"] not in ("queued", "running", "pausing", "paused"):
            raise ValueError("Only queued or running runs can be paused")
        job.update(pause_requested=True, status="pausing" if job["status"] in ("running", "pausing") else "paused")
        studio._save_control(job)
        return studio.job(identity)


def cancel(studio, identity):
    from wb_studio.app import now
    with studio.lock:
        job = read_job(studio, identity)
        if job["status"] in ("queued", "running", "pausing", "paused", "interrupted", "failed", "cancelling"):
            studio.cancelled.setdefault(identity, threading.Event()).set()
            job["cancel_requested"] = True
            job["status"] = "cancelling" if job.get("active_attempts") else "cancelled"
            if job["status"] == "cancelled":
                job["finished_at"] = now()
                database = studio.directory / identity / "results.sqlite3"
                if database.exists():
                    store = Store(database)
                    try:
                        if store.run(identity):
                            store.set_stop_reason(identity, "cancelled")
                    finally:
                        store.close()
            studio._save_control(job)
        return studio.job(identity)


def admission(studio, identity, *attempt):
    with studio.lock:
        job = read_job(studio, identity)
        if job.get("cancel_requested") or job["status"] in ("cancelled", "cancelling"):
            return "cancelled"
        if job.get("pause_requested"):
            return "paused"
        job["active_attempts"] = job.get("active_attempts", 0) + 1
        studio._save_control(job)
        studio.emit(identity, "attempt_started", task=attempt[0], model=attempt[1], trial=attempt[2])


def release(studio, identity, *attempt):
    with studio.lock:
        job = read_job(studio, identity)
        job["active_attempts"] = max(0, job.get("active_attempts", 0) - 1)
        studio._save_control(job)


def recover_startup(studio, path, job):
    from wb_studio.app import now
    if job["status"] not in ("queued", "running", "pausing", "cancelling"):
        return
    try:
        with owner(studio, job["id"]):
            if job["status"] == "queued" and not (path.parent / "execution.claimed").exists():
                return
            cancelled = job.get("cancel_requested") or job["status"] == "cancelling"
            job.update(status="cancelled" if cancelled else "interrupted", cancel_requested=bool(cancelled), active_attempts=0, finished_at=now(),
                       error="Execution stopped. Review remaining work and billing before resuming.")
            if cancelled:
                job.pop("error", None)
                database = path.parent / "results.sqlite3"
                if database.exists():
                    store = Store(database)
                    try:
                        if store.run(job["id"]):
                            store.set_stop_reason(job["id"], "cancelled")
                    finally:
                        store.close()
            write_json(path, job)
            for envelope in studio.ledger.run_reservations():
                if envelope.closed_at is None and (envelope.scope_id == job["id"] or envelope.metadata.get("run_id") == job["id"]):
                    studio.ledger.finish_run(envelope.scope_id)
    except RuntimeError:
        pass  # A live execution owns the lock; never relabel or steal its work.


def execute(studio, identity):
    try:
        with owner(studio, identity):
            _execute_owned(studio, identity)
    except RuntimeError as exc:
        if str(exc) != "Another Studio process owns this data directory":
            raise


def segment_budget_status(ledger, envelope):
    """Only this segment's unused envelope is available to its own admission."""
    with ledger._transaction() as connection:
        week, _ = ledger._time(None)
        status = ledger._status(connection, week)
        row = connection.execute("SELECT maximum_microusd, closed_at FROM budget_run_reservations WHERE scope_id=?", (envelope,)).fetchone()
        unused = max(0, row["maximum_microusd"] - ledger._run_used(connection, envelope)) if row and row["closed_at"] is None else 0
        return replace(status, held_microusd=max(0, status.held_microusd - unused))


def _execute_owned(studio, identity):
    from concurrent.futures import ThreadPoolExecutor
    import shutil
    from wb_studio.app import now
    from wb_studio import benchmark_config as bc
    from scripts.resume_studio_run import RecoveryLedger

    job = read_job(studio, identity)
    if job["status"] != "queued" or job.get("pause_requested"):
        return
    folder = studio.directory / identity
    store, envelope, segment = None, None, None
    try:
        rc, prior_rows, state = inspect(studio, job)
        if state["reasons"]:
            raise ValueError("; ".join(state["reasons"]))
        if not job.get("resumed_at"):
            reasons = bc._readiness(studio, rc, {**os.environ, "WB_OPERATOR": job["operator"]})
            if reasons:
                raise ValueError("; ".join(reasons))
        store = Store(folder / "results.sqlite3")
        continuing = store.run(identity) is not None
        if job.get("approval_request_id"):
            store.bind_approval_run(job["approval_request_id"], identity)
        segment_id = uuid.uuid4().hex
        segment = dict(id=segment_id, started_at=now(), status="running",
                       deployment=os.environ.get("RAILWAY_DEPLOYMENT_ID"),
                       competitor_identities=state["competitor_identities"])
        from wb_studio.monarch_provenance import capture
        segment["monarch_provenance"] = capture(rc, os.environ)
        segment_dir = folder / "segments" / segment_id
        segment_dir.mkdir(parents=True)
        write_json(segment_dir / "prior-results.json", prior_rows)
        output = segment_dir / "evidence"
        # Preserve the old generation, including infrastructure attempts whose
        # cumulative row will be replaced by the existing continuation policy.
        completed = store.completed_identities(identity)
        for row in prior_rows:
            if (row["task_id"], row["arm"], row["trial"]) not in completed:
                old = Path(row["artifacts_uri"])
                new = output / identity / "episodes" / row["task_id"] / row["arm"].replace("/", "_") / f"t{row['trial']}"
                shutil.copytree(old, new)
        ledger = None
        if approvals.is_paid(rc):
            # Close only unused capacity from a dead segment; unknown requests
            # already refused above and their liabilities are never released.
            for old in studio.ledger.run_reservations():
                if old.closed_at is None and (old.scope_id == identity or old.metadata.get("run_id") == identity):
                    studio.ledger.finish_run(old.scope_id)
            envelope = identity + "#" + segment_id
            studio.ledger.reserve_run(envelope, Decimal(state["remaining_ceiling_usd"]),
                metadata={"run_id": identity, "operator": job["operator"], "segment": segment_id})
            ledger = RecoveryLedger(studio.ledger, segment_id, envelope)
        orch = Orchestrator.from_config(store, rc, output, ledger=ledger, operator=job["operator"],
            attempt_admission=lambda *attempt: admission(studio, identity, *attempt),
            attempt_release=lambda *attempt: release(studio, identity, *attempt))
        orch.approval_request_id = job.get("approval_request_id")
        # The global budget already contains this segment's reserved capacity.
        # Its request reservations still enforce both the envelope and the week.
        if ledger is not None:
            ledger.status = lambda: segment_budget_status(studio.ledger, envelope)
        with studio.lock:
            job = read_job(studio, identity)
            if job["status"] != "queued" or job.get("pause_requested"):
                return
            job.update(status="running", active_attempts=0, competitor_identities=state["competitor_identities"])
            job.setdefault("execution_segments", []).append(segment)
            write_json(folder / "execution.claimed", {"segment": segment_id, "started_at": segment["started_at"]})
            write_json(folder / "job.json", job)
            studio.emit(identity, "running", segment=segment_id, resumed_at=job.get("resumed_at"))
        seen = {sha256_json(r) for r in prior_rows}
        cancel_event = studio.cancelled.setdefault(identity, threading.Event())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(orch.resume if continuing else orch.run, identity)
            while True:
                finished = future.done()
                current = read_job(studio, identity)
                if cancel_event.is_set() or current["status"] in ("cancelled", "cancelling"):
                    orch.cancel()
                rows = store.episodes(run=identity)["rows"]
                with studio.lock:
                    current = read_job(studio, identity)
                    current.update(completed=len(rows), results=[{
                        "task": r["task_id"], "model": r["arm"], "passed": r["passed"],
                        "termination": r["termination"], "episode_id": r["episode_id"],
                        "cost_usd": r["cost_usd"]} for r in rows])
                    unknown = any(r.get("cost_usd") is None or {"billing=unknown", "cost_missing"}.intersection(r.get("flags", [])) for r in rows)
                    current["cost_usd"] = None if unknown else sum(r["cost_usd"] for r in rows)
                    write_json(folder / "job.json", current)
                    for row in rows:
                        signature = sha256_json(row)
                        if signature not in seen:
                            seen.add(signature)
                            studio.emit(identity, "result", task=row["task_id"], model=row["arm"],
                                        episode_id=row["episode_id"], passed=row["passed"],
                                        termination=row["termination"], cost_usd=row["cost_usd"], segment=segment_id)
                if finished:
                    future.result()
                    break
                threading.Event().wait(0.1)
        terminal, error = "completed", None
    except Exception as exc:
        stopped = (store.run(identity) or {}).get("stop_reason") if store else None
        terminal = "paused" if stopped == "paused" else "cancelled" if stopped == "cancelled" else "failed"
        error = None if terminal in ("paused", "cancelled") else str(exc)
    finally:
        if envelope:
            studio.ledger.finish_run(envelope)
        if store:
            store.close()
    # A queued pause/cancel racing preflight returned above, without a segment.
    with studio.lock:
        job = read_job(studio, identity)
        if job["status"] in ("cancelled", "cancelling"):
            terminal = "cancelled"
        job.update(status=terminal, active_attempts=0, finished_at=now())
        if error:
            job["error"] = error
        else:
            job.pop("error", None)
        if terminal == "completed":
            job["pause_requested"] = False
        if segment:
            segment.update(status=terminal, finished_at=job["finished_at"])
            for entry in job.get("execution_segments", []):
                if entry["id"] == segment["id"]:
                    entry.update(segment)
        write_json(folder / "job.json", job)
        studio.emit(identity, "finished", job=studio.job(identity), budget=studio.budget())
