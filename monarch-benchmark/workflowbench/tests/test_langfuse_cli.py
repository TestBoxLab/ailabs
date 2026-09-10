import json
import sqlite3

from wb_orchestrator.cli import main
from wb_orchestrator.budget import BudgetLedger
from tests.test_langfuse_export import receiver


def test_status_is_read_only_and_flush_is_explicit(tmp_path, capsys, monkeypatch):
    ledger = tmp_path / "budget.sqlite3"
    results = tmp_path / "results.sqlite3"
    args = ["--ledger", str(ledger), "--db", str(results), "telemetry"]
    assert main([*args, "status"]) == 0
    assert not ledger.exists() and not results.exists()
    capsys.readouterr()
    budget = BudgetLedger(ledger)
    budget.reserve("request", "1", scope_id="run", scope_limit_usd="2")
    budget.claim("request")
    budget.settle("request", ".25")
    before = budget.status()
    # Simulate history recorded before telemetry was installed.
    with sqlite3.connect(ledger) as db:
        db.execute("DELETE FROM telemetry_outbox")
    assert main([*args, "backfill"]) == 0
    assert json.loads(capsys.readouterr().out)["ledger"]["pending"] == 2
    with receiver() as (captured, env):
        monkeypatch.setenv("WB_LANGFUSE_ENABLED", "1")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        assert main([*args, "flush"]) == 0
    assert json.loads(capsys.readouterr().out)["ledger"]["pending"] == 0
    assert captured
    assert budget.status() == before
    assert not results.exists()
