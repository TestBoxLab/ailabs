"""Every number the report pages render, computed in one place.

`contracts/report.md` (feature 006) is the authority for each formula; this
module is its only implementation. It *calls* `wb_stats` for the statistics -
strict pass, pass over repetitions, paired wins and losses - so the page and the
markdown report can never disagree about a rate.

Rules that hold everywhere here:

- a row is an `EpisodeRow.model_dump()` dictionary from `Store.episodes()`;
- an infrastructure attempt is `termination` starting with `infra:`, the
  definition `wb_stats` already uses; it is excluded from every pass
  denominator and reported on its own (PLAN.md section 1, rule 7);
- every division whose denominator is 0 yields `None`, never `inf`, `nan` or a
  silent 0. `None` is what the renderer prints as `n/a`;
- the four figures taken from `arm_summary` arrive rounded (that function rounds
  for the markdown report); the ones computed here are deliberately unrounded,
  and the renderer does all formatting.
"""
from __future__ import annotations

import statistics
from typing import Any

from wb_stats.stats import _is_infra, arm_summary, paired_wl, pass_hat_k

# A phase named `model:<name>` records what one language model cost inside an
# attempt that used several. The writer (wb_arms/monarch.py) and this reader
# share the prefix from here so they cannot drift apart.
SYNTHETIC_PHASE_PREFIX = "model:"


def _div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def attempt_seconds(row: dict) -> float | None:
    """The attempt's wall-clock: the sum over its phases (research R6), so the
    total always agrees with the phase columns beside it. `None` - not 0 - when
    no phase carries one; such an attempt joins neither the mean nor the
    median."""
    values = [p.get("wall_clock_s") for p in (row.get("phases") or {}).values()]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _questions_asked(row: dict) -> int:
    """The count carried on the `questions_asked=N` flag; 0 when absent."""
    total = 0
    for flag in row.get("flags") or []:
        if flag.startswith("questions_asked="):
            try:
                total += int(flag.split("=", 1)[1])
            except ValueError:
                pass
    return total


def _phase_block(rows: list[dict]) -> tuple[dict[str, dict], dict[str, float]]:
    """Per-phase wall-clock mean and cost total, and the cost per model.

    # ponytail: phase names are read off the row, not matched against a table of
    # known phases, so a phase feature 002 or 004 adds shows up with no code
    # change here. Ceiling: a typo in a phase name becomes a column.

    The `run` phase is every competitor's whole attempt and is already the
    wall-clock and cost columns, so it is not repeated as a phase of its own.
    """
    seconds: dict[str, list[float]] = {}
    costs: dict[str, float] = {}
    per_model: dict[str, float] = {}
    for row in rows:
        for name, phase in (row.get("phases") or {}).items():
            cost = phase.get("cost_usd") or 0.0
            if name.startswith(SYNTHETIC_PHASE_PREFIX):
                model = name[len(SYNTHETIC_PHASE_PREFIX):]
                per_model[model] = per_model.get(model, 0.0) + cost
                continue
            if name == "run":
                continue
            costs[name] = costs.get(name, 0.0) + cost
            if phase.get("wall_clock_s") is not None:
                seconds.setdefault(name, []).append(phase["wall_clock_s"])
    phases = {name: {"wall_clock_s": _div(sum(seconds.get(name, [])), len(seconds.get(name, []))),
                     "cost_usd": cost}
              for name, cost in costs.items()}
    return phases, per_model


