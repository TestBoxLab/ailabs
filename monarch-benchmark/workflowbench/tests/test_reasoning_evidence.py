"""What the model thought is evidence too: every transport returns the provider's
own reasoning summary and stop reason, both loops record them, the trace shows
the prompt, and a change outside scope names the writes that could have made it."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms import providers
from wb_arms.api_loop import (ApiLoopArm, _AnthropicAdapter, _GeminiAdapter, _OpenAIResponsesAdapter,
                              build_tools_anthropic, build_tools_gemini, build_tools_responses)
from wb_results import evidence
from wb_studio.agents import run_loop
from wb_studio.failure_analysis import analysis
from wb_studio.gateways import GeminiGateway


class _Block(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {k: [x.model_dump() for x in v] if isinstance(v, list) else v
                for k, v in vars(self).items() if v is not None}

    def model_dump_json(self, exclude_none=True):
        return json.dumps(self.model_dump())


def test_anthropic_returns_thinking_summary_and_stop_reason(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    a = _AnthropicAdapter(providers.get("claude-opus-4-8"), build_tools_anthropic())
    resp = SimpleNamespace(
        content=[_Block(type="thinking", thinking="Find the contact first.", signature="sig"),
                 _Block(type="text", text="done")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0))
    a.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resp), with_options=lambda **kw: a.client)
    t = a.turn(a.start("sys", "brief"))
    assert t["reasoning"] == ["Find the contact first."] and t["stop_reason"] == "end_turn" and t["text"] == "done"


def test_openai_responses_asks_for_and_collects_the_summary(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    key = next(k for k, p in providers.REGISTRY.items() if p.adapter == "openai_responses")
    a = _OpenAIResponsesAdapter(providers.get(key), build_tools_responses())
    sent = {}
    resp = SimpleNamespace(
        output=[_Block(type="reasoning", id="rs1", summary=[_Block(type="summary_text", text="Look up the record.")]),
                _Block(type="message", id="m1", content=[_Block(type="output_text", text="ok")])],
        status="completed", usage=SimpleNamespace(input_tokens=10, output_tokens=5, input_tokens_details=None))
    a.client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: sent.update(kw) or resp),
                               with_options=lambda **kw: a.client)
    t = a.turn(a.start("sys", "brief"))
    assert sent["reasoning"] == {"effort": a.effort, "summary": "auto"}
    assert t["reasoning"] == ["Look up the record."] and t["stop_reason"] == "stop" and t["text"] == "ok"


def test_gemini_sdk_asks_for_thoughts_and_keeps_them_apart_from_the_answer(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    key = next(k for k, p in providers.REGISTRY.items() if p.adapter == "gemini")
    a = _GeminiAdapter(providers.get(key), build_tools_gemini())
    assert a.config.thinking_config.include_thoughts is True
    part = lambda **kw: SimpleNamespace(**{"function_call": None, "text": None, "thought": None, **kw})
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=5, cached_content_token_count=None),
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part(text="Check Airtable first.", thought=True),
                                                                   part(text="All done.")]),
                                    finish_reason="FinishReason.STOP")])
    a.client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: resp))
    t = a.turn(a.start("sys", "brief"))
    assert t["reasoning"] == ["Check Airtable first."] and t["text"] == "All done." and t["stop_reason"] == "STOP"


def test_gemini_gateway_reports_thought_parts_as_reasoning():
    reply = {"candidates": [{"content": {"parts": [{"text": "Plan: search, then patch.", "thought": True},
                                                   {"text": "Finished."}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "thoughtsTokenCount": 2},
             "_billing": {"actual_usd": "0.01"}}
    paid = SimpleNamespace(thinking_level=None, request=lambda *a, **k: reply)
    gateway = GeminiGateway(paid, "low")
    t = gateway.turn(gateway.start("sys", "brief"), scope_id="s", scope_limit_usd="1", request_id="r")
    assert t["reasoning"] == ["Plan: search, then patch."] and t["text"] == "Finished." and t["stop_reason"] == "STOP"


class _Gateway:
    on_text = None

    def start(self, system, brief):
        return [{"role": "user", "content": brief}]

    def turn(self, messages, **kw):
        messages.append({"role": "assistant", "content": "done", "reasoning_content": "Nothing to change."})
        return {"text": "done", "tool_calls": [], "reasoning": ["Nothing to change."], "stop_reason": "stop",
                "prompt_tokens": 3, "output_tokens": 2, "_billing": {"actual_usd": "0.001"}}


def test_studio_loop_records_prompt_reasoning_and_stop_reason():
    events, records = [], []
    result = run_loop(_Gateway(), system="SYS", brief="BRIEF", execute_tool=lambda n, a: "", scope_id="s",
                      scope_limit_usd="1", request_prefix="p",
                      emit=lambda kind, **d: events.append({"type": kind, **d}), record=records.append)
    assert result.termination == "completed"
    prompt = next(e for e in events if e["type"] == "model_prompt")
    assert prompt["arguments"] == {"system": "SYS", "brief": "BRIEF"}
    reply = next(e for e in events if e["type"] == "model_finished")
    assert reply["reasoning"] == ["Nothing to change."] and reply["stop_reason"] == "stop"
    response = next(r for r in records if r["type"] == "agent_response")["response"]
    assert response["reasoning"] == ["Nothing to change."] and response["stop_reason"] == "stop"
    assert result.turn_log[-1]["response"]["reasoning"] == ["Nothing to change."]


def test_api_loop_records_reasoning_in_the_response_entry(monkeypatch):
    class _Adapter:
        def start(self, system, brief):
            return [{"role": "user", "content": brief}]

        def turn(self, messages, timeout=None):
            messages.append({"role": "assistant", "content": "done"})
            return {"tool_calls": [], "text": "done", "reasoning": ["Only one record matches."],
                    "stop_reason": "end_turn", "prompt_tokens": 3, "output_tokens": 2,
                    "cached_tokens": 0, "cache_source": None}

    monkeypatch.setattr(ApiLoopArm, "_adapter", lambda self: _Adapter())
    arm = ApiLoopArm("claude-opus-4-8")
    records = []
    ep = SimpleNamespace(task={"prompt": [{"content": "sys"}, {"content": "brief"}]}, episode_id="e1",
                         record_agent_event=records.append)
    res = arm.run(ep)
    assert res.final_text == "done"
    response = next(r for r in records if r["type"] == "agent_response")["response"]
    assert response["reasoning"] == ["Only one record matches."] and response["stop_reason"] == "end_turn"
    assert res.turn_log[-1]["response"]["reasoning"] == ["Only one record matches."]


def test_unexpected_change_names_the_writes_that_could_have_made_it():
    results = [{"task": "sales.contact", "model": "bare", "passed": False, "termination": "completed",
                "checks": [{"type": "allowed_changes_only", "passed": False}],
                "unexpected_changes": [{"service": "salesforce", "path": "contacts[id=1].phone",
                                        "op": "changed", "before": "1", "after": "2"}]}]
    ev = lambda i, kind, **v: {"id": i, "type": kind, "task": "sales.contact", "model": "bare", **v}
    events = [ev(1, "node_started", node="tool-0", label="api_fetch",
                 arguments={"method": "GET", "url": "https://x.salesforce.com/contacts"}),
              ev(2, "node_finished", node="tool-0", status="completed"),
              ev(3, "node_started", node="tool-1", label="api_fetch",
                 arguments={"method": "PATCH", "url": "https://x.salesforce.com/contacts/1", "body": "{}"}),
              ev(4, "node_finished", node="tool-1", status="completed"),
              ev(5, "node_started", node="tool-2", label="api_fetch",
                 arguments={"method": "POST", "url": "https://gmail.googleapis.com/send"}),
              ev(6, "node_finished", node="tool-2", status="completed"),
              ev(7, "attempt_finished")]
    studio = Mock(spec=["job", "events", "tasks"])
    studio.job.return_value = {"id": "run-1", "results": results, "settings": {"tasks": ["sales.contact"], "models": ["bare"]}}
    studio.events.return_value = events
    studio.tasks = {"sales.contact": {"info": {"assertions": []}}}
    attempt = analysis(studio, "run-1")["attempts"][0]
    fact = next(f for f in attempt["observed_facts"] if f["source"] == "trace.api_fetch")
    assert fact["event_ids"] == [3]                      # the Salesforce write, not the read or the Gmail send
    assert "PATCH https://x.salesforce.com/contacts/1" in fact["text"]


def test_manifest_declares_recorded_reasoning_summaries(tmp_path):
    root = tmp_path / "ep"
    root.mkdir()
    for name in ("snapshot0.json", "snapshot1.json", "grading.json", "result.json"):
        evidence.write_json(root / name, {})
    evidence.write_events(root / "events.jsonl", [])
    evidence.write_events(root / "turns.jsonl", [])
    manifest = evidence.write_manifest(root, episode_id="e", contract_sha256="c", agent_messages="normalized",
                                       private_reasoning="summaries")
    assert manifest["coverage"]["private_reasoning"] == "summaries"
    assert evidence.write_manifest(root, episode_id="e", contract_sha256="c",
                                   agent_messages="normalized")["coverage"]["private_reasoning"] == "unavailable"


@pytest.mark.parametrize("text,stop,termination", [
    ("done", "end_turn", "completed"), ("done", None, "completed"),
    ("", "end_turn", "agent_error"), ("half an answer", "max_tokens", "agent_error"), ("half", "length", "agent_error"),
])
def test_api_loop_treats_an_abnormal_stop_as_no_answer(monkeypatch, text, stop, termination):
    """The CLI loop follows the Studio loop: no text, or a stop the provider calls
    abnormal, is not a finished attempt (it used to be recorded as completed)."""
    class _Adapter:
        def start(self, system, brief):
            return [{"role": "user", "content": brief}]

        def turn(self, messages, timeout=None):
            return {"tool_calls": [], "text": text, "reasoning": [], "stop_reason": stop,
                    "prompt_tokens": 3, "output_tokens": 2, "cached_tokens": 0, "cache_source": None}

    monkeypatch.setattr(ApiLoopArm, "_adapter", lambda self: _Adapter())
    ep = SimpleNamespace(task={"prompt": [{"content": "sys"}, {"content": "brief"}]}, episode_id="e1", record_agent_event=lambda e: None)
    res = ApiLoopArm("claude-opus-4-8").run(ep)
    assert res.termination == termination
    assert res.final_text == text
    if termination == "agent_error":
        assert res.error.startswith("Model stopped without a complete final answer")
