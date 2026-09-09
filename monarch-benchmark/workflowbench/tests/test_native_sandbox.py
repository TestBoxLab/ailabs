"""Offline regressions for the disabled native launch and CLI evidence parser."""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms.api_loop import InfraError
from wb_arms.cli_claude_code import ClaudeCodeArm, invocation, parse_result


def payload(**changes):
    data = {"type": "result", "subtype": "success", "is_error": False,
            "result": "done", "num_turns": 2, "total_cost_usd": 0.12,
            "usage": {"input_tokens": 11, "output_tokens": 5,
                      "cache_read_input_tokens": 7, "cache_creation_input_tokens": 3}}
    data.update(changes)
    return data


def test_native_launch_blocks_before_host_process_or_private_task_export(tmp_path, monkeypatch):
    runner = Mock(side_effect=AssertionError("host subprocess must not run"))
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "provider-secret")
    monkeypatch.setenv("HOST_SECRET", "unrelated-host-secret")
    monkeypatch.setenv("WB_NATIVE_SANDBOX_VERIFIED", "true")
    ep = SimpleNamespace(episode_id="../../escape", task={"grader": "private-answer"})
    arm = ClaudeCodeArm(tmp_path / "agent-work", env={"HOME": str(tmp_path)})
    with pytest.raises(InfraError, match="verified isolated runtime") as error:
        arm.run(ep)
    assert error.value.kind == "infra:harness_crash"
    assert error.value.retryable is False
    assert not (tmp_path / "agent-work").exists()
    assert list(tmp_path.iterdir()) == []
    runner.assert_not_called()
    assert arm.version is None


def test_preflight_is_explicitly_blocked_and_has_no_verification_override():
    from wb_arms.native_sandbox import preflight, require_verified_runtime
    report = preflight()
    assert report.status == "blocked"
    assert report.contract_version == "native-isolation-v1"
    assert set(report.missing_checks) == {
        "runtime_identity", "filesystem_boundary", "environment_boundary",
        "application_gateway", "network_boundary", "evidence_capture", "billing_boundary"}
    with pytest.raises(InfraError, match="runtime_identity"):
        require_verified_runtime()
    assert invocation()["launch_status"] == "blocked"


@pytest.mark.parametrize("stdout", ["", "  ", "garbage", "{}", "[]", "null", "42",
                                       '{"type":"assistant","result":"done"}',
                                       json.dumps(payload(subtype="error_max_turns")),
                                       json.dumps(payload(result=None))])
def test_empty_malformed_or_nonterminal_output_never_completes(stdout):
    result = parse_result(stdout, 0)
    assert result.termination == "agent_error"
    assert result.error


def test_nonzero_exit_overrides_success_but_preserves_reported_billing():
    result = parse_result(json.dumps(payload()), 7, "native process failed")
    assert result.termination == "agent_error"
    assert "7" in result.error
    assert result.cost_usd == 0.12
    assert result.final_text == "done"


@pytest.mark.parametrize("cost", [None, "missing"])
def test_missing_billing_is_explicitly_unknown(cost):
    data = payload()
    if cost == "missing":
        del data["total_cost_usd"]
    else:
        data["total_cost_usd"] = None
    result = parse_result(json.dumps(data), 0)
    assert "billing=unknown" in result.flags
    assert result.cost_usd == 0.0  # Legacy placeholder; cannot settle a reservation.
    assert result.termination == "completed"


@pytest.mark.parametrize("field", ["total_cost_usd", "num_turns", "input_tokens"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "5", {}, []])
def test_invalid_numeric_evidence_never_completes(field, value):
    data = payload()
    if field == "input_tokens":
        data["usage"][field] = value
    else:
        data[field] = value
    result = parse_result(json.dumps(data), 0)
    assert result.termination == "agent_error"
    assert "cli_numeric_invalid" in result.flags
    if field == "total_cost_usd":
        assert "billing=unknown" in result.flags
        assert result.cost_usd == 0.0


def test_pretty_json_and_native_stream_events_preserve_observed_evidence():
    data = payload()
    plain = parse_result(json.dumps(data, indent=2), 0)
    assert plain.termination == "completed"
    assert plain.tokens_prompt == 21
    assert plain.tokens_cached == 7
    assert plain.tokens_cache_write == 3
    events = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}}, data]
    result = parse_result("\n".join(json.dumps(event) for event in events), 0)
    assert result.termination == "completed"
    assert [entry["event"] for entry in result.turn_log] == events
    assert [entry["sequence"] for entry in result.turn_log] == [0, 1]
    assert all(entry["source"] == "claude_code_stream" for entry in result.turn_log)


def test_malformed_stream_cannot_be_masked_by_successful_last_line():
    result = parse_result("not-json\n" + json.dumps(payload()), 0)
    assert result.termination == "agent_error"
    assert "cli_output_unparseable" in result.flags
    assert "billing=unknown" in result.flags


def test_native_error_result_is_preserved_without_claiming_completion():
    result = parse_result(json.dumps(payload(is_error=True, result="tool failed")), 0)
    assert result.termination == "agent_error"
    assert "tool failed" in result.error


def test_explicit_zero_billing_remains_distinct_from_unknown():
    result = parse_result(json.dumps(payload(total_cost_usd=0)), 0)
    assert result.cost_usd == 0.0
    assert "billing=unknown" not in result.flags


@pytest.mark.parametrize("usage", [None, [], "bad"])
def test_invalid_usage_shape_is_rejected(usage):
    result = parse_result(json.dumps(payload(usage=usage)), 0)
    assert result.termination == "agent_error"
    assert "cli_numeric_invalid" in result.flags


def test_native_preflight_rejects_before_reading_the_episode(tmp_path):
    from unittest.mock import PropertyMock
    episode = Mock()
    private_task = PropertyMock(side_effect=AssertionError("private task accessed"))
    type(episode).task = private_task
    with pytest.raises(InfraError, match="verified isolated runtime"):
        ClaudeCodeArm(tmp_path / "agent").run(episode)
    private_task.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("field", ["num_turns", "input_tokens"])
def test_fractional_counts_are_invalid(field):
    data = payload()
    if field == "num_turns":
        data[field] = 1.5
    else:
        data["usage"][field] = 1.5
    result = parse_result(json.dumps(data), 0)
    assert result.termination == "agent_error"
    assert "cli_numeric_invalid" in result.flags
    assert result.cost_usd == 0.12
