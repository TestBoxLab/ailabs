"""SQLite results store. Orchestrator is the single writer (BUILD-SPEC §2.4).

Every query result carries its source line {suite, suite_version, denominator,
arm, run_id} from the query itself — that view is the only path the report
builder may read.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runner.schema import EpisodeRow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  config_hash TEXT NOT NULL,
  suite TEXT NOT NULL,
  config_json TEXT NOT NULL,
  started TEXT NOT NULL,
  finished TEXT,
  stop_reason TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  suite TEXT NOT NULL,
  task_id TEXT NOT NULL,
  arm TEXT NOT NULL,
  trial INTEGER NOT NULL,
  passed INTEGER NOT NULL,
  assertions_passed INTEGER NOT NULL,
  invariant_passed INTEGER NOT NULL,
  termination TEXT NOT NULL,
  tokens_prompt INTEGER,
  tokens_cached INTEGER,
  tokens_output INTEGER,
  cost_usd REAL,
  retries INTEGER NOT NULL DEFAULT 0,
  row_json TEXT NOT NULL,
  UNIQUE (run_id, task_id, arm, trial)
);
CREATE TABLE IF NOT EXISTS artifacts (
  episode_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  uri TEXT NOT NULL,
  PRIMARY KEY (episode_id, kind)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()   # reentrant: status() calls run() under the lock
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        # runs.stop_reason arrived after the first databases were written
        if "stop_reason" not in {r[1] for r in self._conn.execute("PRAGMA table_info(runs)")}:
            with self._conn:
                self._conn.execute("ALTER TABLE runs ADD COLUMN stop_reason TEXT")

    def close(self) -> None:
        self._conn.close()

    # -- runs -----------------------------------------------------------------
    def create_run(self, run_id: str, config_hash: str, suite: str, config: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO runs (run_id, config_hash, suite, config_json, started) VALUES (?,?,?,?,?)",
                (run_id, config_hash, suite, json.dumps(config, sort_keys=True), _now()))

    def finish_run(self, run_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE runs SET finished=?, stop_reason=NULL WHERE run_id=?",
                               (_now(), run_id))

    def set_stop_reason(self, run_id: str, reason: str | None) -> None:
        """One of cost_ceiling, weekly_budget, interrupted, worker_error, or None (data-model.md, State: run)."""
        with self._lock, self._conn:
            self._conn.execute("UPDATE runs SET stop_reason=? WHERE run_id=?", (reason, run_id))

    def run(self, run_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return dict(r) if r else None

    def runs(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM runs ORDER BY started")]

    # -- episodes -------------------------------------------------------------
    def record_episode(self, row: EpisodeRow) -> None:
        tok = row.tokens
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO episodes
                   (episode_id, run_id, suite, task_id, arm, trial, passed, assertions_passed,
                    invariant_passed, termination, tokens_prompt, tokens_cached, tokens_output,
                    cost_usd, retries, row_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row.episode_id, row.run_id, row.suite, row.task_id, row.arm, row.trial,
                 int(row.passed), int(row.assertions_passed), int(row.invariant_passed),
                 row.termination,
                 tok.prompt if tok else None, tok.cached if tok else None,
                 tok.output if tok else None, row.cost_usd, row.retries,
                 row.model_dump_json()))

    def add_artifact(self, episode_id: str, kind: str, uri: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO artifacts (episode_id, kind, uri) VALUES (?,?,?)",
                (episode_id, kind, uri))

    def artifacts(self, episode_id: str) -> dict[str, str]:
        with self._lock:
            return {r["kind"]: r["uri"] for r in self._conn.execute(
                "SELECT kind, uri FROM artifacts WHERE episode_id=?", (episode_id,))}

    def completed_identities(self, run_id: str) -> set[tuple[str, str, int]]:
        """Identities resume may skip. Infra-terminated rows are NOT final
        verdicts (the API failed, not the task) — resume re-attempts them and
        the fresh row replaces the infra one. The one exception is the attempt
        cap: the attempt's own spend hit it, so running it again can only hit
        it again."""
        with self._lock:
            return {(r["task_id"], r["arm"], r["trial"]) for r in self._conn.execute(
                "SELECT task_id, arm, trial FROM episodes WHERE run_id=? "
                "AND (termination NOT LIKE 'infra:%' OR termination = 'infra:attempt_cap')", (run_id,))}

    # -- the query view (only read path for stats/report) ---------------------
    def episodes(self, suite: str | None = None, arm: str | None = None,
                 run: str | None = None) -> dict[str, Any]:
        q, args = "SELECT row_json FROM episodes WHERE 1=1", []
        if suite:
            q += " AND suite=?"; args.append(suite)
        if arm:
            q += " AND arm=?"; args.append(arm)
        if run:
            q += " AND run_id=?"; args.append(run)
        with self._lock:
            rows = [json.loads(r["row_json"]) for r in self._conn.execute(q, args)]
        suites = sorted({r["suite"] for r in rows})
        return {
            "source": {
                "suite": suite or (suites[0] if len(suites) == 1 else suites),
                "suite_version": sorted({s.split("@")[-1] for s in suites}),
                "denominator": len(rows),
                "arm": arm or sorted({r["arm"] for r in rows}),
                "run_id": run or sorted({r["run_id"] for r in rows}),
            },
            "rows": rows,
        }

    def export_jsonl(self, run_id: str, path: str | Path) -> int:
        with self._lock:
            rows = [r["row_json"] for r in self._conn.execute(
                "SELECT row_json FROM episodes WHERE run_id=? ORDER BY task_id, arm, trial",
                (run_id,))]
        Path(path).write_text("\n".join(rows) + ("\n" if rows else ""))
        return len(rows)

    # -- status ---------------------------------------------------------------
    def status(self, run_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id!r}")
        by_arm: dict[str, dict] = {}
        with self._lock:
            arm_rows = list(self._conn.execute(
                """SELECT arm, COUNT(*) n, SUM(passed) passed,
                          SUM(termination='completed') completed,
                          SUM(termination LIKE 'infra:%') infra,
                          SUM(tokens_prompt) tp, SUM(tokens_cached) tc,
                          SUM(tokens_output) tout, SUM(cost_usd) cost,
                          SUM(row_json LIKE '%cache_reporting=absent%') cache_absent
                   FROM episodes WHERE run_id=? GROUP BY arm""", (run_id,)))
            terminations = {r["termination"]: r["n"] for r in self._conn.execute(
                "SELECT termination, COUNT(*) n FROM episodes WHERE run_id=? GROUP BY termination",
                (run_id,))}
        for r in arm_rows:
            tp, tc = r["tp"] or 0, r["tc"] or 0
            infra = r["infra"] or 0
            non_infra = r["n"] - infra
            by_arm[r["arm"]] = {
                "episodes": r["n"], "passed": r["passed"] or 0,
                # Infra failures are the harness's problem, not the task's:
                # they are excluded from the pass denominator (P7) and
                # reported as their own count. All-infra -> None, never 0.
                "non_infra": non_infra,
                "strict_pass_rate": round((r["passed"] or 0) / non_infra, 4) if non_infra else None,
                "completed": r["completed"] or 0, "infra": infra,
                "tokens_prompt": tp, "tokens_cached": tc,
                "tokens_output": r["tout"] or 0,
                "cache_hit_rate": round(tc / tp, 4) if tp else None,
                "cache_reporting_absent": r["cache_absent"] or 0,
                "cost_usd": round(r["cost"] or 0.0, 6),
            }
        config = json.loads(run["config_json"])
        total = config.get("attempts_total") or (
            config.get("n_tasks", 0) * len(config.get("arms", [])) * config.get("k", 0))
        done = sum(a["episodes"] for a in by_arm.values())
        return {"run_id": run_id, "suite": run["suite"], "config_hash": run["config_hash"],
                "started": run["started"], "finished": run["finished"],
                "stop_reason": run["stop_reason"],
                "spend_usd": round(sum(a["cost_usd"] for a in by_arm.values()), 6),
                "episodes_done": done, "episodes_total": total or done,
                "terminations": terminations, "arms": by_arm}
