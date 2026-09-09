"""Evidence must explain outcomes and survive retries, crashes and tampering."""
import hashlib
import json
from pathlib import Path

import pytest

from runner.arms import OracleArm
from wb_arms.api_loop import ArmResult, InfraError
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.store import Store
from wb_world.episode import Episode, load_suite

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def test_tool_event_retains_arguments_and_returned_value():
    ep = Episode(load_suite(TASKS)[0], "evidence/tools")
    assert ep.base64_encode("bench ✓") == "YmVuY2gg4pyT"
    event = ep.events[0]
    assert event["sequence"] == 0
    assert event["kind"] == "tool"
    assert event["tool"] == "base64_encode"
    assert event["arguments"] == {"text": "bench ✓"}
    assert event["result"] == "YmVuY2gg4pyT"
    assert event["status"] == "completed"
    assert event["finished_at"] >= event["started_at"]


def test_tool_exception_retains_failed_call(monkeypatch):
    import wb_world.episode as module
    def broken(*args):
        raise RuntimeError("world unavailable")
    monkeypatch.setattr(module, "api_search", broken)
    ep = Episode(load_suite(TASKS)[0], "evidence/error")
    with pytest.raises(RuntimeError, match="world unavailable"):
        ep.api_search("contact", top_k=3)
    assert ep.events[0]["arguments"] == {"query": "contact", "top_k": 3}
    assert ep.events[0]["status"] == "error"
    assert ep.events[0]["error"] == "world unavailable"


def _run(tmp_path, monkeypatch, arm=None):
    if arm is not None:
        monkeypatch.setattr("wb_orchestrator.orchestrator.build_arm", lambda _: arm)
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out",
                        tasks=load_suite(TASKS)[:1], provider_concurrency=1)
    run_id = orch.run("evidence-run")
    return store, store.episodes(run=run_id)["rows"][0]


def test_manifest_hashes_exact_grading_and_tool_evidence(tmp_path, monkeypatch):
    store, row = _run(tmp_path, monkeypatch)
    artifacts = store.artifacts(row["episode_id"])
    manifest = json.loads(Path(artifacts["manifest"]).read_text(encoding="utf-8"))
    assert manifest["schema"] == "workflowbench-evidence@1"
    assert manifest["episode_id"] == row["episode_id"]
    assert manifest["contract_sha256"] == row["contract_sha256"]
    assert manifest["attempt_count"] == 1
    root = Path(artifacts["manifest"]).parent
    assert manifest["coverage"]["private_reasoning"] == "unavailable"
    assert manifest["coverage"]["agent_messages"] == "not_applicable"
    for item in manifest["artifacts"]:
        data = (root / item["path"]).read_bytes()
        assert item["sha256"] == hashlib.sha256(data).hexdigest()
        assert item["bytes"] == len(data)
    grading = json.loads(Path(artifacts["grading"]).read_text(encoding="utf-8"))
    assert grading["passed"] is True
    assert grading["assertion_results"]
    events = [json.loads(line) for line in Path(artifacts["events"]).read_text(encoding="utf-8").splitlines()]
    assert any(e["kind"] == "tool" and "result" in e for e in events)
    assert row["passed"]


