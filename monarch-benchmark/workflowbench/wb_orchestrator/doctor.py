"""wb doctor: validate every configured provider + cache behavior, one cheap
call each (repeated once verbatim to prove a prefix cache hit). Fails loud per
provider, never aborts the others. Runs before any paid sweep.
"""
from __future__ import annotations

import base64
import json
import os
import traceback
import urllib.request
from pathlib import Path
from typing import Any

from wb_arms import providers
from wb_arms.api_loop import ApiLoopArm
from wb_orchestrator import config
from wb_orchestrator.monarch_setup import Stop, expand

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


MONARCH_KEYS = ("backend", "backend_health", "fd", "langfuse", "authoring_probe")
# Plain names for the printed report; the report keys themselves do not change.
MONARCH_LABELS = {"backend": "monarch backend",
                  "backend_health": "monarch health (session)",
                  "fd": "discovery service",
                  "langfuse": "tracing service"}
_TIMEOUT_S = 5
_PROBE_GOAL = "Connectivity check. Do nothing."


def _call(method: str, url: str, headers: dict | None = None, body: dict | None = None):
    """Returns the decoded JSON body (or the raw text). Any failure raises."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
        raw = r.read()
        try:
            return json.loads(raw or b"null"), r.headers
        except json.JSONDecodeError:
            return raw.decode(errors="replace"), r.headers


def _line(url: str, fn) -> tuple[str, Any]:
    """`fn()` -> (line, value). A line always names the address it tried."""
    try:
        return f"OK {url}", fn()
    except (OSError, ValueError, RuntimeError) as e:
        # Transport (HTTPError/URLError are OSError), decoding, and the auth
        # failures raised above. Anything else is a wb bug and must surface as a
        # traceback rather than hide as a FAIL line.
        return f"FAIL {url}: {type(e).__name__}: {e}", None


def _session_token(harness, env: dict, base_url: str) -> str:
    """The env token if set, else log in and read the monarch_session cookie."""
    token = env.get(harness.credential_env or "")
    if token:
        return token
    password = env.get(harness.login_password_env or "")
    if not password:
        raise RuntimeError(f"environment variable {harness.login_password_env} is not set")
    _, headers = _call("POST", f"{base_url}/api/auth/login",
                       body={"email": harness.login_email, "password": password})
    for cookie in headers.get_all("Set-Cookie") or []:
        if cookie.startswith("monarch_session="):
            return cookie.split("=", 1)[1].split(";", 1)[0]
    raise RuntimeError("login sent no monarch_session cookie")


def check_monarch(harness, env: dict, probe: bool = False) -> dict[str, Any]:
    """Four reachability checks, plus the paid authoring probe when asked.

    Every check runs even when an earlier one failed: the point of doctor is to
    name every broken address in one pass, not to stop at the first.
    """
    report: dict[str, Any] = {"provider": "monarch", "ok": False}

    def _url(field: str) -> str:
        # `${VAR}` in the harness file; an unset variable is that line's failure.
        return expand(getattr(harness, field), env, field)

    try:
        base_url = _url("base_url")
    except Stop as stop:
        base_url = None
        report["backend"] = report["backend_health"] = f"FAIL base_url: {stop.message}"

    if base_url:
        report["backend"], _ = _line(f"{base_url}/api",
                                     lambda: _call("GET", f"{base_url}/api"))
        health = f"{base_url}/api/health"
        report["backend_health"], _ = _line(
            health, lambda: _call("GET", health,
                                  headers={"x-monarch-session":
                                           _session_token(harness, env, base_url)}))

    for field, path, auth in (("fd_url", "/health", None),
                              ("langfuse_url", "/api/public/health", "langfuse")):
        key = "fd" if field == "fd_url" else "langfuse"
        try:
            url = _url(field) + path
        except Stop as stop:
            report[key] = f"FAIL {field}: {stop.message}"
            continue
        headers = {}
        if auth:
            keys = [env.get(harness.langfuse_public_key_env or ""),
                    env.get(harness.langfuse_secret_key_env or "")]
            if not all(keys):
                missing = harness.langfuse_public_key_env if not keys[0] \
                    else harness.langfuse_secret_key_env
                report[key] = f"FAIL {url}: environment variable {missing} is not set"
                continue
            headers["Authorization"] = "Basic " + base64.b64encode(
                f"{keys[0]}:{keys[1]}".encode()).decode()
        report[key], _ = _line(url, lambda u=url, h=headers: _call("GET", u, headers=h))

    if probe and base_url:
        # Costs model money: one authoring run, cancelled immediately.
        runs = f"{base_url}/api/workflows/recipe/runs"

        def fire():
            # ponytail: logs in a second time rather than threading the health
            # check's token down here; one extra cheap call keeps the checks
            # independent. Thread the token through if doctor ever gets chatty.
            token = _session_token(harness, env, base_url)
            sess = {"x-monarch-session": token}
            body, _ = _call("POST", runs, headers=sess, body={"goal": _PROBE_GOAL})
            run_id = (body or {}).get("runId")
            _call("POST", f"{runs}/{run_id}/cancel", headers=sess, body={})
            return run_id

        line, run_id = _line(runs, fire)
        report["authoring_probe"] = f"{line} runId={run_id}" if run_id else line

    # Only the keys actually present are judged: a missing key is a check that
    # never ran, which must never read as OK.
    report["ok"] = all(str(v).startswith("OK") for k, v in report.items() if k in MONARCH_KEYS)
    return report


def run_doctor(keys: list[str] | None = None, monarch_probe: bool = False,
               config_dir=None, env: dict | None = None) -> list[dict[str, Any]]:
    # "monarch" is a name --arms accepts but not a provider: it selects the block
    # below. An explicit list of providers only (as CI passes) skips the block
    # entirely, so `wb doctor --arms <providers>` never fails on an absent stack.
    want_monarch = keys is None or "monarch" in keys
    keys = sorted(providers.REGISTRY) if keys is None else [k for k in keys if k != "monarch"]
    reports = [check_provider(k) for k in keys]
    path = Path(config_dir or config.DEFAULT_CONFIG_DIR) / "harnesses" / "monarch.yaml"
    if want_monarch and path.is_file():
        harness = config.load_harness(path)
        if harness.runnable:
            reports.append(check_monarch(harness, env if env is not None else os.environ,
                                         probe=monarch_probe))
    return reports


def format_report(reports: list[dict[str, Any]]) -> str:
    lines = ["wb doctor"]
    for r in reports:
        mark = "OK " if r.get("ok") else "FAIL"
        lines.append(f"[{mark}] {r['provider']}")
        for k in ("error", "reachable", "tool_call_works", "prompt_tokens",
                  "cached_tokens_second_call", "cache_probe_attempts", "cache_field",
                  "cache_hit", "cache_min_warning", "cache_warning", *MONARCH_KEYS):
            if k in r:
                lines.append(f"       {MONARCH_LABELS.get(k, k)}: {r[k]}")
    return "\n".join(lines)
