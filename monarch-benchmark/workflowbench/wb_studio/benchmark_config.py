"""Studio editing and execution of committed plans through the CLI resolver."""
from datetime import datetime, timezone
import json
import os
import re
import threading
import uuid

from wb_orchestrator import approvals, config
from wb_orchestrator.config_repository import Repository, RepositoryError, Conflict, validate_files, artifact, artifact_types
from wb_results.evidence import write_json
from wb_results.store import Store


def _now():
    return datetime.now(timezone.utc).isoformat()


def repository(studio):
    return getattr(studio, "config_repository", None) or Repository.from_env(studio.directory / "config-revisions")


def catalog(studio, snapshot=None, actor=None):
    repo = repository(studio)
    if repo is None:
        return {"configured": False, "writable": False, "repository": None, "branch": "main", "commit": None,
                "files": [], "history_url": None, "actor": actor, "artifact_types": artifact_types()}
    snapshot = snapshot or repo.snapshot()
    files = [{**f, "artifact": description} for f in snapshot["files"]
             if (description := artifact(f["path"], f["text"])) is not None]
    return {k: snapshot[k] for k in ("repository", "branch", "commit")} | {
        "files": files, "actor": actor, "artifact_types": artifact_types(),
        "configured": True, "writable": bool(repo.token),
        "history_url": f"https://github.com/{repo.repository}/commits/main/config",
        "warnings": validate_files({f["path"]: f["text"] for f in snapshot["files"]})}


def history(studio):
    try:
        repo = repository(studio)
        if repo is None:
            raise RepositoryError("The configuration repository is not configured")
        return {"history": repo.history(), "error": None}
    except (RepositoryError, ValueError) as exc:
        return {"history": [], "error": str(exc)}


def resolve(studio, payload):
    studio._load_env()
    repo = repository(studio)
    if repo is None:
        raise ValueError("Configure WB_CONFIG_REPOSITORY before selecting a repository plan")
    commit = payload.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Select an immutable configuration commit")
    return config.resolve_snapshot(repo.snapshot(commit), payload.get("product"), payload.get("plan"))


def _readiness(studio, rc, env):
    reasons = approvals.launch_readiness(rc, env) if approvals.is_paid(rc) else []
    if studio.coordinator is not None:
        reasons.append("Repository plan execution currently requires the local Studio runtime")
    if any(c.harness.kind == "cli" and c.harness.launcher != "claude-code" for c in rc.competitors):
        reasons.append("A plan requests a launcher unavailable in the configured-plan runtime")
    if any(t["task"] not in studio.tasks for t in rc.tasks):
        reasons.append("A plan references tasks outside the Studio catalog")
    if approvals.is_paid(rc) and rc.plan.cost_ceiling_usd > studio.ledger.status().available_usd:
        reasons.append("This week's available budget does not cover the plan ceiling")
    return reasons


def preview(studio, payload):
    result = {k: payload.get(k) for k in ("commit", "product", "plan")}
    result.update(tasks=[], competitors=[], attempts_min=0, attempts_max=0,
                  cost_ceiling_usd=None, launchable=False, reasons=[])
    try:
        rc = resolve(studio, payload)
        env = {**os.environ, **({"WB_OPERATOR": payload["operator"]} if payload.get("operator") else {})}
        reasons = _readiness(studio, rc, env)
        result.update(config_hash=rc.hash, tasks=[t["task"] for t in rc.tasks],
                      competitors=[c.name for c in rc.competitors],
                      attempts_min=rc.attempts_per_competitor_min * len(rc.competitors),
                      attempts_max=rc.attempts_total, cost_ceiling_usd=rc.plan.cost_ceiling_usd,
                      launchable=not reasons, reasons=reasons,
                      semantics="WorkflowBench configured plan; same execution as the CLI")
        result["preview_id"] = uuid.uuid4().hex
        write_json(studio.directory / "config-previews" / (result["preview_id"] + ".json"), result)
    except (config.ConfigError, ValueError) as exc:
        result["reasons"] = [str(exc)]
    return result


