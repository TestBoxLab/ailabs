"""The unified episode record (DESIGN.md §"Unified episode schema")."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class PhaseMetrics(BaseModel):
    turns: int = 0
    tool_calls: int = 0
    tokens_input: int | None = None
    tokens_output: int | None = None
    cost_usd: float | None = None
    wall_clock_s: float | None = None


class TokenUsage(BaseModel):
    """Prompt tokens split cached/uncached; the cache hit rate lives here."""
    prompt: int = 0            # total prompt tokens across all turns
    cached: int = 0            # of which served from provider prompt cache
    cache_write: int = 0       # of which billed at cache-creation rate (Anthropic)
    output: int = 0

    @property
    def uncached(self) -> int:
        return max(self.prompt - self.cached, 0)

    @property
    def cache_hit_rate(self) -> float:
        return self.cached / self.prompt if self.prompt else 0.0


class EpisodeRow(BaseModel):
    episode_id: str
    run_id: str
    suite: str = "workflowbench-synthetic@0.1"
    task_id: str
    contract_sha256: str | None = None
    arm: str                      # e.g. "oracle", "claude-opus-4-8/api"
    mode: str = "synthetic"
    test_mode: str | None = None   # the plan's mode: full-flow | create-run | run-only
    agent: str | None = None
    model: str | None = None
    trial: int = 0
    passed: bool
    assertions_passed: bool
    invariant_passed: bool
    invariant_declared: bool
    check_results: list[dict[str, Any]] = Field(default_factory=list)
    unexpected_changes: list[dict[str, Any]] = Field(default_factory=list)
    count_violations: list[dict[str, Any]] = Field(default_factory=list)  # {want, got}: the right write, done too many times
    n_changes: int = 0
    phases: dict[str, PhaseMetrics] = Field(default_factory=dict)
    tool_calls: int = 0
    tokens: TokenUsage | None = None
    cost_usd: float | None = None
    flags: list[str] = Field(default_factory=list)   # cache_reporting=absent, cache_degraded@msg=N, ...
    gate_refusals: list[dict[str, Any]] = Field(default_factory=list)  # M2 telemetry: engine gate decisions
    retries: int = 0
    termination: str = "completed"   # completed|agent_error|timeout|infra:rate_limit|infra:model_unavailable|infra:harness_crash
    env_fingerprint: str | None = None
    artifacts_uri: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
