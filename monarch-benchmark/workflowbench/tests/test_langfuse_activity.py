"""Execution history keeps measured billing and unknown liabilities intact."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from wb_orchestrator.budget import BudgetLedger, ReservationConflict
from tests.test_paid_dispatch import Adapter
from tests.test_studio_paid import Fake, run as run_paid
from tests.test_studio_native_runtime import broker, request as native_request  # noqa: F401


USAGE = {"input": 11, "output": 7, "cache_read": 3, "cache_write": 2}


@pytest.mark.parametrize("actual,outcome", [("0.125", "completed"), ("0", "completed"), (None, "unknown")])
def test_settlement_usage_never_changes_money_or_releases_unknown_billing(tmp_path, actual, outcome):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    held = ledger.reserve("request", "2", scope_id="attempt", metadata={"model": "mock"})
    ledger.claim("request")
    result = ledger.settle("request", actual, usage=USAGE, outcome=outcome)
    assert result.maximum_usd == held.maximum_usd == Decimal("2")
    assert result.actual_usd == (None if actual is None else Decimal(actual))
    assert ledger.status().held_usd == (Decimal("2") if actual is None else Decimal("0"))
    assert ledger.reservations()[0] == result
    if actual is not None:
        with pytest.raises(ReservationConflict, match="immutable"):
            ledger.settle("request", "0.5", usage=USAGE, outcome="completed")
        assert ledger.reservations()[0].actual_usd == Decimal(actual)


@pytest.fixture
def activity(monkeypatch):
    from wb_orchestrator import langfuse_export
    calls = []
    record = langfuse_export.record

    def capture(connection, reservation, **kwargs):
        calls.append({**dict(reservation), **kwargs})
        return record(connection, reservation, **kwargs)

    monkeypatch.setattr(langfuse_export, "record", capture)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    return calls


@pytest.mark.parametrize("path", ["cli", "studio"])
@pytest.mark.parametrize("receipt", [
    {"prompt_tokens": 16, "cached_tokens": 3, "cache_write_tokens": 2, "output_tokens": 7},
    {},
])
def test_provider_receipts_reach_history_without_double_counting_cache(tmp_path, monkeypatch, activity, path, receipt):
    from wb_arms import providers, reservations
    from wb_studio.gateways import ProviderGateway
    provider = providers.Provider("activity-mock", "mock-model", "UNUSED", "openai_responses", 1, .1, 2)
    monkeypatch.setitem(providers.REGISTRY, provider.key, provider)
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    if path == "cli":
        _, billing = reservations.dispatch(ledger, provider, lambda: receipt,
            request_id="request", scope_id="attempt", system="", messages=[], tools=[])
    else:
        gateway = ProviderGateway(ledger, provider.key, with_tools=False,
                                  adapter_factory=lambda *_: Adapter(receipt=receipt))
        messages = gateway.start("", "Do the work")
        billing = gateway.turn(messages, scope_id="attempt", scope_limit_usd="2", request_id="request")["_billing"]
    settled = activity[-1]
    assert settled["outcome"] == "completed"
    assert settled["usage"] == (USAGE if receipt else None)
    assert ledger.reservations()[0].actual_usd == (Decimal(billing["actual_usd"]) if receipt else None)
    assert (ledger.status().held_usd > 0) is (not receipt)


@pytest.mark.parametrize("path", ["cli", "studio", "gemini"])
def test_failed_provider_history_keeps_hold_and_never_retries(tmp_path, monkeypatch, activity, path):
    from wb_arms import providers, reservations
    from wb_studio.gateways import GatewayError, ProviderGateway
    from wb_studio.paid import PaidGateway, PaidGatewayError
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    adapter = Adapter(fail=TimeoutError("private-provider-message"))
    provider = providers.Provider("activity-mock", "mock-model", "UNUSED", "openai_responses", 1, .1, 2)
    monkeypatch.setitem(providers.REGISTRY, provider.key, provider)
    with pytest.raises((TimeoutError, GatewayError, PaidGatewayError)):
        if path == "cli":
            reservations.dispatch(ledger, provider, lambda: adapter.turn([]),
                request_id="request", scope_id="attempt", system="", messages=[], tools=[])
        elif path == "studio":
            gateway = ProviderGateway(ledger, provider.key, with_tools=False, adapter_factory=lambda *_: adapter)
            messages = gateway.start("", "Do the work")
            gateway.turn(messages, scope_id="attempt", scope_limit_usd="2", request_id="request")
        else:
            transport = Fake(ledger, fail=True)
            run_paid(PaidGateway(ledger, transport=transport))
    assert activity[-1]["outcome"] == "error"
    assert activity[-1]["actual_microusd"] is None
    assert ledger.status().held_usd == ledger.reservations()[0].maximum_usd > 0
    assert (adapter.calls if path != "gemini" else sum(op == "generateContent" for op, _ in transport.calls)) == 1


def test_gemini_history_includes_thoughts_and_disjoint_cached_input(tmp_path, activity):
    from wb_studio.paid import PaidGateway
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    transport = Fake(ledger)
    transport.response["usageMetadata"] = {**transport.response["usageMetadata"], "cachedContentTokenCount": 30}
    result = run_paid(PaidGateway(ledger, transport=transport))
    assert activity[-1]["usage"] == {"input": 70, "output": 50, "cache_read": 30, "cache_write": 0}
    assert activity[-1]["outcome"] == "completed"
    assert ledger.status().actual_usd == Decimal(result["_billing"]["actual_usd"]) == Decimal("0.000263")


def test_native_anthropic_receipt_reaches_history_as_disjoint_counts(broker, activity):
    assert broker(native_request())["status"] == 200
    assert activity[-1]["usage"] == {"input": 20, "output": 10, "cache_read": 5, "cache_write": 2}
    assert activity[-1]["outcome"] == "completed"
    assert broker.ledger.reservations()[0].actual_usd == Decimal("0.000365")


def test_studio_unknown_monarch_price_retains_hold_instead_of_settling_zero(tmp_path):
    from wb_arms.api_loop import ArmResult
    from wb_studio.enterprise import EnterpriseArm
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    ledger.reserve("monarch", "3", scope_id="attempt", metadata={"harness": "monarch-enterprise"})
    ledger.claim("monarch")
    arm = SimpleNamespace(studio=SimpleNamespace(ledger=ledger, budget=lambda: {}),
        inner=SimpleNamespace(_price_unknown=True, _trace_ids={"existing-trace"}, _infra=None),
        _summary=lambda _: "summary", emit=lambda *args, **kwargs: None)
    result = ArmResult(cost_usd=0)
    EnterpriseArm._settle(arm, "monarch", Decimal("3"), result)
    assert ledger.reservations()[0].actual_usd is None
    assert ledger.status().held_usd == Decimal("3")
    assert "billing=unknown" in result.flags


@pytest.mark.parametrize("tokens", [None, 16, 0])
def test_genesis_embedding_history_uses_receipt_never_token_estimate(tmp_path, monkeypatch, activity, tokens):
    from wb_studio import genesis_harness, genesis_memory_suite
    from unittest.mock import Mock
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    # Embedding passes the weekly allowance gate before it reserves; this test is about the receipt.
    genesis = SimpleNamespace(studio=SimpleNamespace(ledger=ledger),
        allowance_allows=lambda amount: (True, None),
        config=SimpleNamespace(route_for=lambda *args, **kwargs: {"id": "gpt-5.6-sol", "available": True}))
    result = SimpleNamespace(data=[SimpleNamespace(embedding=[.1, .2])],
        usage=None if tokens is None else SimpleNamespace(prompt_tokens=tokens))
    create = Mock(return_value=result)
    monkeypatch.setattr(genesis_harness, "model_routes", lambda: [])
    monkeypatch.setattr(genesis_memory_suite, "embedding_price", lambda _: Decimal("1"))
    monkeypatch.setattr(genesis_memory_suite, "_client", lambda _: SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    assert genesis_memory_suite.embed(genesis, ["x" * 200]) == [[.1, .2]]
    assert ledger.reservations()[0].actual_usd == (None if tokens is None else Decimal(tokens) / 1_000_000)
    assert (ledger.status().held_usd > 0) is (tokens is None)
    assert activity[-1]["usage"] == (None if tokens is None else
        {"input": tokens, "output": 0, "cache_read": 0, "cache_write": 0})
    assert activity[-1]["outcome"] == "completed"
    create.assert_called_once()
