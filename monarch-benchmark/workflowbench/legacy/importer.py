"""M3: one-time import of historical AutomationBench rows (BUILD-SPEC §2.9).

Source: Monarch_Main\\bench-host-state\\runs\\<run>\\{merged-,}run-summary.json
(merged preferred; shard-*/ rolls up into merged and is skipped to avoid
double-counting). Each source run directory becomes its own run_id
`legacy/<dirname>` under suite `automationbench-legacy@1.0.6`.

NOTE the spec says "v9.12" and "5,427 rows"; neither exists on disk — every
fork is on the 1.0.6 line and the summaries hold ~7.9k deduplicated rows. The
importer derives its own count and labels with the real version. Nulls + flags
where fields can't populate (tokens are unsplit totals; graded fields come
from the canonical block), never guesses.

Effort tiers normalized per §2.8: low|medium|high canonical; max/xhigh -> high.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runner.schema import EpisodeRow
from wb_results.store import Store

LEGACY_SUITE = "automationbench-legacy@1.0.6"
_EFFORT = {"low": "low", "medium": "medium", "high": "high",
           "max": "high", "xhigh": "high", "minimal": "low", None: None, "": None}
_TERMINATION = {"completed": "completed", "timeout": "timeout",
                "error": "agent_error", "aborted": "infra:harness_crash"}


def normalize_effort(e: str | None) -> str | None:
    return _EFFORT.get((e or "").lower() if e is not None else None, e)


def _row_from_summary(rec: dict[str, Any], run_id: str, idx: int) -> EpisodeRow:
    canonical = rec.get("canonical") or {}
    effort = normalize_effort(rec.get("reasoning_effort"))
    arm = f"legacy/{rec.get('arm', 'unknown')}@{rec.get('model', 'unknown')}" \
          + (f"/{effort}" if effort else "")
    trial = rec.get("replicate")
    if trial is None:
        trial = rec.get("position", idx)
    flags = ["legacy_import", "tokens_unsplit"]
    if rec.get("integrity_issues"):
        flags.append("integrity_issues")
    if canonical.get("guard_unknown"):
        flags.append("guard_unknown")
    if canonical.get("strict_min") != canonical.get("strict_max"):
        flags.append("strict_bounds_diverge")
    pos_total = canonical.get("positive_total")
    pos_passed = canonical.get("positive_passed")
    assertions_passed = (pos_passed == pos_total and (pos_total or 0) > 0) \
        if pos_total is not None else False
    invariant_passed = (canonical.get("guard_violations") or 0) == 0
    termination = _TERMINATION.get(str(rec.get("status", "")).lower(), "agent_error")
    return EpisodeRow(
        episode_id=f"{run_id}/{rec.get('task_id', f'row{idx}')}/{arm.replace('/', '_')}/t{trial}",
        run_id=run_id, suite=LEGACY_SUITE,
        task_id=rec.get("task_id", f"row{idx}"),
        arm=arm, model=rec.get("model"), trial=int(trial),
        # strict_min is the conservative bound; divergence is flagged above.
        # Same gate as the orchestrator: a non-completed episode never passes.
        passed=bool(canonical.get("strict_min", False)) and termination == "completed",
        assertions_passed=bool(assertions_passed),
        invariant_passed=bool(invariant_passed),
        invariant_declared=bool(canonical),
        n_changes=0, tokens=None,                    # unsplit totals: null, flagged
        cost_usd=rec.get("enforced_cost_usd"),
        flags=flags,
        termination=termination,
        contract_sha256=(rec.get("config_raw_sha256") or "")[:16] or None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
    )


def import_runs(store: Store, runs_dir: str | Path,
                limit_dirs: int | None = None) -> dict[str, Any]:
    runs_dir = Path(runs_dir)
    imported_runs, imported_rows, skipped_dirs = 0, 0, []
    dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())
    if limit_dirs:
        dirs = dirs[:limit_dirs]
    for d in dirs:
        src = d / "merged-run-summary.json"
        if not src.exists():
            src = d / "run-summary.json"
        if not src.exists():
            skipped_dirs.append(d.name)
            continue
        try:
            records = json.loads(src.read_text())
        except (json.JSONDecodeError, OSError) as e:
            skipped_dirs.append(f"{d.name} ({e})")
            continue
        if not isinstance(records, list) or not records:
            skipped_dirs.append(d.name)
            continue
        run_id = f"legacy/{d.name}"
        if store.run(run_id) is None:
            store.create_run(run_id, "legacy-import", LEGACY_SUITE,
                             {"source": str(src), "arms": [], "k": 0, "n_tasks": 0,
                              "importer": "legacy.importer@1"})
        for i, rec in enumerate(records):
            store.record_episode(_row_from_summary(rec, run_id, i))
            imported_rows += 1
        store.finish_run(run_id)
        imported_runs += 1
    return {"runs_imported": imported_runs, "rows_imported": imported_rows,
            "dirs_skipped": skipped_dirs, "suite": LEGACY_SUITE}
