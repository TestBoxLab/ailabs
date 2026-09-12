"""Customer infrastructure failures survive harness tool wrappers; no provider calls."""
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
import json
import time

import pytest

from wb_arms.api_loop import ArmResult, InfraError, _exec_tool
from wb_arms.providers import Provider
from wb_orchestrator import external_runtime as runtime
from wb_orchestrator.budget import BudgetExceeded, BudgetLedger
from wb_report.metrics import competitor_metrics


@dataclass
class Participant:
    role: str = "simulated-user"
    model: str = "customer"


REQUEST = {"messages": [{"role": "user", "content": "A synthetic customer request."}], "tools": []}
PROVIDER = Provider("customer", "synthetic-model", "UNUSED_TEST_KEY", "openai_responses", 1, 0.5, 2)
RECEIPT = {"prompt_tokens": 1000, "cached_tokens": 200, "cache_write_tokens": 0, "output_tokens": 100}


class Episode:
    episode_id = "test/task/native/t0"
    _reservation_token = "attempt-000"

    def __init__(self):
        self.events = []

    def attach_customer(self, callback, participant):
        self.customer = callback

    def record_agent_event(self, event):
        self.events.append(event)

    def api_fetch(self, method, url, params=None, body=None):
        return json.dumps(self.customer(REQUEST))


class Arm:
    provider_key = "native"

    def __init__(self, action):
        self.action = action

    def run(self, ep, deadline=None):
        return self.action(ep)


def setup(monkeypatch, tmp_path, outcomes, *, cap=2, participant=True):
    calls = []

    class Adapter:
        def __init__(self, provider, tools, timeout):
            self.tools = tools

        def turn(self, messages):
            calls.append((messages, self.tools))
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(runtime, "_OpenAIResponsesAdapter", Adapter)
    monkeypatch.setattr(runtime, "frozen_provider", lambda model: PROVIDER)
    config = SimpleNamespace(product=SimpleNamespace(participants=[Participant()] if participant else []),
        plan=SimpleNamespace(attempt_cap_usd=cap), models={"customer": object()})
    ledger = BudgetLedger(tmp_path / "ledger.sqlite", weekly_limit_usd="10")
    return config, ledger, calls


def run(config, ledger, ep, action, deadline=None):
    return runtime.run_attempt(Arm(action), ep, config, ledger, None,
                               deadline if deadline is not None else time.monotonic() + 30)


def fetch(ep):
    return json.loads(_exec_tool(ep, "api_fetch", {"method": "POST", "url": "/customer/send_message"}))


def test_swallowed_customer_provider_failure_is_infra_and_preserves_partial_billing(monkeypatch, tmp_path):
    config, ledger, calls = setup(monkeypatch, tmp_path, [
        {"text": "First reply", "tool_calls": [], **RECEIPT}, RuntimeError("provider disconnected")])
    ep = Episode()

    def action(ep):
        assert fetch(ep)["content"] == "First reply"
        assert "provider disconnected" in fetch(ep)["error"]
        assert "provider disconnected" in fetch(ep)["error"]  # sticky: no third provider request
        return ArmResult(cost_usd=0.25, tokens_prompt=7, tokens_output=3, final_text="Finished")

    with pytest.raises(InfraError) as caught:
        run(config, ledger, ep, action)
    error, partial = caught.value, caught.value.partial
    assert error.kind == partial.termination == "infra:customer"
    assert ep._customer_failure is error and error.retryable is False
    assert len(calls) == 2
    assert partial.cost_usd == pytest.approx(0.2511)
    assert (partial.tokens_prompt, partial.tokens_cached, partial.tokens_output) == (1007, 200, 103)
    assert partial.final_text == "Finished"
    assert partial.flags == ["billing=unknown"]
    assert [r["billing"]["status"] for r in partial.turn_log] == ["estimated_from_usage", "unknown_hold"]
    known, unknown = ledger.reservations()
    assert known.actual_usd == Decimal("0.001100")
    assert unknown.dispatched_at is not None and unknown.actual_usd is None
    assert ledger.status().held_usd == unknown.maximum_usd > 0
    assert ledger.run_reservations()[0].closed_at is not None
    metrics = competitor_metrics([dict(task_id="task", arm="native", model="native", trial=0,
        passed=False, termination=partial.termination, flags=partial.flags, cost_usd=partial.cost_usd)], 1)
    assert metrics["strict_pass_denominator"] == 0 and metrics["infra"] == 1
    assert metrics["cost_total"] == pytest.approx(0.2511)


