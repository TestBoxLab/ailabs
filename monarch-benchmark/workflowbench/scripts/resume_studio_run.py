"""Explicit operational recovery, not an automatic Studio restart policy.

An operator first inspects external work and billing, then supplies a receipt
binding every uncommitted attempt to its preserved files and settled reservation.
Recovery records an ungraded infrastructure outcome and continues the same run in
a fresh evidence generation. Original files and completed rows remain untouched.
Only fully reconciled interruptions are supported here; unknown billing refuses.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from runner.schema import EpisodeRow, TokenUsage
from wb_orchestrator import approvals, config
from wb_orchestrator.budget import BudgetLedger
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.evidence import verify_manifest, write_json
from wb_results.store import Store
from wb_studio.app import Studio


class RecoveryLedger:
    """Namespace new dispatch IDs while preserving the original budget scopes."""
    def __init__(self, ledger, namespace, run_id=None):
        self.ledger, self.namespace, self.run_id = ledger, namespace, run_id

    def __getattr__(self, name):
        return getattr(self.ledger, name)

    def reserve(self, identity, *args, **kwargs):
        if self.run_id:
            kwargs["run_id"] = self.run_id
        kwargs["metadata"] = {**kwargs.get("metadata", {}), "recovery": self.namespace,
                              "original_request_id": identity}
        return self.ledger.reserve(identity + "#" + self.namespace, *args, **kwargs)

    def claim(self, identity, *args, **kwargs):
        return self.ledger.claim(identity + "#" + self.namespace, *args, **kwargs)

    def settle(self, identity, *args, **kwargs):
        return self.ledger.settle(identity + "#" + self.namespace, *args, **kwargs)


def recover(folder, receipt, ledger, *, execute=False):
    folder = Path(folder).resolve()
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    identity = job["id"]
    if job["status"] != "interrupted":
        raise ValueError("Only an interrupted run can use operational recovery")
    if (receipt.get("run_id") != identity or receipt.get("config_hash") != job["config_hash"]
            or not receipt.get("reason") or receipt.get("operator") != os.environ.get("WB_OPERATOR")):
        raise ValueError("Recovery needs a matching run, configuration, reason and named operator")
    store = Store(folder / "results.sqlite3")
    try:
        rc = config.resume_config(job["resolved_config"])
        if rc.hash != job["config_hash"] or store.run(identity)["config_hash"] != rc.hash:
            raise ValueError("Configuration changed since the original launch")
        if approvals.is_paid(rc):
            reasons = approvals.launch_readiness(rc, os.environ)
            if reasons:
                raise ValueError("; ".join(reasons))
        rows = store.episodes(run=identity)["rows"]
        if any(r["termination"] != "completed" for r in rows):
            raise ValueError("This procedure requires review of any existing non-completed rows")
        for row in rows:
            root = Path(row["artifacts_uri"]).resolve()
            if not root.is_relative_to(folder) or verify_manifest(
                    root / "manifest.json", episode_id=row["episode_id"],
                    contract_sha256=row["contract_sha256"]):
                raise ValueError("Original completed evidence is invalid")
        reservations = {r.reservation_id: r for r in ledger.reservations()}
        items = receipt.get("items", [])
        listed = {Path(i["artifacts_uri"]).resolve() for i in items}
        if len(listed) != len(items) or len({i["episode_id"] for i in items}) != len(items):
            raise ValueError("Duplicate interrupted evidence")
        original = folder / "evidence" / identity / "episodes"
        completed_paths = {Path(r["artifacts_uri"]).resolve() for r in rows}
        uncommitted = {p.parent.parent.resolve() for p in original.rglob("attempt.json")} - completed_paths
        if listed != uncommitted:
            raise ValueError("Receipt must cover every uncommitted evidence directory")
        tasks = {t["task"]: t for t in rc.tasks}
        arms = {r["arm"] for r in rows} | {c.name for c in rc.competitors}
        partials = []
        for item in items:
            root = Path(item["artifacts_uri"]).resolve()
            expected_id = f"{identity}/{item['task_id']}/{item['arm'].replace('/', '_')}/t{item['trial']}"
            expected_path = original / item["task_id"] / item["arm"].replace("/", "_") / f"t{item['trial']}"
            if (item["task_id"] not in tasks or item["arm"] not in arms or item["episode_id"] != expected_id
                    or root != expected_path.resolve() or not root.is_relative_to(original.resolve())):
                raise ValueError("Interrupted identity does not match the frozen run")
            files = list(root.rglob("*"))
            if any(p.is_symlink() for p in files):
                raise ValueError("Interrupted evidence contains a symbolic link")
            actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in files if p.is_file()}
            if not actual or actual != item["files"]:
                raise ValueError("Interrupted evidence changed after inspection")
            matching = {r.reservation_id for r in reservations.values() if r.scope_id == expected_id}
            if not matching or matching != set(item["reservations"]) or not item.get("billing_evidence"):
                raise ValueError("Receipt must cover every interrupted reservation")
            bills = [reservations[r] for r in matching]
            if item["cost_usd"] is None or any(r.actual_usd is None for r in bills):
                raise ValueError("Unknown interrupted billing must be reconciled before recovery")
            amount = Decimal(str(item["cost_usd"]))
            if not amount.is_finite() or amount < 0 or sum(r.actual_usd for r in bills) != amount:
                raise ValueError("Interrupted cost disagrees with the shared ledger")
            metadata = json.loads((root / "attempt-000" / "attempt.json").read_text())
            partials.append(EpisodeRow(
                episode_id=expected_id, run_id=identity, task_id=item["task_id"], arm=item["arm"],
                trial=item["trial"], suite=store.run(identity)["suite"],
                contract_sha256=config.contract_hash(tasks[item["task_id"]]),
                passed=False, assertions_passed=False, invariant_passed=False, invariant_declared=False,
                termination="infra:interrupted", error="Server replaced; no final world or grader verdict retained",
                cost_usd=float(amount), tokens=TokenUsage(**item.get("tokens", {})),
                flags=["interrupted_generation", "final_world_unavailable", "ungraded"],
                artifacts_uri=str(root), started_at=metadata["started_at"]))
        probe = Orchestrator.from_config(store, rc, folder / "recovery" / "evidence",
                                         ledger=ledger if approvals.is_paid(rc) else None,
                                         operator=receipt["operator"])
        built = probe._arms()
        skip = store.completed_identities(identity)
        work = sum(sum((t["task"], a.name, trial) not in skip for t in rc.tasks
                       for trial in range(rc.plan.repetitions)) + len(probe._pending_retries(identity, a.name))
                   for a in built)
        first = sum(sum((t["task"], a.name, trial) not in skip for t in rc.tasks
                        for trial in range(rc.plan.repetitions)) for a in built)
        known = store.status(identity)["spend_usd"] + sum(float(i["cost_usd"]) for i in items)
        probe._spent = known
        if known >= rc.plan.cost_ceiling_usd:
            raise ValueError("The original run ceiling has already been reached")
        probe._admit(identity, built, skip)
        preview = dict(pending_min=work, pending_max=work + first * rc.plan.retry_on_fail,
                       recorded_cost_usd=known, remaining_ceiling_usd=rc.plan.cost_ceiling_usd-known,
                       interrupted_attempts=len(items), config_hash=rc.hash)
        if not execute:
            return preview
        recovery = folder / "recovery"
        recovery.mkdir(exist_ok=True)
        if (recovery / "evidence").exists():
            raise ValueError("A recovery generation already exists; inspect it before continuing")
        with (recovery / "operational.claimed").open("x") as claim:
            claim.write(json.dumps(preview))
            claim.flush()
            os.fsync(claim.fileno())
        write_json(recovery / "receipt.json", receipt)
        write_json(recovery / "interrupted-attempts.json", [p.model_dump(mode="json") for p in partials])
        for partial in partials:
            store.record_episode(partial)
        envelope = identity + "#recovery-1" if approvals.is_paid(rc) else None
        if envelope:
            ledger.reserve_run(envelope, Decimal(str(preview["remaining_ceiling_usd"])), metadata={
                "operator": receipt["operator"], "run_id": identity,
                "purpose": "Remaining original ceiling after reconciled interrupted spending"})
        orch = Orchestrator.from_config(store, rc, recovery / "evidence",
                                        ledger=RecoveryLedger(ledger, "recovery-1", envelope) if envelope else None,
                                        operator=receipt["operator"])
        # Keep the interrupted generation visible after the normal infrastructure
        # retry replaces its temporary row. Raw observations are never synthesized.
        original_arms = orch._arms
        def marked_arms():
            result = original_arms()
            for arm in result:
                run = arm.run
                def marked(ep, deadline=None, run=run):
                    value = run(ep, deadline=deadline)
                    if any(i["episode_id"] == ep.episode_id for i in items):
                        value.flags.append("interruption_recovered")
                    return value
                arm.run = marked
            return result
        orch._arms = marked_arms
        emitter = SimpleNamespace(directory=folder.parent, lock=threading.RLock(), _event_counts={})
        def emit(kind, **data):
            return Studio.emit(emitter, identity, kind, **data)
        job.update(status="running", recovery=preview, resumed_at=datetime.now(timezone.utc).isoformat(),
                   error=None, finished_at=None, interrupted_attempts=[p.model_dump(mode="json") for p in partials])
        write_json(folder / "job.json", job)
        emit("running", recovery=preview)
        seen = {r["episode_id"] for r in rows}
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(orch.resume, identity)
                while True:
                    current = json.loads((folder / "job.json").read_text())
                    if current["status"] in ("cancelling", "cancelled"):
                        orch.cancel()
                    rows = store.episodes(run=identity)["rows"]
                    job["results"] = [{"task": r["task_id"], "model": r["arm"], **{k: r.get(k)
                        for k in ("episode_id", "passed", "termination", "cost_usd", "error", "flags")}} for r in rows]
                    job["completed"] = len(rows)
                    job["cost_usd"] = None if any(r["cost_usd"] is None or
                        {"billing=unknown", "cost_missing"}.intersection(r.get("flags", [])) for r in rows) else sum(r["cost_usd"] for r in rows)
                    job["status"] = "cancelling" if current["status"] in ("cancelling", "cancelled") else "running"
                    write_json(folder / "job.json", job)
                    for result in job["results"]:
                        key = (result["episode_id"], result["termination"])
                        if result["episode_id"] not in seen and key not in seen:
                            seen.add(key)
                            emit("result", **result)
                    if future.done():
                        future.result()
                        if len(store.episodes(run=identity)["rows"]) == len(rows):
                            break
                    time.sleep(0.5)
            job["status"] = "completed"
        except Exception as exc:
            job.update(status="cancelled" if store.run(identity).get("stop_reason") == "cancelled" else "failed",
                       error=str(exc))
        finally:
            if envelope:
                ledger.finish_run(envelope)
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(folder / "job.json", job)
        emit("finished", job=job)
        return job
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", help="Paid continuation; default is read-only preflight")
    args = parser.parse_args()
    config.derive_langfuse_keys(os.environ)
    result = recover(args.job_dir, json.loads(args.receipt.read_text()), BudgetLedger(args.ledger), execute=args.execute)
    print(json.dumps({k: v for k, v in result.items() if k not in ("results", "resolved_config", "config_source", "interrupted_attempts")}, default=str))
