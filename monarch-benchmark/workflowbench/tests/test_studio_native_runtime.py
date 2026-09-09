"""Offline native boundary/broker verification; these tests do not attest Docker."""
import base64
import hashlib
import io
import json
import subprocess
import threading
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, call

import pytest

from wb_arms.api_loop import InfraError
from wb_arms.native_sandbox import DockerRuntime, NATIVE_VERSIONS, container_command
from wb_orchestrator.budget import BudgetExceeded, BudgetLedger
from wb_studio.native import CONTAINER_HELPER, NativeArm, NativeBroker, status


IMAGE = "sha256:" + "a" * 64
NAME = "ailabs-native-" + "1" * 32


def request(**changes):
    return {"id": 1, "path": "/v1/messages", "body": {"model": "claude-opus-5", "max_tokens": 20,
            "messages": [{"role": "user", "content": "Find contact"}]}, **changes}


def receipt():
    return 200, "application/json", json.dumps({"type": "message", "usage": {"input_tokens": 20,
        "output_tokens": 10, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 2}}).encode()


@pytest.fixture
def broker(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    ledger.reserve_run("run", "5")
    episode = Mock(spec=["api_search", "api_fetch", "base64_encode"])
    episode.api_search.return_value = "Allowed application catalog"
    transport = Mock(return_value=receipt())
    value = NativeBroker(episode, ledger, scope_id="run", maximum=Decimal("5"), model_key="claude-opus-5",
                         prefix="attempt-one", observe=Mock(), transport=transport)
    return value


def decode(response):
    return json.loads(base64.b64decode(response["body"]))


def test_only_immutable_image_and_no_host_environment_mount_or_network_enter_command():
    command = container_command(IMAGE, NAME)
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--user") + 1] == "65532:65532"
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges"
    assert command[command.index("--pids-limit") + 1] == "256"
    assert "--read-only" in command
    assert not set(command) & {"--mount", "--volume", "-v", "--env", "-e", "--privileged", "--pid"}
    assert command[-2:] == [IMAGE, "/opt/native/helper.py"]
    with pytest.raises(ValueError, match="immutable"):
        container_command("my-native:latest", NAME)
    with pytest.raises(ValueError, match="identity"):
        container_command(IMAGE, "../../host")


def test_absent_image_record_blocks_without_process_and_does_not_fake_readiness(tmp_path, monkeypatch):
    execute = Mock(side_effect=AssertionError("No Docker command without a build record"))
    monkeypatch.setattr(subprocess, "run", execute)
    report = status(SimpleNamespace(directory=tmp_path))
    assert report["status"] == "blocked" and report["launchable"] is False
    assert "not been built" in report["reason"]
    execute.assert_not_called()


def test_changed_container_helper_or_cli_version_fails_live_probe_validation(tmp_path, monkeypatch):
    expected = hashlib.sha256(CONTAINER_HELPER.encode()).hexdigest()
    (tmp_path / "image.json").write_text(json.dumps({"image": IMAGE, "helper_sha256": expected}))
    runtime = DockerRuntime(tmp_path)
    for evidence in ({"helper_sha256": "tampered", "claude-code": "2.1.261 (Claude Code)", "codex": "codex-cli 0.153.4"},
                     {"helper_sha256": expected, "claude-code": "9.9.9 (Claude Code)", "codex": "codex-cli 0.153.4"}):
        monkeypatch.setattr(runtime, "_command", Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(evidence))))
        with pytest.raises(InfraError, match="probe failed"):
            runtime.verify()


def test_provider_request_is_reserved_and_claimed_before_transport_and_settled_from_receipt(broker):
    def transport(provider, path, body):
        reservation = broker.ledger.reservations(scope_id="run")[0]
        assert reservation.dispatched_at is not None
        assert reservation.actual_usd is None
        assert (provider.key, path, body["model"]) == ("claude-opus-5", "/v1/messages", "claude-opus-5")
        return receipt()
    broker.transport.side_effect = transport
    response = broker(request())
    assert response["status"] == 200
    reservation = broker.ledger.reservations(scope_id="run")[0]
    assert reservation.actual_usd == Decimal("0.000365")
    assert broker.receipts[0]["usage"] == {"prompt_tokens": 27, "cached_tokens": 5, "cache_write_tokens": 2, "output_tokens": 10}
    assert [call.args[0]["type"] for call in broker.observe.call_args_list] == ["native_provider_request", "native_provider_response"]


