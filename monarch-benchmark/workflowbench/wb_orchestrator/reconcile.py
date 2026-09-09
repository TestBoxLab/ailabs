"""`wb budget reconcile`: one week's provider usage against the ledger's settled total (T3.3).

Input: normalized usage rows `date,provider,usd`, exported from each provider's
console (config/README.md says how). For the named providers and one ledger
week, the provider's own total is compared with what the ledger settled for
that provider in that week (a reservation belongs to the week it was
dispatched in). Both numbers and the difference are written to
`research/reconciliation/<week>.md`; a JSON file beside it carries the same
figures for `wb budget status`. The week is `historical_billing_verified`
only when every provider with spend, in the ledger or in an export, has been
reconciled within 5 % of its own total. Unsettled holds are reported, never
released: the ledger has no path for that, by design.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from wb_arms import providers as provider_registry

TOLERANCE = Decimal("0.05")          # of the provider's own total
COLUMNS = ("date", "provider", "usd")
KNOWN_PROVIDERS = ("anthropic", "openai", "fireworks", "google", "moonshot", "zai", "monarch")


def default_dir(ledger) -> Path:
    """`research/reconciliation/` next to the canonical ledger; temporary ledgers get their own."""
    return Path(ledger.path).parent / "reconciliation"


def week_range(week: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(week)
    except ValueError as exc:
        raise ValueError(f"--week must be a date, YYYY-MM-DD; got {week!r}") from exc
    if start.weekday() != 0:
        raise ValueError(f"--week must be the week's Monday; {week} is a {start.strftime('%A')}")
    return start, start + timedelta(days=7)


def read_rows(paths) -> list[tuple[date, str, Decimal]]:
    """Every row of every file as (date, provider, usd); the header must be date,provider,usd."""
    rows: list[tuple[date, str, Decimal]] = []
    for path in paths:
        path = Path(path)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            header = tuple(name.strip().lower() for name in (reader.fieldnames or ()))
            if header[:3] != COLUMNS:
                raise ValueError(f"{path}: the header must be {','.join(COLUMNS)}; got {','.join(header) or 'nothing'}")
            for number, row in enumerate(reader, start=2):
                values = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
                if not any(values.values()):
                    continue
                try:
                    when = date.fromisoformat(values["date"][:10])
                    amount = Decimal(values["usd"].replace("$", "").replace(",", ""))
                    if not amount.is_finite() or amount < 0:
                        raise InvalidOperation
                except (KeyError, ValueError, InvalidOperation) as exc:
                    raise ValueError(f"{path}, line {number}: expected date,provider,usd with an ISO date "
                                     f"and a non-negative amount; got {row}") from exc
                provider = values.get("provider", "").lower()
                if not provider:
                    raise ValueError(f"{path}, line {number}: the provider column is empty")
                rows.append((when, provider, amount))
    return rows


def reservation_provider(metadata: dict) -> str | None:
    """The billing account a reservation belongs to, for old and new metadata shapes."""
    if metadata.get("billing_provider"):
        return str(metadata["billing_provider"]).lower()
    harness = str(metadata.get("harness") or "")
    if harness.startswith("monarch"):
        return "monarch"
    key = metadata.get("provider")
    if key in provider_registry.REGISTRY:
        return provider_registry.REGISTRY[key].family or key
    return str(key).lower() if key else None


def ledger_totals(ledger, week: str) -> dict[str, dict[str, Any]]:
    """Per provider, what the ledger settled and still holds for reservations dispatched that week."""
    totals: dict[str, dict[str, Any]] = {}
    for row in ledger.reservations():
        dispatched = datetime.fromisoformat(row.dispatched_at or row.created_at)
        if ledger.week_of(dispatched) != week:
            continue
        provider = reservation_provider(row.metadata) or "unknown"
        entry = totals.setdefault(provider, {"settled": Decimal("0"), "requests": 0, "unsettled": 0, "held": Decimal("0")})
        entry["requests"] += 1
        if row.actual_usd is None:
            entry["unsettled"] += 1
            entry["held"] += row.maximum_usd
        else:
            entry["settled"] += row.actual_usd
    return totals


def _load(path: Path, week: str) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"week_start": week, "providers": {}, "historical_billing_verified": False}


def reconcile(ledger, week: str, names: list[str], csv_paths: list[str], out_dir=None,
              now: datetime | None = None) -> dict:
    """Reconcile `names` for `week`; write <week>.json and <week>.md; return the week's state."""
    start, end = week_range(week)
    rows = read_rows(csv_paths)
    names = [name.strip().lower() for name in names if name.strip()]
    if not names:
        raise ValueError("--provider names at least one billing account")
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    totals = ledger_totals(ledger, week)
    folder = Path(out_dir) if out_dir else default_dir(ledger)
    folder.mkdir(parents=True, exist_ok=True)
    state = _load(folder / f"{week}.json", week)
    for name in names:
        provider_usd = sum((usd for when, who, usd in rows if who == name and start <= when < end), Decimal("0"))
        entry = totals.get(name, {})
        ledger_usd = entry.get("settled", Decimal("0"))
        difference = ledger_usd - provider_usd
        if provider_usd > 0:
            share = abs(difference) / provider_usd
            within = share <= TOLERANCE
        else:
            share = None
            within = ledger_usd == 0        # nothing billed: only a ledger with nothing settled agrees
        state["providers"][name] = {
            "provider_usd": str(provider_usd), "ledger_usd": str(ledger_usd), "difference_usd": str(difference),
            "difference_share": None if share is None else str(share.quantize(Decimal("0.0001"))),
            "within_tolerance": within, "requests": entry.get("requests", 0),
            "unsettled": entry.get("unsettled", 0), "held_usd": str(entry.get("held", Decimal("0"))),
            "rows": sum(1 for when, who, _ in rows if who == name and start <= when < end),
            "reconciled_at": stamp}
    with_spend = ({name for name, entry in totals.items() if entry["settled"] > 0 or entry["unsettled"] > 0}
                  | {name for name, entry in state["providers"].items() if Decimal(entry["provider_usd"]) > 0})
    not_reconciled = sorted(name for name in with_spend if name not in state["providers"])
    off = sorted(name for name in with_spend if name in state["providers"] and not state["providers"][name]["within_tolerance"])
    state["not_reconciled"] = not_reconciled
    state["outside_tolerance"] = off
    state["unsettled"] = {name: {"count": entry["unsettled"], "held_usd": str(entry["held"])}
                          for name, entry in sorted(totals.items()) if entry["unsettled"]}
    state["historical_billing_verified"] = not not_reconciled and not off
    state["ledger"] = str(ledger.path)
    state["updated_at"] = stamp
    (folder / f"{week}.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (folder / f"{week}.md").write_text(render(state), encoding="utf-8")
    state["files"] = {"markdown": str(folder / f"{week}.md"), "json": str(folder / f"{week}.json")}
    return state


def render(state: dict) -> str:
    week = state["week_start"]
    lines = [f"# Budget reconciliation, week of {week}", "",
             f"Ledger: `{state.get('ledger', '')}`. A reservation belongs to the week it was dispatched in. "
             f"Tolerance: {TOLERANCE * 100:.0f} % of the provider's own total. Updated {state.get('updated_at', '')}.",
             "", "| provider | provider usage (US$) | ledger settled (US$) | difference (US$) | difference | "
             "within tolerance | requests | reconciled at |", "|---|---|---|---|---|---|---|---|"]
    for name, entry in sorted(state["providers"].items()):
        share = entry["difference_share"]
        lines.append(f"| {name} | {Decimal(entry['provider_usd']):.6f} | {Decimal(entry['ledger_usd']):.6f} | "
                     f"{Decimal(entry['difference_usd']):+.6f} | "
                     f"{'n/a' if share is None else f'{Decimal(share) * 100:.1f} %'} | "
                     f"{'yes' if entry['within_tolerance'] else 'no'} | {entry['requests']} | {entry['reconciled_at']} |")
    lines.append("")
    if state.get("unsettled"):
        parts = [f"{name}: {v['count']} (US$ {Decimal(v['held_usd']):.2f} held)" for name, v in state["unsettled"].items()]
        lines.append("Unsettled reservations dispatched this week, whose cost the ledger does not know and "
                     "still holds at their maximum: " + "; ".join(parts) + ".")
    else:
        lines.append("Every reservation dispatched this week is settled.")
    if state.get("not_reconciled"):
        lines.append("Providers with spend and no reconciliation yet: " + ", ".join(state["not_reconciled"]) + ".")
    if state.get("outside_tolerance"):
        lines.append("Providers outside the tolerance: " + ", ".join(state["outside_tolerance"]) + ".")
    verdict = "yes" if state["historical_billing_verified"] else "no"
    lines.append("")
    lines.append(f"historical_billing_verified: {verdict}")
    return "\n".join(lines) + "\n"


def summaries(folder: Path) -> dict[str, dict]:
    """What `wb budget status` shows per week: the flag and the per-provider figures."""
    out: dict[str, dict] = {}
    if not Path(folder).is_dir():
        return out
    for path in sorted(Path(folder).glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        week = state.get("week_start") or path.stem
        out[week] = {"historical_billing_verified": bool(state.get("historical_billing_verified")),
                     "providers": {name: {"provider_usd": entry["provider_usd"], "ledger_usd": entry["ledger_usd"],
                                          "difference_usd": entry["difference_usd"],
                                          "within_tolerance": entry["within_tolerance"]}
                                   for name, entry in (state.get("providers") or {}).items()},
                     "not_reconciled": state.get("not_reconciled", []),
                     "outside_tolerance": state.get("outside_tolerance", []), "file": str(path)}
    return out


def format_result(state: dict) -> str:
    lines = [f"week {state['week_start']}: reconciliation"]
    for name, entry in sorted(state["providers"].items()):
        share = entry["difference_share"]
        lines.append(f"  {name:<10} provider US$ {Decimal(entry['provider_usd']):.6f}   ledger settled US$ "
                     f"{Decimal(entry['ledger_usd']):.6f}   difference US$ {Decimal(entry['difference_usd']):+.6f}"
                     f" ({'n/a' if share is None else f'{Decimal(share) * 100:.1f} %'}) "
                     f"{'within' if entry['within_tolerance'] else 'OUTSIDE'} {TOLERANCE * 100:.0f} %")
    for name, value in state.get("unsettled", {}).items():
        lines.append(f"  {name:<10} {value['count']} unsettled reservation(s), US$ {Decimal(value['held_usd']):.2f} held")
    if state.get("not_reconciled"):
        lines.append("  not reconciled yet: " + ", ".join(state["not_reconciled"]))
    lines.append(f"historical_billing_verified: {'yes' if state['historical_billing_verified'] else 'no'}")
    files = state.get("files", {})
    if files:
        lines.append(f"wrote {files['markdown']}")
        lines.append(f"wrote {files['json']}")
    return "\n".join(lines)
