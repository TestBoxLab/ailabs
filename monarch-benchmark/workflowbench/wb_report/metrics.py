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
import statistics
from pathlib import Path
from typing import Any

from wb_stats.stats import (_is_infra, arm_summary, mean_sem, paired_wl,
                            pass_hat_k)

# A phase named `model:<name>` records what one language model cost inside an
# attempt that used several. The writer (wb_arms/monarch.py) and this reader
# share the prefix from here so they cannot drift apart.
SYNTHETIC_PHASE_PREFIX = "model:"


def _div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def attempt_seconds(row: dict) -> float | None:
    """The attempt's wall-clock, agreeing with the phase columns beside it (research R6).

    `run` is the whole attempt, written by the orchestrator beside whatever phases the
    arm recorded (`{**arm_phases, "run": ...}`), so it is the answer where it carries a
    clock — never a term added to its own parts. It was, until 11 September: a Monarch
    row reported `run` + `authoring` + `execution` and so was roughly twice its true
    duration, which is the number the "faster than a harness" claim is read off.
    `model:<family>` is the same attempt cut by model and is excluded for the same
    reason, by name rather than by carrying no clock.

    `None` - not 0 - when nothing carries one; such an attempt joins neither the mean
    nor the median.
    """
    phases = row.get("phases") or {}
    whole = (phases.get("run") or {}).get("wall_clock_s")
    if whole is not None:
        return whole
    values = [p.get("wall_clock_s") for name, p in phases.items()
              if name != "run" and not name.startswith(SYNTHETIC_PHASE_PREFIX)]
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


def _assumptions(row: dict) -> list[str]:
    """What the unattended builder decided for itself, from the attempt's turn
    log: the `{"assumptions": [...]}` entry the arm wrote on the done frame.

    An attempt whose builder assumed nothing, and one whose log is gone, both
    read as an empty list; the page shows nothing either way.
    """
    log = row.get("turn_log")
    if log is None:
        log = _turn_log_entries(row, "assumptions")
    for entry in log or []:
        if isinstance(entry, dict) and entry.get("assumptions"):
            return [str(a) for a in entry["assumptions"]]
    return []


def _turn_log_entries(row: dict, needle: str) -> list[dict]:
    """The attempt's stored turn log, filtered to the lines naming `needle`."""
    uri = row.get("artifacts_uri")
    if not uri:
        return []
    try:
        text = (Path(uri) / "turns.jsonl").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        if needle not in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


# The retry a plan asks for with `retry_on_fail`: one extra attempt at a prompt
# whose first attempt failed. The orchestrator writes it as trial 1 carrying
# this flag, so the report can tell a retry apart from a second repetition.
RETRY_FLAG = "retry=1"


def _front_door(row: dict) -> dict[str, Any]:
    """What the attempt's front door saw, from `front-door.jsonl` beside the
    turn log: how many requests arrived, how many failed, and the last failure
    written out as `<method> <path> -> <status>`.

    Every value is None when the attempt has no readable log - a competitor that
    never used the front door, or a run whose artifacts are gone.
    """
    uri = row.get("artifacts_uri")
    if not uri:
        return {"front_door_calls": None, "front_door_errors": None,
                "front_door_last_error": None}
    try:
        text = (Path(uri) / "front-door.jsonl").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"front_door_calls": None, "front_door_errors": None,
                "front_door_last_error": None}
    calls, errors, last = 0, 0, None
    for line in text.splitlines():
        try:
            call = json.loads(line)
        except json.JSONDecodeError:
            continue
        calls += 1
        if (call.get("status") or 0) >= 400:
            errors += 1
            last = f"{call.get('method')} {call.get('path')} -> {call.get('status')}"
    return {"front_door_calls": calls, "front_door_errors": errors,
            "front_door_last_error": last}


def _is_retry(row: dict) -> bool:
    return RETRY_FLAG in (row.get("flags") or [])


def _by_task(rows: list[dict]) -> dict[str, list[dict]]:
    """Non-infrastructure attempts grouped by prompt, in trial order.

    Infrastructure failures never consume a retry, so they are dropped here
    exactly as they are dropped from every other denominator.
    """
    out: dict[str, list[dict]] = {}
    for row in sorted(rows, key=lambda r: r["trial"]):
        if not _is_infra(row):
            out.setdefault(row["task_id"], []).append(row)
    return out


def _first_try_pass(rows: list[dict]) -> dict[str, Any]:
    """Strict pass rate over the first attempt at each prompt only.

    This is what the competitor did with no second chance. Mean and SEM over
    prompts, the same shape as `strict_pass`, so the error bars read alike.
    """
    firsts = [attempts[0] for attempts in _by_task(rows).values() if attempts]
    return mean_sem([1.0 if bool(r["passed"]) else 0.0 for r in firsts])


def _pass_after_retry(rows: list[dict]) -> dict[str, Any]:
    """The share of prompts whose first attempt or its retry passed strictly.

    On a round with `retry_on_fail` that is trial 0 or the retry row. On a round
    with plain repetitions and no retries it is "any repetition passed", which
    answers the same question - would one more go have delivered it - so the
    figure stays meaningful either way.
    """
    return mean_sem([1.0 if any(bool(r["passed"]) for r in attempts) else 0.0
                     for attempts in _by_task(rows).values()])


