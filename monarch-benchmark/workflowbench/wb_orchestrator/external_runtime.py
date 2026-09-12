"""Shared admission for external attempts and their simulated customer."""
from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace

from wb_arms.api_loop import ArmResult, InfraError, _OpenAIResponsesAdapter
from wb_arms import providers, reservations
from wb_studio.runtime import Runtime
from wb_orchestrator.budget import ROUND_ENVELOPE_MARKER, BudgetExceeded


class AttemptBudget:
    """One cap for every party; nested in the atomically reserved round when present."""
    def __init__(self, ledger, identity, maximum, *, participants=(), run_id=None):
        self.ledger, self.identity, self.maximum = ledger, identity, Decimal(str(maximum))
        self.participants, self.run_id = list(participants), run_id

    def open(self):
        if self.run_id is None:
            self.ledger.reserve_run(self.identity, self.maximum, metadata={"participants":self.participants})
        else:
            run = self.ledger.run_reservation(self.run_id)
            if run is None or run.closed_at:
                raise ValueError("The complete external round must be reserved before dispatch")

    def close(self):
        if self.run_id is None:
            self.ledger.finish_run(self.identity)

    def reserve(self, identity, maximum, **kwargs):
        kwargs.update(scope_id=self.identity, scope_limit_usd=self.maximum)
        if self.run_id:
            kwargs["run_id"] = self.run_id
        return self.ledger.reserve(identity, maximum, **kwargs)

    def run_reservation(self, _identity):
        return self.ledger.run_reservation(self.run_id or self.identity)

    def reservations(self, **kwargs):
        return self.ledger.reservations(scope_id=self.identity)

    def __getattr__(self, name):
        return getattr(self.ledger, name)


def frozen_provider(model):
    return providers.Provider(key=model.name, model_id=model.model, key_env=model.key_env,
        adapter=model.adapter or providers._DEFAULT_ADAPTER.get(model.provider, "openai"),
        price_in=model.usd_per_million.input, price_cached=model.usd_per_million.cached,
        price_out=model.usd_per_million.output, price_cache_write=model.usd_per_million.cache_write,
        base_url=model.base_url, cache_min_prompt_tokens=model.cache_min_prompt_tokens,
        header_fallbacks=tuple(model.header_fallbacks), effort=model.effort, family=model.provider)


def customer_input(messages):
    """Convert the source's OpenAI chat history without losing customer tool turns."""
    system, items = [], []
    for message in messages:
        role, content = message["role"], message.get("content")
        if role == "system":
            system.append(content or "")
        elif role == "tool":
            items.append({"type":"function_call_output", "call_id":message["tool_call_id"], "output":content or ""})
        else:
            if content:
                items.append({"role":role, "content":content})
            for call in message.get("tool_calls") or []:
                function = call["function"]
                items.append({"type":"function_call", "call_id":call["id"], "name":function["name"],
                              "arguments":function["arguments"]})
    return "\n\n".join(system), items


def _budget_failure(exc):
    """Which refusal the ledger gave, as a termination the orchestrator can act on.

    Three outcomes, not two, and the difference decides whether the round continues.
    `infra:budget` is the attempt's own scope cap: that attempt is over, the round is
    not. `infra:run_budget` (the round's admission envelope) and `infra:weekly_budget`
    both mean nothing further can be paid for at all.

    Collapsing the envelope case into `infra:budget` is what let a round run on to its
    last attempt recording refusals, then finish and report as though it had measured
    them. See `orchestrator.STOPS_THE_ROUND`.

    The message cannot tell the first two apart: an attempt's cap is itself a run
    reservation, so both say `run budget exhausted`. The scope that ran out is the
    discriminator -- a round's envelope carries `ROUND_ENVELOPE_MARKER`, an attempt's
    does not.
    """
    message = str(exc)
    scope = getattr(exc, "scope_id", None) or ""
    if "weekly" in message or "overrun" in message:
        kind = "infra:weekly_budget"
    elif ROUND_ENVELOPE_MARKER in scope:
        kind = "infra:run_budget"
    else:
        kind = "infra:budget"
    return InfraError(kind, message, retryable=False)


