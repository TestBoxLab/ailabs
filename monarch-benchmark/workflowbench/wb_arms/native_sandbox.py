"""Fail-closed native-harness isolation preflight.

This is a launch prohibition and a verification contract, NOT a sandbox. There
is deliberately no environment switch, caller-supplied attestation, or fallback
host launcher. A Docker executable/daemon and a separate working directory do
not prove isolation. Replace this gate only with an implemented runtime plus
adversarial boundary verification and evaluator-owned evidence capture.
"""
from __future__ import annotations

from dataclasses import dataclass

from wb_arms.api_loop import InfraError


@dataclass(frozen=True)
class NativePreflight:
    contract_version: str
    status: str
    missing_checks: tuple[str, ...]


# The future launcher must enforce all checks, not just accept these labels.
# runtime_identity: immutable image and native CLI version, validated runtime.
# filesystem_boundary: only public system/goal + agent-owned work; no evaluator
# source, grader, answers, snapshots, competitor traces, host mounts or sockets.
# environment_boundary: independent HOME/config; explicit minimal environment;
# no inherited host secrets, subscription sessions, hooks or personal settings.
# application_gateway: evaluator-owned external service exposing authorized app
# actions only; never give the agent a task file or snapshot-control endpoint.
# network_boundary: deny host/control-plane/other-competitor reachability; allow
# only scoped application and provider endpoints without container escape paths.
# evidence_capture: evaluator owns immutable event capture and final world state;
# native stdout is observed evidence, never authoritative grading or snapshots.
# billing_boundary: verified API-key billing via narrowly scoped credentials or
# broker; a held reservation covers the maximum attempt including retries.
_MISSING_CHECKS = (
    "runtime_identity", "filesystem_boundary", "environment_boundary",
    "application_gateway", "network_boundary", "evidence_capture", "billing_boundary",
)


def preflight() -> NativePreflight:
    """Read-only report; no supported isolated native runtime exists yet."""
    return NativePreflight("native-isolation-v1", "blocked", _MISSING_CHECKS)


def require_verified_runtime() -> None:
    """Reject every launch until the runtime contract has working enforcement."""
    report = preflight()
    raise InfraError(
        "infra:harness_crash",
        "Native launch blocked: no verified isolated runtime is implemented "
        f"({report.contract_version}); missing checks: {', '.join(report.missing_checks)}",
        retryable=False,
    )