def _retries(rows: list[dict]) -> dict[str, Any]:
    """How many retries were spent, and on what share of the prompts."""
    retried = {r["task_id"] for r in rows if _is_retry(r)}
    prompts = len(_by_task(rows))
    return {"count": sum(1 for r in rows if _is_retry(r)),
            "prompts_retried": len(retried),
            "share": _div(len(retried), prompts)}


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
    blind: dict[str, int] = {}
    per_model: dict[str, float] = {}
    for row in rows:
        for name, phase in (row.get("phases") or {}).items():
            # `PhaseMetrics.cost_usd` is None when nobody could price the phase, and
            # `or 0.0` read that as free. An unpriced attempt holds its whole ceiling
            # against the week instead of settling, so calling it zero tells a reader
            # the round was cheap while the ledger is still holding the money.
            priced = phase.get("cost_usd")
            cost = 0.0 if priced is None else priced
            if name.startswith(SYNTHETIC_PHASE_PREFIX):
                model = name[len(SYNTHETIC_PHASE_PREFIX):]
                per_model[model] = per_model.get(model, 0.0) + cost
                continue
            if name == "run":
                continue
            costs[name] = costs.get(name, 0.0) + cost
            blind[name] = blind.get(name, 0) + (priced is None)
            if phase.get("wall_clock_s") is not None:
                seconds.setdefault(name, []).append(phase["wall_clock_s"])
    phases = {name: {"wall_clock_s": _div(sum(seconds.get(name, [])), len(seconds.get(name, []))),
                     # Unknown for the whole phase the moment one attempt of it is
                     # unpriced: a partial sum presented as the total is the error.
                     "cost_usd": None if blind.get(name) else cost,
                     "cost_unknown": blind.get(name, 0)}
              for name, cost in costs.items()}
    return phases, per_model


# The scripted answer key (`oracle`) only knows how to act on the pilot's
# Salesforce field updates. Put in front of another task set it searches, reads
# and stops: no change, one or two tool calls, and a failed attempt. That is the
# answer key being out of its depth, not a competitor scoring nothing, so the
# report says "not applicable" instead of 0%.
ANSWER_KEY_ARM = "oracle"
NOT_APPLICABLE_REASON = "answer key does not cover this task set"
# it only searched and read
_NA_MAX_TOOL_CALLS = 2


def is_not_applicable(row: dict) -> bool:
    """Whether one attempt is the answer key acting on nothing.

    Only the answer key can be not-applicable: a language model that read the
    world and changed nothing simply failed the task, and the report must keep
    saying so.
    """
    return (row.get("arm") == ANSWER_KEY_ARM
            and not row.get("passed")
            and not _is_infra(row)
            and (row.get("n_changes") or 0) == 0
            and (row.get("tool_calls") or 0) <= _NA_MAX_TOOL_CALLS)


def _collateral_of(row: dict) -> int:
    """Changes this attempt made that its approval rule did not ask for.

    Two sources, same meaning: a write in a place the rule never named, and the
    right write repeated. Doing the requested thing 201 times is 200 of these.
    """
    extra = sum(max(0, v.get("got", 0) - v.get("want", 0))
                for v in (row.get("count_violations") or []))
    return len(row.get("unexpected_changes") or []) + extra


