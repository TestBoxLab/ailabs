"""bare/cli/claude-code arm per BUILD-SPEC §2.2.

Per-episode workdir with a generated .mcp.json pointing at wb_world.server
(env: task file, episode id, snapshot dir); invokes pinned
`claude -p "<goal>" --output-format json` headless; parses usage/cost from the
JSON result; version recorded from `claude --version`.

Stock policy (DESIGN §3): every non-default flag is documented in the row via
invocation(). API-key billing only — ANTHROPIC_API_KEY must be set;
subscription auth is never used for benchmark runs (the launcher strips
login-session env so a configured key is the only path).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from wb_arms.api_loop import ArmResult, EpisodeTimeout, InfraError
from wb_world.episode import Episode

# Non-default flags, named because "stock" is defined operationally:
# -p / --output-format json  : headless single-shot with parseable result
# --permission-mode bypassPermissions : unattended (no TTY to approve tools)
# --strict-mcp-config --mcp-config .mcp.json : only the episode's world server
_FLAGS = ["--output-format", "json", "--permission-mode", "bypassPermissions",
          "--strict-mcp-config", "--mcp-config", ".mcp.json"]


def claude_version() -> str | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
    return out.stdout.strip() or None


def invocation() -> dict:
    """Documented in every row: the exact non-default invocation (stock policy)."""
    return {"cmd": "claude -p <goal>", "flags": _FLAGS, "billing": "api-key"}


class ClaudeCodeArm:
    name = "bare/cli/claude-code"
    provider_key = "claude-code"   # its own concurrency bucket

    def __init__(self, workdir_root: str | Path = "out/cc-work", env: dict[str, str] | None = None):
        self.workdir_root = Path(workdir_root)
        self.env = dict(env or {})  # from the harness file, merged over os.environ at launch
        self.version = claude_version()
        self.name = f"bare/cli/claude-code@{self.version or 'missing'}"

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise InfraError("infra:harness_crash",
                             "ANTHROPIC_API_KEY not set — benchmark runs are API-key "
                             "billed only; refusing to fall back to subscription auth")
        exe = shutil.which("claude")
        if not exe:
            raise InfraError("infra:harness_crash", "claude CLI not on PATH")

        workdir = self.workdir_root / ep.episode_id.replace("/", "_")
        snap_dir = workdir / "snapshots"
        workdir.mkdir(parents=True, exist_ok=True)
        task_file = workdir / "task.json"
        task_file.write_text(json.dumps(ep.task, default=str))
        # The CLI talks to an out-of-process world; same tool surface, MCP hop.
        (workdir / ".mcp.json").write_text(json.dumps({
            "mcpServers": {"wb-world": {
                "command": sys.executable,
                "args": ["-m", "wb_world.server"],
                "env": {"WB_TASK_FILE": str(task_file),
                        "WB_EPISODE_ID": ep.episode_id,
                        "WB_SNAPSHOT_DIR": str(snap_dir)},
            }}}, indent=1))

        goal = ep.task["prompt"][1]["content"]
        sysprompt = ep.task["prompt"][0]["content"]
        timeout = max((deadline - time.monotonic()) if deadline else 600.0, 1.0)
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_OAUTH")}
        env.update(self.env)
        try:
            proc = subprocess.run(
                [exe, "-p", goal, "--append-system-prompt", sysprompt, *_FLAGS],
                cwd=workdir, capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise EpisodeTimeout(f"claude CLI exceeded {timeout:.0f}s") from e

        res = parse_result(proc.stdout, proc.returncode, proc.stderr)
        # Fold the out-of-process snapshot back into this Episode so the
        # orchestrator's SNAPSHOT1/GRADE path is identical across arms.
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
                res.tool_calls = len(ep.tool_calls)
        else:
            res.flags.append("no_snapshot1_from_mcp_server")
        return res


def parse_result(stdout: str, returncode: int, stderr: str = "") -> ArmResult:
    """Parse `claude -p --output-format json` output into an ArmResult."""
    res = ArmResult()
    try:
        data = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        data = {}
    if not data:
        res.termination = "agent_error" if returncode != 0 else "completed"
        res.error = (stderr or "empty CLI output")[:500]
        res.flags.append("cli_output_unparseable")
        return res
    if data.get("is_error"):
        res.termination = "agent_error"
        res.error = str(data.get("result"))[:500]
    res.final_text = data.get("result")
    res.turns = int(data.get("num_turns") or 0)
    res.cost_usd = float(data.get("total_cost_usd") or 0.0)
    usage = data.get("usage") or {}
    res.tokens_prompt = int(usage.get("input_tokens") or 0) \
        + int(usage.get("cache_read_input_tokens") or 0) \
        + int(usage.get("cache_creation_input_tokens") or 0)
    res.tokens_cached = int(usage.get("cache_read_input_tokens") or 0)
    res.tokens_output = int(usage.get("output_tokens") or 0)
    if "usage" not in data:
        res.flags.append("cache_reporting=absent")
    return res