@pytest.mark.parametrize("admission", ["missing", "closed"])
def test_missing_or_closed_full_run_liability_never_dispatches(broker, admission):
    if admission == "missing":
        broker.scope_id = "unreserved-run"
    else:
        broker.ledger.finish_run("run")
    response = broker(request())
    assert response["status"] == 409
    assert "complete run liability" in decode(response)["error"]
    broker.transport.assert_not_called()
    assert broker.ledger.reservations() == []


def test_request_budget_exhaustion_cannot_dispatch_or_create_a_request_hold(broker):
    broker.ledger.reserve("other-request", "5", scope_id="run", scope_limit_usd="5")
    with pytest.raises(BudgetExceeded):
        broker(request())
    broker.transport.assert_not_called()
    assert [r.reservation_id for r in broker.ledger.reservations()] == ["other-request"]


@pytest.mark.parametrize("bad", [
    {"path": "https://attacker.example/v1/messages"}, {"path": "/snapshot"},
    {"body": {"model": "other-model", "max_tokens": 20}},
    {"body": {"model": "claude-opus-5", "max_tokens": 32769}},
    {"body": {"model": "claude-opus-5", "max_tokens": True}},
    {"body": {"model": "claude-opus-5", "max_tokens": 20, "background": True}},
    {"body": {"model": "claude-opus-5", "max_tokens": 20, "tools": [{"type": "web_search"}]}},
    {"body": {"model": "claude-opus-5", "max_tokens": 20, "tools": ["malformed"]}},
    {"body": {"model": "claude-opus-5", "max_tokens": 20, "messages": [{"type": "input_image", "image_url": "https://other"}]}},
    {"body": {"model": "claude-opus-5", "max_tokens": 20, "system": [{"cache_control": {"type": "ephemeral", "ttl": "1h"}}]}},
])
def test_unapproved_endpoints_models_tools_or_billing_features_are_refused(broker, bad):
    assert broker(request(**bad))["status"] == 403
    broker.transport.assert_not_called()
    assert broker.ledger.reservations() == []


def test_task_tools_cannot_reach_grader_snapshot_or_other_episode_and_preserve_arguments(broker):
    allowed = broker({"path": "/tool", "body": {"name": "api_search", "arguments": {"query": "contacts", "top_k": 3}}})
    assert decode(allowed) == {"output": "Allowed application catalog"}
    broker.episode.api_search.assert_called_once_with("contacts", 3)
    for name in ("snapshot", "grade", "read_task", "other_episode", "__dict__"):
        assert broker({"path": "/tool", "body": {"name": name}})["status"] == 403
    assert broker.episode.method_calls == [call.api_search("contacts", 3)]
    broker.transport.assert_not_called()


@pytest.mark.parametrize("failure", ["transport", "receipt", "truncated_stream"])
def test_unknown_provider_billing_keeps_hold_and_hides_provider_errors(broker, failure):
    if failure == "transport":
        broker.transport.side_effect = ValueError("Secret sk-test-do-not-expose")
    elif failure == "receipt":
        broker.transport.return_value = (200, "application/json", b'{"type":"message"}')
    else:
        broker.transport.return_value = (200, "text/event-stream", b'data: {"type":"message_start","message":{"usage":{"input_tokens":3}}}\n')
    response = broker(request())
    reservation = broker.ledger.reservations()[0]
    assert reservation.actual_usd is None and reservation.dispatched_at is not None
    assert broker.receipts[0]["cost"] is None
    assert "sk-test-do-not-expose" not in json.dumps(response)


def test_public_native_launch_still_refuses_before_private_task_access(tmp_path):
    episode = Mock()
    private = PropertyMock(side_effect=AssertionError("Private task must not be read"))
    type(episode).task = private
    arm = NativeArm(SimpleNamespace(directory=tmp_path), "run", {"harness": "claude-code", "model_key": "claude-opus-5"}, "task", None, Decimal("5"))
    with pytest.raises(InfraError, match="not been built and verified"):
        arm.run(episode)
    private.assert_not_called()


