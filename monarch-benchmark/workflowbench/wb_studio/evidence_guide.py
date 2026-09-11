"""Build a standalone human review guide from frozen tasks and saved outcomes."""
import json
from pathlib import Path

from wb_world.episode import contract_hash
from wb_studio.measures import initial_repetitions


def download(studio, identity, audience):
    from wb_studio.report_data import visible_setups
    from wb_studio.report_inputs import saved_rows
    job = studio.job(identity)
    shown, _ = visible_setups(job, audience)
    rows = saved_rows(studio.directory / identity / "results.sqlite3", identity)
    rows = [r for r in rows if r["arm"] in shown]
    return build(job, rows, studio.tasks)


def build(job, rows, tasks):
    settings = dict(job.get("settings") or {})
    settings.setdefault("repetitions", ((job.get("resolved_config") or {}).get("plan") or {}).get("repetitions", 1))
    job = {**job, "settings": settings}
    selected = []
    for identity, expected_hash in job["task_hashes"].items():
        task = tasks.get(identity)
        if task is None or contract_hash(task) != expected_hash:
            raise ValueError(f"Frozen task hash mismatch: {identity}")
        info = task.get("info") or {}
        selected.append({"id": identity, "hash": expected_hash, "prompt": task.get("prompt"),
                         "assertions": info.get("assertions", []),
                         "expected_changes": info.get("expected_changes", []),
                         "allowed_changes": info.get("allowed_changes", []),
                         "initial_state": info.get("initial_state")})
    attempts = [{"attempt_id": r["episode_id"], "task": r["task_id"], "competitor": r["arm"],
                 "initial_repetitions": initial_repetitions(job, r["arm"]),
                 "is_retry": "retry" in (r.get("flags") or []) or (r.get("trial") or 0) >= initial_repetitions(job, r["arm"]),
                 "trial": r.get("trial"), "passed": r.get("passed"), "termination": r.get("termination"),
                 "assertions_passed": r.get("assertions_passed"), "allowed_changes_passed": r.get("invariant_passed"),
                 "checks": r.get("check_results"), "unexpected_changes": r.get("unexpected_changes"),
                 "cost_usd": r.get("cost_usd")} for r in rows]
    data = {"run": job["id"], "tasks": selected, "attempts": attempts}
    # Escape the HTML script terminator without changing parsed JSON values.
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return (Path(__file__).parent / "templates/evidence-guide.html").read_text(encoding="utf-8").replace("__GUIDE_DATA__", encoded)
