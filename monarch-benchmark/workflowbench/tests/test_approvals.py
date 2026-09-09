"""The approval flow and the capability checks of paid launches (decision D5, milestone M3).

The launcher is `WB_OPERATOR`. An approver's launch runs at once under an
approved record; anyone else's launch creates a pending request and waits for
`wb approve <id>`, after which `wb run --request <id>` runs it while the config
hash still matches. Smoke scale needs no record. Monarch and native
competitors stay refused with the exact reason until their milestones land.
Mock provider only; temporary ledgers and result stores.
"""
from __future__ import annotations

import json

import pytest

from tests.monarch_helpers import KB, MONARCH_ENV, monarch_site, repo  # noqa: F401  (repo is a fixture)
from tests.test_config import edit, site, write  # noqa: F401  (site is a fixture)
from tests.test_paid_dispatch import mock_plan
from wb_orchestrator import approvals, cli
from wb_orchestrator.budget import BudgetLedger
from wb_results.store import Store


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    """No .env, no operator, the default approvers: every test says who launches."""
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("WB_OPERATOR", raising=False)
    monkeypatch.delenv("WB_APPROVERS", raising=False)
    monkeypatch.delenv("MONARCH_ATTEMPT_CEILING_USD", raising=False)


def wb(tmp_path, *args):
    return cli.main(["--db", str(tmp_path / "wb.sqlite3"), "--out", str(tmp_path / "out"),
                     "--ledger", str(tmp_path / "budget.sqlite3"), *args])


def run_args(site):
    return ["run", "--product", str(site / "config/products/simulated-apps.yaml"),
            "--plan", str(site / "config/plans/smoke-frontier.yaml")]


def big_plan(site, **kw):
    """Above smoke scale: 2 prompts x 11 repetitions = 22 attempts per competitor."""
    return mock_plan(site, repetitions=11, **kw)


def requests(tmp_path):
    return Store(tmp_path / "wb.sqlite3").approval_requests()


# -- the identity ------------------------------------------------------------------

def test_the_approvers_default_to_lucas_and_can_be_overridden():
    assert approvals.approvers({}) == ("lucas",)
    assert approvals.approvers({"WB_APPROVERS": "carlos, Alex,"}) == ("carlos", "alex")
    assert approvals.is_approver("Lucas", {}) and not approvals.is_approver("carlos", {})
    assert approvals.operator({"WB_OPERATOR": "  Carlos "}) == "carlos"
    assert approvals.operator({}) is None and approvals.operator({"WB_OPERATOR": " "}) is None


def test_a_paid_launch_without_an_operator_is_refused_before_anything_is_created(site, tmp_path, mock_server, capsys):
    big_plan(site)
    assert wb(tmp_path, *run_args(site)) == 2
    assert approvals.NO_OPERATOR in capsys.readouterr().err
    assert not (tmp_path / "wb.sqlite3").exists() and not (tmp_path / "budget.sqlite3").exists()
    assert mock_server.request_count == 0


def test_a_scripted_only_plan_needs_no_operator_and_no_ledger(site, tmp_path, capsys):
    mock_plan(site, competitors="  - {harness: oracle}\n")
    plan = (site / "config/plans/smoke-frontier.yaml").read_text().replace("baseline: mock/api", "baseline: oracle")
    write(site / "config/plans", plan)
    assert wb(tmp_path, *run_args(site)) == 0
    assert not (tmp_path / "budget.sqlite3").exists()


# -- decision D5 -----------------------------------------------------------------------

