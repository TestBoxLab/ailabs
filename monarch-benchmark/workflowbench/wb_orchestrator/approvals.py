"""Who may launch a paid round, and the record of it (decision D5, milestone M3).

The launcher is named by `WB_OPERATOR`. Approvers (`WB_APPROVERS`, default
Carlos or Lucas, by first or full name) run at once under an approved record; anyone else's launch above
smoke scale creates a pending request that an approver decides with
`wb approve <id>` or `wb deny <id>`; `wb run --request <id>` then runs it,
by any operator, as long as the config hash still matches, once. Smoke scale
(at most `SMOKE_SCALE_ATTEMPTS` attempts per competitor) needs no record.
The weekly ledger is the spending gate either way; a record is a decision
about a round, not a budget.

Capability checks say which paid competitors may launch today: the API loop,
once the ledger and an operator are in place; Monarch and native competitors
stay refused with the milestone that unblocks them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from wb_orchestrator.config import SMOKE_SCALE_ATTEMPTS

OPERATOR_ENV = "WB_OPERATOR"
APPROVERS_ENV = "WB_APPROVERS"
DEFAULT_APPROVERS = ("carlos", "carlos mattos", "lucas", "lucas wakigawa")

NO_OPERATOR = ("WB_OPERATOR is not set: a paid launch names the person launching it "
               "(set WB_OPERATOR=<name> in the environment)")
MONARCH_REASON = "Monarch instance not verified: milestone M5"
NATIVE_REASON = "native runtime not verified: milestone M7"
VERIFY_HINT = "run `wb monarch verify` (or Verify in the Studio) against the instance"


class ApprovalError(Exception):
    """A launch or a decision the approval flow refuses; the message says why."""


def operator(env) -> str | None:
    """The launcher's name, lower-cased; None when unset or blank."""
    return (env.get(OPERATOR_ENV) or "").strip().lower() or None


def approvers(env) -> tuple[str, ...]:
    raw = env.get(APPROVERS_ENV) or ""
    names = tuple(name.strip().lower() for name in raw.split(",") if name.strip())
    return names or DEFAULT_APPROVERS


def is_approver(name: str | None, env) -> bool:
    return bool(name) and name.strip().lower() in approvers(env)


def capabilities() -> dict[str, str | None]:
    """Per competitor kind, None when it may launch, else the reason it may not."""
    return {"api": None, "monarch": MONARCH_REASON, "native": NATIVE_REASON}


def _probe_site() -> SimpleNamespace:
    """Where the verification record lives: the Studio's folder (a hosted bench keeps it on its volume)."""
    root = Path(__file__).resolve().parents[1]
    data = os.environ.get("STUDIO_DATA_DIR")
    return SimpleNamespace(directory=Path(data) / "studio" if data else root / "out" / "studio")


