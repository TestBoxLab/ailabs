"""Cost of one Monarch attempt, read from its Langfuse traces.

Contract: specs/002-monarch-create-run/contracts/monarch-telemetry.md.
Langfuse's own cost fields are ignored; tokens are priced with our own table.
"""
from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

PHASE_SPANS = {
    "recipe.triage": "authoring", "recipe.select": "authoring", "recipe.plan": "authoring",
    "recipe.critic": "authoring", "recipe.review": "authoring",
    "engine.run": "execution", "engine.step": "execution",
    "discovery.run": "discovery",
}


class LangfuseUnavailable(Exception):
    """Langfuse did not answer (connection, 401, any non-2xx)."""


class PriceLookupError(Exception):
    """A model in the traces has no entry in the price table."""


@dataclass
class Generation:
    trace_id: str
    observation_id: str
    model: str
    family: str
    phase: str
    input: int
    output: int
    cache_read: int
    cache_write: int
    # ponytail: "<none>" sentinel instead of Optional — the field is only read when
    # phase == "other", and other_spans is a list of names for the report.
    ancestor: str = "<none>"   # nearest ancestor span name; only read when phase == "other"


@dataclass
class CostSummary:
    by_phase: dict = field(default_factory=dict)   # phase -> family -> tokens + cost_usd
    total_usd: float = 0.0
    missing: bool = True
    other_spans: list = field(default_factory=list)
    tokens: dict = field(default_factory=dict)


def cost_for(prices, input: int, output: int, cache_read: int, cache_write: int) -> float:
    """Price four disjoint token counts (contract §3: usage.input excludes cache).

    Unlike providers.cost_usd — which takes an inclusive prompt count and subtracts
    the cached and cache-write subsets out of it, clamping provider overreports —
    Bedrock reports the four separately here, so nothing is subtracted or clamped.
    """
    return round((input * prices.input + cache_read * prices.cached
                  + cache_write * prices.cache_write + output * prices.output) / 1e6, 6)


def _family(model: str, table) -> str:
    # ponytail: first match wins on a case-insensitive substring. Ceiling: overlapping
    # match lists silently resolve by table order; upgrade: validate non-overlap in
    # load_price_table.
    low = (model or "").lower()
    for entry in table.models:
        if any(m.lower() in low for m in entry.match):
            return entry.family
    raise PriceLookupError(f"model {model!r} is not in price table {table.name}")


def _get(base_url: str, path: str, params: dict, auth: str, timeout: float, page_size: int):
    """All pages of one public-API listing."""
    items, page = [], 1
    while True:
        query = urllib.parse.urlencode({**params, "limit": page_size, "page": page})
        req = urllib.request.Request(f"{base_url.rstrip('/')}{path}?{query}",
                                     headers={"Authorization": auth})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read() or b"{}")
        except (OSError, json.JSONDecodeError) as e:  # URLError/HTTPError are OSError
            raise LangfuseUnavailable(f"GET {path}: {e}") from e
        items += body.get("data") or []
        if page >= (body.get("meta") or {}).get("totalPages", 1):
            return items
        page += 1


def _phase_of(obs: dict, by_id: dict) -> tuple[str, str]:
    """Walk up parentObservationId to the first span named in the contract table.

    Returns (phase, nearest ancestor name). No listed ancestor -> ("other", nearest
    ancestor name, or "<none>" when the generation has no parent at all).
    """
    ancestor, cur, seen = "<none>", by_id.get(obs.get("parentObservationId")), set()
    while cur is not None and cur["id"] not in seen:   # cycle-safe on malformed traces
        seen.add(cur["id"])
        if ancestor == "<none>":
            ancestor = cur.get("name") or "<none>"
        if cur.get("name") in PHASE_SPANS:
            return PHASE_SPANS[cur["name"]], cur["name"]
        cur = by_id.get(cur.get("parentObservationId"))
    return "other", ancestor


# ponytail: page_size is a test seam (force multi-page paging); production always uses
# the contract's 100.
def read_generations(base_url: str, public_key: str, secret_key: str, episode_id: str,
                     price_table, timeout: float = 10.0, page_size: int = 100) -> list[Generation]:
    auth = "Basic " + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    traces = _get(base_url, "/api/public/traces",
                  {"metadata[bench_episode_id]": episode_id}, auth, timeout, page_size)
    out = []
    for trace in traces:
        obs = _get(base_url, "/api/public/observations",
                   {"traceId": trace["id"]}, auth, timeout, page_size)
        by_id = {o["id"]: o for o in obs}
        for o in obs:
            if o.get("type") != "GENERATION":
                continue
            phase, ancestor = _phase_of(o, by_id)
            u = o.get("usage") or {}
            out.append(Generation(
                trace_id=trace["id"], observation_id=o["id"], model=o.get("model"),
                family=_family(o.get("model"), price_table), phase=phase, ancestor=ancestor,
                input=int(u.get("input") or 0), output=int(u.get("output") or 0),
                cache_read=int(u.get("cache_read_input_tokens") or 0),
                cache_write=int(u.get("cache_creation_input_tokens") or 0)))
    return out


def summarize(generations: list[Generation], price_table) -> CostSummary:
    prices = {e.family: e.usd_per_million for e in price_table.models}
    fields = ("input", "output", "cache_read", "cache_write")
    s = CostSummary(missing=not generations,
                    tokens={f: 0 for f in fields} if generations else {})
    others = []
    for g in generations:
        row = s.by_phase.setdefault(g.phase, {}).setdefault(
            g.family, {**{f: 0 for f in fields}, "cost_usd": 0.0})
        for f in fields:
            row[f] += getattr(g, f)
            s.tokens[f] += getattr(g, f)
        if g.phase == "other" and g.ancestor not in others:
            others.append(g.ancestor)
    for phase in s.by_phase.values():
        for family, row in phase.items():
            row["cost_usd"] = cost_for(prices[family], *(row[f] for f in fields))
    s.other_spans = others
    s.total_usd = round(sum(r["cost_usd"] for p in s.by_phase.values() for r in p.values()), 6)
    return s