def test_an_approver_launch_runs_at_once_under_an_approved_record(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    big_plan(site)
    assert wb(tmp_path, *run_args(site)) == 0
    out = capsys.readouterr().out
    (record,) = requests(tmp_path)
    assert record["status"] == "approved" and record["requested_by"] == "lucas" and record["decided_by"] == "lucas"
    assert record["plan_name"] == "smoke-frontier" and record["attempts_total"] == 22 and record["ceiling_usd"] == 5.0
    assert record["run_id"] and f"approval {record['id']}" in out
    store = Store(tmp_path / "wb.sqlite3")
    assert len(store.episodes(run=record["run_id"])["rows"]) == 22
    config = json.loads(store.run(record["run_id"])["config_json"])
    assert config["launched_by"] == "lucas" and config["approval_request"] == record["id"]
    assert record["config_hash"] == store.run(record["run_id"])["config_hash"]
    assert BudgetLedger(tmp_path / "budget.sqlite3").status().actual_usd > 0


def test_a_non_approver_launch_creates_a_pending_request_and_waits(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    big_plan(site)
    assert wb(tmp_path, *run_args(site)) == 0
    out = capsys.readouterr().out
    (record,) = requests(tmp_path)
    assert record["status"] == "pending" and record["requested_by"] == "carlos"
    assert record["decided_by"] is None and record["run_id"] is None
    assert f"{record['id']} awaiting approval" in out and "wb approve " + record["id"] in out
    assert Store(tmp_path / "wb.sqlite3").runs() == [] and mock_server.request_count == 0


def test_approve_then_run_with_the_request(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    big_plan(site)
    wb(tmp_path, *run_args(site))
    (record,) = requests(tmp_path)
    request = record["id"]

    assert wb(tmp_path, "approve", request) == 2                       # carlos is not an approver
    assert "carlos is not an approver" in capsys.readouterr().err
    assert requests(tmp_path)[0]["status"] == "pending"

    monkeypatch.setenv("WB_OPERATOR", "lucas")
    assert wb(tmp_path, "approve", request) == 0
    (record,) = requests(tmp_path)
    assert record["status"] == "approved" and record["decided_by"] == "lucas" and record["decided_at"]

    monkeypatch.setenv("WB_OPERATOR", "carlos")                        # any operator may run an approved request
    assert wb(tmp_path, *run_args(site), "--request", request) == 0
    (record,) = requests(tmp_path)
    assert record["run_id"] and len(Store(tmp_path / "wb.sqlite3").episodes(run=record["run_id"])["rows"]) == 22
    config = json.loads(Store(tmp_path / "wb.sqlite3").run(record["run_id"])["config_json"])
    assert config["launched_by"] == "carlos" and config["approval_request"] == request

    capsys.readouterr()
    assert wb(tmp_path, *run_args(site), "--request", request) == 2    # single use
    assert "already ran" in capsys.readouterr().err


def test_a_request_whose_config_drifted_is_refused(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    big_plan(site)
    wb(tmp_path, *run_args(site))
    request = requests(tmp_path)[0]["id"]
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    wb(tmp_path, "approve", request)
    plan = site / "config/plans/smoke-frontier.yaml"
    plan.write_text(edit(plan.read_text(), "timeout_s", "601"))       # a different measurement
    capsys.readouterr()
    assert wb(tmp_path, *run_args(site), "--request", request) == 2
    err = capsys.readouterr().err
    assert "config" in err and request in err
    assert requests(tmp_path)[0]["run_id"] is None and mock_server.request_count == 0


def test_deny_and_unknown_and_pending_requests_are_refused(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    big_plan(site)
    wb(tmp_path, *run_args(site))
    request = requests(tmp_path)[0]["id"]
    capsys.readouterr()
    assert wb(tmp_path, *run_args(site), "--request", request) == 2
    assert "is pending, not approved" in capsys.readouterr().err
    assert wb(tmp_path, *run_args(site), "--request", "apr-nope") == 2
    assert "unknown approval request apr-nope" in capsys.readouterr().err

    monkeypatch.setenv("WB_OPERATOR", "lucas")
    assert wb(tmp_path, "deny", request) == 0
    assert requests(tmp_path)[0]["status"] == "denied"
    assert wb(tmp_path, "approve", request) == 2                       # a decided request stays decided
    assert "already denied" in capsys.readouterr().err
    assert wb(tmp_path, *run_args(site), "--request", request) == 2
    assert "is denied, not approved" in capsys.readouterr().err
    assert mock_server.request_count == 0


def test_wb_approvals_lists_every_request(site, tmp_path, mock_server, monkeypatch, capsys):
    assert wb(tmp_path, "approvals") == 0
    assert "no approval requests" in capsys.readouterr().out
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    big_plan(site)
    wb(tmp_path, *run_args(site))
    request = requests(tmp_path)[0]["id"]
    capsys.readouterr()
    assert wb(tmp_path, "approvals") == 0
    out = capsys.readouterr().out
    assert request in out and "pending" in out and "carlos" in out and "smoke-frontier" in out and "22" in out


def test_smoke_scale_runs_without_a_record_but_through_the_ledger(site, tmp_path, mock_server, monkeypatch):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    mock_plan(site, repetitions=1)                                     # 2 attempts per competitor
    assert wb(tmp_path, *run_args(site)) == 0
    assert requests(tmp_path) == []
    assert len(Store(tmp_path / "wb.sqlite3").runs()) == 1
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    assert ledger.status().actual_usd > 0 and len(ledger.reservations()) == mock_server.request_count


def test_wb_approvers_overrides_who_approves(site, tmp_path, mock_server, monkeypatch):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    monkeypatch.setenv("WB_APPROVERS", "carlos,alex")
    big_plan(site)
    assert wb(tmp_path, *run_args(site)) == 0
    (record,) = requests(tmp_path)
    assert record["status"] == "approved" and record["decided_by"] == "carlos" and record["run_id"]


def test_approved_by_in_the_plan_file_is_ignored_with_a_notice(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    big_plan(site)
    plan = site / "config/plans/smoke-frontier.yaml"
    plan.write_text(edit(plan.read_text(), "approved_by", "carlos"))
    assert wb(tmp_path, *run_args(site)) == 0
    out = capsys.readouterr().out
    assert "approved_by" in out and "ignored" in out
    assert requests(tmp_path)[0]["status"] == "pending"                # the file's word approves nothing


def test_the_launch_notice_names_the_operator_and_the_cap(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    mock_plan(site, "attempt_cap_usd: 1.5\n", repetitions=1)
    assert wb(tmp_path, *run_args(site)) == 0
    out = capsys.readouterr().out
    assert "ceiling   US$ 5.00   attempt cap US$ 1.50" in out
    assert "launched by lucas (approver)" in out


# -- resume ---------------------------------------------------------------------------

def test_resume_of_a_paid_run_needs_the_operator_and_keeps_the_ledger(site, tmp_path, mock_server, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    mock_plan(site, repetitions=1)
    from wb_orchestrator import orchestrator as orch_mod
    original = orch_mod.Orchestrator.from_config

    def one_attempt(*args, **kwargs):
        orch = original(*args, **kwargs)
        orch._stop_after = 1
        return orch
    monkeypatch.setattr(orch_mod.Orchestrator, "from_config", one_attempt)
    monkeypatch.setattr(cli.Orchestrator, "from_config", one_attempt)
    assert wb(tmp_path, *run_args(site)) == 1                          # killed after one attempt
    (run,) = Store(tmp_path / "wb.sqlite3").runs()
    monkeypatch.setattr(orch_mod.Orchestrator, "from_config", original)
    monkeypatch.setattr(cli.Orchestrator, "from_config", original)
    before = len(BudgetLedger(tmp_path / "budget.sqlite3").reservations())

    monkeypatch.delenv("WB_OPERATOR")
    assert wb(tmp_path, "resume", run["run_id"]) == 2
    assert approvals.NO_OPERATOR in capsys.readouterr().err
    monkeypatch.setenv("WB_OPERATOR", "carlos")
    assert wb(tmp_path, "resume", run["run_id"]) == 0
    assert len(Store(tmp_path / "wb.sqlite3").episodes(run=run["run_id"])["rows"]) == 2
    assert len(BudgetLedger(tmp_path / "budget.sqlite3").reservations()) > before


# -- capability checks: what may launch today -------------------------------------------

def test_the_capability_matrix_names_the_pending_milestones():
    assert approvals.capabilities() == {"api": None, "monarch": approvals.MONARCH_REASON,
                                        "native": approvals.NATIVE_REASON}
    assert approvals.MONARCH_REASON == "Monarch instance not verified: milestone M5"
    assert approvals.NATIVE_REASON == "native runtime not verified: milestone M7"


def test_a_monarch_competitor_is_refused_with_the_m5_reason(site, tmp_path, repo, monkeypatch, capsys):
    for key, value in MONARCH_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    monarch_site(site, monarch_repo=str(repo))
    assert wb(tmp_path, *run_args(site)) == 2
    err = capsys.readouterr().err
    assert approvals.MONARCH_REASON in err
    assert not (tmp_path / "wb.sqlite3").exists()


def test_a_claude_code_competitor_is_refused_with_the_m7_reason(site, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-placeholder")
    mock_plan(site, competitors="  - {model: claude-opus-4-8, harness: claude-code}\n")
    plan = site / "config/plans/smoke-frontier.yaml"
    plan.write_text(plan.read_text().replace("baseline: mock/api", "baseline: claude-opus-4-8/claude-code"))
    assert wb(tmp_path, *run_args(site)) == 2
    assert approvals.NATIVE_REASON in capsys.readouterr().err


def test_a_missing_operator_is_reported_before_the_milestone_reasons(site, tmp_path, repo, monkeypatch, capsys):
    for key, value in MONARCH_ENV.items():
        monkeypatch.setenv(key, value)
    monarch_site(site, monarch_repo=str(repo))
    assert wb(tmp_path, *run_args(site)) == 2
    err = capsys.readouterr().err
    assert err.index(approvals.NO_OPERATOR) < err.index(approvals.MONARCH_REASON)


def test_monarch_recipes_stays_refused_with_the_m5_reason(site, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    assert wb(tmp_path, "monarch", "recipes", "--tasks", str(site / "tasks"), "--yes") == 2
    assert approvals.MONARCH_REASON in capsys.readouterr().err


def test_the_doctor_monarch_probe_is_refused_with_the_m5_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WB_OPERATOR", "lucas")
    assert wb(tmp_path, "doctor", "--arms", "monarch", "--monarch-probe") == 2
    assert approvals.MONARCH_REASON in capsys.readouterr().err


def test_doctor_probes_need_the_operator_and_reserve_every_request(tmp_path, mock_server, monkeypatch, capsys):
    assert wb(tmp_path, "doctor", "--arms", "mock") == 2
    assert approvals.NO_OPERATOR in capsys.readouterr().err
    assert mock_server.request_count == 0

    monkeypatch.setenv("WB_OPERATOR", "carlos")
    assert wb(tmp_path, "doctor", "--arms", "mock") == 0
    out = capsys.readouterr().out
    assert "[OK ] mock" in out and "reservations: 4" in out
    rows = BudgetLedger(tmp_path / "budget.sqlite3").reservations()
    assert len(rows) == mock_server.request_count == 4
    assert all(r.actual_usd is not None and r.metadata["harness"] == "doctor" for r in rows)
    assert all(r.metadata["operator"] == "carlos" and r.metadata["billing_provider"] == "mock" for r in rows)


def test_doctor_offline_monarch_checks_need_nothing(tmp_path, capsys):
    """`--arms monarch` without the probe spends nothing, so it needs no operator."""
    assert wb(tmp_path, "doctor", "--arms", "monarch") in (0, 1)
    assert not (tmp_path / "budget.sqlite3").exists()



# -- M5: a fresh, passing verification admits the Monarch competitor ----------------------

def _write_probe(tmp_path, monkeypatch, **overrides):
    import json
    from datetime import datetime, timezone
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "data"))
    folder = tmp_path / "data" / "studio"
    folder.mkdir(parents=True, exist_ok=True)
    record = {"checked_at": datetime.now(timezone.utc).isoformat(), "ok": True,
              "backend_host": "127.0.0.1:4174", "version": "monarch@abc1234",
              "checks": [{"name": "backend", "ok": True, "detail": "200"}]}
    record.update(overrides)
    (folder / "enterprise-probe.json").write_text(json.dumps(record), encoding="utf-8")


def test_monarch_competitor_is_admitted_by_a_fresh_passing_verification_of_its_instance(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "data"))
    harness = SimpleNamespace(kind="monarch", base_url="${MONARCH_URL}")
    env = {"MONARCH_URL": "http://127.0.0.1:4174"}
    missing = approvals.competitor_reason(harness, env)
    assert missing.startswith(approvals.MONARCH_REASON) and "wb monarch verify" in missing
    _write_probe(tmp_path, monkeypatch)
    assert approvals.competitor_reason(harness, env) is None
    _write_probe(tmp_path, monkeypatch, backend_host="other.example:4174")
    assert "other.example:4174" in approvals.competitor_reason(harness, env)
    _write_probe(tmp_path, monkeypatch, ok=False, checks=[{"name": "session", "ok": False, "detail": "401"}])
    assert "session" in approvals.competitor_reason(harness, env)
    _write_probe(tmp_path, monkeypatch, checked_at=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat())
    assert "older than 2 hours" in approvals.competitor_reason(harness, env)
    assert approvals.competitor_reason(SimpleNamespace(kind="monarch", base_url="${UNSET_URL}"), {}).startswith(approvals.MONARCH_REASON)


def test_wb_monarch_verify_prints_every_check_and_exits_on_the_verdict(tmp_path, monkeypatch, capsys):
    from wb_orchestrator.cli import main
    from wb_studio import enterprise
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "data"))
    passing = {"ok": True, "version": "monarch@abc1234", "front_door": "https://studio.example/front-door",
               "checks": [{"name": "backend", "ok": True, "detail": "200"}, {"name": "session", "ok": True, "detail": "logged in"}]}
    monkeypatch.setattr(enterprise, "verify", lambda studio: passing)
    assert main(["monarch", "verify"]) == 0
    out = capsys.readouterr().out
    assert "[OK ] backend: 200" in out and "monarch@abc1234" in out and "may launch" in out
    failing = {**passing, "ok": False, "checks": [{"name": "knowledge_base", "ok": False, "detail": "bench-gmail drifted"}]}
    monkeypatch.setattr(enterprise, "verify", lambda studio: failing)
    assert main(["monarch", "verify"]) == 1
    captured = capsys.readouterr()
    assert "[NO ] knowledge_base: bench-gmail drifted" in captured.out and "stay refused" in captured.err
