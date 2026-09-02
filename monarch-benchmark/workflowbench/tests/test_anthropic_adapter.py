"""Anthropic adapter: usage normalization, thinking-block echo, single-message
tool results, cache-write pricing. Uses a stub client so no key is needed."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from wb_arms import providers
from wb_arms.api_loop import _AnthropicAdapter, build_tools_anthropic, canonical_json


class _Block(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in vars(self).items() if v is not None}


def _resp(content, stop="tool_use", inp=100, out=20, read=0, write=0):
    return SimpleNamespace(
        content=content, stop_reason=stop,
        usage=SimpleNamespace(input_tokens=inp, output_tokens=out,
                              cache_read_input_tokens=read, cache_creation_input_tokens=write))


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    a = _AnthropicAdapter(providers.get("claude-opus-4-8"), build_tools_anthropic())
    a.calls = []

    class _Msgs:
        def create(self_, **kw):
            a.calls.append(kw)
            return a.next

    a.client = SimpleNamespace(messages=_Msgs(), with_options=lambda **kw: a.client)
    return a


def test_tools_prefix_is_stable_and_cached():
    a, b = build_tools_anthropic(), build_tools_anthropic()
    assert canonical_json(a) == canonical_json(b)
    assert a[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("input_schema" in t for t in a)


def test_turn_normalizes_usage_and_echoes_thinking(adapter):
    msgs = adapter.start("sys", "brief")
    adapter.next = _resp([
        _Block(type="thinking", thinking="", signature="sig"),
        _Block(type="tool_use", id="tu1", name="api_search", input={"query": "x"}),
        _Block(type="tool_use", id="tu2", name="base64_encode", input={"text": "y"}),
    ], inp=100, read=4000, write=1500, out=30)
    t = adapter.turn(msgs)
    assert t["prompt_tokens"] == 5600 and t["cached_tokens"] == 4000 and t["cache_write_tokens"] == 1500
    assert [c["name"] for c in t["tool_calls"]] == ["api_search", "base64_encode"]
    sent = adapter.calls[0]
    assert sent["thinking"] == {"type": "adaptive"} and sent["output_config"] == {"effort": "xhigh"}
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    # thinking block echoed verbatim in the appended assistant turn
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["content"][0]["type"] == "thinking"

    adapter.append_tool_result(msgs, t["tool_calls"][0], "r1")
    adapter.append_tool_result(msgs, t["tool_calls"][1], "r2")
    assert msgs[-1]["role"] == "user"
    assert [b["tool_use_id"] for b in msgs[-1]["content"]] == ["tu1", "tu2"]  # one message, both results


def test_refusal_ends_turn_without_tool_calls(adapter):
    msgs = adapter.start("sys", "brief")
    adapter.next = _resp([_Block(type="text", text="no")], stop="refusal")
    t = adapter.turn(msgs)
    assert t["tool_calls"] == [] and t["text"] == "no"


def test_cost_prices_cache_write_separately():
    p = providers.get("claude-opus-4-8")
    assert providers.cost_usd(p, prompt=10000, cached=8000, output=500, cache_write=1000) == pytest.approx(0.02775)
    # providers without a write rate fall back to the input rate
    g = providers.get("gpt-5.6-terra")
    assert providers.cost_usd(g, 1000, 0, 0, cache_write=1000) == providers.cost_usd(g, 1000, 0, 0)
