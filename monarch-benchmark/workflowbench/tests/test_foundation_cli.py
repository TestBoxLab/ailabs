"""Public paid entry points stay behind the capability checks and the ledger (milestone M3).

API-loop competitors launch once an operator and the ledger are in place;
Monarch and native competitors are refused with the milestone that unblocks
them; `wb budget status` says which is which. The approval flow itself is
tested in tests/test_approvals.py.
"""
import json
from types import SimpleNamespace

import pytest

from wb_orchestrator import approvals, cli
from wb_results.store import Store


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("WB_OPERATOR", raising=False)


def test_paid_run_without_an_operator_refuses_before_creating_result_store(tmp_path, monkeypatch, capsys):
    config = SimpleNamespace(competitors=[SimpleNamespace(harness=SimpleNamespace(kind="api"), name="x/api")],
                             plan=SimpleNamespace(approved_by=None))
    monkeypatch.setattr(cli.config, "resolve", lambda *args: config)
    database = tmp_path / "results.sqlite3"
    result = cli.main(["--db", str(database), "--ledger", str(tmp_path / "budget.sqlite3"),
                       "run", "--product", "simulated-apps", "--plan", "smoke-frontier"])
    assert result == 2
    assert not database.exists() and not (tmp_path / "budget.sqlite3").exists()
    assert approvals.NO_OPERATOR in capsys.readouterr().err


def test_legacy_paid_resume_refuses_without_dispatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    database = tmp_path / "results.sqlite3"
    store = Store(database)
    store.create_run("legacy", "h", "legacy", {"arms": ["claude-code"], "suite_dir": "absent",
                                               "k": 1, "timeout_s": 60})
    store.close()
    result = cli.main(["--db", str(database), "--ledger", str(tmp_path / "budget.sqlite3"), "resume", "legacy"])
    assert result == 2
    err = capsys.readouterr().err
    assert "paid launch refused" in err and "recorded before product and plan files" in err


def test_doctor_paid_probes_need_an_operator(tmp_path, capsys):
    result = cli.main(["--ledger", str(tmp_path / "budget.sqlite3"), "doctor", "--arms", "unknown-provider"])
    assert result == 2
    assert approvals.NO_OPERATOR in capsys.readouterr().err
    assert not (tmp_path / "budget.sqlite3").exists()


def test_doctor_unknown_provider_with_an_operator_fails_that_probe_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    result = cli.main(["--ledger", str(tmp_path / "budget.sqlite3"), "doctor", "--arms", "unknown-provider"])
    assert result == 1
    out = capsys.readouterr().out
    assert "[FAIL] unknown-provider" in out and "unknown provider" in out


def test_recipe_authoring_is_refused_until_m5_even_with_yes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    result = cli.main(["--ledger", str(tmp_path / "budget.sqlite3"),
                       "monarch", "recipes", "--tasks", "absent", "--yes"])
    assert result == 2
    assert approvals.MONARCH_REASON in capsys.readouterr().err


def test_budget_status_uses_durable_ledger_and_discloses_the_capabilities(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(approvals, "configured_harnesses", lambda: [])
    from wb_orchestrator.budget import BudgetLedger
    ledger = tmp_path / "budget.sqlite3"
    BudgetLedger(ledger).reserve("held", "75", scope_id="exp-1")
    result = cli.main(["budget", "status", "--ledger", str(ledger)])
    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["weekly_limit_usd"] == "300.000000"
    assert report["held_usd"] == "75.000000"
    assert report["available_usd"] == "225.000000"
    assert report["historical_billing_verified"] is False and report["reconciliation"] == {}
    assert report["paid_launch_enabled"] == {"api": True, "monarch": False, "native": False}
    assert report["paid_launch_reasons"] == {"monarch": approvals.MONARCH_REASON, "native": approvals.NATIVE_REASON}


def test_budget_status_takes_the_top_level_ledger_too(tmp_path, capsys):
    from wb_orchestrator.budget import BudgetLedger
    ledger = tmp_path / "budget.sqlite3"
    BudgetLedger(ledger).reserve("held", "5", scope_id="exp-1")
    assert cli.main(["--ledger", str(ledger), "budget", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["held_usd"] == "5.000000"


def test_run_repetitions_flag_overrides_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    captured = {}
    config_obj = SimpleNamespace(
        product=SimpleNamespace(name="simulated-apps", version="1", kind="simulated",
                                data=SimpleNamespace(mutable=False)),
        competitors=[],
        plan=SimpleNamespace(name="smoke-frontier", approved_by=None, repetitions=1,
                             cost_ceiling_usd=10, mode="create-run", tasks="tasks",
                             retry_on_fail=0, attempt_cap_usd=3.0),
        tasks=[],
        tasks_dir="tasks",
        product_path="p",
        plan_path="q",
        hash="h",
        attempts_total=0,
        attempts_per_competitor=0,
        excluded_tasks={},
        monarch_kb=None,
        monarch_recipes=None,
        config_source={},
    )
    monkeypatch.setattr(cli.config, "resolve", lambda *args: config_obj)
    monkeypatch.setattr(cli.approvals, "is_paid", lambda rc: False)

    class FakeOrch:
        @classmethod
        def from_config(cls, store, rc, out, **kwargs):
            captured["rc"] = rc
            return cls()

        def run(self, run_id):
            pass

    monkeypatch.setattr(cli, "Orchestrator", FakeOrch)
    monkeypatch.setattr(cli, "_print_run_report", lambda *args: None)

    database = tmp_path / "results.sqlite3"
    result = cli.main(["--db", str(database), "run", "--product", "simulated-apps", "--plan", "smoke-frontier", "--repetitions", "4"])
    assert result == 0
    assert captured["rc"].plan.repetitions == 4


def test_run_repetitions_must_be_at_least_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    config_obj = SimpleNamespace(
        competitors=[],
        plan=SimpleNamespace(approved_by=None, repetitions=1, cost_ceiling_usd=10, mode="create-run", tasks="tasks"),
        tasks=[],
        tasks_dir="tasks",
        product_path="p",
        plan_path="q",
        hash="h",
        attempts_total=0,
        excluded_tasks={},
    )
    monkeypatch.setattr(cli.config, "resolve", lambda *args: config_obj)
    monkeypatch.setattr(cli.approvals, "is_paid", lambda rc: False)

    database = tmp_path / "results.sqlite3"
    result = cli.main(["--db", str(database), "run", "--product", "simulated-apps", "--plan", "smoke-frontier", "--repetitions", "0"])
    assert result == 2
    assert "repetitions must be at least 1" in capsys.readouterr().err

