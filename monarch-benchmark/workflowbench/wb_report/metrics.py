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

import json
import re
import statistics
from pathlib import Path
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
    """How many questions the builder actually asked, deduplicated by request.

    The flag `questions_asked=N` over-counts: the arm accumulates the questions
    of every `awaiting_input` frame it sees, and the SSE stream re-delivers the
    same frame whenever it reconnects. On run-20260904-192933 one request
    (`ask_1_6b211c69`, two questions) was re-delivered once and recorded as 4.

    So where the attempt's turn log is available, the count is the number of
    questions across *distinct* request ids; the flag is the fallback for a row
    whose log has been cleaned up.

    # ponytail: dedupe at read time, in the reader. Fixing the writer in
    # wb_arms/monarch.py is the real repair, but that file is owned by another
    # feature right now and re-counting a stored log costs nothing. Ceiling:
    # once the arm dedupes at write time this falls back to the flag and agrees.
    """
    counted = _questions_from_log(row)
    if counted is not None:
        return counted
    total = 0
    for flag in row.get("flags") or []:
        if flag.startswith("questions_asked="):
            try:
                total += int(flag.split("=", 1)[1])
            except ValueError:
                pass
    return total


def _questions_from_log(row: dict) -> int | None:
    """Questions across distinct `requestId`s in the attempt's turn log, or
    `None` when there is no readable log to count from."""
    uri = row.get("artifacts_uri")
    if not uri:
        return None
    log = Path(uri) / "turns.jsonl"
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    seen: dict[str, int] = {}
    for line in text.splitlines():
        if "awaiting_reply" not in line:
            continue
        try:
            ask = (json.loads(line).get("frame") or {}).get("awaiting_reply") or {}
        except (json.JSONDecodeError, AttributeError):
            continue
        rid = ask.get("requestId")
        if rid:
            # the same request re-delivered on reconnect counts once
            seen[rid] = len(ask.get("questions") or [])
    return sum(seen.values()) or None


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


# The two phase keys Monarch writes, and the words Carlos uses for them. The
# keys stay `authoring` and `execution` on the row and in the source line; the
# page says "builder" and "dispatch" everywhere a person reads it.
BUILDER_PHASE = "authoring"
DISPATCH_PHASE = "execution"
PHASE_WORDS = {BUILDER_PHASE: "builder", DISPATCH_PHASE: "dispatch"}


def is_monarch(arm: str) -> bool:
    """Monarch competitors are named `monarch` or `monarch@<version>`, and the
    lab ones `monarch-lab*`. The page needs to know which rows carry phases."""
    return arm.startswith("monarch")


def _builder_outcome(row: dict, phase: dict | None) -> str:
    """What the builder did, in the words the round sheet uses.

    `declined` is a real Monarch answer, not a failure: it decided the request
    could not become a workflow. It is distinguished from an error and from a
    timeout because the three mean different things to a reader.
    """
    if "no_workflow" in (row.get("flags") or []):
        return "declined"
    if phase is None:
        return "n/a"
    termination = str(row.get("termination") or "")
    # A timeout inside the builder ends the attempt before dispatch exists.
    if termination == "timeout" and not row.get("phases", {}).get(DISPATCH_PHASE):
        return "timeout"
    if termination == "agent_error":
        return "error"
    return "done"


def _dispatch_outcome(row: dict, phase: dict | None) -> str:
    """What the engine did with the workflow the builder produced."""
    if phase is None:
        return "n/a"
    termination = str(row.get("termination") or "")
    if termination == "timeout":
        # The engine was still polling when the deadline passed: the workflow
        # was parked, not refused and not failed.
        return "parked-timeout"
    if termination.startswith("infra:"):
        return "infrastructure"
    if row.get("gate_refusals"):
        return "refused"
    if termination == "agent_error":
        return "error"
    return "success" if row.get("passed") else "failed"


def monarch_attempts(rows: list[dict]) -> list[dict]:
    """One entry per Monarch attempt, for the Monarch phases section.

    The page shows what happened in each half of the attempt separately, because
    "the builder wrote a workflow and the engine timed out running it" and "the
    builder never finished" are different results that a single pass/fail hides.
    """
    out = []
    for row in sorted(rows, key=lambda r: (r["task_id"], r["trial"])):
        phases = row.get("phases") or {}
        builder = phases.get(BUILDER_PHASE)
        dispatch = phases.get(DISPATCH_PHASE)
        out.append({
            "task_id": row["task_id"], "trial": row["trial"],
            "builder_outcome": _builder_outcome(row, builder),
            "questions_asked": _questions_asked(row),
            "builder_seconds": (builder or {}).get("wall_clock_s"),
            "builder_cost": (builder or {}).get("cost_usd"),
            "dispatch_outcome": _dispatch_outcome(row, dispatch),
            "dispatch_seconds": (dispatch or {}).get("wall_clock_s"),
            "checker": "pass" if row.get("passed") else "fail",
            # the reason, abbreviated the same way the failures table does it
            "reason": (row.get("error") or "")[:200] or None,
        })
    return out


def round_totals(metrics: list[dict]) -> dict[str, Any]:
    """The whole round in three numbers, for the overview section."""
    return {
        "spend_usd": sum(m["cost_total"] for m in metrics),
        "attempts": sum(m["attempts"] for m in metrics),
        "infra": sum(m["infra"] for m in metrics),
    }
