"""Provider registry + cached-token normalization.

Providers come from the model files in `config/models/` (prices, adapter,
cache fields, provenance notes); see `load_models`. Caching policy is provider-specific: Anthropic uses explicit markers;
OpenAI and Gemini support automatic prefix caching. Nothing here creates caches. The registry's
job is to say where each provider reports cached tokens and what they cost,
so EpisodeRow.tokens.cached is comparable across arms.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent / "config" / "models"
_DEFAULT_ADAPTER = {"anthropic": "anthropic", "openai": "openai_responses", "google": "gemini"}


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
    effort: str = "xhigh"             # default reasoning effort; WB_*_EFFORT env overrides
    family: str = ""                  # the billing account: anthropic, openai, google, fireworks, ...


REGISTRY: dict[str, Provider] = {}


def register(p: Provider) -> Provider:
    REGISTRY[p.key] = p
    return p


def load_models(folder: str | Path) -> dict[str, Provider]:
    """One Provider per model file in `folder`, keyed by name (research.md R4)."""
    from wb_orchestrator.config import is_price_table, load_model  # lazy: config pulls wb_world at import
    out = {}
    for path in sorted(Path(folder).glob("*.yaml")):
        if is_price_table(path):  # price tables live in models/ but are not competitors
            continue
        m = load_model(path)
        out[m.name] = Provider(
            key=m.name, model_id=m.model, key_env=m.key_env,
            adapter=m.adapter or _DEFAULT_ADAPTER.get(m.provider, "openai"),
            price_in=m.usd_per_million.input, price_cached=m.usd_per_million.cached,
            price_out=m.usd_per_million.output, price_cache_write=m.usd_per_million.cache_write,
            base_url=m.base_url, cache_min_prompt_tokens=m.cache_min_prompt_tokens,
            header_fallbacks=tuple(m.header_fallbacks), effort=m.effort, family=m.provider)
    return out


REGISTRY.update(load_models(DEFAULT_MODELS_DIR))


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


def context_rates(p: Provider, input_tokens: int) -> tuple[float, float, float, float]:
    """Input, cache read/write, output rates for this complete request.

    Astra standard pricing changes above 272K input tokens (official rate card,
    verified 2026-09-11). Existing model rates and historical pins are unchanged.
    """
    long_context = p.model_id == 'gpt-6-astra' and input_tokens > 272000
    factor = 2 if long_context else 1
    write = p.price_cache_write if p.price_cache_write is not None else p.price_in
    return (p.price_in * factor, p.price_cached * factor, write * factor,
            p.price_out * (1.5 if long_context else 1))


def cost_usd(p: Provider, prompt: int, cached: int, output: int, cache_write: int = 0) -> float:
    """prompt = all input tokens incl. cached and cache-write; cache_write is the
    subset billed at the creation rate (Anthropic); others report 0."""
    cached = min(max(cached, 0), prompt)   # clamp provider overreport; flag is set upstream
    cache_write = min(max(cache_write, 0), prompt - cached)
    uncached = prompt - cached - cache_write
    input_rate, cached_rate, write_rate, output_rate = context_rates(p, prompt)
    return (uncached * input_rate + cached * cached_rate + cache_write * write_rate
            + output * output_rate) / 1e6
