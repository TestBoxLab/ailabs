"""Budget-admitted, single-dispatch gateways for every rate-carded API control.

One provider request is one reservation: reserve a conservative maximum, claim
the one-time right to dispatch, send, then settle with the cost computed from
the provider's usage receipt. A failed or unreadable dispatch keeps its hold.

Gemini keeps the countTokens preflight and verified rate card of
``wb_studio.paid``. Other providers have no free count, so the input ceiling
is derived from the request bytes (one token per two characters, well above
any tokenizer's real ratio) plus the adapter's output cap.

Every gateway speaks the same three calls so the agent loop never knows the
wire format: ``start(system, brief) -> messages``, ``turn(messages, ...) ->
{text, tool_calls, tokens..., _billing}`` and ``append_tool_result``.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, localcontext
import math

from wb_arms import providers
from wb_arms.api_loop import (InfraError, _AnthropicAdapter, _GeminiAdapter, _OpenAIAdapter, _OpenAIResponsesAdapter,
                              build_tools_anthropic, build_tools_gemini, build_tools_openai, build_tools_responses, canonical_json)

# Effort vocabularies each API actually accepts. Chat-completions adapters
# (Fireworks, Moonshot, Z.ai) carry no reasoning-effort parameter at all.
EFFORTS = {"gemini": ("low", "medium", "high"), "anthropic": ("low", "medium", "high", "xhigh", "max"),
           "openai_responses": ("low", "medium", "high", "xhigh"), "openai": ()}
# Output caps the adapters send (anthropic/responses) or a conservative bound
# where the API has no cap in the request (chat completions).
OUTPUT_CEILING = {"gemini": 4096, "anthropic": 16000, "openai_responses": 16000, "openai": 32768}
TOOL_BUILDERS = {"gemini": build_tools_gemini, "anthropic": build_tools_anthropic,
                 "openai_responses": build_tools_responses, "openai": build_tools_openai}
ADAPTERS = {"gemini": _GeminiAdapter, "anthropic": _AnthropicAdapter,
            "openai_responses": _OpenAIResponsesAdapter, "openai": _OpenAIAdapter}


class GatewayError(RuntimeError):
    """A sanitized provider failure; the dispatch outcome is unknown and never retried here."""
    def __init__(self, message, *, kind="infra:harness_crash", retryable=False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


def resolve_effort(provider: providers.Provider, effort: str) -> str | None:
    """The effort actually sent; None when the API has no such control."""
    family = provider.adapter
    allowed = EFFORTS[family]
    if effort in (None, "default"):
        return None if not allowed else ("low" if family == "gemini" else provider.effort)
    if effort not in allowed:
        raise ValueError(f"{provider.key} accepts " + (", ".join(allowed) if allowed else "no reasoning-effort setting") + f"; not {effort}")
    return effort


def input_upper_bound(system: str, messages, tools) -> int:
    chars = len(system) + len(canonical_json(messages)) + len(canonical_json(tools))
    return math.ceil(chars / 2) + 1024


def _money(value) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return Decimal(value).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def ceiling_cost(provider: providers.Provider, input_tokens: int, output_tokens: int) -> Decimal:
    rate_in = max(provider.price_in, provider.price_cache_write or 0)
    with localcontext() as context:
        context.prec = 40
        total = (Decimal(input_tokens) * Decimal(str(rate_in)) + Decimal(output_tokens) * Decimal(str(provider.price_out))) / Decimal(1_000_000)
        return _money(total)


FIRST_REQUEST_INPUT_TOKENS = 6000   # system prompt, tools and brief on the first turn; later turns grow


def request_ceiling(provider_key: str) -> Decimal:
    """The maximum one first request of this control can reserve; a run budget below it can never dispatch."""
    provider = providers.get(provider_key)
    if provider.adapter == "gemini":
        from wb_studio.paid import INPUT_CEILING, THINKING_CEILING, _cost
        return _cost(INPUT_CEILING, THINKING_CEILING + 4096)
    return ceiling_cost(provider, FIRST_REQUEST_INPUT_TOKENS, OUTPUT_CEILING[provider.adapter])


class ProviderGateway:
    """Anthropic, OpenAI Responses and OpenAI-compatible chat providers."""

    def __init__(self, ledger, provider_key: str, effort: str = "default", *, with_tools: bool = True,
                 adapter_factory=None, request_timeout: float = 120.0):
        self.provider = providers.get(provider_key)
        if self.provider.adapter == "gemini":
            raise ValueError("Gemini runs through GeminiGateway with its verified preflight")
        self.family = self.provider.adapter
        self.effort = resolve_effort(self.provider, effort)
        self.ledger = ledger
        self.tools = TOOL_BUILDERS[self.family]() if with_tools else []
        self.adapter_factory = adapter_factory
        self.request_timeout = request_timeout
        self.adapter = None
        self.system = ""

    def describe(self) -> dict:
        return {"provider": self.provider.key, "model": self.provider.model_id, "adapter": self.family,
                "effort": self.effort, "tools": [t.get("name") or t.get("function", {}).get("name") for t in self.tools]}

    def _build(self):
        if self.adapter_factory is not None:
            adapter = self.adapter_factory(self.provider, self.tools)
        else:
            if not providers.api_key(self.provider):
                raise GatewayError(f"{self.provider.key_env} is not configured", retryable=False)
            adapter = ADAPTERS[self.family](self.provider, self.tools, self.request_timeout)
        if self.effort is not None and hasattr(adapter, "effort"):
            adapter.effort = self.effort
        return adapter

    def start(self, system: str, brief: str):
        self.adapter = self._build()
        self.system = system
        return self.adapter.start(system, brief)

    def turn(self, messages, *, scope_id: str, scope_limit_usd, request_id: str, timeout: float | None = None) -> dict:
        if self.adapter is None:
            raise RuntimeError("start() before turn()")
        bound = input_upper_bound(self.system, messages, self.tools)
        output_cap = OUTPUT_CEILING[self.family]
        maximum = ceiling_cost(self.provider, bound, output_cap)
        metadata = {"provider": self.provider.key, "model": self.provider.model_id, "harness": "api-control",
                    "effort": self.effort, "input_token_ceiling": bound, "output_token_ceiling": output_cap,
                    "input_rate_per_million": str(max(self.provider.price_in, self.provider.price_cache_write or 0)),
                    "output_rate_per_million": str(self.provider.price_out), "rate_card": f"config/models/{self.provider.key}.yaml"}
        self.ledger.reserve(request_id, maximum, scope_id=scope_id, scope_limit_usd=scope_limit_usd, metadata=metadata)
        self.ledger.claim(request_id)
        try:
            turn = self.adapter.turn(messages, timeout=timeout)
        except InfraError as exc:
            # Provider messages can carry URLs, ids or key fragments: never forwarded.
            raise GatewayError(f"Provider request failed ({exc.kind}); outcome unknown, reservation retained",
                               kind=exc.kind, retryable=False) from None
        except Exception:
            raise GatewayError("Provider request failed; outcome unknown, reservation retained") from None
        prompt, cached, output = turn.get("prompt_tokens"), turn.get("cached_tokens"), turn.get("output_tokens")
        cache_write = turn.get("cache_write_tokens", 0)
        counts = (prompt, cached, output, cache_write)
        known = all(type(v) is int and 0 <= v <= 10_000_000 for v in counts) and (prompt > 0 or output > 0)
        actual = _money(str(providers.cost_usd(self.provider, prompt, cached, output, cache_write))) if known else None
        self.ledger.settle(request_id, actual)
        return {**turn, "_billing": {**metadata, "reservation_id": request_id, "maximum_usd": str(maximum),
                                     "actual_usd": None if actual is None else str(actual),
                                     "status": "unknown_hold" if actual is None else "estimated_from_usage",
                                     "invoice_verified": False,
                                     "usage_receipt": {"prompt_tokens": prompt, "cached_tokens": cached, "output_tokens": output, "cache_write_tokens": cache_write}}}

    def append_tool_result(self, messages, call: dict, result: str) -> None:
        self.adapter.append_tool_result(messages, call, result)


class GeminiGateway:
    """The verified Gemini control (``wb_studio.paid``) behind the common interface."""

    def __init__(self, paid, effort: str = "default", *, with_tools: bool = True):
        self.paid = paid
        self.effort = resolve_effort(providers.get("gemini-3.7-flash"), effort)
        paid.thinking_level = self.effort
        self.tools = [{"functionDeclarations": build_tools_gemini()}] if with_tools else []
        self.system = ""

    def describe(self) -> dict:
        return {"provider": "gemini-3.7-flash", "model": "gemini-3.7-flash", "adapter": "gemini", "effort": self.effort,
                "tools": [d["name"] for t in self.tools for d in t["functionDeclarations"]]}

    def start(self, system: str, brief: str):
        self.system = system
        return [{"role": "user", "parts": [{"text": brief}]}]

    def turn(self, contents, *, scope_id: str, scope_limit_usd, request_id: str, timeout: float | None = None) -> dict:
        reply = self.paid.request(contents, self.system, self.tools, scope_id=scope_id, scope_limit_usd=scope_limit_usd, request_id=request_id)
        usage = reply.get("usageMetadata", {}) or {}
        candidate = (reply.get("candidates") or [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        contents.append({"role": "model", "parts": parts})
        text = "\n".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
        calls = [{"id": p["functionCall"].get("id"), "name": p["functionCall"]["name"], "args": p["functionCall"].get("args", {}) or {}}
                 for p in parts if "functionCall" in p]
        prompt = usage.get("promptTokenCount", 0)
        candidates = usage.get("candidatesTokenCount", 0)
        thoughts = usage.get("thoughtsTokenCount", max(0, usage.get("totalTokenCount", 0) - prompt - candidates))
        return {"text": text or None, "tool_calls": calls, "prompt_tokens": prompt, "output_tokens": candidates + thoughts,
                "cached_tokens": usage.get("cachedContentTokenCount", 0) or 0, "cache_write_tokens": 0,
                "finish_reason": candidate.get("finishReason"), "raw": reply, "_billing": reply.get("_billing", {})}

    def append_tool_result(self, contents, call: dict, result: str) -> None:
        response = {"name": call["name"], "response": {"result": result}}
        if call.get("id"):
            response["id"] = call["id"]
        part = {"functionResponse": response}
        last = contents[-1] if contents else None
        if last and last.get("role") == "user" and last["parts"] and "functionResponse" in last["parts"][0]:
            last["parts"].append(part)
        else:
            contents.append({"role": "user", "parts": [part]})
