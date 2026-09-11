"""Read configured-run reports from saved outcomes, never regrade or migrate."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3


def saved_rows(database, identity):
    database = Path(database)
    if not database.is_file():
        return []
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return [json.loads(r[0]) for r in connection.execute(
            "SELECT row_json FROM episodes WHERE run_id=? ORDER BY episode_id", (identity,))]
    finally:
        connection.close()


def configured_job(job, folder):
    if not job.get("resolved_config") or not job.get("settings", {}).get("plan_semantics"):
        return job
    folder = Path(folder).resolve()
    rows = saved_rows(folder / "results.sqlite3", job["id"])
    results, versions, judges = [], set(), set()
    for row in rows:
        seconds = None
        if row.get("started_at") and row.get("finished_at"):
            seconds = (datetime.fromisoformat(row["finished_at"]) - datetime.fromisoformat(row["started_at"])).total_seconds()
        checks = list(row.get("check_results") or [])
        checks.append({"type": "allowed_changes_only", "passed": row.get("invariant_passed")})
        results.append({**row, "task": row["task_id"], "model": row["arm"], "checks": checks,
                        "seconds": seconds, "turns": sum(p.get("turns", 0) for p in row.get("phases", {}).values())})
        root = Path(row.get("artifacts_uri") or "").resolve()
        manifest = root / "manifest.json"
        if root.is_relative_to(folder) and manifest.is_file():
            provenance = json.loads(manifest.read_text(encoding="utf-8")).get("provenance", {})
            if provenance.get("automation_bench_version"):
                versions.add(provenance["automation_bench_version"])
            sources = {k: v for k, v in provenance.get("source_sha256", {}).items() if k.startswith("grader/")}
            if sources:
                judges.add(json.dumps(sources, sort_keys=True))
    settings = dict(job["settings"])
    recorded = list(dict.fromkeys(r["model"] for r in results))
    models = []
    for name in settings.get("models", []):
        matches = [n for n in recorded if n.startswith("monarch@")] if name == "monarch" else []
        models.extend(matches or [name])
    models.extend(n for n in recorded if n not in models)
    settings["models"] = models
    # Configured plans use their frozen competitors, not ordinary Studio architectures.
    settings["arms"] = []
    plan = job["resolved_config"]["plan"]
    settings.update(repetitions=plan["repetitions"], retry_on_fail=plan.get("retry_on_fail", 0),
                    baseline=plan.get("baseline"))
    if settings["baseline"] == "monarch":
        matches = [n for n in models if n.startswith("monarch@")]
        settings["baseline"] = matches[0] if len(matches) == 1 else None
    components = dict(job.get("component_manifest") or {})
    if judges:
        components["judge"] = {"id": "WorkflowBench recorded grading sources",
                               "sha256": hashlib.sha256(json.dumps(sorted(judges)).encode()).hexdigest()}
    return {**job, "settings": settings, "results": results or job.get("results", []),
            "component_manifest": components, "world_manifest": {"version": ", ".join(sorted(versions)) or "unknown"},
            "recorded_world_version": ", ".join(sorted(versions)) or "unknown"}
