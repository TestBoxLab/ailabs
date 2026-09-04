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


def _tokens(o: dict) -> tuple[int, int, int, int]:
    """The four disjoint counts of one generation: (input, output, cache_read, cache_write).

    Verified on Langfuse Cloud v4.28, 4 Sep 2026: a generation carries both
    `usageDetails` -- disjoint, `input` is the NON-cached part -- and `usage`,
    whose `input` is INCLUSIVE of the cache reads and writes. usageDetails is
    preferred; the fallback subtracts the cache out of the inclusive count.
    """
    d = o.get("usageDetails") or {}
    if d:
        return (int(d.get("input") or 0), int(d.get("output") or 0),
                int(d.get("cache_read_input_tokens") or 0),
                int(d.get("cache_creation_input_tokens") or 0))
    u = o.get("usage") or {}
    read = int(u.get("cache_read_input_tokens") or 0)
    write = int(u.get("cache_creation_input_tokens") or 0)
    return (max(0, int(u.get("input") or 0) - read - write),
            int(u.get("output") or 0), read, write)


# ponytail: page_size is a test seam (force multi-page paging); production always uses
# the contract's 100.
def _one_trace(base_url: str, trace_id: str, auth: str, timeout: float):
    """One trace by id. Returns None when Langfuse does not have it."""
    req = urllib.request.Request(f"{base_url.rstrip('/')}/api/public/traces/{trace_id}",
                                 headers={"Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None                       # not ingested yet, or never existed
        raise LangfuseUnavailable(f"GET /api/public/traces/{trace_id}: {e}") from e
    except (OSError, json.JSONDecodeError) as e:
        raise LangfuseUnavailable(f"GET /api/public/traces/{trace_id}: {e}") from e


def read_generations(base_url: str, public_key: str, secret_key: str, episode_id: str,
                     price_table, timeout: float = 10.0, page_size: int = 100,
                     from_timestamp=None, trace_ids: list[str] | None = None) -> list[Generation]:
    """The episode's generations. `from_timestamp` (aware datetime) narrows the list.

    `trace_ids` is the primary join: Monarch's own frames carry `traceId`, so the
    attempt knows its traces exactly and each is fetched by id. Without them the
    listing is scanned and filtered on metadata, which is the fallback below.

    Verified on Langfuse Cloud v4.28, 4 Sep 2026: GET /api/public/traces IGNORES
    the `metadata[bench_episode_id]` filter and returns every trace in the
    project, so the episode's traces are picked out client-side on
    trace.metadata.bench_episode_id. The parameter is still sent -- harmless, and
    it starts working the day Cloud honours it. `fromTimestamp` IS honoured, and
    is what keeps the listing from growing without bound.
    """
    auth = "Basic " + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    if trace_ids:
        out = []
        for trace_id in trace_ids:
            trace = _one_trace(base_url, trace_id, auth, timeout)
            if trace is None:
                continue
            # An empty list is not "this trace has no observations": Langfuse
            # answers `[]` when it serves the trace without expanding them, and
            # taking that at face value cost the live attempt every parent -- so
            # every generation landed in `other` with ancestor `<none>`
            # (4 Sep 2026). Absent and empty are both "ask the other endpoint".
            obs = trace.get("observations") or _get(
                base_url, "/api/public/observations",
                {"traceId": trace_id}, auth, timeout, page_size)
            out += _generations(obs, trace_id, price_table)
        return out
    params = {"metadata[bench_episode_id]": episode_id}
    if from_timestamp is not None:
        params["fromTimestamp"] = from_timestamp.isoformat()
    traces = _get(base_url, "/api/public/traces", params, auth, timeout, page_size)
    out = []
    for trace in traces:
        if (trace.get("metadata") or {}).get("bench_episode_id") != episode_id:
            continue
        obs = _get(base_url, "/api/public/observations",
                   {"traceId": trace["id"]}, auth, timeout, page_size)
        out += _generations(obs, trace["id"], price_table)
    return out


def _generations(obs: list[dict], trace_id: str, price_table) -> list[Generation]:
    """The priced generations among one trace's observations."""
    by_id = {o["id"]: o for o in obs}
    out = []
    for o in obs:
        if o.get("type") != "GENERATION":
            continue
        phase, ancestor = _phase_of(o, by_id)
        i, out_t, read, write = _tokens(o)
        out.append(Generation(
            trace_id=trace_id, observation_id=o["id"], model=o.get("model"),
            family=_family(o.get("model"), price_table), phase=phase, ancestor=ancestor,
            input=i, output=out_t, cache_read=read, cache_write=write))
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
