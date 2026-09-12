"""Descriptive performance of one run, projected from its original evidence.

This does not grade or compare task revisions. A successful sample requires the
stored pass and a normal finish. Missing telemetry stays separate from zero.
"""
from __future__ import annotations

import math
from collections import defaultdict

from wb_studio import measures
from wb_studio.reports import tool_error


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _count(value):
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _distribution(values):
    recorded = [_number(value) for value in values]
    valid = sorted(value for value in recorded if value is not None)

    def quantile(fraction):
        if not valid:
            return None
        position = fraction * (len(valid) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        return valid[lower] + (valid[upper] - valid[lower]) * (position - lower)

    return {"count": len(valid), "missing": len(recorded) - len(valid),
            "median": quantile(.5), "p90": quantile(.9),
            "max": valid[-1] if valid else None, "values": valid}


def _passed(row):
    return (bool(row.get("passed")) and row.get("termination") == "completed"
            and not measures.is_ungraded(row))


def _unique_events(events):
    seen = set()
    for event in events:
        identity = event.get("id")
        if identity is not None and identity != "":
            identity = str(identity)
            if identity in seen:
                continue
            seen.add(identity)
        yield event


def _attempt_id(record):
    return record.get("attempt_id") or record.get("episode_id")


def _telemetry(rows, events):
    """Count delivered events once, never once per same-task result row.

    Repeated attempts without an identity cannot provide per-attempt coverage.
    Their observed model turns still contribute once to the setup's total.
    """
    pairs = defaultdict(list)
    for row in rows:
        pairs[(row.get("task"), row.get("model"))].append(_attempt_id(row))
    identities = {pair: {identity for identity in values if identity} for pair, values in pairs.items()}
    tools, turns, observed_attempts = [], 0, set()
    for event in events:
        pair = (event.get("task"), event.get("model"))
        if pair not in pairs:
            continue
        identity = _attempt_id(event)
        known_ids = identities[pair]
        if identity and len(known_ids) == len(pairs[pair]) and identity not in known_ids:
            continue
        kind = event.get("type")
        if kind == "model_finished":
            turns += 1
            if identity and identity in known_ids:
                observed_attempts.add((identity, *pair))
            elif len(pairs[pair]) == 1:
                observed_attempts.add((pairs[pair][0], *pair))
        elif kind == "tool_completed" or (kind == "node_finished" and event.get("category") in (None, "tool")):
            if event.get("status") in ("completed", "error", "failed", "success", "succeeded"):
                tools.append(event)
    errors = sum(event.get("status") in ("error", "failed") or tool_error(event) is not None for event in tools)
    return {"errors": errors, "observed_calls": len(tools),
            "error_rate": errors / len(tools) if tools else None}, {
                "total": turns, "observed_attempts": len(observed_attempts)}


def _collateral(row):
    count = len(row.get("unexpected_changes") or [])
    for violation in row.get("count_violations") or []:
        got, want = _count(violation.get("got")), _count(violation.get("want"))
        if got is not None and want is not None:
            count += max(0, got - want)
    return count


def performance_report(job, events):
    """One shared report member for Activity and the permanent run report.

    Phase coverage concerns only attempts declaring that phase; its absence is
    not applicable. Run/model cuts are not additional phases. Original rows are
    retained even when their task's current hash moved or a report borrows a
    baseline: operational spend and timing belong to this run alone.
    """
    rows = job.get("results") or []
    settings = job.get("settings") or {}
    declared = list(dict.fromkeys([a["id"] for a in settings.get("arms") or []]
                                 or settings.get("models") or []))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["model"]].append(row)
    order = list(dict.fromkeys([*declared, *grouped]))
    names = measures.setup_names(job)
    repetitions = _count(settings.get("repetitions", 1)) or 1
    planned_each = len(settings.get("tasks") or []) * repetitions
    unique_events = list(_unique_events(events))
    setups = {}
    for model in order:
        attempts = grouped[model]
        valid = measures.evaluated(attempts)
        successful = [row for row in valid if _passed(row)]
        failed = [row for row in valid if not _passed(row)]
        costs = [None if isinstance(row.get("cost_usd"), bool) else measures.known_cost(row) for row in attempts]
        unknown = sum(value is None for value in costs)
        subtotal = sum(value for value in costs if value is not None)
        total = None if unknown else subtotal
        calls = [_count(row.get("tool_calls")) for row in attempts]
        tools, turns = _telemetry(attempts, unique_events)
        phases = defaultdict(list)
        for row in attempts:
            for phase, metrics in (row.get("phases") or {}).items():
                if phase != measures.TOTAL_PHASE and not phase.startswith(measures.SYNTHETIC_PHASE):
                    phases[phase].append((metrics or {}).get("wall_clock_s"))
        collateral = [_collateral(row) for row in valid]
        complete_collateral = sum(isinstance(row.get("unexpected_changes"), list)
                                  and isinstance(row.get("count_violations"), list) for row in valid)
        setups[model] = {
            "id": model, "name": names.get(model, model), "recorded": len(attempts),
            "planned": planned_each if model in declared else 0,
            "passed": len(successful), "failed": len(failed),
            "infrastructure": sum(measures.is_infrastructure(row) for row in attempts),
            "ungraded": sum(measures.is_ungraded(row) and not measures.is_infrastructure(row) for row in attempts),
            "success_rate": len(successful) / len(valid) if valid else None,
            "operational_success_rate": len(successful) / len(attempts) if attempts else None,
            "timing": {"successful": _distribution(row.get("seconds") for row in successful),
                       "failed": _distribution(row.get("seconds") for row in failed),
                       "all": _distribution(row.get("seconds") for row in attempts)},
            "cost": {"total": total, "known_subtotal": subtotal, "unknown_attempts": unknown,
                     "per_success": total / len(successful) if total is not None and successful else None},
            "tools": {"calls": None if any(value is None for value in calls) else sum(calls), **tools},
            "turns": turns,
            "collateral": {"attempts": sum(value > 0 for value in collateral), "changes": sum(collateral),
                           "complete_attempts": complete_collateral, "missing_attempts": len(valid) - complete_collateral},
            "phases": {phase: _distribution(values) for phase, values in phases.items()},
            "attempts": [{"task": row["task"], "model": model, "passed": _passed(row),
                          "infrastructure": measures.is_infrastructure(row), "ungraded": measures.is_ungraded(row), "seconds": _number(row.get("seconds")),
                          "cost_usd": cost, "tool_calls": call, "termination": row.get("termination")}
                         for row, cost, call in zip(attempts, costs, calls)],
        }
    return {"version": 1, "run": job.get("id"), "order": order,
            "planned_attempts": planned_each * len(declared), "recorded_attempts": len(rows),
            "source": f"Run {job.get('id')}: {len(rows)} recorded attempts from original result rows and deduplicated events. "
                      "Descriptive only; original task revisions, no borrowed baseline. Phase samples require a declared phase; "
                      "tool errors and model turns cover observed events only. Collateral counts are a lower bound "
                      "when unexpected-change or count-violation detail is missing.",
            "setups": setups}
