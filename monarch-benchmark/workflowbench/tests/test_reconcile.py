"""`wb budget reconcile`: the week's provider usage against the ledger (T3.3, milestone M3).

Rows `date,provider,usd` for one week are compared with what the ledger
settled for that provider in that week; both numbers and the difference go to
research/reconciliation/<week>.md, and the week is verified only when every
provider with spend is within 5 %. `wb budget status` shows the flag per week.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from wb_orchestrator import cli, reconcile
from wb_orchestrator.budget import BudgetLedger


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)


def ledger_with_spend(tmp_path, spend: dict[str, list[str]], unsettled: dict[str, str] | None = None):
    """A ledger whose reservations were dispatched this week: settled per provider, plus open holds."""
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    n = 0
    for provider, amounts in spend.items():
        for amount in amounts:
            n += 1
            ledger.reserve(f"r{n}", "5", scope_id=f"scope-{n}", metadata={"billing_provider": provider, "harness": "api"})
            ledger.claim(f"r{n}")
            ledger.settle(f"r{n}", amount)
    for provider, maximum in (unsettled or {}).items():
        n += 1
        ledger.reserve(f"r{n}", maximum, scope_id=f"scope-{n}", metadata={"billing_provider": provider, "harness": "api"})
        ledger.claim(f"r{n}")
    return ledger


def this_week(ledger) -> str:
    return ledger.week_of(datetime.now(timezone.utc))


def rows_file(tmp_path, rows: list[tuple[str, str, str]], name="usage.csv"):
    path = tmp_path / name
    path.write_text("date,provider,usd\n" + "".join(f"{d},{p},{u}\n" for d, p, u in rows), encoding="utf-8")
    return path


def wb(tmp_path, *args):
    return cli.main(["--ledger", str(tmp_path / "budget.sqlite3"), *args])


def status(tmp_path, capsys):
    capsys.readouterr()
    assert wb(tmp_path, "budget", "status") == 0
    return json.loads(capsys.readouterr().out)


def test_a_provider_within_five_percent_verifies_the_week(tmp_path, capsys):
    ledger = ledger_with_spend(tmp_path, {"anthropic": ["1.20", "0.80"]})     # settled US$ 2.00
    week = this_week(ledger)
    usage = rows_file(tmp_path, [(week, "anthropic", "1.50"), (week, "anthropic", "0.56")])   # billed US$ 2.06
    assert wb(tmp_path, "budget", "reconcile", "--week", week, "--provider", "anthropic", "--csv", str(usage)) == 0
    out = capsys.readouterr().out
    assert "provider US$ 2.060000" in out and "ledger settled US$ 2.000000" in out
    assert "difference US$ -0.060000" in out and "within 5 %" in out
    assert "historical_billing_verified: yes" in out
    folder = tmp_path / "reconciliation"
    page = (folder / f"{week}.md").read_text(encoding="utf-8")
    assert f"# Budget reconciliation, week of {week}" in page
    assert "| anthropic | 2.060000 | 2.000000 | -0.060000 | 2.9 % | yes | 2 |" in page
    assert "historical_billing_verified: yes" in page
    state = json.loads((folder / f"{week}.json").read_text(encoding="utf-8"))
    assert state["historical_billing_verified"] is True and state["providers"]["anthropic"]["within_tolerance"] is True

    report = status(tmp_path, capsys)
    assert report["historical_billing_verified"] is True
    assert report["reconciliation"][week]["historical_billing_verified"] is True
    assert report["reconciliation"][week]["providers"]["anthropic"]["difference_usd"] == "-0.060000"


def test_a_difference_above_five_percent_is_recorded_and_leaves_the_week_unverified(tmp_path, capsys):
    ledger = ledger_with_spend(tmp_path, {"anthropic": ["2.00"]})
    week = this_week(ledger)
    usage = rows_file(tmp_path, [(week, "anthropic", "2.30")])                     # 13 % more than settled
    assert wb(tmp_path, "budget", "reconcile", "--week", week, "--provider", "anthropic", "--csv", str(usage)) == 0
    out = capsys.readouterr().out
    assert "difference US$ -0.300000 (13.0 %) OUTSIDE 5 %" in out
    assert "historical_billing_verified: no" in out
    page = (tmp_path / "reconciliation" / f"{week}.md").read_text(encoding="utf-8")
    assert "| anthropic | 2.300000 | 2.000000 | -0.300000 | 13.0 % | no |" in page
    assert "Providers outside the tolerance: anthropic." in page
    assert status(tmp_path, capsys)["historical_billing_verified"] is False


def test_every_provider_with_spend_must_be_reconciled_and_the_week_can_be_finished_later(tmp_path, capsys):
    ledger = ledger_with_spend(tmp_path, {"anthropic": ["1.00"], "openai": ["3.00"]})
    week = this_week(ledger)
    anthropic = rows_file(tmp_path, [(week, "anthropic", "1.02")], "anthropic.csv")
    assert wb(tmp_path, "budget", "reconcile", "--week", week, "--provider", "anthropic", "--csv", str(anthropic)) == 0
    out = capsys.readouterr().out
    assert "not reconciled yet: openai" in out and "historical_billing_verified: no" in out
    assert status(tmp_path, capsys)["reconciliation"][week]["not_reconciled"] == ["openai"]

    openai = rows_file(tmp_path, [(week, "openai", "2.95")], "openai.csv")
    assert wb(tmp_path, "budget", "reconcile", "--week", week, "--provider", "openai", "--csv", str(openai)) == 0
    assert "historical_billing_verified: yes" in capsys.readouterr().out
    state = json.loads((tmp_path / "reconciliation" / f"{week}.json").read_text(encoding="utf-8"))
    assert set(state["providers"]) == {"anthropic", "openai"} and state["historical_billing_verified"] is True


def test_billing_for_a_provider_the_ledger_never_settled_is_a_difference_too(tmp_path, capsys):
    ledger = ledger_with_spend(tmp_path, {"anthropic": ["1.00"]})
    week = this_week(ledger)
    usage = rows_file(tmp_path, [(week, "anthropic", "1.00"), (week, "google", "0.40")])
    assert wb(tmp_path, "budget", "reconcile", "--week", week, "--provider", "anthropic", "--provider", "google",
              "--csv", str(usage)) == 0
    out = capsys.readouterr().out
    assert "google     provider US$ 0.400000   ledger settled US$ 0.000000" in out
    assert "historical_billing_verified: no" in out


def test_unsettled_holds_and_rows_outside_the_week_are_reported_not_counted(tmp_path, capsys):
    ledger = ledger_with_spend(tmp_path, {"anthropic": ["1.00"]}, unsettled={"anthropic": "0.75"})
    week = this_week(ledger)
    usage = rows_file(tmp_path, [(week, "anthropic", "1.01"), ("2020-01-06", "anthropic", "99"),
                                 (week, "openai", "7")])
    assert wb(tmp_path, "budget", "reconcile", "--week", week, "--provider", "anthropic", "--csv", str(usage)) == 0
    out = capsys.readouterr().out
    assert "provider US$ 1.010000" in out and "1 unsettled reservation(s), US$ 0.75 held" in out
    page = (tmp_path / "reconciliation" / f"{week}.md").read_text(encoding="utf-8")
    assert "Unsettled reservations dispatched this week" in page and "anthropic: 1 (US$ 0.75 held)" in page
    assert "historical_billing_verified: yes" in page          # within tolerance; the hold is disclosed, not released


def test_bad_inputs_are_refused_with_exit_2(tmp_path, capsys):
    BudgetLedger(tmp_path / "budget.sqlite3")
    usage = rows_file(tmp_path, [("2026-09-08", "anthropic", "1")])
    assert wb(tmp_path, "budget", "reconcile", "--week", "2026-09-08", "--provider", "anthropic", "--csv", str(usage)) == 2
    assert "Monday" in capsys.readouterr().err
    bad = tmp_path / "bad.csv"
    bad.write_text("day,vendor,amount\n2026-09-08,anthropic,1\n", encoding="utf-8")
    assert wb(tmp_path, "budget", "reconcile", "--week", "2026-09-07", "--provider", "anthropic", "--csv", str(bad)) == 2
    assert "date,provider,usd" in capsys.readouterr().err
    worse = tmp_path / "worse.csv"
    worse.write_text("date,provider,usd\n2026-09-08,anthropic,lots\n", encoding="utf-8")
    assert wb(tmp_path, "budget", "reconcile", "--week", "2026-09-07", "--provider", "anthropic", "--csv", str(worse)) == 2
    assert "line 2" in capsys.readouterr().err
    assert not (tmp_path / "reconciliation").exists()


def test_reservation_provider_reads_every_metadata_shape():
    assert reconcile.reservation_provider({"billing_provider": "mock", "provider": "mock"}) == "mock"
    assert reconcile.reservation_provider({"provider": "claude-opus-5", "harness": "api-control"}) == "anthropic"
    assert reconcile.reservation_provider({"provider": "kimi-k3-fireworks", "harness": "api-control"}) == "fireworks"
    assert reconcile.reservation_provider({"harness": "monarch-enterprise", "version": "monarch@abc"}) == "monarch"
    assert reconcile.reservation_provider({}) is None


def test_reconcile_attributes_a_reservation_to_the_week_it_was_dispatched_in(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    monday = datetime(2026, 9, 7, 3, tzinfo=timezone.utc)
    later = datetime(2026, 9, 15, 3, tzinfo=timezone.utc)           # settled the week after
    ledger.reserve("old", "5", scope_id="s", metadata={"billing_provider": "anthropic"}, now=monday)
    ledger.claim("old", now=monday)
    ledger.settle("old", "1.00", now=later)
    assert reconcile.ledger_totals(ledger, "2026-09-07")["anthropic"]["settled"] == Decimal("1.00")
    assert reconcile.ledger_totals(ledger, "2026-09-14") == {}
