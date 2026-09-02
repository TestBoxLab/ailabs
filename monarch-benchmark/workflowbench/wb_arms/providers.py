"""Provider registry + cached-token normalization.

Field shapes and prices verified 31 Aug 2026 against vendor docs (see
CLAUDE-CODE-PROMPT.md table). Prices are $/Mtok: input / cached-input / output.
Gemini prices double Jan 1 2027 per vendor announcement — update then.

All four providers cache automatically on prefix match; nothing here creates
caches. The registry's job is to say where each provider reports cached tokens
and what they cost, so EpisodeRow.tokens.cached is comparable across arms.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    key: str
    model_id: str
    key_env: str
    adapter: str                      # "openai" | "openai_responses" | "gemini" | "anthropic"
    price_in: float                   # $/Mtok uncached input
    price_cached: float               # $/Mtok cached input (cache read)
    price_out: float                  # $/Mtok output
    base_url: str | None = None       # None for native adapters
    price_cache_write: float | None = None  # $/Mtok cache creation; None -> price_in
    cache_min_prompt_tokens: int = 0  # provider's minimum cacheable prefix
    header_fallbacks: tuple[str, ...] = field(default_factory=tuple)


REGISTRY: dict[str, Provider] = {}


def register(p: Provider) -> Provider:
    REGISTRY[p.key] = p
    return p


register(Provider(
    key="glm-5.3", model_id="glm-5.3", key_env="ZAI_API_KEY", adapter="openai",
    base_url="https://api.z.ai/api/paas/v4",
    price_in=1.40, price_cached=0.26, price_out=4.40))

register(Provider(
    key="kimi-k3", model_id="kimi-k3", key_env="MOONSHOT_API_KEY", adapter="openai",
    base_url="https://api.moonshot.ai/v1",
    price_in=3.00, price_cached=0.30, price_out=15.00,
    cache_min_prompt_tokens=256))

register(Provider(
    key="kimi-k3-fireworks", model_id="accounts/fireworks/models/kimi-k3",
    key_env="FIREWORKS_API_KEY", adapter="openai",
    base_url="https://api.fireworks.ai/inference/v1",
    price_in=3.00, price_cached=0.30, price_out=15.00,
    header_fallbacks=("fireworks-cached-prompt-tokens",)))

# Anthropic first-party rates, verified 2 Sep 2026 (claude-api skill table):
# input 5.00, cache read 0.10x, cache write (5 min) 1.25x, output 25.00.
# claude-opus-4-8 is Monarch's authoring brain (monarch config/env.ts), so it
# is the control arm: same model, no product.
register(Provider(
    key="claude-opus-4-8", model_id="claude-opus-4-8", key_env="ANTHROPIC_API_KEY",
    adapter="anthropic",
    price_in=5.00, price_cached=0.50, price_out=25.00, price_cache_write=6.25,
    cache_min_prompt_tokens=1024))

# OpenAI standard rates, verified 2 Sep 2026 at developers.openai.com/api/docs/pricing.
# gpt-5.6-sol is promotional pricing through at least 21 Nov 2026. Responses
# API: chat-completions rejects function tools when reasoning is on (doctor,
# 2 Sep 2026), and reasoning off would be an unfair control.
register(Provider(
    key="gpt-5.6-sol", model_id="gpt-5.6-sol", key_env="OPENAI_API_KEY",
    adapter="openai_responses", price_in=4.00, price_cached=0.40, price_out=20.00))

register(Provider(
    key="gpt-5.6-terra", model_id="gpt-5.6-terra", key_env="OPENAI_API_KEY",
    adapter="openai_responses", price_in=2.00, price_cached=0.20, price_out=12.00))

register(Provider(
    key="gemini-3.7-flash", model_id="gemini-3.7-flash", key_env="GEMINI_API_KEY",
    adapter="gemini",  # native google-genai: implicit-cache reporting via OpenAI-compat is undocumented
    price_in=0.75, price_cached=0.075, price_out=3.75,
    cache_min_prompt_tokens=4096))


def get(key: str) -> Provider:
    if key not in REGISTRY:
        raise KeyError(f"unknown provider {key!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[key]


def api_key(p: Provider) -> str | None:
    return os.environ.get(p.key_env) or None


def extract_cached_tokens(usage: dict | None, headers: dict | None = None,
                          provider: Provider | None = None) -> tuple[int, str | None]:
    """Normalize the four vendor shapes into one number.

    Returns (cached_tokens, source_field). source_field None means no cache
    reporting was found anywhere — caller must flag cache_reporting=absent,
    never silently treat as a real zero.
    """
    usage = usage or {}
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        return int(details["cached_tokens"]), "prompt_tokens_details.cached_tokens"
    if usage.get("cached_tokens") is not None:
        return int(usage["cached_tokens"]), "cached_tokens"
    meta = usage.get("usageMetadata") or usage
    if meta.get("cachedContentTokenCount") is not None:
        return int(meta["cachedContentTokenCount"]), "usageMetadata.cachedContentTokenCount"
    if usage.get("cached_content_token_count") is not None:
        return int(usage["cached_content_token_count"]), "cached_content_token_count"
    if headers and provider:
        lower = {k.lower(): v for k, v in headers.items()}
        for h in provider.header_fallbacks:
            if h.lower() in lower:
                return int(lower[h.lower()]), f"header:{h}"
    return 0, None


def cost_usd(p: Provider, prompt: int, cached: int, output: int, cache_write: int = 0) -> float:
    """prompt = all input tokens incl. cached and cache-write; cache_write is the
    subset billed at the creation rate (Anthropic); others report 0."""
    cached = min(max(cached, 0), prompt)   # clamp provider overreport; flag is set upstream
    cache_write = min(max(cache_write, 0), prompt - cached)
    uncached = prompt - cached - cache_write
    write_rate = p.price_cache_write if p.price_cache_write is not None else p.price_in
    return (uncached * p.price_in + cached * p.price_cached + cache_write * write_rate
            + output * p.price_out) / 1e6
