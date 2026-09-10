"""One provider request, one reservation in the shared weekly ledger (milestone M3).

The CLI's API loop and `wb doctor` reserve each request for its rate-card
maximum before sending it, claim the single right to dispatch, call the
provider, and settle from the usage receipt. A receipt that cannot be read
settles as unknown and keeps the whole hold; a provider failure or a crash
between the claim and the receipt never settles, so the hold stays too. The
Studio's gateways (`wb_studio.gateways`) do the same for their own requests,
and the maximum comes from the same three functions.

Reservation ids are `<episode id>#<invocation>#r<turn>`: the invocation is the
attempt's evidence directory (`attempt-000`, `attempt-001`, ...), which the
orchestrator derives from disk, so an infra retry or a resume runs under new
ids and can never reserve, claim or settle an earlier request again.
"""
from __future__ import annotations

import secrets
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path
from typing import Any, Callable

from wb_arms import providers
from wb_arms.providers import Provider

# Receipts above this are not a usage report anyone should settle from.
MAX_RECEIPT_TOKENS = 10_000_000


def money(value: Any) -> Decimal:
    """A rate-card amount rounded up to the millionth of a dollar the ledger keeps."""
    with localcontext() as context:
        context.prec = 40
        return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def billing_provider(provider: Provider) -> str:
    """The account the request bills to: the model file's provider, or the key for an ad-hoc provider."""
    return provider.family or provider.key


def request_maximum(provider: Provider, system: str, messages: list, tools: list) -> tuple[Decimal, int, int]:
    """The most one request can cost: (maximum, input token ceiling, output token ceiling)."""
    from wb_studio.gateways import OUTPUT_CEILING, ceiling_cost, input_upper_bound  # lazy: gateways imports api_loop
    bound = input_upper_bound(system, messages, tools)
    output_cap = OUTPUT_CEILING[provider.adapter]
    return ceiling_cost(provider, bound, output_cap), bound, output_cap


def receipt_cost(provider: Provider, turn: dict) -> Decimal | None:
    """The cost the usage receipt supports, or None when the receipt cannot be read."""
    prompt, cached, output = turn.get("prompt_tokens"), turn.get("cached_tokens"), turn.get("output_tokens")
    cache_write = turn.get("cache_write_tokens", 0)
    counts = (prompt, cached, output, cache_write)
    known = (all(type(value) is int and 0 <= value <= MAX_RECEIPT_TOKENS for value in counts)
             and (prompt > 0 or output > 0))
    if not known:
        return None
    return money(providers.cost_usd(provider, prompt, cached, output, cache_write))


def usage_details(turn: dict | None) -> dict | None:
    """Convert inclusive provider receipts to the disjoint Langfuse buckets."""
    if not isinstance(turn, dict):
        return None
    prompt, cached, output = (turn.get(k) for k in ('prompt_tokens', 'cached_tokens', 'output_tokens'))
    write = turn.get('cache_write_tokens', 0)
    if any(type(v) is not int or not 0 <= v <= MAX_RECEIPT_TOKENS for v in (prompt, cached, output, write)):
        return None
    cached = min(cached, prompt)
    write = min(write, prompt - cached)
    return {'input': prompt - cached - write, 'output': output, 'cache_read': cached, 'cache_write': write}


def invocation_token(ep) -> str:
    """The attempt's evidence directory name; a one-off token when no journal is attached."""
    directory = getattr(getattr(ep, "_journal", None), "directory", None)
    if directory is not None:
        return Path(directory).name
    token = getattr(ep, "_reservation_token", None)
    if token is None:
        token = "adhoc-" + secrets.token_hex(4)
        ep._reservation_token = token
    return token


def request_id(ep, turn: int) -> str:
    return f"{ep.episode_id}#{invocation_token(ep)}#r{turn}"


def dispatch(ledger, provider: Provider, call: Callable[[], dict], *, request_id: str, scope_id: str,
             system: str, messages: list, tools: list, metadata: dict | None = None,
             scope_limit_usd=None) -> tuple[dict, dict]:
    """Reserve the request's maximum, claim, call, settle from the receipt.

    Returns (turn, billing). `BudgetExceeded` from the reservation means nothing
    was written; whatever `call` raises propagates after the claim, so the hold
    stays until someone settles it from verified billing.
    """
    maximum, bound, output_cap = request_maximum(provider, system, messages, tools)
    rate_in = max(provider.price_in, provider.price_cache_write or 0)
    facts = {"harness": "api", "billing_provider": billing_provider(provider), "provider": provider.key,
             "model": provider.model_id, "input_token_ceiling": bound, "output_token_ceiling": output_cap,
             "input_rate_per_million": str(rate_in), "output_rate_per_million": str(provider.price_out),
             "rate_card": f"config/models/{provider.key}.yaml", **(metadata or {})}
    ledger.reserve(request_id, maximum, scope_id=scope_id, scope_limit_usd=scope_limit_usd, metadata=facts)
    ledger.claim(request_id)
    try:
        turn = call()
    except Exception:
        ledger.settle(request_id, None, outcome='error')
        raise
    actual = receipt_cost(provider, turn)
    ledger.settle(request_id, actual, usage=usage_details(turn), outcome='completed')
    billing = {"reservation_id": request_id, "scope_id": scope_id, "maximum_usd": str(maximum),
               "actual_usd": None if actual is None else str(actual),
               "status": "unknown_hold" if actual is None else "estimated_from_usage",
               "invoice_verified": False, "billing_provider": facts["billing_provider"],
               "usage_receipt": {"prompt_tokens": turn.get("prompt_tokens"), "cached_tokens": turn.get("cached_tokens"),
                                 "output_tokens": turn.get("output_tokens"),
                                 "cache_write_tokens": turn.get("cache_write_tokens", 0)}}
    return turn, billing
