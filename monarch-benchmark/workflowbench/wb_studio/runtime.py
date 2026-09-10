"""Bounded single-host execution and shared provider admission for Studio clients."""
from collections import deque
from contextlib import contextmanager
import json
import os
import threading
import time

from wb_studio.gateways import GatewayError


def positive_int(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    return value


class Runtime:
    def __init__(self, *, max_agents=None, max_runs=None, provider_limits=None):
        self.max_agents = positive_int(max_agents if max_agents is not None else int(os.getenv("STUDIO_MAX_AGENTS", "8")), "Agent capacity", 64)
        self.max_runs = positive_int(max_runs if max_runs is not None else int(os.getenv("STUDIO_MAX_RUNS", "4")), "Run capacity", 32)
        self.agents = threading.BoundedSemaphore(self.max_agents)
        self.runs = threading.BoundedSemaphore(self.max_runs)
        self.condition = threading.Condition()
        self.active_agents = 0
        self.limits = provider_limits if provider_limits is not None else json.loads(os.getenv("STUDIO_PROVIDER_LIMITS", "{}"))
        if not isinstance(self.limits, dict):
            raise ValueError("Provider limits must be an object")
        for provider, limit in self.limits.items():
            if not isinstance(limit, dict) or set(limit) - {"concurrency", "requests_per_minute", "tokens_per_minute"}:
                raise ValueError(f"Invalid limits for {provider}")
            positive_int(limit.get("concurrency", 2), "Provider concurrency", 64)
            positive_int(limit.get("requests_per_minute", 30), "Requests per minute", 100000)
            if "tokens_per_minute" in limit:
                positive_int(limit["tokens_per_minute"], "Tokens per minute", 1000000000)
        self.providers = {}

    @contextmanager
    def agent(self, cancel):
        acquired = False
        while not cancel.is_set():
            if self.agents.acquire(timeout=.1):
                acquired = True
                break
        if not acquired:
            yield False
            return
        with self.condition:
            self.active_agents += 1
        try:
            yield not cancel.is_set()
        finally:
            with self.condition:
                self.active_agents -= 1
            self.agents.release()

    @contextmanager
    def provider(self, name, *, timeout=None, cancel=None, tokens=0):
        deadline = time.monotonic() + (timeout if timeout is not None else 600)
        limit = self.limits.get(name, {})
        concurrency, rpm = limit.get("concurrency", 2), limit.get("requests_per_minute", 30)
        tpm = limit.get("tokens_per_minute")
        if type(tokens) is not int or tokens < 0:
            raise ValueError("Token reservation must be a nonnegative integer")
        if tpm is not None and tokens > tpm:
            raise GatewayError("This request exceeds the configured token-per-minute capacity; reduce its context or raise the operator limit", kind="infra:rate_limit")
        with self.condition:
            state = self.providers.setdefault(name, {"active": 0, "starts": deque(), "token_starts": deque()})
            while True:
                now = time.monotonic()
                while state["starts"] and state["starts"][0] <= now - 60:
                    state["starts"].popleft()
                while state["token_starts"] and state["token_starts"][0][0] <= now - 60:
                    state["token_starts"].popleft()
                if cancel is not None and cancel.is_set():
                    raise GatewayError("Cancelled while waiting for provider capacity", kind="infra:cancelled")
                if now >= deadline:
                    raise GatewayError("Provider capacity wait timed out; no request sent", kind="infra:timeout")
                if state["active"] < concurrency and len(state["starts"]) < rpm and (tpm is None or sum(n for _, n in state["token_starts"]) + tokens <= tpm):
                    state["active"] += 1
                    state["starts"].append(now)
                    state["token_starts"].append((now,tokens))
                    break
                self.condition.wait(min(.2, deadline - now))
        try:
            yield max(.001, deadline - time.monotonic())
        finally:
            with self.condition:
                state["active"] -= 1
                self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            names = sorted(set(self.limits) | set(self.providers))
            return {"mode": "single-host", "max_agents": self.max_agents, "max_runs": self.max_runs,
                    "active_agents": self.active_agents, "default_provider_limits": {"concurrency": 2, "requests_per_minute": 30},
                    "providers": [{"provider": name, "concurrency": self.limits.get(name, {}).get("concurrency", 2),
                                   "requests_per_minute": self.limits.get(name, {}).get("requests_per_minute", 30),
                                   "tokens_per_minute": self.limits.get(name, {}).get("tokens_per_minute"),
                                   "active": self.providers.get(name, {}).get("active", 0)} for name in names],
                    "recovery": "Unclaimed queued runs resume on startup. Claimed work is interrupted and never automatically replayed.",
                    "limits_note": "Operator request caps, shared by this host. Configure them for your provider account; optional token quotas use conservative request bounds and are not refunded from unverified usage."}


class AdmittedGateway:
    def __init__(self, gateway, runtime, provider, cancel_for):
        self.gateway, self.runtime, self.provider, self.cancel_for = gateway, runtime, provider, cancel_for

    def __getattr__(self, name):
        return getattr(self.gateway, name)

    def turn(self, messages, **kwargs):
        cancel = self.cancel_for(kwargs.get("scope_id"))
        # Text-only tool calls: UTF-8 byte count safely overestimates tokenized input.
        # Include schema/system bytes and maximum completion/thinking allowance.
        from wb_studio.gateways import OUTPUT_CEILING
        from wb_studio.paid import THINKING_CEILING
        family = getattr(self.gateway, "family", "gemini")
        output = OUTPUT_CEILING.get(family, THINKING_CEILING + 4096)
        tokens = len(json.dumps([getattr(self.gateway,"system",""), messages, getattr(self.gateway,"tools",[])], ensure_ascii=False, default=str).encode()) + output + 1024
        with self.runtime.provider(self.provider, timeout=kwargs.get("timeout"), cancel=cancel, tokens=tokens) as remaining:
            if kwargs.get("timeout") is not None:
                kwargs["timeout"] = remaining
            return self.gateway.turn(messages, **kwargs)


@contextmanager
def single_host_owner(directory):
    """Hold an OS lock for the web process, released by the OS even after a crash."""
    directory.mkdir(parents=True, exist_ok=True)
    stream = (directory / "studio.owner.lock").open("a+b")
    try:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another Studio process owns this data directory") from None
        yield
    finally:
        stream.close()