def competitor_metrics(rows: list[dict], k: int) -> dict[str, Any]:
    """One competitor's row of the metrics table, per contracts section 1."""
    # Attempts the answer key could not act on leave every pass denominator;
    # they are counted so the page can say how many, and the cost, token and
    # time columns still cover every attempt that was actually made.
    na_count = sum(1 for r in rows if is_not_applicable(r))
    scored = [r for r in rows if not is_not_applicable(r)]
    ok = [r for r in scored if not _is_infra(r)]
    passed = sum(1 for r in ok if r["passed"])
    # infrastructure is counted over every attempt: a not-applicable one is
    # still an attempt that did or did not hit infrastructure trouble
    infra = sum(1 for r in rows if _is_infra(r))
    phk = pass_hat_k(scored, k)
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
        "strict_pass": arm_summary(scored)["strict_pass"],
        # What this competitor touched that nobody asked for. Two competitors can
        # share a pass rate and differ entirely here: one takes the safe path, the
        # other finishes more prompts by making a bigger mess. Infrastructure
        # attempts are out — the harness broke, the competitor did not.
        "collateral_attempts": sum(1 for r in ok if _collateral_of(r)),
        "collateral_changes": sum(_collateral_of(r) for r in ok),
        "collateral_rate": _div(sum(1 for r in ok if _collateral_of(r)), len(ok)),
        # what one attempt achieved, and what one retry would have added
        "first_try_pass": _first_try_pass(scored),
        "pass_after_retry": _pass_after_retry(scored),
        "retries": _retries(scored),
        # the answer key on a task set it cannot act on: not a 0%
        "not_applicable": bool(na_count) and not scored,
        "not_applicable_rows": na_count,
        "not_applicable_reason": NOT_APPLICABLE_REASON if na_count else None,
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
    # A side that is not applicable has nothing to pair against: comparing it
    # would read its blank rows as losses.
    skipped = (NOT_APPLICABLE_REASON
               if a.get("not_applicable") or b.get("not_applicable") else None)
    if skipped:
        rows_arm = [r for r in rows_arm if not is_not_applicable(r)]
        rows_base = [r for r in rows_base if not is_not_applicable(r)]
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
        "verdict": skipped or verdict(wl["pairs"], wl["mcnemar"]["p"],
                                      wl["wins"], wl["losses"]),
        "skipped": skipped,
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
    could not become a workflow. `needs_input` is likewise its own outcome, not
    an error: the attempt ended before the run because the builder needed more
    from the user than the request gave it. Both are distinguished from an
    error and from a timeout because these mean different things to a reader.
    """
    error = str(row.get("error") or "")
    # The arm writes the decline as the error; the flag is the older shape.
    if "no_workflow" in (row.get("flags") or []) or error.startswith("no_workflow:"):
        return "declined"
    if error.startswith("needs_input:"):
        return "needs_input"
    if phase is None:
        return "n/a"
    termination = str(row.get("termination") or "")
    # A timeout inside the builder ends the attempt before dispatch exists.
    if termination == "timeout" and not row.get("phases", {}).get(DISPATCH_PHASE):
        return "timeout"
    if termination == "agent_error":
        # A run that wrote nothing is dispatch's failure, not the builder's: the
        # builder produced a workflow, and the engine ran it to the end.
        return "done" if error == "run_no_writes" else "error"
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
        # A run that finished having written nothing is not an engine error: the
        # workflow ran to the end and changed nothing (backend 2ede4b3ee).
        if str(row.get("error") or "") == "run_no_writes":
            return "ran, no writes"
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
            "assumptions": _assumptions(row),
            "builder_seconds": (builder or {}).get("wall_clock_s"),
            "builder_cost": (builder or {}).get("cost_usd"),
            "dispatch_outcome": _dispatch_outcome(row, dispatch),
            "dispatch_seconds": (dispatch or {}).get("wall_clock_s"),
            "checker": "pass" if row.get("passed") else "fail",
            # the reason, abbreviated the same way the failures table does it
            "reason": (row.get("error") or "")[:200] or None,
            **_front_door(row),
        })
    return out


# One row per outcome, in this fixed order and these plain words, for the
# "Monarch attempts by outcome" summary table. `_outcome_of` below is the only
# place that decides which bucket an attempt falls in.
_OUTCOME_WORDS = [
    ("passed", "passed"),
    ("needs_input", "asked for user input"),
    ("declined", "declined to build"),
    ("builder_or_dispatch_failed", "builder error or timeout"),
    ("dispatch_error", "dispatch error"),
    ("ran_not_made", "ran but the change was not made"),
    ("checker_failed_other", "checker failed for another reason"),
]


def _outcome_of(attempt: dict) -> str:
    """Which of the seven buckets one `monarch_attempts` entry falls in.

    Order matters: an attempt that never reached dispatch is read off the
    builder outcome first, because "the builder asked a question" and "dispatch
    failed" cannot both be true of the same attempt.
    """
    if attempt["checker"] == "pass":
        return "passed"
    builder = attempt["builder_outcome"]
    if builder == "needs_input":
        return "needs_input"
    if builder == "declined":
        return "declined"
    if builder in ("timeout", "error"):
        return "builder_or_dispatch_failed"
    dispatch = attempt["dispatch_outcome"]
    if dispatch in ("parked-timeout", "error"):
        return "builder_or_dispatch_failed"
    if dispatch in ("infrastructure", "refused"):
        return "dispatch_error"
    if dispatch in ("success", "ran, no writes"):
        # the workflow ran, the checker still says no: the change was not made.
        # A run that wrote nothing is the same story, said by the engine itself.
        return "ran_not_made"
    return "checker_failed_other"


def monarch_outcomes(rows: list[dict]) -> list[dict]:
    """The "Monarch attempts by outcome" summary: one row per outcome bucket,
    count and share, in the fixed order `_OUTCOME_WORDS` defines. Gated the
    same way the rest of the Monarch section is - callers render it only when
    a Monarch competitor is on the page."""
    attempts = monarch_attempts(rows)
    total = len(attempts)
    counts = {key: 0 for key, _ in _OUTCOME_WORDS}
    for a in attempts:
        counts[_outcome_of(a)] += 1
    return [{"outcome": label, "count": counts[key], "share": _div(counts[key], total)}
            for key, label in _OUTCOME_WORDS]


def round_totals(metrics: list[dict]) -> dict[str, Any]:
    """The whole round in three numbers, for the overview section."""
    return {
        "spend_usd": sum(m["cost_total"] for m in metrics),
        "attempts": sum(m["attempts"] for m in metrics),
        "infra": sum(m["infra"] for m in metrics),
    }
