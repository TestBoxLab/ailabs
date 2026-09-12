"""Focused native failure/billing and recursive tool-admission regressions; no Docker or paid calls."""
import json
import threading
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms.api_loop import InfraError
from wb_orchestrator.budget import BudgetLedger
from wb_studio import native

IMAGE = "sha256:" + "a" * 64


def _request(**fields):
    return {"path": "/v1/responses", "body": {"model": "gpt-5.6-sol", "max_output_tokens": 20, **fields}}


def _receipt():
    return 200, "application/json", json.dumps({"status": "completed", "usage": {
        "input_tokens": 20, "input_tokens_details": {"cached_tokens": 5}, "output_tokens": 10}}).encode()


@pytest.fixture
def broker(tmp_path):
    ledger = BudgetLedger(tmp_path / "billing.sqlite3")
    ledger.reserve_run("run", "5")
    return native.NativeBroker(Mock(), ledger, scope_id="run", maximum=Decimal("5"),
        model_key="gpt-5.6-sol", prefix="attempt", observe=Mock(), transport=Mock(return_value=_receipt()))


@pytest.mark.parametrize("location", ["top_namespace", "input_namespace", "deep_namespace"])
def test_server_tools_inside_namespaces_are_refused_before_reservation(broker, location):
    bad = {"type": "namespace", "name": "functions", "tools": [{"type": "web_search"}]}
    if location == "top_namespace":
        fields = {"tools": [bad]}
    else:
        if location == "deep_namespace":
            bad = {"type": "namespace", "name": "outer", "tools": [bad]}
        fields = {"input": [{"type": "additional_tools", "tools": [bad]}]}
    response = broker(_request(**fields))
    assert response["status"] == 403
    broker.transport.assert_not_called()
    assert broker.ledger.reservations() == []


@pytest.mark.parametrize("location", ["top", "additional"])
def test_client_custom_and_function_namespace_tools_remain_available(broker, location):
    tools = [{"type": "namespace", "name": "functions", "tools": [
        {"type": "custom", "name": "exec", "format": {"type": "text"}},
        {"type": "function", "name": "lookup", "parameters": {"type": "object", "properties": {"type": {"type": "string"}}}}]}]
    fields = {"tools": tools} if location == "top" else {"input": [{"type": "additional_tools", "tools": tools}]}
    assert broker(_request(**fields))["status"] == 200
    broker.transport.assert_called_once()
    assert broker.ledger.reservations()[0].actual_usd == Decimal("0.000262")


@pytest.mark.parametrize("failure", ["timeout", "missing_exit", "malformed_stream"])
def test_native_failures_keep_known_receipts_and_unknown_holds_in_partial_result(tmp_path, monkeypatch, failure):
    ledger = BudgetLedger(tmp_path / "ledger.sqlite3")
    ledger.reserve_run("run", "5")
    studio = SimpleNamespace(directory=tmp_path, ledger=ledger, runtime=Mock(), emit=Mock(),
                             job=lambda _: {"settings": {"configuration": {}}})
    ep = SimpleNamespace(episode_id="ep", task={"prompt": [{"content": "Policy"}, {"content": "Task"}]},
                         tool_calls=[{"tool": "api_search"}], record_agent_event=Mock())
    manifest = {"harness": "codex", "model_key": "gpt-5.6-sol", "model": "gpt-5.6-sol", "image": IMAGE, "effort": "high"}
    transport = Mock(side_effect=[_receipt(), ValueError("provider transport interrupted")])
    monkeypatch.setattr(native, "admitted_transport", lambda *a, **k: transport)
    monkeypatch.setattr(native.DockerRuntime, "verify", lambda _: {"image": IMAGE})
    def execute(_runtime, config, request, observe, **kwargs):
        assert request(_request())["status"] == 200
        assert request(_request())["status"] == 502
        if failure == "timeout":
            raise InfraError("infra:timeout", "deadline", retryable=False)
        if failure == "missing_exit":
            return [{"type": "native_output", "stream": "stdout", "text": ""}]
        return [{"type": "native_exit", "returncode": 0},
                {"type": "native_output", "stream": "stdout", "text": "invalid json"}]
    monkeypatch.setattr(native.DockerRuntime, "execute", execute)
    arm = native.NativeArm(studio, "run", manifest, "task", threading.Event(), Decimal("5"))
    with pytest.raises((InfraError, ValueError)) as error:
        arm._execute_verified(ep)
    result = getattr(error.value, "partial", None)
    assert result is not None, "every post-dispatch failure must return retained billing"
    assert result.cost_usd == pytest.approx(0.000262)
    assert (result.tokens_prompt, result.tokens_cached, result.tokens_output) == (20, 5, 10)
    assert "billing=unknown" in result.flags
    assert result.tool_calls == 1
    assert result.termination != "completed"
    assert len(result.turn_log) >= 2
    paid, unknown = ledger.reservations()
    assert paid.actual_usd == Decimal("0.000262")
    assert unknown.actual_usd is None and unknown.dispatched_at is not None


def test_native_retry_uses_new_request_ids_without_reusing_billing(tmp_path, monkeypatch):
    ledger = BudgetLedger(tmp_path / "retries.sqlite3")
    ledger.reserve_run("run", "5")
    studio = SimpleNamespace(directory=tmp_path, ledger=ledger, runtime=Mock(), emit=Mock(),
                             job=lambda _: {"settings": {"configuration": {}}})
    ep = SimpleNamespace(episode_id="ep", task={"prompt": [{"content": "Policy"}, {"content": "Task"}]},
                         tool_calls=[], record_agent_event=Mock())
    manifest = {"harness": "codex", "model_key": "gpt-5.6-sol", "model": "gpt-5.6-sol", "image": IMAGE, "effort": "high"}
    transport = Mock(return_value=_receipt())
    monkeypatch.setattr(native, "admitted_transport", lambda *a, **k: transport)
    monkeypatch.setattr(native.DockerRuntime, "verify", lambda _: {"image": IMAGE})
    def execute(_runtime, config, request, observe, **kwargs):
        assert request(_request())["status"] == 200
        return [{"type": "native_exit", "returncode": 0}, {"type": "native_output", "stream": "stdout",
                 "text": json.dumps({"type": "turn.completed"}) + "\n"}]
    monkeypatch.setattr(native.DockerRuntime, "execute", execute)
    arm = native.NativeArm(studio, "run", manifest, "task", threading.Event(), Decimal("5"))
    for index in range(2):
        ep._journal = SimpleNamespace(directory=tmp_path / f"attempt-{index:03d}")
        result = arm._execute_verified(ep)
        assert result.termination == "completed" and result.cost_usd == pytest.approx(0.000262)
    assert [r.reservation_id for r in ledger.reservations()] == ["ep#attempt-000#native-1", "ep#attempt-001#native-1"]
    assert transport.call_count == 2