def test_cancellation_removes_container_and_all_descendants(tmp_path, monkeypatch):
    runtime = DockerRuntime(tmp_path)
    monkeypatch.setattr(runtime, "verify", Mock(return_value={"image": IMAGE}))
    commands = Mock(return_value=subprocess.CompletedProcess([], 0, ""))
    monkeypatch.setattr(runtime, "_command", commands)
    process = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(), stderr=io.BytesIO())
    process.poll.return_value = None
    process.wait.return_value = 0
    launch = Mock(return_value=process)
    monkeypatch.setattr(subprocess, "Popen", launch)
    cancel = threading.Event(); cancel.set()
    callback = Mock(side_effect=AssertionError("Cancelled request must not dispatch"))
    with pytest.raises(InfraError, match="cancelled"):
        runtime.execute({"prompt": "Task only"}, callback, Mock(), cancel=cancel)
    native_name = launch.call_args.args[0][launch.call_args.args[0].index("--name") + 1]
    commands.assert_called_once_with(["docker", "rm", "--force", native_name], timeout=30)
    process.kill.assert_called_once()
    callback.assert_not_called()


def test_acceptance_must_match_current_image_source_tests_and_harness(tmp_path, monkeypatch):
    from wb_studio import native
    studio = SimpleNamespace(directory=tmp_path)
    manifest = {"image": IMAGE, "helper_sha256": "helper", "probe": {"observed": True}}
    monkeypatch.setattr(DockerRuntime, "verify", Mock(return_value=manifest))
    path = tmp_path / "native-runtime" / "acceptance.json"
    path.parent.mkdir()
    with pytest.raises(InfraError, match="acceptance has not passed"):
        native.require_acceptance(studio, "codex")
    sources = native._acceptance_sources()
    valid = {"contract": "native-isolation-v2", "image": IMAGE, "source_sha256": sources,
             "offline_tests": {"exit_code": 0}, "harnesses": {"codex": {"application_tool_observed": True}}}
    for change in ({"image": "sha256:" + "b" * 64}, {"source_sha256": {}},
                   {"offline_tests": {"exit_code": 1}}, {"harnesses": {"codex": {"application_tool_observed": False}}}):
        path.write_text(json.dumps({**valid, **change}))
        with pytest.raises(InfraError, match="differs"):
            native.require_acceptance(studio, "codex")
    path.write_text(json.dumps(valid))
    assert native.require_acceptance(studio, "codex")["acceptance"] == valid
    with pytest.raises(InfraError, match="differs"):
        native.require_acceptance(studio, "claude-code")


def test_native_request_cap_prevents_further_dispatch_and_retains_first_receipt(broker):
    broker.max_requests = 1
    assert broker(request())["status"] == 200
    second = broker(request())
    assert second["status"] == 403 and "limit reached" in decode(second)["error"]
    broker.transport.assert_called_once()
    assert len(broker.ledger.reservations()) == 1


