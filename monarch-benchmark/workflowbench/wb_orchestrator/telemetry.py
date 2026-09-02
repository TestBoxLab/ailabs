"""M2 telemetry per BUILD-SPEC §2.3: per-episode event stream (events.jsonl)
folded into EpisodeRow.phases.{authoring, execution} + gate_refusals.

Event shape: {episode_id, phase: authoring|execution, event, ts, tokens?, cost?, meta}
Minimum events: turn_start/turn_end (authoring), workflow_saved |
workflow_abandoned, engine_run_start/end, step_dispatch,
gate_decision{allowed|refused, reason}, retry.

This event list is simultaneously the product feature request from the RFC —
the bench is its first consumer, the release pipeline its second. The Monarch
arm (M2) emits these; this module only collects.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from runner.schema import PhaseMetrics

PHASES = ("authoring", "execution")
KNOWN_EVENTS = {"turn_start", "turn_end", "workflow_saved", "workflow_abandoned",
                "engine_run_start", "engine_run_end", "step_dispatch",
                "gate_decision", "retry"}


class TelemetryWriter:
    """Append-only events.jsonl writer for arm launchers."""

    def __init__(self, path: str | Path, episode_id: str):
        self.path = Path(path)
        self.episode_id = episode_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, phase: str, event: str, ts: str, tokens: dict | None = None,
             cost: float | None = None, **meta: Any) -> None:
        if phase not in PHASES:
            raise ValueError(f"phase must be one of {PHASES}, got {phase!r}")
        rec: dict[str, Any] = {"episode_id": self.episode_id, "phase": phase,
                               "event": event, "ts": ts}
        if tokens is not None:
            rec["tokens"] = tokens
        if cost is not None:
            rec["cost"] = cost
        if meta:
            rec["meta"] = meta
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def read_events(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def collect(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Fold an event stream into phases + gate_refusals + outcome flags."""
    phases = {p: PhaseMetrics() for p in PHASES}
    wall: dict[str, dict[str, str]] = {p: {} for p in PHASES}
    gate_refusals: list[dict[str, Any]] = []
    retries = 0
    workflow_outcome: str | None = None
    unknown_events: set[str] = set()

    for e in events:
        phase, event = e.get("phase"), e.get("event")
        if phase not in PHASES:
            continue
        m = phases[phase]
        if event not in KNOWN_EVENTS:
            unknown_events.add(str(event))
        if event == "turn_end":
            m.turns += 1
        elif event == "step_dispatch":
            m.tool_calls += 1
        elif event == "gate_decision":
            meta = e.get("meta") or {}
            if meta.get("decision") == "refused":
                gate_refusals.append({"phase": phase, "reason": meta.get("reason"),
                                      "ts": e.get("ts")})
        elif event == "retry":
            retries += 1
        elif event in ("workflow_saved", "workflow_abandoned"):
            workflow_outcome = event
        if event in ("turn_start", "engine_run_start") and "start" not in wall[phase]:
            wall[phase]["start"] = e["ts"]
        if event in ("turn_end", "engine_run_end"):
            wall[phase]["end"] = e["ts"]
        tok = e.get("tokens") or {}
        if tok:
            m.tokens_input = (m.tokens_input or 0) + int(tok.get("input", 0))
            m.tokens_output = (m.tokens_output or 0) + int(tok.get("output", 0))
        if e.get("cost") is not None:
            m.cost_usd = (m.cost_usd or 0.0) + float(e["cost"])

    for p in PHASES:
        w = wall[p]
        if "start" in w and "end" in w:
            try:
                t0 = datetime.fromisoformat(w["start"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(w["end"].replace("Z", "+00:00"))
                phases[p].wall_clock_s = round((t1 - t0).total_seconds(), 4)
            except ValueError:
                pass

    return {"phases": phases, "gate_refusals": gate_refusals, "retries": retries,
            "workflow_outcome": workflow_outcome,
            "unknown_events": sorted(unknown_events)}
