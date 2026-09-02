"""wb doctor: validate every configured provider + cache behavior, one cheap
call each (repeated once verbatim to prove a prefix cache hit). Fails loud per
provider, never aborts the others. Runs before any paid sweep.
"""
from __future__ import annotations

import json
import traceback
from typing import Any

from wb_arms import providers
from wb_arms.api_loop import ApiLoopArm, build_tools_openai

# Fixed doctor prompts: byte-identical across the two calls so the second call
# lands on the first's prefix. No timestamps or ids, same rule as real runs.
_SYSTEM = ("You are a workflow automation agent. Execute the requested tasks using "
           "the available tools. This is a connectivity check.")
_TOOL_PROMPT = "Call the base64_encode tool on the text 'doctor' and then stop."


def check_provider(key: str) -> dict[str, Any]:
    report: dict[str, Any] = {"provider": key, "ok": False}
    try:
        p = providers.get(key)
    except KeyError as e:
        report["error"] = str(e)
        return report
    if not providers.api_key(p):
        report["error"] = f"{p.key_env} not set"
        return report

    try:
        arm = ApiLoopArm(key)
        adapter = arm._adapter()

        def one_call():
            msgs = adapter.start(_SYSTEM, _TOOL_PROMPT)
            turns = []
            for _ in range(3):
                t = adapter.turn(msgs)
                turns.append(t)
                if not t["tool_calls"]:
                    break
                for call in t["tool_calls"]:
                    adapter.append_tool_result(msgs, call, "ZG9jdG9y")
            return turns

        first = one_call()
        report["reachable"] = True
        report["tool_call_works"] = any(t["tool_calls"] for t in first)
        prompt_tokens = first[0]["prompt_tokens"]
        report["prompt_tokens"] = prompt_tokens
        if p.cache_min_prompt_tokens and prompt_tokens < p.cache_min_prompt_tokens:
            report["cache_min_warning"] = (
                f"doctor prompt is {prompt_tokens} tokens, below the provider cache "
                f"minimum {p.cache_min_prompt_tokens}; real runs carry the full tool "
                "schemas and clear it, but this probe may not show a hit")

        # Implicit caches are per-node behind load balancers (verified on
        # Fireworks: identical probes hit or miss by routing). Repeat the
        # identical call up to 3x; a real prefix break misses ALL of them.
        cached, source, probes = 0, None, 0
        for probes in range(1, 4):
            second = one_call()
            cached = max(t["cached_tokens"] for t in second)
            source = source or next((t["cache_source"] for t in second if t["cache_source"]), None)
            if cached > 0:
                break
        report["cached_tokens_second_call"] = cached
        report["cache_probe_attempts"] = probes
        report["cache_field"] = source
        report["cache_hit"] = cached > 0
        if not report["cache_hit"]:
            report["cache_warning"] = (
                f"no cached tokens on {probes} identical repeat calls — either the "
                "provider is not caching this prefix or is not reporting it; do not "
                "run a paid sweep assuming cache savings on this provider")
        report["ok"] = report["tool_call_works"]
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        report["traceback"] = traceback.format_exc(limit=3)
    return report


def run_doctor(keys: list[str] | None = None) -> list[dict[str, Any]]:
    keys = keys or sorted(providers.REGISTRY)
    return [check_provider(k) for k in keys]


def format_report(reports: list[dict[str, Any]]) -> str:
    lines = ["wb doctor"]
    for r in reports:
        mark = "OK " if r.get("ok") else "FAIL"
        lines.append(f"[{mark}] {r['provider']}")
        for k in ("error", "reachable", "tool_call_works", "prompt_tokens",
                  "cached_tokens_second_call", "cache_probe_attempts", "cache_field",
                  "cache_hit", "cache_min_warning", "cache_warning"):
            if k in r:
                lines.append(f"       {k}: {r[k]}")
    return "\n".join(lines)