class Customer:
    def __init__(self, ep, participant, budget, deadline, provider):
        self.ep, self.participant, self.budget, self.deadline = ep, participant, budget, deadline
        self.receipts, self.sequence = [], 0
        self.provider = provider
        self.failure = None

    def __call__(self, request):
        if self.failure is not None:
            raise self.failure
        try:
            return self._generate(request)
        except Exception as exc:
            if isinstance(exc, BudgetExceeded):
                failure = _budget_failure(exc)
            elif isinstance(exc, InfraError):
                failure = exc
            else:
                kind = "infra:timeout" if isinstance(exc, TimeoutError) else "infra:customer"
                failure = InfraError(kind, "Simulated customer failed: " + str(exc), retryable=False)
            self.failure = self.ep._customer_failure = failure
            if failure is exc:
                raise
            raise failure from exc

    def _generate(self, request):
        provider = self.provider
        if provider.adapter != "openai_responses":
            raise ValueError("The initial simulated customer requires the verified OpenAI Responses transport")
        system, items = customer_input(request["messages"])
        tools = [{"type":"function", **tool.get("function", tool)} for tool in request.get("tools", [])]
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise InfraError("infra:timeout", "Customer deadline reached", retryable=False)
        adapter = _OpenAIResponsesAdapter(provider, tools, min(120, remaining))
        adapter.instructions = system
        adapter.effort = provider.effort
        adapter.max_output = request.get("max_tokens", 2048)
        self.sequence += 1
        identity = self.budget.identity + f"#customer-{self.sequence}"
        self.ep.record_agent_event({"type":"customer_provider_request", "request_id":identity,
                                    "model":provider.model_id, "messages":request["messages"], "tools":tools})
        try:
            turn, billing = reservations.dispatch(self.budget, provider, lambda: adapter.turn(items),
                request_id=identity, scope_id=self.budget.identity, system=system, messages=items, tools=tools,
                metadata={"participant":"simulated-user"}, scope_limit_usd=self.budget.maximum)
        except Exception:
            # Admission refusal creates no liability. Only a durable reservation
            # can support an unknown hold after a failed dispatch.
            row = next((r for r in self.budget.reservations() if r.reservation_id == identity), None)
            if row is not None:
                self.receipts.append({"reservation_id":identity, "maximum_usd":str(row.maximum_usd),
                    "actual_usd":None if row.actual_usd is None else str(row.actual_usd),
                    "status":"unknown_hold" if row.actual_usd is None else "estimated_from_usage",
                    "usage_receipt":{}})
            raise

        self.receipts.append(billing)
        self.ep.record_agent_event({"type":"customer_provider_response", "request_id":identity,
                                    "response":turn, "billing":billing})
        if not (isinstance(turn.get("text"), str) and turn["text"].strip()) and not turn.get("tool_calls"):
            raise InfraError("infra:customer", "Simulated customer returned no content or tool calls", retryable=False)
        return {"content":turn.get("text"),
                "tool_calls":[{"id":c["id"], "name":c["name"], "arguments":c["args"]} for c in turn.get("tool_calls", [])],
                "usage":billing["usage_receipt"], "cost_usd":billing["actual_usd"]}

    def add_cost(self, result):
        for receipt in self.receipts:
            result.cost_usd += float(receipt["actual_usd"] or 0)
            if receipt["actual_usd"] is None and "billing=unknown" not in result.flags:
                result.flags.append("billing=unknown")
            for field, key in (("tokens_prompt","prompt_tokens"), ("tokens_cached","cached_tokens"),
                               ("tokens_cache_write","cache_write_tokens"), ("tokens_output","output_tokens")):
                setattr(result, field, getattr(result, field) + (receipt["usage_receipt"].get(key) or 0))
        result.turn_log.extend({"participant":"simulated-user", "billing":r} for r in self.receipts)


