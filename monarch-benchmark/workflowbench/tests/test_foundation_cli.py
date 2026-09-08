"""Public paid entry points cannot outrun unfinished foundation controls."""
import json
from types import SimpleNamespace

from wb_orchestrator import cli
from wb_results.store import Store


def test_paid_run_refuses_before_creating_result_store(tmp_path, monkeypatch, capsys):
    config = SimpleNamespace(competitors=[SimpleNamespace(harness=SimpleNamespace(kind="api"))])
    monkeypatch.setattr(cli.config, "resolve", lambda *args: config)
    database = tmp_path / "results.sqlite3"
    result = cli.main(["--db", str(database), "run", "--product", "simulated-apps", "--plan", "smoke-frontier"])
    assert result == 2
    assert not database.exists()
    assert "foundation" in capsys.readouterr().err.lower()


def test_legacy_paid_resume_refuses_without_dispatch(tmp_path, capsys):
    database = tmp_path / "results.sqlite3"
    store = Store(database)
    store.create_run("legacy", "h", "legacy", {"arms": ["claude-code"], "suite_dir": "absent",
                                               "k": 1, "timeout_s": 60})
    store.close()
    result = cli.main(["--db", str(database), "resume", "legacy"])
    assert result == 2
    assert "foundation" in capsys.readouterr().err.lower()


def test_doctor_paid_probes_are_gated(capsys):
    result = cli.main(["doctor", "--arms", "unknown-provider"])
    assert result == 2
    assert "foundation" in capsys.readouterr().err.lower()


def test_recipe_authoring_is_gated_even_with_yes(capsys):
    result = cli.main(["monarch", "recipes", "--tasks", "absent", "--yes"])
    assert result == 2
    assert "foundation" in capsys.readouterr().err.lower()


def test_budget_status_uses_durable_ledger_and_discloses_unknown_history(tmp_path, capsys):
    from wb_orchestrator.budget import BudgetLedger
    ledger = tmp_path / "budget.sqlite3"
    BudgetLedger(ledger).reserve("held", "75", scope_id="exp-1")
    result = cli.main(["budget", "status", "--ledger", str(ledger)])
    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["weekly_limit_usd"] == "300.000000"
    assert report["held_usd"] == "75.000000"
    assert report["available_usd"] == "225.000000"
    assert report["historical_billing_verified"] is False
    assert report["paid_launch_enabled"] is False
