"""Evidence I/O failure must stop paid work without discarding known usage."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from wb_arms.api_loop import ApiLoopArm, InfraError, _exec_tool
from wb_results import evidence
from wb_world.episode import Episode, load_task_file

TASK = Path(__file__).resolve().parents[1] / "tasks/simple.email_sf_contact_city_update.json"


class Adapter:
    def __init__(self):
        self.calls = 0
        self.delivered = []

    def start(self, system, brief):
        return [{"role": "user", "content": brief}]

    def turn(self, messages, timeout=None):
        self.calls += 1
        assert self.calls <= 2, "provider was called again after evidence failure"
        return {"text": "working", "prompt_tokens": 1000, "cached_tokens": 200,
                "cache_write_tokens": 100, "output_tokens": 50, "cache_source": "usage",
                "tool_calls": [{"id": "call-1", "name": "base64_encode", "args": {"text": "abc"}}]}

    def append_tool_result(self, messages, call, result):
        self.delivered.append(result)
        messages.append({"role": "tool", "content": result})


def setup(tmp_path, monkeypatch, fail_at):
    ep = Episode(load_task_file(TASK), "journal/failure")
    ep.attach_journal(tmp_path / "attempt-000")
    arm = ApiLoopArm("gpt-5.6-sol")
    arm.provider = replace(arm.provider, price_in=2, price_cached=0.5,
                           price_cache_write=3, price_out=8)
    adapter = Adapter()
    monkeypatch.setattr(arm, "_adapter", lambda: adapter)
    calls = []
    real_fsync = evidence.os.fsync

    def fail_once(fd):
        calls.append(fd)
        if len(calls) == fail_at:
            raise OSError("transient journal disk failure")
        real_fsync(fd)

    monkeypatch.setattr(evidence.os, "fsync", fail_once)
    return ep, arm, adapter


@pytest.mark.parametrize("fail_at, stage", [(1, "request"), (2, "response"),
                                           (3, "tool-start"), (4, "tool-completed"),
                                           (5, "world-snapshot"), (6, "tool-result")],
                         ids=lambda value: str(value))
def test_journal_failure_stops_requests_and_retains_known_usage(tmp_path, monkeypatch, fail_at, stage):
    ep, arm, adapter = setup(tmp_path, monkeypatch, fail_at)
    with pytest.raises(InfraError) as caught:
        arm.run(ep)
    exc = caught.value
    assert exc.kind == "infra:harness_crash" and exc.retryable is False
    assert "journal" in str(exc)
    partial = exc.partial
    assert "evidence_incomplete" in partial.flags
    assert partial.termination == "infra:harness_crash"
    assert partial.error == str(exc)
    known_turns = 0 if stage == "request" else 1
    assert adapter.calls == known_turns
    assert partial.turns == known_turns
    assert (partial.tokens_prompt, partial.tokens_cached, partial.tokens_cache_write,
            partial.tokens_output) == tuple(value * known_turns for value in (1000, 200, 100, 50))
    assert partial.cost_usd == pytest.approx(0.0022 * known_turns)
    assert partial.turn_log[0]["request"]["messages"][0]["role"] == "user"
    if known_turns:
        assert partial.turn_log[0]["response"]["text"] == "working"
    assert adapter.delivered == (["YWJj"] if stage == "tool-result" else [])
    if stage in ("tool-completed", "world-snapshot", "tool-result"):
        assert ep.events[0]["status"] == "completed"
        assert ep.events[0]["result"] == "YWJj"
    elif stage == "tool-start":
        assert "result" not in ep.events[0]


def test_response_journal_failure_preserves_prior_turn_flags_and_cumulative_spend(tmp_path, monkeypatch):
    ep, arm, adapter = setup(tmp_path, monkeypatch, fail_at=8)
    turn = adapter.turn

    def overreported_then_normal(messages, timeout=None):
        response = turn(messages, timeout)
        if adapter.calls == 1:
            response["cached_tokens"] = 1200
        return response

    monkeypatch.setattr(adapter, "turn", overreported_then_normal)
    with pytest.raises(InfraError) as caught:
        arm.run(ep)
    partial = caught.value.partial
    assert adapter.calls == 2 and partial.turns == 2
    assert partial.tokens_prompt == 2000 and partial.tokens_cached == 1400
    assert partial.tokens_cache_write == 200 and partial.tokens_output == 100
    assert partial.cost_usd == pytest.approx((400 * 2 + 1400 * 0.5 + 200 * 3 + 100 * 8) / 1e6)
    assert {"cache_overreport", "evidence_incomplete"} <= set(partial.flags)
    assert partial.tool_calls == 1 and len(partial.turn_log) == 2
    assert caught.value.retryable is False


def test_world_io_error_remains_a_recoverable_tool_result(monkeypatch):
    ep = Episode(load_task_file(TASK), "journal/tool-error")

    def broken(query, top_k=5):
        raise OSError("application unavailable")

    monkeypatch.setattr(ep, "api_search", broken)
    assert json.loads(_exec_tool(ep, "api_search", {"query": "contact"})) == {
        "error": "application unavailable"}