class NativeCliArm:
    message_evidence = "native-stream-and-provider-receipts"

    def __init__(self, competitor, run_config, ledger):
        from wb_orchestrator.approvals import _probe_site
        from wb_studio.native import freeze
        self.name, self.provider_key = competitor.name, competitor.model.name
        self.ledger, self.plan = ledger, run_config.plan
        self.site = _probe_site()
        self.manifest = run_config.native_runtimes[competitor.name]
        self.model_label = self.manifest["model"]
        self.provider = frozen_provider(competitor.model)

    def run(self, ep, deadline=None):
        from wb_studio.native import NativeArm
        if providers.get(self.provider_key) != self.provider:
            raise ValueError("Native provider/rate card changed after configuration was frozen")
        studio = SimpleNamespace(directory=self.site.directory, ledger=self.ledger,
            runtime=Runtime(), emit=lambda *args, **kwargs:None,
            job=lambda _: {"settings":{"configuration":{"max_turns":self.manifest["limits"]["max_turns"]}}})
        identity = self.ledger.identity
        arm = NativeArm(studio, identity, self.manifest, ep.task["task"], threading.Event(), self.ledger.maximum)
        return arm.run(ep, deadline=deadline)


def run_attempt(arm, ep, run_config, ledger, run_id, deadline):
    participants = [asdict(p) for p in run_config.product.participants]
    maximum = Decimal(str(run_config.plan.attempt_cap_usd))
    if getattr(arm, "provider_key", None) == "monarch":
        from wb_arms.monarch import attempt_ceiling_usd
        maximum += attempt_ceiling_usd(arm.env) if participants else 0
        if not participants:
            maximum = attempt_ceiling_usd(arm.env)
    identity = ep.episode_id + "#" + reservations.invocation_token(ep)
    budget = AttemptBudget(ledger, identity, maximum, participants=participants, run_id=run_id)
    budget.open()
    scoped_arm = copy.copy(arm)
    scoped_arm.ledger = budget
    ep.budget_scope_id = identity
    customer = None
    result = None
    try:
        if participants:
            if len(participants) != 1 or not hasattr(ep, "attach_customer"):
                raise InfraError("infra:customer", "This world requires exactly one supported customer participant", retryable=False)
            customer = Customer(ep, participants[0], budget, deadline, frozen_provider(run_config.models[participants[0]["model"]]))
            try:
                ep.attach_customer(customer, participants[0])
            except Exception as exc:
                if customer.failure is not None:
                    raise customer.failure
                raise InfraError("infra:customer", "Could not attach simulated customer: " + str(exc), retryable=False) from exc
        result = scoped_arm.run(ep, deadline=deadline)
        # Harness tool wrappers may have converted the callback's exception into
        # a normal tool response. That must never become a scored agent failure.
        #
        # One exception, and only one: the arm's own `timeout` verdict and a customer
        # call cut at the same deadline are one event, not two. `api_loop.py:670-673`
        # makes an expired episode deadline a scored verdict on purpose, and the
        # customer's `infra:timeout` is that same clock. Raising the customer's copy
        # moved a real agent timeout out of the pass denominator, inflating the rate
        # by exactly the attempts that ran out of time.
        if customer is not None and customer.failure is not None:
            if not (getattr(result, "termination", None) == "timeout"
                    and getattr(customer.failure, "kind", None) == "infra:timeout"):
                raise customer.failure
    except Exception as exc:
        failure = customer.failure if customer is not None and customer.failure is not None else exc
        if isinstance(failure, BudgetExceeded):
            failure = _budget_failure(failure)
        partial = getattr(exc, "partial", None) or result or ArmResult()
        if customer:
            customer.add_cost(partial)
        if isinstance(failure, InfraError):
            partial.termination, partial.error = failure.kind, str(failure)
        failure.partial = partial
        if failure is exc:
            raise
        raise failure from exc
    else:
        if customer:
            customer.add_cost(result)
        return result
    finally:
        budget.close()
