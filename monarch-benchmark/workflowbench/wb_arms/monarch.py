"""monarch/stock@release and monarch/lab@cfg-hash arms per BUILD-SPEC §2.2.

Two integration points, both configured by env until Deyton names the real
entrypoints (open question #1 — blocks running, not building):

  MONARCH_AUTHORING_CMD  command template driving Monarch's workflow-authoring
                         agent headless. Placeholders: {goal_file} {workdir}.
  MONARCH_ENGINE_CMD     command template running the engine (Option A: the
                         engine speaks MCP and reads {mcp_config}; if the
                         answer turns out to be HTTP, build the §2.2 Option B
                         FastAPI shim instead). Placeholders: {workdir}
                         {mcp_config}.
  MONARCH_VERSION        release tag recorded in the stock arm name.
  MONARCH_LAB_CONFIG     path to the lab config bundle; its sha256 becomes the
                         lab arm's cfg-hash (printed in every row; the report
                         builder quarantines monarch/lab@* by allowlist).

Both phases append telemetry to events.jsonl (BUILD-SPEC §2.3) if Monarch
emits it; the collector folds it into phases + gate_refusals either way.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from wb_arms.api_loop import ArmResult, EpisodeTimeout, InfraError
from wb_orchestrator.telemetry import collect, read_events
from wb_world.episode import Episode


def _cfg_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


class MonarchArm:
    provider_key = "monarch"

    def __init__(self, key: str, workdir_root: str | Path = "out/monarch-work"):
        if key.startswith("monarch/lab"):
            cfg = os.environ.get("MONARCH_LAB_CONFIG")
            if not cfg or not Path(cfg).exists():
                raise InfraError("infra:harness_crash",
                                 "monarch/lab requires MONARCH_LAB_CONFIG (config bundle path); "
                                 "cfg-hash is derived from it and printed in every row")
            self.lab_config = cfg
            self.name = f"monarch/lab@{_cfg_hash(cfg)}"
        elif key.startswith("monarch/stock"):
            self.lab_config = None
            self.name = f"monarch/stock@{os.environ.get('MONARCH_VERSION', 'unknown')}"
        else:
            raise ValueError(f"unknown monarch arm {key!r}")
        self.workdir_root = Path(workdir_root)

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        authoring = os.environ.get("MONARCH_AUTHORING_CMD")
        engine = os.environ.get("MONARCH_ENGINE_CMD")
        if not authoring or not engine:
            raise InfraError(
                "infra:harness_crash",
                "Monarch arm blocked: set MONARCH_AUTHORING_CMD and MONARCH_ENGINE_CMD "
                "(BUILD-SPEC §2.2 open question #1 — Deyton names the headless authoring "
                "entrypoint and confirms the engine speaks MCP)")

        workdir = self.workdir_root / ep.episode_id.replace("/", "_")
        snap_dir = workdir / "snapshots"
        workdir.mkdir(parents=True, exist_ok=True)
        task_file = workdir / "task.json"
        task_file.write_text(json.dumps(ep.task, default=str))
        goal_file = workdir / "goal.txt"
        goal_file.write_text(ep.task["prompt"][1]["content"])
        mcp_config = workdir / "mcp.json"
        mcp_config.write_text(json.dumps({
            "mcpServers": {"wb-world": {
                "command": sys.executable,
                "args": ["-m", "wb_world.server"],
                "env": {"WB_TASK_FILE": str(task_file),
                        "WB_EPISODE_ID": ep.episode_id,
                        "WB_SNAPSHOT_DIR": str(snap_dir)},
            }}}, indent=1))
        env = dict(os.environ)
        env["WB_EVENTS_FILE"] = str(workdir / "events.jsonl")
        if self.lab_config:
            env["MONARCH_CONFIG"] = self.lab_config

        res = ArmResult()
        for phase, template in (("authoring", authoring), ("execution", engine)):
            budget = (deadline - time.monotonic()) if deadline else 600.0
            if budget <= 0:
                raise EpisodeTimeout(f"deadline hit before {phase}")
            cmd = [a.format(goal_file=goal_file, workdir=workdir, mcp_config=mcp_config)
                   for a in shlex.split(template)]
            try:
                proc = subprocess.run(cmd, cwd=workdir, capture_output=True,
                                      text=True, timeout=budget, env=env)
            except subprocess.TimeoutExpired as e:
                raise EpisodeTimeout(f"{phase} exceeded budget") from e
            if proc.returncode != 0:
                res.termination = "agent_error"
                res.error = f"{phase} rc={proc.returncode}: {proc.stderr[:400]}"
                break

        tel = collect(read_events(workdir / "events.jsonl"))
        res.turn_log = [{"telemetry": {
            "gate_refusals": tel["gate_refusals"],
            "workflow_outcome": tel["workflow_outcome"]}}]
        for phase, m in tel["phases"].items():
            res.tokens_prompt += m.tokens_input or 0
            res.tokens_output += m.tokens_output or 0
            res.cost_usd += m.cost_usd or 0.0
            res.turns += m.turns
            res.tool_calls += m.tool_calls
        res.phases = tel["phases"]          # picked up by the orchestrator row
        res.gate_refusals = tel["gate_refusals"]
        if tel["workflow_outcome"] == "workflow_abandoned" and res.termination == "completed":
            res.termination = "agent_error"
            res.error = "workflow_abandoned"

        # Same fold-back as the CLI arm: the engine acted through wb_world.server,
        # so the authoritative snapshot1 comes from the MCP server process.
        snap1 = snap_dir / "snapshot1.json"
        if snap1.exists():
            from automationbench.runner import strip_none_values
            from automationbench.schema.world import WorldState
            data = json.loads(snap1.read_text())
            ep.world = WorldState(**strip_none_values(
                {k: v for k, v in data.items() if k != "meta"}))
            calls = snap_dir / "tool_calls.json"
            if calls.exists():
                ep.tool_calls = json.loads(calls.read_text())
        else:
            res.flags.append("no_snapshot1_from_mcp_server")
        return res