def test_accepted_native_manifest_enters_bare_leaderboard_but_custom_prompt_does_not(tmp_path, monkeypatch):
    from wb_studio import native
    from wb_studio.app import ROOT, Studio
    from wb_studio.leaderboard import leaderboard, rank_records
    from wb_world.episode import load_suite
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-only")
    accepted = {"image": IMAGE, "helper_sha256": "1" * 64, "acceptance": {"contract": "native-isolation-v2"}}
    monkeypatch.setattr(native, "require_acceptance", Mock(return_value=accepted))
    monkeypatch.setattr(native, "status", Mock(return_value={"status": "ready", "launchable": True, "reason": "Offline fixture"}))
    def forbidden(*args, **kwargs):
        pytest.fail("No paid request is allowed")
    studio = Studio(tmp_path, tasks=load_suite(ROOT / "tasks")[:1], gateway_factory=forbidden)
    for prompt in ("", "Verify record IDs twice"):
        job = studio.create({"models": ["claude-code@high"], "tasks": list(studio.tasks), "maximum_usd": "5",
                             "configuration": {"prompt": prompt, "max_turns": 10}}, start=False)
        arm = job["settings"]["arms"][0]
        assert arm["kind"] == "native"
        manifest = job["runner_manifests"][arm["id"]]
        assert manifest["harness_version"] == "2.1.261"
        assert manifest["model"] == manifest["model_version"] == "claude-opus-5"
        assert manifest["effort"] == "high"
        assert all(len(manifest[key]) == 64 for key in ("tools_sha256", "world_sha256", "acceptance_sha256"))
        runtime_arm = studio._arm(job, arm, list(studio.tasks)[0], threading.Event())
        assert isinstance(runtime_arm, NativeArm)
        assert runtime_arm.name == arm["id"]
        job.update(status="completed", results=[{"model": arm["id"], "task": list(studio.tasks)[0],
                                                 "passed": True, "termination": "completed", "cost_usd": 0}])
        studio.save(job)
    assert leaderboard(studio)["cohorts"] == [], "One-task pilots must not enter public rankings"
    cohorts = rank_records(studio)["cohorts"]
    assert len(cohorts) == 1
    entries = cohorts[0]["entries"]
    assert sorted(entry["is_bare"] for entry in entries) == [False, True]
    assert studio.ledger.status().actual_usd == 0


def test_verification_writes_acceptance_only_after_both_real_cli_paths_report_tool_roundtrip(tmp_path, monkeypatch):
    from wb_studio import native
    studio = SimpleNamespace(directory=tmp_path)
    monkeypatch.setattr(DockerRuntime, "verify", Mock(return_value={"image": IMAGE, "probe": {"network": "none"}}))
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, "tests passed")))
    observed = []
    def execute(self, config, request, observe, **kwargs):
        observed.append(config["harness"])
        tool = "mcp__applications__base64_encode"
        path = "/v1/messages" if config["harness"] == "claude-code" else "/v1/responses"
        auxiliary = request({"path": path, "body": {"model": config["model"], "tools": []}})
        assert "READY" in base64.b64decode(auxiliary["body"]).decode()
        first = request({"path": path, "body": {"model": config["model"], "tools": [{"name": tool}]}})
        assert first["content_type"] == "text/event-stream"
        result = request({"path": "/tool", "body": {"name": "base64_encode", "arguments": {"text": "boundary"}}})
        assert decode(result)["output"] == "Ym91bmRhcnk="
        final = request({"path": path, "body": {"model": config["model"], "tools": [{"name": tool}]}})
        assert "READY" in base64.b64decode(final["body"]).decode()
        return [{"type": "native_output", "stream": "stdout", "text": "READY"}, {"type": "native_exit", "returncode": 0}]
    monkeypatch.setattr(DockerRuntime, "execute", execute)
    (tmp_path / "native-runtime").mkdir()
    record = native.verify_runtime(studio)
    assert observed == ["claude-code", "codex"]
    assert record["harnesses"]["codex"]["application_tool_observed"] is True
    assert record["harnesses"]["claude-code"]["provider_requests"] == 3
    assert json.loads((tmp_path / "native-runtime" / "acceptance.json").read_text())["source_sha256"] == native._acceptance_sources()


def test_native_transport_enters_shared_provider_capacity_before_sending(monkeypatch):
    from contextlib import contextmanager
    from wb_arms import providers
    from wb_studio import native
    events = []
    cancel = threading.Event()
    @contextmanager
    def capacity(name, *, timeout, cancel, tokens):
        events.append(("admitted", name, timeout, cancel, tokens))
        yield 30
        events.append(("released", name))
    def transport(provider, path, body, *, timeout):
        assert events == [("admitted", "anthropic", 120, cancel, 33796)]
        assert timeout == 30
        events.append(("sent", path))
        return receipt()
    monkeypatch.setattr(native, "_transport", transport)
    studio = SimpleNamespace(runtime=SimpleNamespace(provider=capacity))
    response = native.admitted_transport(studio, cancel)(providers.get("claude-opus-5"), "/v1/messages", {})
    assert response == receipt()
    assert events[-2:] == [("sent", "/v1/messages"), ("released", "anthropic")]


