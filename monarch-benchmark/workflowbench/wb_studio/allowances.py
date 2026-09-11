"""Named weekly allowances inside the one lab week.

The ledger authorises US$300 a week (`AUTHORIZED_WEEKLY_MICROUSD`) and nothing
here raises that. An allowance is a smaller weekly ceiling for one kind of work,
so research cannot quietly eat the week a round needs. It is a gate checked
before a reservation, never a second pot of money: every dollar still passes
through the one ledger and one `wb budget reconcile`.

An allowance nobody set is uncapped — that work draws on whatever the week has
left. Only Genesis starts with a value, migrated from the envelope of feature
022 lane B the first time this module is read.
"""
from __future__ import annotations

import json
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path

# The kinds of work a person budgets separately, and how the Budget page names them.
KINDS = {
    "genesis": "Genesis research",
    "analysis": "Run readings",
    "rounds": "Benchmark rounds",
}
# Genesis is the one that spends on its own, so it starts capped and cannot be
# uncapped — clearing its field restores this, it never removes the ceiling.
# The value is the envelope default Lucas set on 10 Sep 2026.
DEFAULTS = {"genesis": "25.00"}
LAB_WEEK_USD = Decimal("300")
_LOCK = threading.RLock()


def _path(studio) -> Path:
    return Path(studio.directory) / "allowances.json"


def _migrated(studio) -> dict:
    """The Genesis envelope a person set before allowances existed, so their
    number survives the change rather than silently reverting to a default."""
    try:
        data = json.loads((Path(studio.directory) / "genesis" / "people.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {}
    envelope = data.get("envelope_usd") if isinstance(data, dict) else None
    if envelope is None:
        return {}
    try:
        return {"genesis": f"{Decimal(str(envelope)):.2f}"}
    except (InvalidOperation, ValueError):
        return {}


def limits(studio) -> dict:
    """Every allowance in force, as {kind: '25.00'}. A kind that is absent here
    is uncapped and draws on whatever the lab week has left."""
    with _LOCK:
        try:
            data = json.loads(_path(studio).read_text(encoding="utf8"))
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            data = _migrated(studio)
            if data:
                _write(studio, data)
        return {**DEFAULTS, **{k: v for k, v in data.items() if k in KINDS}}


def _write(studio, data: dict) -> None:
    _path(studio).parent.mkdir(parents=True, exist_ok=True)
    _path(studio).write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf8", newline="\n")


def set_limit(studio, kind: str, usd) -> dict:
    """Set or clear one allowance. An empty value clears it: back to uncapped for
    a kind with no default, and back to the default for one that has it."""
    if kind not in KINDS:
        raise ValueError("Name one of: " + ", ".join(sorted(KINDS)))
    with _LOCK:
        data = {k: v for k, v in limits(studio).items() if DEFAULTS.get(k) != v}
        if usd is None or str(usd).strip() == "":
            data.pop(kind, None)
        else:
            try:
                value = Decimal(str(usd))
            except (InvalidOperation, ValueError):
                raise ValueError("An allowance is an amount in dollars, like 25.00.")
            if value < 0 or value > LAB_WEEK_USD:
                raise ValueError(f"An allowance stays between $0 and the lab week of ${LAB_WEEK_USD:.0f}.")
            data[kind] = f"{value:.2f}"
        _write(studio, data)
        return data


def kind_of(line: dict) -> str:
    """Which allowance a ledger line counts against.

    `allowance` is the money fact, set where the reservation is read. `who` is a
    display fact — who asked for the work — and deciding the first from the second
    was a defect: `usage.who` maps a conversation turn's `by='person'` to
    'Studio user', so a person's Genesis turn counted against benchmark rounds and
    the research allowance never saw it (feature 024, FR-005).

    A line written before this field existed still counts by its name, so history
    keeps the meaning it had when it was recorded.
    """
    named = line.get("allowance")
    if named in KINDS:
        return named
    if line.get("who") == "Genesis":
        return "genesis"
    if str(line.get("what") or "") == "post-run-analysis":
        return "analysis"
    return "rounds"


def _spent(lines, kind) -> tuple:
    """(held, settled) this week for one kind: an open reservation is held at its
    ceiling, a settled one counts what it actually cost."""
    held = settled = Decimal("0")
    for line in lines:
        if kind_of(line) != kind:
            continue
        if line.get("actual_usd") is not None:
            settled += Decimal(str(line["actual_usd"]))
        elif line.get("state") == "open":
            held += Decimal(str(line["maximum_usd"]))
    return held, settled


def state(studio, kind: str, lines=None) -> dict:
    """What one allowance holds this week. `limit_usd` and `left_usd` are None
    when nobody set a ceiling; that work is bounded by the lab week alone."""
    if lines is None:
        from wb_studio.usage import ledger_lines
        lines = ledger_lines(studio)["lines"]
    held, settled = _spent(lines, kind)
    limit = limits(studio).get(kind)
    left = None if limit is None else max(Decimal("0"), Decimal(limit) - held - settled)
    return {"kind": kind, "label": KINDS.get(kind, kind),
            "limit_usd": None if limit is None else f"{Decimal(limit):.2f}",
            "held_usd": f"{held:.2f}", "settled_usd": f"{settled:.2f}",
            "left_usd": None if left is None else f"{left:.2f}"}


def states(studio) -> list:
    """Every allowance, for the Budget page; one read of the ledger for all of them."""
    from wb_studio.usage import ledger_lines
    lines = ledger_lines(studio)["lines"]
    return [state(studio, kind, lines) for kind in KINDS]


def allows(studio, kind: str, amount, lines=None) -> tuple:
    """(ok, reason): whether `kind` can still spend `amount` this week.

    A ledger that cannot be read never blocks work; the weekly limit in the
    ledger itself is the gate that must not be bypassed, and it still applies.
    """
    try:
        current = state(studio, kind, lines=lines)
    except Exception:
        return True, None
    if current["left_usd"] is None:
        return True, None
    try:
        wanted = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return True, None
    left = Decimal(current["left_usd"])
    if left < wanted:
        return False, (f"The weekly allowance for {current['label'].lower()} cannot cover ${wanted:.2f}: "
                       f"${left:.2f} left of ${Decimal(current['limit_usd']):.2f}. "
                       "Raise it on the Budget page, or wait for the week to reset.")
    return True, None
