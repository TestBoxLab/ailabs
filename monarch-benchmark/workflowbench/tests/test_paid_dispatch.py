"""Paid dispatch through the weekly ledger (unblock plan of 8 Sep, milestone M3).

Every provider request of the CLI's API loop is one reservation: reserved for
its rate-card maximum, claimed, sent, settled from the usage receipt. An
unreadable receipt keeps the hold. The attempt cap ends an attempt as
infrastructure, the exhausted week stops the run resumably, and round
admission refuses a round the week cannot cover, naming the shortfall.
Mock providers only; temporary ledgers with small weekly limits.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_config import edit, site, write  # noqa: F401  (site is a fixture)
from tests.test_run_config import mock_model
from wb_arms.api_loop import ApiLoopArm, InfraError
from wb_orchestrator import config
from wb_orchestrator.budget import BudgetLedger
from wb_orchestrator.orchestrator import Orchestrator, RoundAdmissionError, RunKilled
from wb_results.store import Store
from wb_world.episode import Episode, load_task_file

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks/simple.email_sf_contact_city_update.json"


def episode(tmp_path, eid="run-1/simple.email_sf_contact_city_update/mock_api/t0", journal="attempt-000"):
    ep = Episode(load_task_file(TASK), episode_id=eid)
    ep.attach_journal(tmp_path / "evidence" / journal)
    return ep


class Adapter:
    """A scripted provider: one final answer, with whatever receipt the test asks for."""

    def __init__(self, receipt=None, fail=None):
        self.receipt = receipt if receipt is not None else {
            "prompt_tokens": 1000, "cached_tokens": 200, "cache_write_tokens": 100, "output_tokens": 50}
        self.fail = fail
        self.calls = 0

    def start(self, system, brief):
        return [{"role": "user", "content": brief}]

    def turn(self, messages, timeout=None):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        messages.append({"role": "assistant", "content": "done"})
        return {"text": "done", "tool_calls": [], "cache_source": "usage", **self.receipt}

    def append_tool_result(self, messages, call, result):
        messages.append({"role": "tool", "content": result})


def scripted_arm(monkeypatch, ledger, adapter, provider="gpt-5.6-sol", **kw):
    arm = ApiLoopArm(provider, ledger=ledger, **kw)
    monkeypatch.setattr(arm, "_adapter", lambda: adapter)
    return arm


# -- one request, one reservation ----------------------------------------------------

def test_api_loop_reserves_claims_and_settles_every_request(tmp_path, mock_server):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    arm = ApiLoopArm("mock", ledger=ledger)
    ep = episode(tmp_path)
    result = arm.run(ep)
    assert result.termination == "completed" and result.turns == 2

    rows = ledger.reservations()
    eid = "run-1/simple.email_sf_contact_city_update/mock_api/t0"
    assert [r.reservation_id for r in rows] == [f"{eid}#attempt-000#r0", f"{eid}#attempt-000#r1"]
    for row in rows:
        assert row.scope_id == eid
        assert row.dispatched_at is not None and row.actual_usd is not None
        assert row.metadata["billing_provider"] == "mock" and row.metadata["harness"] == "api"
        assert row.metadata["model"] == "mock-1" and row.metadata["turn"] in (0, 1)
        assert Decimal("0") < row.actual_usd < row.maximum_usd
    status = ledger.status()
    assert status.held_usd == 0
    # settled per request (each rounded up to a millionth) against the row's own arithmetic
    assert abs(float(status.actual_usd) - result.cost_usd) < 1e-5
    assert result.turn_log[0]["billing"]["reservation_id"] == rows[0].reservation_id
    assert result.turn_log[0]["billing"]["status"] == "estimated_from_usage"


def test_without_a_ledger_the_loop_runs_as_before(tmp_path, mock_server):
    result = ApiLoopArm("mock").run(episode(tmp_path))
    assert result.termination == "completed" and "billing" not in result.turn_log[0]


def test_an_unreadable_receipt_settles_as_unknown_and_keeps_the_hold(tmp_path, monkeypatch):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    adapter = Adapter(receipt={"prompt_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0})
    arm = scripted_arm(monkeypatch, ledger, adapter)
    result = arm.run(episode(tmp_path))
    (row,) = ledger.reservations()
    assert row.dispatched_at is not None and row.actual_usd is None
    assert ledger.status().held_usd == row.maximum_usd > 0
    assert result.turn_log[0]["billing"]["status"] == "unknown_hold"
    assert "billing=unknown" in result.flags


def test_a_provider_failure_after_the_claim_keeps_the_hold(tmp_path, monkeypatch):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    boom = InfraError("infra:rate_limit", "429 from https://api.example/v1?key=sk-secret", retry_after=0.0)
    arm = scripted_arm(monkeypatch, ledger, Adapter(fail=boom))
    with pytest.raises(InfraError) as caught:
        arm.run(episode(tmp_path))
    assert caught.value.kind == "infra:rate_limit"
    (row,) = ledger.reservations()
    assert row.dispatched_at is not None and row.actual_usd is None
    assert ledger.status().held_usd == row.maximum_usd > 0


def test_a_crash_inside_the_provider_call_keeps_the_hold(tmp_path, monkeypatch):
    """A crash between claim and receipt (a killed process looks the same to the
    ledger): the reservation is dispatched, never settled, and stays held."""
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    arm = scripted_arm(monkeypatch, ledger, Adapter(fail=RuntimeError("process died mid-request")))
    with pytest.raises(RuntimeError):
        arm.run(episode(tmp_path))
    (row,) = ledger.reservations()
    assert row.dispatched_at is not None and row.actual_usd is None
    assert BudgetLedger(tmp_path / "budget.sqlite3").status().held_usd == row.maximum_usd


def test_a_second_invocation_of_the_same_attempt_gets_new_reservation_ids(tmp_path, monkeypatch):
    """An infra retry or a resume runs the attempt again under its own evidence
    index: the ids differ, so nothing is reserved twice and nothing is reused."""
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    arm = scripted_arm(monkeypatch, ledger, Adapter())
    arm.run(episode(tmp_path, journal="attempt-000"))
    arm.run(episode(tmp_path, journal="attempt-001"))
    ids = [r.reservation_id for r in ledger.reservations()]
    assert ids == ["run-1/simple.email_sf_contact_city_update/mock_api/t0#attempt-000#r0",
                   "run-1/simple.email_sf_contact_city_update/mock_api/t0#attempt-001#r0"]


# -- the attempt cap ---------------------------------------------------------------

def test_attempt_cap_refuses_the_request_before_any_reservation(tmp_path, mock_server):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    arm = ApiLoopArm("mock", ledger=ledger, attempt_cap_usd=0.01)   # below one request's maximum
    with pytest.raises(InfraError) as caught:
        arm.run(episode(tmp_path))
    assert caught.value.kind == "infra:attempt_cap" and caught.value.retryable is False
    assert "attempt cap US$ 0.01" in str(caught.value)
    assert mock_server.request_count == 0 and ledger.reservations() == []
    assert caught.value.partial.termination == "infra:attempt_cap"


def test_attempt_cap_counts_what_the_attempt_already_settled(tmp_path, mock_server):
    """The cap is per attempt across its invocations: spend an earlier
    invocation settled under the same identity counts against the next request."""
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    eid = "run-1/simple.email_sf_contact_city_update/mock_api/t0"
    ledger.reserve(f"{eid}#attempt-000#r0", "3", scope_id=eid)
    ledger.settle(f"{eid}#attempt-000#r0", "2.99")
    arm = ApiLoopArm("mock", ledger=ledger, attempt_cap_usd=3.0)
    with pytest.raises(InfraError) as caught:
        arm.run(episode(tmp_path, journal="attempt-001"))
    assert caught.value.kind == "infra:attempt_cap"
    assert "US$ 2.99" in str(caught.value) and mock_server.request_count == 0


# -- the plan field --------------------------------------------------------------

def mock_plan(site, extra="", repetitions=1, ceiling=5, competitors="  - {model: mock, harness: api}\n"):
    write(site / "config/models", mock_model())
    plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
    plan = edit(plan, "baseline", "mock/api").replace("repetitions: 2", f"repetitions: {repetitions}")
    plan = plan.replace("concurrency: 4", "concurrency: 1")
    plan = edit(plan, "cost_ceiling_usd", ceiling)
    plan += "competitors:\n" + competitors + extra
    write(site / "config/plans", plan)
    return plan


def resolve(site):
    return config.resolve(site / "config/products/simulated-apps.yaml",
                          site / "config/plans/smoke-frontier.yaml")


def test_attempt_cap_defaults_to_three_dollars_and_moves_the_hash_only_when_set(site, monkeypatch):
    monkeypatch.setenv("WB_MOCK_KEY", "set")
    mock_plan(site)
    rc = resolve(site)
    assert rc.plan.attempt_cap_usd == 3.0
    h0 = rc.hash
    mock_plan(site, "attempt_cap_usd: 3.00\n")
    assert resolve(site).hash == h0, "writing the default cap must not move the hash"
    mock_plan(site, "attempt_cap_usd: 1.5\n")
    rc = resolve(site)
    assert rc.plan.attempt_cap_usd == 1.5 and rc.hash != h0
    assert rc.config_json["plan"]["attempt_cap_usd"] == 1.5


@pytest.mark.parametrize("value", ["0", "-2", "much"])
def test_attempt_cap_must_be_a_positive_amount(site, monkeypatch, value):
    monkeypatch.setenv("WB_MOCK_KEY", "set")
    mock_plan(site, f"attempt_cap_usd: {value}\n")
    with pytest.raises(config.ConfigError) as caught:
        resolve(site)
    assert caught.value.field == "attempt_cap_usd"


# -- through the orchestrator -----------------------------------------------------

def test_attempt_cap_ends_the_attempt_as_infra_and_the_round_goes_on(site, tmp_path, mock_server):
    mock_plan(site, "attempt_cap_usd: 0.01\n")
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    store = Store(tmp_path / "wb.sqlite3")
    run_id = Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).run("run-cap")
    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 2 and {r["termination"] for r in rows} == {"infra:attempt_cap"}
    assert all(r["passed"] is False for r in rows)
    assert store.run(run_id)["finished"] is not None and store.run(run_id)["stop_reason"] is None
    assert mock_server.request_count == 0 and ledger.reservations() == []
    # a capped attempt is final: resume must not run it again and hit the cap forever
    assert len(store.completed_identities(run_id)) == 2


def test_weekly_budget_exhausted_mid_run_stops_the_run_and_resume_continues_it(site, tmp_path, mock_server):
    """The week's capacity runs out under a request: the attempt is recorded as
    infrastructure, the run stops with `weekly_budget`, and once capacity is
    back (here: an earlier unknown hold settles) `resume` finishes it without
    resetting or double-reserving anything."""
    mock_plan(site, "attempt_cap_usd: 0.20\n", ceiling=0.05)
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", weekly_limit_usd="1")
    ledger.reserve("earlier-round", "0.95", scope_id="earlier")      # leaves US$ 0.05 for the week
    store = Store(tmp_path / "wb.sqlite3")
    with pytest.raises(RunKilled) as caught:
        Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).run("run-week")
    assert "weekly budget" in str(caught.value) and "wb resume run-week" in str(caught.value)
    assert store.run("run-week")["stop_reason"] == "weekly_budget"
    rows = store.episodes(run="run-week")["rows"]
    assert rows and {r["termination"] for r in rows} == {"infra:weekly_budget"}
    assert mock_server.request_count == 0
    before = [r.reservation_id for r in ledger.reservations()]

    ledger.settle("earlier-round", "0.01")                            # the week has room again
    Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).resume("run-week")
    rows = store.episodes(run="run-week")["rows"]
    assert len(rows) == 2 and {r["termination"] for r in rows} == {"completed"}
    assert store.run("run-week")["stop_reason"] is None and store.run("run-week")["finished"] is not None
    after = [r.reservation_id for r in ledger.reservations()]
    assert after[:len(before)] == before and len(after) == len(before) + mock_server.request_count


# -- round admission -------------------------------------------------------------

def test_the_second_round_of_an_oversubscribed_week_is_refused_naming_the_shortfall(site, tmp_path, mock_server):
    """Round A's requests all fail after the claim (the provider rate-limits every
    call), so their holds stay; round B then asks the same week for more than
    what is left and is refused before it reserves anything."""
    mock_plan(site, "attempt_cap_usd: 0.40\n")            # 2 attempts x US$ 0.40 = US$ 0.80 per round
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", weekly_limit_usd="1")
    store = Store(tmp_path / "wb.sqlite3")
    mock_server.fail_requests = set(range(1, 1000))
    Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).run("round-a")
    rows = store.episodes(run="round-a")["rows"]
    assert {r["termination"] for r in rows} == {"infra:rate_limit"}
    held = ledger.status()
    assert held.held_usd > 0 and len(ledger.reservations()) == 6      # 2 attempts x 3 invocations
    available = held.available_usd
    assert available < Decimal("0.80")

    with pytest.raises(RoundAdmissionError) as caught:
        Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).run("round-b")
    message = str(caught.value)
    assert "maximum liability US$ 0.80" in message and "2 API attempts x attempt cap US$ 0.40" in message
    assert f"available US$ {available:.2f}" in message
    assert f"short by US$ {Decimal('0.80') - available:.2f}" in message
    assert len(ledger.reservations()) == 6 and store.run("round-b") is None


def test_admission_caps_the_liability_by_the_plans_cost_ceiling(site, tmp_path, mock_server):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", weekly_limit_usd="1")
    ledger.reserve("earlier-round", "0.95", scope_id="earlier")      # US$ 0.05 left
    store = Store(tmp_path / "wb.sqlite3")
    mock_plan(site, "attempt_cap_usd: 0.20\n", ceiling=5)             # 2 x 0.20 = 0.40 asked
    with pytest.raises(RoundAdmissionError) as caught:
        Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).run("run-refused")
    assert "maximum liability US$ 0.40" in str(caught.value) and "short by US$ 0.35" in str(caught.value)
    assert store.run("run-refused") is None and mock_server.request_count == 0
    # the ceiling bounds what the round may spend, so it bounds the liability too
    mock_plan(site, "attempt_cap_usd: 0.20\n", ceiling=0.05)
    orch = Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger)
    with pytest.raises(RunKilled):                                    # admitted; the first request then finds no room
        orch.run("run-admitted")
    assert store.run("run-admitted")["stop_reason"] == "weekly_budget"


def test_admission_counts_monarch_attempts_at_the_monarch_ceiling(site, tmp_path, repo):
    from tests.monarch_helpers import monarch_site, resolve_monarch
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", weekly_limit_usd="10")
    store = Store(tmp_path / "wb.sqlite3")
    rc = resolve_monarch(monarch_site(site, monarch_repo=str(repo)))   # 2 tasks x 2 repetitions, ceiling US$ 5
    rc.plan.cost_ceiling_usd = 60
    with pytest.raises(RoundAdmissionError) as caught:
        Orchestrator.from_config(store, rc, tmp_path / "out", ledger=ledger).run("run-monarch")
    message = str(caught.value)
    assert "4 Monarch attempts x ceiling US$ 25.00" in message and "maximum liability US$ 60.00" in message
    assert "available US$ 10.00" in message and "short by US$ 50.00" in message


def test_resume_admits_the_remaining_attempts_only_and_never_resets_spend(site, tmp_path, mock_server):
    mock_plan(site, "attempt_cap_usd: 0.40\n")
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", weekly_limit_usd="1")
    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger)
    orch._stop_after = 1
    with pytest.raises(RunKilled):
        orch.run("run-half")
    spent = store.status("run-half")["spend_usd"]
    settled = ledger.status().actual_usd
    ids = [r.reservation_id for r in ledger.reservations()]
    assert spent > 0 and settled > 0 and len(ids) == 2

    # room for one attempt (US$ 0.40) but not for the whole round (US$ 0.80)
    ledger.reserve("someone-else", str(Decimal("1") - settled - Decimal("0.45")), scope_id="other")
    assert Decimal("0.40") <= ledger.status().available_usd < Decimal("0.80")
    Orchestrator.from_config(store, resolve(site), tmp_path / "out", ledger=ledger).resume("run-half")
    rows = store.episodes(run="run-half")["rows"]
    assert len(rows) == 2 and {r["termination"] for r in rows} == {"completed"}
    assert store.status("run-half")["spend_usd"] > spent
    after = ledger.reservations()
    assert [r.reservation_id for r in after][:2] == ids and len(after) == 5     # 2 + the other hold + 2 new
    assert ledger.status().actual_usd > settled


# -- Monarch attempts reserve their ceiling through the same ledger ---------------------

from tests.fake_langfuse import FakeLangfuse  # noqa: E402
from tests.fake_monarch import FakeMonarch, Scenario  # noqa: E402
from tests.monarch_helpers import MONARCH_ENV, arm_against, free_port, repo  # noqa: E402, F401  (repo is a fixture)
from tests.test_monarch_arm import (  # noqa: E402, F401  (fast_polling is an autouse fixture)
    EPISODE, LANGFUSE_ENV, SF, both_phases, fast_polling, task)


def monarch_attempt(site, repo, langfuse, ledger, trace=None, ceiling="0.50"):
    import time
    from wb_arms.monarch import bench_episode_id
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        env = {**MONARCH_ENV, **LANGFUSE_ENV(langfuse), "MONARCH_ATTEMPT_CEILING_USD": ceiling}
        arm = arm_against(site, fake, port, repo, langfuse=langfuse, env=env)
        arm.ledger = ledger
        if trace is not None:
            trace(langfuse, bench_episode_id(EPISODE))
        result = arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)
    return arm, result


def test_a_monarch_attempt_reserves_the_ceiling_and_settles_from_langfuse(site, repo, tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    with FakeLangfuse() as lf:
        arm, result = monarch_attempt(site, repo, lf, ledger, trace=both_phases)
    assert result.termination == "completed" and result.cost_usd > 0
    (row,) = ledger.reservations()
    assert row.reservation_id.startswith(f"{EPISODE}#") and row.reservation_id.endswith("#monarch")
    assert row.scope_id == EPISODE and row.maximum_usd == Decimal("0.50")
    assert row.actual_usd == Decimal(str(result.cost_usd)).quantize(Decimal("0.000001"))
    assert row.metadata["billing_provider"] == "monarch" and row.metadata["harness"] == "monarch"
    assert row.metadata["version"] == arm.name
    assert ledger.status().held_usd == 0
    assert result.turn_log[-1]["billing"]["status"] == "estimated_from_langfuse"


def test_a_monarch_attempt_whose_cost_cannot_be_read_keeps_the_hold(site, repo, tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    lf = FakeLangfuse().start()
    lf.stop()                                   # nothing answers there any more
    arm, result = monarch_attempt(site, repo, lf, ledger)
    assert "cost_missing" in result.flags and "billing=unknown" in result.flags
    (row,) = ledger.reservations()
    assert row.dispatched_at is not None and row.actual_usd is None
    assert ledger.status().held_usd == Decimal("0.50")