def competitor_metrics(rows: list[dict], k: int) -> dict[str, Any]:
    """One competitor's row of the metrics table, per contracts section 1."""
    ok = [r for r in rows if not _is_infra(r)]
    passed = sum(1 for r in ok if r["passed"])
    infra = len(rows) - len(ok)
    phk = pass_hat_k(rows, k)
    # Every attempt was paid for, infrastructure ones included.
    cost_total = sum(r.get("cost_usd") or 0.0 for r in rows)
    # `tokens` is null on a row whose competitor reports none; it counts as 0.
    tokens = {field: sum((r.get("tokens") or {}).get(field, 0) or 0 for r in rows)
              for field in ("prompt", "cached", "cache_write", "output")}
    seconds = [s for s in (attempt_seconds(r) for r in rows) if s is not None]
    phases, per_model = _phase_block(rows)
    return {
        "arm": rows[0]["arm"] if rows else None,
        "attempts": len(rows),
        "passed": passed,
        "infra": infra,
        "agent_errors": sum(1 for r in rows if r.get("termination") == "agent_error"),
        "timeouts": sum(1 for r in rows if r.get("termination") == "timeout"),
        "infra_rate": _div(infra, len(rows)),
        # The two rates are wb_stats' verbatim; both exclude infrastructure
        # attempts from their denominator inside those functions.
        "strict_pass": arm_summary(rows)["strict_pass"],
        "pass_over_repetitions": {"k": phk["k"], "mean": phk["mean"], "sem": phk["sem"]},
        "strict_pass_denominator": len(ok),
        "cost_total": cost_total,
        "cost_per_attempt": _div(cost_total, len(rows)),
        "cost_per_passed": _div(cost_total, passed),
        "tokens": tokens,
        "cache_hit_rate": _div(tokens["cached"], tokens["prompt"]),
        "wall_clock": {
            "mean": _div(sum(seconds), len(seconds)),
            "median": statistics.median(seconds) if seconds else None,
            "n_with": len(seconds), "n_total": len(rows),
        },
        "turns": sum(p.get("turns") or 0 for r in rows
                     for p in (r.get("phases") or {}).values()),
        # the row's own total, not the phase sum (contracts section 1)
        "tool_calls": sum(r.get("tool_calls") or 0 for r in rows),
        "phases": phases,
        "cost_per_model": per_model,
        "questions_asked": sum(_questions_asked(r) for r in rows),
        "declined_to_build": sum(1 for r in rows if "no_workflow" in (r.get("flags") or [])),
    }


def verdict(pairs: int, p: float, wins: int, losses: int) -> str:
    """The plain-words reading of a comparison, per contracts section 2.

    Four strings, no others. It renders the p that `paired_wl` already computed;
    it is never a new test.
    """
    if pairs == 0:
        return "no comparable attempts"
    if p >= 0.05:
        return "no significant difference at this size"
    direction = "better" if wins > losses else "worse"
    return f"{direction} than the baseline (p = {p:.3f})"


def comparison(a: dict, b: dict, rows_arm: list[dict], rows_base: list[dict],
               source: dict | None = None) -> dict[str, Any]:
    """One row of the comparison table, per contracts section 2.

    `a` and `b` are the two competitors' already-computed `competitor_metrics`
    entries, so the comparison table can never disagree with the metrics table
    above it; the rows are needed only for the pairing. Every figure is on the
    identical attempt set - the pairs `paired_wl` finds - and an infrastructure
    attempt on either side drops the pair, exactly as the markdown report does.
    """
    wl = paired_wl(rows_arm, rows_base)
    a_rate, b_rate = a["strict_pass"]["mean"], b["strict_pass"]["mean"]
    diff = (a_rate - b_rate) * 100 if a_rate is not None and b_rate is not None else None
    return {
        "arm": a["arm"], "baseline": b["arm"],
        "strict_pass_diff_pp": diff,
        "pass_rate_ratio": _div(a_rate, b_rate) if a_rate is not None and b_rate else None,
        "cost_per_passed_ratio": (_div(a["cost_per_passed"], b["cost_per_passed"])
                                  if a["cost_per_passed"] is not None
                                  and b["cost_per_passed"] is not None else None),
        "wins": wl["wins"], "losses": wl["losses"],
        "both": wl["both_pass"], "neither": wl["neither_pass"],
        "pairs": wl["pairs"], "dropped_infra": wl["dropped_infra"],
        "mcnemar": wl["mcnemar"],
        "verdict": verdict(wl["pairs"], wl["mcnemar"]["p"], wl["wins"], wl["losses"]),
        # Its own source: this row's denominator is its pairs, not a total over
        # every comparison on the page (data-model.md section 2.3).
        "source": dict(source or {}, denominator=wl["pairs"],
                       arm=[a["arm"], b["arm"]]),
    }
