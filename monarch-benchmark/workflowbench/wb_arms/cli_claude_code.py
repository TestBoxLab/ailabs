"""Claude Code adapter: native execution blocked; offline parsing supported.

The old host launcher exposed grading tasks, snapshots and host credentials to
an agent with unrestricted shell access. No native execution is supported until
native_sandbox's isolation contract has an implemented, verified runtime.

CLI output formats: https://code.claude.com/docs/en/headless and
https://code.claude.com/docs/en/cli-reference (checked 2026-09-08).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from wb_arms.api_loop import ArmResult
from wb_arms.native_sandbox import require_verified_runtime
from wb_world.episode import Episode

# Historical configuration retained for evidence interpretation; not executable.
_FLAGS = ["--output-format", "json", "--permission-mode", "bypassPermissions",
          "--strict-mcp-config", "--mcp-config", ".mcp.json"]


def claude_version() -> str | None:
    """No verified runtime version; a host installation is not that runtime."""
    return None


def invocation() -> dict:
    """Historical flags plus explicit current launch status, never a launch claim."""
    return {"cmd": "claude -p <goal>", "flags": list(_FLAGS), "billing": "api-key",
            "launch_status": "blocked", "isolation_contract": "native-isolation-v1"}


class ClaudeCodeArm:
    name = "bare/cli/claude-code"
    provider_key = "claude-code"

    def __init__(self, workdir_root: str | Path = "out/cc-work", env: dict[str, str] | None = None):
        self.workdir_root = Path(workdir_root)
        self.env = dict(env or {})  # Configuration only; never merged into host env.
        self.version = claude_version()
        self.name = f"bare/cli/claude-code@{self.version or 'unverified'}"

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        # Before task access, filesystem writes, credentials, or process creation.
        require_verified_runtime()
        raise AssertionError("Native runtime gate must fail closed")


def _number(value: object, field: str, *, integer: bool = False) -> int | float:
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a nonnegative finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0 or (integer and type(value) is not int):
        raise ValueError(f"{field} must be a nonnegative finite {'integer' if integer else 'number'}")
    return value


def _decode(stdout: str) -> tuple[dict, list[dict]]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if not events or any(not isinstance(event, dict) for event in events):
            raise ValueError("CLI stream is empty or contains non-object events")
        return events[-1], events
    if not isinstance(data, dict):
        raise ValueError("CLI result must be an object")
    return data, []


def parse_result(stdout: str, returncode: int, stderr: str = "") -> ArmResult:
    """Parse observed JSON/NDJSON evidence without inferring missing success.

A missing/invalid bill uses cost_usd=0.0 ONLY as the legacy ArmResult numeric
placeholder and always carries billing=unknown. It must never settle a held
reservation as zero. Native events retain their observed shape and order; no
hidden reasoning, event timestamps, complete trace, or trusted state is inferred.
"""
    res = ArmResult(termination="agent_error")
    try:
        data, events = _decode(stdout)
    except (ValueError, TypeError):
        res.error = (stderr or "empty or malformed CLI output")[:500]
        res.flags.extend(["cli_output_unparseable", "billing=unknown"])
        return res
    res.turn_log = [{"source": "claude_code_stream", "sequence": i, "event": event}
                    for i, event in enumerate(events)]
    numeric_errors = []
    if data.get("total_cost_usd") is None:
        res.flags.append("billing=unknown")
    else:
        try:
            res.cost_usd = float(_number(data["total_cost_usd"], "total_cost_usd"))
        except ValueError as error:
            numeric_errors.append(str(error))
            res.flags.append("billing=unknown")
    if isinstance(data.get("result"), str):
        res.final_text = data["result"]
    try:
        res.turns = _number(data.get("num_turns", 0), "num_turns", integer=True)
        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            raise ValueError("usage must be an object")
        counts = {name: _number(usage.get(name, 0), name, integer=True) for name in (
            "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        res.tokens_cached = counts["cache_read_input_tokens"]
        res.tokens_cache_write = counts["cache_creation_input_tokens"]
        res.tokens_prompt = counts["input_tokens"] + res.tokens_cached + res.tokens_cache_write
        res.tokens_output = counts["output_tokens"]
        if "usage" not in data:
            res.flags.append("cache_reporting=absent")
    except ValueError as error:
        numeric_errors.append(str(error))
    if numeric_errors:
        res.flags.append("cli_numeric_invalid")
        res.error = "; ".join(numeric_errors)[:500]
    elif returncode != 0:
        res.error = f"CLI exited with status {returncode}: {stderr}"[:500]
    elif data.get("is_error"):
        res.error = str(data.get("result", "CLI reported an error"))[:500]
    elif (data.get("type") != "result" or data.get("subtype") != "success"
          or data.get("is_error") is not False or not isinstance(data.get("result"), str)):
        res.flags.append("cli_output_unparseable")
        res.error = "CLI output lacks a valid terminal success result"
    else:
        res.termination = "completed"
    return res