def test_customer_admission_refusal_has_no_dispatch_or_fictitious_unknown_receipt(monkeypatch, tmp_path):
    config, ledger, calls = setup(monkeypatch, tmp_path, [], cap=0.001)
    ep = Episode()

    def action(ep):
        assert "budget exhausted" in fetch(ep)["error"]
        return ArmResult(cost_usd=0.25)

    with pytest.raises(InfraError) as caught:
        run(config, ledger, ep, action)
    assert caught.value.kind == "infra:budget" and caught.value.retryable is False
    assert caught.value.partial.cost_usd == 0.25
    assert caught.value.partial.flags == [] and caught.value.partial.turn_log == []
    assert calls == [] and ledger.reservations() == []
    assert ledger.status().held_usd == 0


def test_empty_billed_customer_reply_is_infra_and_keeps_known_receipt(monkeypatch, tmp_path):
    config, ledger, calls = setup(monkeypatch, tmp_path, [{"text": "  ", "tool_calls": [], **RECEIPT}])
    ep = Episode()

    def action(ep):
        assert "no content or tool calls" in fetch(ep)["error"]
        return ArmResult()

    with pytest.raises(InfraError) as caught:
        run(config, ledger, ep, action)
    assert caught.value.kind == "infra:customer"
    assert caught.value.partial.cost_usd == pytest.approx(0.0011)
    assert caught.value.partial.tokens_output == 100
    assert caught.value.partial.flags == []
    assert len(calls) == 1 and ledger.status().held_usd == 0


def test_customer_timeout_before_dispatch_is_sticky_and_unbilled(monkeypatch, tmp_path):
    config, ledger, calls = setup(monkeypatch, tmp_path, [])
    ep = Episode()
    with pytest.raises(InfraError) as caught:
        run(config, ledger, ep, lambda ep: (fetch(ep), ArmResult())[1], deadline=time.monotonic() - 1)
    assert caught.value.kind == "infra:timeout" and caught.value.retryable is False
    assert ep._customer_failure is caught.value
    assert caught.value.partial.turn_log == [] and caught.value.partial.cost_usd == 0
    assert calls == [] and ledger.reservations() == []


def test_attach_customer_failure_closes_budget_and_preserves_customer_billing(monkeypatch, tmp_path):
    config, ledger, calls = setup(monkeypatch, tmp_path, [RuntimeError("initial customer failed")])
    ep = Episode()
    ep.attach_customer = lambda callback, participant: callback(REQUEST)
    action_calls = []
    with pytest.raises(InfraError) as caught:
        run(config, ledger, ep, lambda ep: action_calls.append(True))
    assert caught.value.kind == "infra:customer"
    assert caught.value.partial.flags == ["billing=unknown"]
    assert action_calls == [] and len(calls) == 1
    assert ledger.run_reservations()[0].closed_at is not None
    assert ledger.status().held_usd == ledger.reservations()[0].maximum_usd > 0


@pytest.mark.parametrize("reason,kind", [
    ("scope budget exhausted", "infra:budget"), ("run budget exhausted", "infra:budget"),
    ("shared weekly budget exhausted", "infra:weekly_budget"),
    ("recorded reservation overrun blocks further launches", "infra:weekly_budget")])
def test_direct_arm_budget_refusal_is_infrastructure_with_partial_cost(monkeypatch, tmp_path, reason, kind):
    config, ledger, calls = setup(monkeypatch, tmp_path, [], participant=False)

    def action(ep):
        exc = BudgetExceeded(reason)
        exc.partial = ArmResult(cost_usd=0.2, tokens_output=4)
        raise exc

    with pytest.raises(InfraError) as caught:
        run(config, ledger, Episode(), action)
    assert caught.value.kind == caught.value.partial.termination == kind
    assert caught.value.retryable is False and caught.value.partial.cost_usd == 0.2
    assert caught.value.partial.tokens_output == 4 and caught.value.partial.flags == []
    assert calls == [] and ledger.run_reservations()[0].closed_at is not None