def test_retry_preserves_both_attempts_and_marks_missing_agent_messages(tmp_path, monkeypatch):
    class RetryArm:
        name = "retry-evidence"
        provider_key = None
        calls = 0
        def run(self, ep, deadline=None):
            self.calls += 1
            ep.base64_encode(f"try-{self.calls}")
            if self.calls == 1:
                exc = InfraError("infra:harness_crash", "transient", retry_after=0)
                exc.partial = ArmResult(cost_usd=0.02, turn_log=[{"observed": "first"}])
                raise exc
            OracleArm().run(ep)
            return ArmResult(cost_usd=0.03, turn_log=[{"observed": "second"}])
    store, row = _run(tmp_path, monkeypatch, RetryArm())
    root = Path(row["artifacts_uri"])
    first = json.loads((root / "attempt-000" / "attempt.json").read_text(encoding="utf-8"))
    second = json.loads((root / "attempt-001" / "attempt.json").read_text(encoding="utf-8"))
    assert first["termination"] == "infra:harness_crash"
    assert second["termination"] == "completed"
    for index, expected in [(0, "try-1"), (1, "try-2")]:
        events = [json.loads(line) for line in
                  (root / f"attempt-{index:03d}" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert events[0]["arguments"] == {"text": expected}
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["attempt_count"] == 2
    assert manifest["coverage"]["agent_messages"] == "unavailable"
    assert row["cost_usd"] == pytest.approx(0.05)


def test_manifest_verification_rejects_tampered_and_missing_artifacts(tmp_path, monkeypatch):
    from wb_results import evidence
    store, row = _run(tmp_path, monkeypatch)
    root = Path(row["artifacts_uri"])
    assert evidence.verify_manifest(root / "manifest.json") == []
    snapshot = root / "snapshot1.json"
    snapshot.write_text('{"tampered":true}', encoding="utf-8")
    problems = evidence.verify_manifest(root / "manifest.json")
    assert any(p["path"] == "snapshot1.json" and p["reason"] == "hash_mismatch" for p in problems)
    snapshot.unlink()
    problems = evidence.verify_manifest(root / "manifest.json")
    assert any(p["path"] == "snapshot1.json" and p["reason"] == "missing" for p in problems)

def test_api_turn_evidence_includes_text_arguments_results_and_truncation(tmp_path, mock_server):
    from wb_arms.api_loop import ApiLoopArm
    mock_server.n_tool_turns = 1
    mock_server.override_tool_call = {"name": "base64_encode", "args": {"text": "abc"}}
    result = ApiLoopArm("mock").run(Episode(load_suite(TASKS)[0], "api-trace"))
    turn = result.turn_log[0]
    assert turn["response"]["tool_calls"][0]["args"] == {"text": "abc"}
    assert turn["tool_results"][0]["content"] == "YWJj"
    assert turn["tool_results"][0]["truncated"] is False
    assert result.turn_log[-1]["response"]["text"] == "done"
    assert result.turn_log[0]["request"]["messages"][0]["role"] == "system"


def test_corrupted_evidence_cannot_be_regraded(tmp_path, monkeypatch):
    from wb_orchestrator.orchestrator import regrade
    store, row = _run(tmp_path, monkeypatch)
    snapshot = Path(row["artifacts_uri"]) / "snapshot1.json"
    snapshot.write_text("{}", encoding="utf-8")
    before = store.episodes(run=row["run_id"])["rows"]
    report = regrade(store, row["run_id"], TASKS)
    assert report["evidence_invalid"] == 1
    assert report["regraded"] == 0
    assert store.episodes(run=row["run_id"])["rows"] == before


@pytest.mark.parametrize("manifest", [
    {"schema": "workflowbench-evidence@1", "artifacts": None},
    {"schema": "workflowbench-evidence@1", "artifacts": []},
    {"schema": "workflowbench-evidence@1", "artifacts": [{"path": "../outside", "bytes": 0, "sha256": ""}]},
])
def test_incomplete_or_unsafe_manifest_is_rejected(tmp_path, manifest):
    from wb_results import evidence
    file = tmp_path / "manifest.json"
    file.write_text(json.dumps(manifest), encoding="utf-8")
    assert evidence.verify_manifest(file)

def test_sdk_messages_are_saved_as_structured_json(tmp_path, monkeypatch):
    from google.genai import types
    from wb_arms.api_loop import ApiLoopArm
    class Adapter:
        def start(self, system, brief):
            return [types.Content(role="user", parts=[types.Part(text="a request")])]
        def turn(self, messages, timeout=None):
            return {"text": "done", "tool_calls": [], "prompt_tokens": 5, "cached_tokens": 0,
                    "output_tokens": 1, "cache_source": None}
    arm = ApiLoopArm("gpt-5.6-sol")
    arm.provider_key = None
    monkeypatch.setattr(arm, "_adapter", lambda: Adapter())
    store, row = _run(tmp_path, monkeypatch, arm)
    assert row["termination"] == "completed"
    turns = [json.loads(line) for line in
             (Path(row["artifacts_uri"]) / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    assert turns[0]["request"]["messages"][0]["parts"][0]["text"] == "a request"


@pytest.mark.parametrize("remove_manifest", [False, True])
def test_resume_rejects_corrupted_old_attempt_before_overwriting(tmp_path, monkeypatch, remove_manifest):
    from wb_results.evidence import EvidenceIntegrityError
    class FailedArm:
        name = "failed"
        provider_key = None
        def run(self, ep, deadline=None):
            ep.base64_encode("observed")
            raise InfraError("infra:harness_crash", "failure", retryable=False)
    monkeypatch.setattr("wb_orchestrator.orchestrator.build_arm", lambda _: FailedArm())
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out",
                        tasks=load_suite(TASKS)[:1], provider_concurrency=1)
    orch.run("resume-evidence")
    row = store.episodes(run="resume-evidence")["rows"][0]
    root = Path(row["artifacts_uri"])
    manifest_before = (root / "manifest.json").read_bytes()
    (root / "attempt-000" / "events.jsonl").write_text("corrupt", encoding="utf-8")
    if remove_manifest:
        (root / "manifest.json").unlink()
    resumed = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out",
                           tasks=load_suite(TASKS)[:1], provider_concurrency=1)
    with pytest.raises(EvidenceIntegrityError):
        resumed.resume("resume-evidence")
    if remove_manifest:
        assert not (root / "manifest.json").exists()
    else:
        assert (root / "manifest.json").read_bytes() == manifest_before
    assert not (root / "attempt-001").exists()


def test_nonempty_incomplete_manifest_is_rejected(tmp_path):
    from wb_results import evidence
    data = b"hello"
    (tmp_path / "arbitrary").write_bytes(data)
    manifest = {"schema": "workflowbench-evidence@1", "artifacts": [
        {"path": "arbitrary", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}]}
    file = tmp_path / "manifest.json"
    file.write_text(json.dumps(manifest), encoding="utf-8")
    assert evidence.verify_manifest(file)


def test_corrupt_manifest_cannot_produce_a_report(tmp_path, monkeypatch):
    from wb_report.report import GateError, build_report
    store, row = _run(tmp_path, monkeypatch)
    (Path(row["artifacts_uri"]) / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(GateError, match="evidence"):
        build_report(store, row["run_id"])

def test_resume_keeps_prior_reported_spend_without_double_counting(tmp_path, monkeypatch):
    class ResumeArm:
        name = "resume-cost"
        provider_key = None
        calls = 0
        def run(self, ep, deadline=None):
            self.calls += 1
            if self.calls == 1:
                exc = InfraError("infra:harness_crash", "retry later", retryable=False)
                exc.partial = ArmResult(cost_usd=0.2, tokens_prompt=20,
                                        turn_log=[{"observed": "first invocation"}])
                raise exc
            OracleArm().run(ep)
            return ArmResult(cost_usd=0.3, tokens_prompt=30)
    arm = ResumeArm()
    monkeypatch.setattr("wb_orchestrator.orchestrator.build_arm", lambda _: arm)
    store = Store(tmp_path / "results.sqlite3")
    kwargs = dict(tasks=load_suite(TASKS)[:1], provider_concurrency=1)
    Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out", **kwargs).run("resume-cost")
    resumed = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out", **kwargs)
    resumed.resume("resume-cost")
    row = store.episodes(run="resume-cost")["rows"][0]
    assert row["cost_usd"] == pytest.approx(0.5)
    assert row["tokens"]["prompt"] == 50
    assert resumed._spent == pytest.approx(0.5)
    assert "spend_includes_resumed_attempts" in row["flags"]
    assert json.loads((Path(row["artifacts_uri"]) / "manifest.json").read_text())["attempt_count"] == 2


def test_tool_turn_limit_cannot_be_reported_as_normal_completion(monkeypatch, mock_server):
    import wb_arms.api_loop as module
    monkeypatch.setattr(module, "MAX_TOOL_TURNS", 1)
    mock_server.n_tool_turns = 5
    result = module.ApiLoopArm("mock").run(Episode(load_suite(TASKS)[0], "turn-limit"))
    assert result.termination == "agent_error"
    assert "turn_budget_exhausted" in result.flags
    assert result.final_text is None


@pytest.mark.parametrize("finalized", [False, True])
def test_uncommitted_attempt_is_quarantined_before_resume(tmp_path, monkeypatch, finalized):
    from wb_results import evidence
    task = load_suite(TASKS)[0]
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out", tasks=[task])
    # recorded under the set's own suite id: a run under another suite is refused
    # for that reason before its evidence is looked at (M1, test_world_revision)
    store.create_run("crashed", orch._hash(), orch.suite, orch._config())
    eid = f"crashed/{task['task']}/Oracle/t0"
    root = tmp_path / "out" / eid.split('/')[0] / "episodes" / task['task'] / "Oracle" / "t0"
    root.mkdir(parents=True)
    ep = Episode(task, eid)
    ep.attach_journal(root / "attempt-000")
    ep.base64_encode("last observed")
    if finalized:
        evidence.write_attempt(root, 0, ep, ArmResult(cost_usd=0.7), "completed", None)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    class ForbiddenArm:
        name = "Oracle"
        provider_key = None
        def run(self, *args, **kwargs):
            pytest.fail("unreconciled attempt must not dispatch")
    monkeypatch.setattr("wb_orchestrator.orchestrator.build_arm", lambda _: ForbiddenArm())
    with pytest.raises(evidence.EvidenceIntegrityError, match="unreconciled|incomplete"):
        orch.resume("crashed")
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert store.episodes(run="crashed")["rows"] == []


def test_evidence_failure_keeps_known_usage_and_blocks_report(tmp_path, monkeypatch):
    from wb_report.report import GateError, build_report
    from wb_orchestrator.orchestrator import regrade
    class BrokenEvidenceArm:
        name = "broken-evidence"
        provider_key = None
        def run(self, ep, deadline=None):
            exc = InfraError("infra:harness_crash", "journal write failed", retryable=False)
            exc.partial = ArmResult(cost_usd=0.25, tokens_prompt=1000, tokens_output=100,
                                    flags=["evidence_incomplete"])
            raise exc
    store, row = _run(tmp_path, monkeypatch, BrokenEvidenceArm())
    assert row["cost_usd"] == pytest.approx(0.25)
    assert row["tokens"]["prompt"] == 1000
    assert row["tokens"]["output"] == 100
    assert "evidence_incomplete" in row["flags"]
    assert row["termination"] == "infra:harness_crash"
    assert not row["passed"]
    with pytest.raises(GateError, match="evidence"):
        build_report(store, row["run_id"])
    assert regrade(store, row["run_id"], TASKS)["evidence_invalid"] == 1
    from wb_results.evidence import EvidenceIntegrityError
    resumed = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out",
                           tasks=load_suite(TASKS)[:1], provider_concurrency=1)
    with pytest.raises(EvidenceIntegrityError, match="incomplete"):
        resumed.resume(row["run_id"])


def test_resume_does_not_replace_inputs_of_a_selected_regrade(tmp_path, monkeypatch):
    from wb_results.evidence import EvidenceIntegrityError
    from wb_orchestrator.orchestrator import regrade
    class FailedArm:
        name = "failed-regraded"
        provider_key = None
        def run(self, ep, deadline=None):
            raise InfraError("infra:harness_crash", "interrupted", retryable=False)
    store, row = _run(tmp_path, monkeypatch, FailedArm())
    assert regrade(store, row["run_id"], TASKS)["regraded"] == 1
    root = Path(row["artifacts_uri"])
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    resumed = Orchestrator(store, TASKS, ["oracle"], 1, tmp_path / "out",
                           tasks=load_suite(TASKS)[:1], provider_concurrency=1)
    with pytest.raises(EvidenceIntegrityError, match="regraded"):
        resumed.resume(row["run_id"])
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
