"""The one agent loop every Studio arm and architecture step runs.

A loop owns nothing paid: it asks its gateway for one turn at a time, executes
the tool calls the model returned against the supplied executor, and emits the
same event vocabulary whatever the provider. ``step`` names the architecture
node the loop is running for, so the builder and the activity view can light
up the node that is actually executing.
"""
from __future__ import annotations

import json
import time

from wb_arms.api_loop import ArmResult, MAX_TOOL_RESULT_CHARS, _exec_tool
from wb_orchestrator.budget import BudgetExceeded, ReservationConflict
from wb_studio.gateways import GatewayError
from wb_world.episode import EvidenceWriteError


def episode_executor(ep):
    """Tool executor for a live episode world; node events come from ep._observe."""
    return lambda name, args: _exec_tool(ep, name, args)


def run_loop(gateway, *, system: str, brief: str, execute_tool, emit, scope_id: str, scope_limit_usd, request_prefix: str,
             max_turns: int = 20, cancel=None, deadline: float | None = None, step: str | None = None,
             record=lambda entry: None, budget=lambda: None) -> ArmResult:
    result = ArmResult()
    prefix = f"{step}:" if step else ""
    tag = {"step": step} if step else {}
    messages = gateway.start(system, brief)
    turn = 0
    try:
        for turn in range(max_turns):
            if (cancel is not None and cancel.is_set()) or (deadline and time.monotonic() >= deadline):
                result.termination, result.error = "timeout", "Cancelled or deadline reached; no further requests sent."
                break
            emit("model_started", node=f"{prefix}model-{turn}", label="Working", turn=turn, **tag)
            # The system prompt is evidence too (knowledge, upstream outputs, role); it is
            # constant for the loop, so it is journaled once with the first request.
            record({"type": "agent_request", "turn": turn, "step": step,
                    "request": {"messages": messages, **({"system": system, "brief": brief} if turn == 0 else {})}})
            gateway.on_text = lambda text: emit("model_delta", node=f"{prefix}model-{turn}", text=text, turn=turn, **tag)
            reply = gateway.turn(messages, scope_id=scope_id, scope_limit_usd=scope_limit_usd,
                                 request_id=f"{request_prefix}-{turn}", timeout=None if not deadline else max(deadline - time.monotonic(), 1.0))
            billing = reply.get("_billing", {})
            result.tokens_prompt += reply.get("prompt_tokens", 0)
            result.tokens_cached += reply.get("cached_tokens", 0)
            result.tokens_cache_write += reply.get("cache_write_tokens", 0)
            result.tokens_output += reply.get("output_tokens", 0)
            result.cost_usd += float(billing.get("actual_usd") or 0)
            if billing.get("actual_usd") is None:
                result.flags.append("billing=unknown")
            result.turns += 1
            result.turn_log.append({"turn": turn, "step": step, "response": {k: v for k, v in reply.items() if k != "raw"}})
            emit("billing", billing=billing, budget=budget(), **tag)
            record({"type": "agent_response", "turn": turn, "step": step, "response": {k: v for k, v in reply.items() if k != "raw"}})
            text, calls = reply.get("text") or "", reply.get("tool_calls") or []
            emit("model_finished", node=f"{prefix}model-{turn}", output=text, status="completed", **tag)
            if not calls:
                result.final_text = text
                if not text or reply.get("finish_reason") not in (None, "STOP", "stop", "end_turn"):
                    result.termination, result.error = "agent_error", "Model stopped without a complete final answer."
                break
            for call in calls:
                if call.get("parse_error"):
                    value = json.dumps({"error": "tool call arguments were not valid JSON: " + call["parse_error"]})
                else:
                    value = execute_tool(call["name"], call.get("args", {}))
                if len(value) > MAX_TOOL_RESULT_CHARS:
                    value = value[:MAX_TOOL_RESULT_CHARS] + " ...[truncated by harness]"
                result.tool_calls += 1
                gateway.append_tool_result(messages, call, value)
        else:
            result.termination, result.error = "agent_error", "Turn limit reached"
    except Exception as exc:
        result.termination = "infra:harness_crash"
        refused = isinstance(exc, (BudgetExceeded, ReservationConflict, ValueError)) or str(exc).startswith(("Token preflight failed", "Verified Gemini introductory pricing expired"))
        from wb_studio.paid import PaidGatewayError
        safe = str(exc) if isinstance(exc, (PaidGatewayError, GatewayError, BudgetExceeded, ReservationConflict)) else type(exc).__name__
        result.error = (f"Request admission refused: {safe}. No new generation dispatched." if refused
                        else f"Request stopped ({safe}); uncertain charges remain reserved.")
        result.flags.append("admission_refused" if refused else "billing=unknown")
        if isinstance(exc, EvidenceWriteError):
            result.flags.append("evidence_incomplete")
        else:
            emit("model_finished", node=f"{prefix}model-{turn}", output=result.error, status="error", **tag)
            emit("attempt_error", message=result.error, **tag)
    return result