def test_native_acceptance_directory_remains_host_local_for_temporary_worker_jobs(tmp_path, monkeypatch):
    from wb_studio import native
    local = tmp_path / "host-native"
    monkeypatch.setenv("STUDIO_NATIVE_RUNTIME_DIR", str(local))
    studio = SimpleNamespace(directory=tmp_path / "temporary-job")
    assert native.runtime_directory(studio) == local
    assert native._acceptance_path(studio) == local / "acceptance.json"


def test_display_status_uses_source_bound_acceptance_without_running_docker(tmp_path, monkeypatch):
    from wb_studio import native
    studio = SimpleNamespace(directory=tmp_path)
    folder = tmp_path / "native-runtime"
    folder.mkdir()
    (folder / "image.json").write_text(json.dumps({"image": IMAGE}))
    accepted = {"contract": "native-isolation-v2", "image": IMAGE, "source_sha256": native._acceptance_sources(),
                "offline_tests": {"exit_code": 0}, "harnesses": {name: {"application_tool_observed": True} for name in NATIVE_VERSIONS}}
    (folder / "acceptance.json").write_text(json.dumps(accepted))
    probe = Mock(side_effect=AssertionError("Display loading must never run Docker"))
    monkeypatch.setattr(DockerRuntime, "verify", probe)
    display = native.status(studio)
    assert display["launchable"] is True and display["verification"] == "recorded_acceptance"
    probe.assert_not_called()
    accepted["source_sha256"] = {}
    (folder / "acceptance.json").write_text(json.dumps(accepted))
    assert native.status(studio)["launchable"] is False


def test_native_execution_exports_only_public_task_and_uses_broker_billing_not_cli_claim(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from wb_studio import native
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    ledger.reserve_run("run", "5")
    @contextmanager
    def capacity(*args, **kwargs):
        yield 120
    studio = SimpleNamespace(directory=tmp_path, ledger=ledger, runtime=SimpleNamespace(provider=capacity),
                             emit=Mock(), job=Mock(return_value={"settings": {"configuration": {"prompt": "Check IDs", "max_turns": 2}}}))
    episode = SimpleNamespace(episode_id="attempt", record_agent_event=Mock(), tool_calls=[],
                              task={"prompt": [{"content": "Public system"}, {"content": "Update the contact"}],
                                    "info": {"assertions": ["PRIVATE_ORACLE"], "initial_state": {"secret": "PRIVATE_SNAPSHOT"}}})
    monkeypatch.setattr(DockerRuntime, "verify", Mock(return_value={"image": IMAGE}))
    monkeypatch.setattr(native, "_transport", Mock(return_value=receipt()))
    def execute(self, config, broker, observe, **kwargs):
        assert config["prompt"] == "Public system\n\nUpdate the contact\n\nExperiment instructions:\nCheck IDs"
        assert "PRIVATE_ORACLE" not in json.dumps(config) and "PRIVATE_SNAPSHOT" not in json.dumps(config)
        assert {t["name"] for t in config["tools"]} == {"api_search", "api_fetch", "base64_encode"}
        assert config["max_turns"] == broker.max_requests == 2
        assert broker(request())["status"] == 200
        claimed = {"type": "result", "subtype": "success", "is_error": False, "result": "Recorded completion",
                   "total_cost_usd": 999, "num_turns": 1, "usage": {"input_tokens": 999, "output_tokens": 999}}
        return [{"type": "native_output", "stream": "stdout", "text": json.dumps(claimed) + "\n"},
                {"type": "native_exit", "returncode": 0}]
    monkeypatch.setattr(DockerRuntime, "execute", execute)
    arm = NativeArm(studio, "run", {"harness": "claude-code", "model_key": "claude-opus-5", "model": "claude-opus-5",
                                    "effort": "low", "image": IMAGE}, "task", None, Decimal("5"))
    result = arm._execute_verified(episode)
    assert result.termination == "completed" and result.final_text == "Recorded completion"
    assert result.cost_usd == 0.000365
    assert (result.tokens_prompt, result.tokens_cached, result.tokens_cache_write, result.tokens_output) == (27, 5, 2, 10)
    assert "billing=unknown" not in result.flags
    assert [c.args[0]["type"] for c in episode.record_agent_event.call_args_list] == ["native_provider_request", "native_provider_response"]