def test_customer_preserves_provider_infra_kind_and_retry_policy(monkeypatch, tmp_path):
    failure = InfraError("infra:rate_limit", "provider throttled", retry_after=0.5, retryable=True)
    config, ledger, calls = setup(monkeypatch, tmp_path, [failure])
    with pytest.raises(InfraError) as caught:
        run(config, ledger, Episode(), lambda ep: (fetch(ep), ArmResult())[1])
    assert caught.value is failure and caught.value.retryable is True
    assert caught.value.retry_after == 0.5 and caught.value.partial.flags == ["billing=unknown"]
    assert len(calls) == 1


@pytest.mark.parametrize("wrapped", [False, True])
def test_customer_tool_only_reply_preserves_source_schema_and_arguments(monkeypatch, tmp_path, wrapped):
    schema = {"name": "check_balance", "description": "Read the available balance", "parameters": {
        "type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}}
    turn = {"text": None, "tool_calls": [{"id": "call-1", "name": "check_balance", "args": {"account_id": "a1"}}], **RECEIPT}
    config, ledger, calls = setup(monkeypatch, tmp_path, [turn])
    ep = Episode()

    def action(ep):
        response = ep.customer({**REQUEST, "tools": [{"type": "function", "function": schema} if wrapped else schema]})
        assert response["content"] is None
        assert response["tool_calls"] == [{"id": "call-1", "name": "check_balance", "arguments": {"account_id": "a1"}}]
        return ArmResult(cost_usd=0.2)

    result = run(config, ledger, ep, action)
    assert result.termination == "completed" and result.cost_usd == pytest.approx(0.2011)
    assert result.tokens_prompt == 1000 and result.flags == []
    assert calls[0][1] == [{"type": "function", **schema}]
    assert ledger.status().held_usd == 0


def test_an_agent_timeout_keeps_its_verdict_when_the_customer_hit_the_same_deadline(monkeypatch, tmp_path):
    """An expired episode deadline is a scored `timeout` verdict by deliberate rule
    (`wb_arms/api_loop.py:670-673`), not an infrastructure retry.

    The simulated customer is cut at that same deadline and records `infra:timeout`.
    Letting the customer's sticky copy overwrite the arm's verdict dropped a real
    agent timeout out of the pass denominator, so tau2 pass rates came out inflated
    by exactly the attempts that ran out of time -- whenever the agent's last turn
    happened to call the customer.
    """
    config, ledger, calls = setup(monkeypatch, tmp_path, [])
    ep = Episode()

    def action(ep):
        assert "deadline" in fetch(ep)["error"]
        return ArmResult(cost_usd=0.25, termination="timeout", final_text="ran out of time")

    result = run(config, ledger, ep, action, deadline=time.monotonic() - 1)
    assert result.termination == "timeout", "the customer overwrote the arm's scored verdict"
    assert calls == [], "the deadline was already gone; no provider call should be made"
    rows = [dict(task_id="task", arm="native", model="native", trial=0, passed=False,
                 termination=result.termination, flags=result.flags, cost_usd=result.cost_usd)]
    metrics = competitor_metrics(rows, 1)
    assert metrics["strict_pass_denominator"] == 1 and metrics["infra"] == 0


def test_a_customer_failure_that_is_not_the_deadline_still_wins(monkeypatch, tmp_path):
    """The guard's own purpose, kept: a swallowed customer break must not be scored,
    even when the arm goes on to finish and hand back a verdict."""
    config, ledger, calls = setup(monkeypatch, tmp_path, [RuntimeError("provider disconnected")])
    ep = Episode()

    def action(ep):
        assert "provider disconnected" in fetch(ep)["error"]
        return ArmResult(cost_usd=0.25, termination="timeout", final_text="finished anyway")

    with pytest.raises(InfraError) as caught:
        run(config, ledger, ep, action)
    assert caught.value.kind == "infra:customer"