def monarch_reason(harness, env) -> str | None:
    """None when a fresh, passing verification names this harness's instance; else why not.

    The record is the one `wb monarch verify` and the Studio's Verify write
    (`wb_studio.enterprise.verify`): backend, session, knowledge base and
    Langfuse checked against the deployment, no model money spent. It admits
    Monarch competitors for `PROBE_TTL` (two hours), for that backend only.
    """
    from wb_studio import enterprise
    from wb_orchestrator.monarch_setup import Stop, expand
    probe = enterprise.load_probe(_probe_site())
    if probe is None:
        return f"{MONARCH_REASON}; {VERIFY_HINT}"
    try:
        checked = datetime.fromisoformat(probe["checked_at"])
    except (KeyError, TypeError, ValueError):
        return f"{MONARCH_REASON}; the last record carries no valid time; {VERIFY_HINT}"
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    hours = int(enterprise.PROBE_TTL.total_seconds() // 3600)
    if datetime.now(timezone.utc) - checked > enterprise.PROBE_TTL:
        return f"{MONARCH_REASON}; the last verification is older than {hours} hours; {VERIFY_HINT}"
    if not probe.get("ok"):
        failed = ", ".join(c.get("name", "?") for c in probe.get("checks", []) if not c.get("ok")) or "unknown check"
        return f"{MONARCH_REASON}; the last verification failed ({failed}); {VERIFY_HINT}"
    try:
        host = urlparse(expand(harness.base_url, env, "base_url")).netloc
    except Stop as stop:
        return f"{MONARCH_REASON}; {stop.message}"
    if probe.get("backend_host") != host:
        return (f"{MONARCH_REASON}; the last verification was of {probe.get('backend_host')}, "
                f"this harness names {host}; {VERIFY_HINT}")
    return None


def competitor_reason(harness, env=None) -> str | None:
    if harness.kind == "monarch":
        return monarch_reason(harness, os.environ if env is None else env)
    if harness.kind == "cli":
        return NATIVE_REASON
    return None   # scripted checks are free; the API loop reserves per request


def is_paid(rc) -> bool:
    return any(c.harness.kind != "scripted" for c in rc.competitors)


def launch_readiness(rc, env) -> list[str]:
    """Every reason this run config may not launch today, the operator first; empty when it may."""
    reasons: list[str] = []
    if not is_paid(rc):
        return reasons
    if operator(env) is None:
        reasons.append(NO_OPERATOR)
    named: dict[str, list[str]] = {}
    for c in rc.competitors:
        reason = competitor_reason(c.harness, env)
        if reason:
            named.setdefault(reason, []).append(c.name)
    for reason, names in named.items():
        reasons.append(f"competitor{'s' if len(names) != 1 else ''} {', '.join(names)}: {reason}")
    return reasons


@dataclass(frozen=True)
class Launch:
    run: bool                 # start the round now
    request_id: str | None    # the approval record it runs under, if any
    message: str              # one line for the operator


def admit_launch(store, rc, env, *, request_id: str | None = None) -> Launch:
    """Apply decision D5 to a resolved paid run config; see the module docstring."""
    who = operator(env)
    if who is None:
        raise ApprovalError(NO_OPERATOR)
    if request_id is not None:
        record = store.approval_request(request_id)
        if record is None:
            raise ApprovalError(f"unknown approval request {request_id}; see `wb approvals`")
        if record["status"] != "approved":
            raise ApprovalError(f"approval request {request_id} is {record['status']}, not approved")
        if record["run_id"]:
            raise ApprovalError(f"approval request {request_id} already ran as {record['run_id']}; "
                                "a new round needs a new request")
        if record["config_hash"] != rc.hash:
            raise ApprovalError(
                f"approval request {request_id} was approved for config {record['config_hash']}, but the "
                f"current config hashes to {rc.hash}: the plan, product, models, harnesses or tasks changed "
                "since; launch again to create a new request")
        return Launch(True, request_id,
                      f"approval {request_id}: approved by {record['decided_by']} at {record['decided_at']}; "
                      f"launched by {who}{' (approver)' if is_approver(who, env) else ''}")
    per = rc.attempts_per_competitor
    if per <= SMOKE_SCALE_ATTEMPTS:
        return Launch(True, None,
                      f"smoke scale: {per} attempts per competitor, at most {SMOKE_SCALE_ATTEMPTS}, so no "
                      f"approval record is needed; launched by {who}{' (approver)' if is_approver(who, env) else ''}")
    fields = dict(plan_name=rc.plan.name, config_hash=rc.hash, product_path=rc.product_path,
                  plan_path=rc.plan_path, attempts_total=rc.attempts_total,
                  ceiling_usd=float(rc.plan.cost_ceiling_usd))
    if is_approver(who, env):
        rid = store.create_approval_request(requested_by=who, status="approved", decided_by=who, **fields)
        return Launch(True, rid, f"approval {rid}: {who} is an approver, so the request is approved on "
                                 f"creation; launched by {who} (approver)")
    rid = store.create_approval_request(requested_by=who, status="pending", **fields)
    return Launch(False, rid,
                  f"{rid} awaiting approval: {per} attempts per competitor exceed smoke scale "
                  f"({SMOKE_SCALE_ATTEMPTS}); nothing ran. An approver ({', '.join(approvers(env))}) decides "
                  f"with `wb approve {rid}` or `wb deny {rid}`; then anyone runs the same product and plan "
                  f"with `wb run ... --request {rid}`")


def decide(store, request_id: str, decision: str, env) -> dict:
    """`wb approve` / `wb deny`: an approver settles a pending request, once."""
    who = operator(env)
    if who is None:
        raise ApprovalError(NO_OPERATOR)
    if not is_approver(who, env):
        raise ApprovalError(f"{who} is not an approver (approvers: {', '.join(approvers(env))})")
    record = store.approval_request(request_id)
    if record is None:
        raise ApprovalError(f"unknown approval request {request_id}; see `wb approvals`")
    if record["status"] != "pending":
        raise ApprovalError(f"approval request {request_id} is already {record['status']} "
                            f"(by {record['decided_by']} at {record['decided_at']})")
    return store.decide_approval(request_id, decision, decided_by=who)