def create(studio, payload, start=True):
    preview_id = payload.get("preview_id", "")
    if not isinstance(preview_id, str) or not re.fullmatch(r"[a-f0-9]{32}", preview_id):
        raise ValueError("A server preview is required before launching a plan")
    identity = payload.get("request_id") or uuid.uuid4().hex
    if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", identity):
        raise ValueError("Invalid request ID")
    operator = payload.get("operator")
    if not isinstance(operator, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._-]{0,79}", operator):
        raise ValueError("Name the operator launching this plan")
    with studio.lock:
        if (studio.directory / identity / "job.json").exists():
            old = studio.job(identity)
            recorded = old.get("resolved_config", {})
            matches = (old.get("config_preview_id") == preview_id and old.get("operator") == operator
                       and old.get("config_source", {}).get("commit") == payload.get("commit")
                       and recorded.get("product", {}).get("name") == payload.get("product")
                       and recorded.get("plan", {}).get("name") == payload.get("plan"))
            if not matches:
                raise Conflict("This request ID belongs to a different plan launch")
            return old
    path = studio.directory / "config-previews" / (preview_id + ".json")
    if not path.exists():
        raise ValueError("The plan preview is unavailable; preview it again")
    saved = json.loads(path.read_text(encoding="utf-8"))
    if any(saved.get(k) != payload.get(k) for k in ("commit", "product", "plan")):
        raise ValueError("The selection changed since preview")
    rc = resolve(studio, payload)
    if saved["config_hash"] != rc.hash:
        raise Conflict("The task or configuration changed since preview; preview again before spending")
    env = {**os.environ, "WB_OPERATOR": operator}
    reasons = _readiness(studio, rc, env)
    if reasons:
        raise ValueError("; ".join(reasons))
    with studio.lock:
        folder = studio.directory / identity
        if (folder / "job.json").exists():
            old = studio.job(identity)
            if old.get("config_preview_id") != preview_id or old.get("operator") != operator:
                raise Conflict("This request ID belongs to a different plan launch")
            return old
        settings = {"models": [c.name for c in rc.competitors], "tasks": [t["task"] for t in rc.tasks],
                    "maximum_usd": str(rc.plan.cost_ceiling_usd), "concurrency": rc.plan.concurrency,
                    "track": "create-and-run" if rc.plan.track == "create-run" else "agentic-request",
                    "architectures": [], "configuration": {}, "plan_semantics": "workflowbench-configured-plan"}
        job = {"id": identity, "title": f"{rc.product.name} / {rc.plan.name}", "created_at": _now(),
               "status": "queued", "settings": settings, "results": [], "completed": 0,
               "total": rc.attempts_total, "cost_usd": 0, "active_attempts": 0,
               "config_source": rc.config_source, "resolved_config": rc.config_json,
               "config_preview_id": preview_id, "config_hash": rc.hash, "operator": operator,
               "task_hashes": {t["task"]: config.contract_hash(t) for t in rc.tasks}}
        folder.mkdir(parents=True, exist_ok=True)
        if approvals.is_paid(rc):
            store = Store(folder / "results.sqlite3")
            try:
                launch = approvals.admit_launch(store, rc, env, request_id=payload.get("approval_request_id"))
            finally:
                store.close()
            if not launch.run:
                raise ValueError(launch.message)
            job["approval_request_id"] = launch.request_id
        write_json(folder / "config-source.json", rc.config_source)
        studio.save(job)
        studio.cancelled[identity] = threading.Event()
        studio.emit(identity, "queued", job=job)
    if start:
        threading.Thread(target=studio.execute, args=(identity,), daemon=True).start()
    return job


def execute(studio, identity):
    from wb_studio.configured_controls import execute as execute_controlled
    return execute_controlled(studio, identity)


def dispatch(studio, action, payload, person=None, actor=None):
    allowed, why = studio.genesis.access.may_write(person)
    if not allowed:
        raise PermissionError(why)
    if person:
        payload = {**payload, "operator": person["name"]}
    if action == "preview":
        return preview(studio, payload)
    if action == "run":
        return create(studio, payload)
    repo = repository(studio)
    if repo is None:
        raise ValueError("Configure WB_CONFIG_REPOSITORY first")
    if action == "validate":
        result = repo.validate(payload.get("base_commit"), payload.get("changes"))
        return {k: result[k] for k in ("valid", "errors", "warnings", "diff")}
    if action == "save":
        if actor is None:
            raise PermissionError("An authenticated person or Basic login is required to save configuration")
        return catalog(studio, repo.save(payload.get("base_commit"), payload.get("changes"),
                                        payload.get("message"), actor), actor=actor)
    raise ValueError("Unknown configuration operation")
