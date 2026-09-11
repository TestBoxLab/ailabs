"""Live evidence survives abrupt process exit; observed state is never called final."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from runner.schema import PhaseMetrics
from wb_arms.api_loop import ArmResult
from wb_results import evidence
from wb_world.episode import Episode, load_task_file

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks/simple.email_sf_contact_city_update.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def episode():
    return Episode(load_task_file(TASK), "journal/test")


def city(snapshot):
    return next(c["mailing_city"] for c in snapshot["salesforce"]["contacts"]
                if c["id"] == "003004")


@pytest.mark.parametrize("crash_during_action", [False, True], ids=["after-tool", "mid-tool"])
def test_process_exit_preserves_completed_observations_without_final_world(tmp_path, crash_during_action):
    directory = tmp_path / "attempt-000"
    script = r"""
import json
import os
from pathlib import Path
import sys
import wb_world.episode as module
from wb_world.episode import Episode, load_task_file

ep = Episode(load_task_file(sys.argv[2]), "journal/crash")
ep.attach_journal(Path(sys.argv[1]))
ep.record_agent_event({"type": "agent_request", "request": {"messages": [{"role": "user", "content": "Update the city"}]}})
ep.api_fetch("PATCH", "https://yourinstance.salesforce.com/services/data/v61.0/sobjects/Contact/003004", body=json.dumps({"MailingCity": "Denver"}))
ep.record_agent_event({"type": "agent_response", "response": {"text": "Updated"}})
if sys.argv[3] == "True":
    def interrupted(world, *args, **kwargs):
        next(contact for contact in world.salesforce.contacts if contact.id == "003004").mailing_city = "unobserved mutation"
        os._exit(73)
    module.api_fetch = interrupted
    ep.api_fetch("PATCH", "https://yourinstance.salesforce.com/services/data/v61.0/sobjects/Contact/003004", body=json.dumps({"MailingCity": "Boulder"}))
os._exit(73)
"""
    result = subprocess.run([sys.executable, "-c", script, str(directory), str(TASK),
                             str(crash_during_action)], cwd=ROOT, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 73, result.stderr
    events = lines(directory / "events.live.jsonl")
    assert [e["status"] for e in events] == (["running", "completed", "running"]
                                             if crash_during_action else ["running", "completed"])
    assert events[0]["arguments"]["method"] == "PATCH"
    assert events[1]["sequence"] == 0 and "result" in events[1]
    turns = lines(directory / "turns.live.jsonl")
    assert [t["type"] for t in turns] == ["agent_request", "agent_response"]
    assert turns[1]["response"] == {"text": "Updated"}
    observations = sorted(events + turns, key=lambda event: event["observation_id"])
    assert [e["observation_id"] for e in observations] == list(range(len(observations)))
    observed = read_json(directory / "snapshot.observed.json")
    assert city(observed["world"]) == "Denver"
    assert observed["observation_id"] == events[1]["observation_id"]
    assert observed["final"] is False
    state = read_json(directory / "attempt.json")
    assert state["status"] == "running" and state["completion"] == "incomplete"
    assert state["final_world_state"] == "unavailable"
    assert not (directory / "snapshot1.json").exists()


def test_tool_start_is_fsynced_before_call_and_error_is_retained(tmp_path, monkeypatch):
    import wb_world.episode as module
    ep = episode()
    directory = tmp_path / "attempt-000"
    ep.attach_journal(directory)
    synced = []
    fsync = os.fsync

    def track_sync(fd):
        fsync(fd)
        synced.append(fd)

    monkeypatch.setattr(evidence.os, "fsync", track_sync)

    def broken(query, top_k):
        assert len(synced) == 1
        assert lines(directory / "events.live.jsonl")[0]["status"] == "running"
        raise RuntimeError("world unavailable")

    monkeypatch.setattr(module, "api_search", broken)
    with pytest.raises(RuntimeError, match="world unavailable"):
        ep.api_search("contact", top_k=3)
    assert len(synced) == 2
    events = lines(directory / "events.live.jsonl")
    assert [e["type"] for e in events] == ["tool_started", "tool_error"]
    assert events[1]["error"] == "world unavailable"
    assert events[1]["arguments"] == {"query": "contact", "top_k": 3}
    assert len(ep.events) == 1 and ep.events[0]["status"] == "error"
    assert read_json(directory / "snapshot.observed.json")["observation_id"] is None


def test_agent_events_are_copied_and_fsynced_immediately(tmp_path, monkeypatch):
    ep = episode()
    directory = tmp_path / "attempt-000"
    ep.attach_journal(directory)
    synced = []
    fsync = os.fsync

    def track_sync(fd):
        fsync(fd)
        synced.append(fd)

    monkeypatch.setattr(evidence.os, "fsync", track_sync)
    entry = {"type": "agent_request", "request": {"messages": [{"content": "original"}]}}
    ep.record_agent_event(entry)
    entry["request"]["messages"][0]["content"] = "later mutation"
    assert len(synced) == 1
    records = lines(directory / "turns.live.jsonl")
    assert records[0]["request"]["messages"] == [{"content": "original"}]
    assert records[0]["observation_id"] == 0 and records[0]["kind"] == "agent"
    assert ep.events == []


def test_failed_atomic_snapshot_update_preserves_last_observation(tmp_path, monkeypatch):
    ep = episode()
    directory = tmp_path / "attempt-000"
    ep.attach_journal(directory)
    before = (directory / "snapshot.observed.json").read_bytes()
    replace = evidence.os.replace

    def fail_snapshot(source, target):
        if Path(target).name == "snapshot.observed.json":
            raise OSError("disk unavailable")
        return replace(source, target)

    monkeypatch.setattr(evidence.os, "replace", fail_snapshot)
    with pytest.raises(OSError, match="disk unavailable"):
        ep.base64_encode("observed")
    assert (directory / "snapshot.observed.json").read_bytes() == before
    assert read_json(directory / "attempt.json")["completion"] == "incomplete"
    assert not (directory / "snapshot1.json").exists()


def test_finalization_preserves_live_journals_and_manifest_requires_them(tmp_path):
    ep = episode()
    directory = tmp_path / "attempt-000"
    ep.attach_journal(directory)
    ep.base64_encode("observed")
    ep.record_agent_event({"type": "agent_response", "response": {"text": "done"}})
    original = {name: (directory / name).read_bytes() for name in
                ("events.live.jsonl", "turns.live.jsonl", "snapshot.observed.json")}
    result = ArmResult(cost_usd=0.02, final_text="done", turn_log=[{"response": "done"}],
                       tokens_prompt=40, tokens_cached=5, tokens_cache_write=3, tokens_output=12,
                       turns=2, tool_calls=1, phases={"execution": PhaseMetrics(wall_clock_s=1.5)})
    evidence.write_attempt(tmp_path, 0, ep, result, "completed", None)
    assert all((directory / name).read_bytes() == data for name, data in original.items())
    state = read_json(directory / "attempt.json")
    assert state["status"] == "finalized" and state["completion"] == "complete"
    assert state["final_world_state"] == "recorded" and state["cost_usd"] == 0.02
    assert state["tokens"] == {"prompt": 40, "cached": 5, "cache_write": 3, "output": 12}
    assert state["turns"] == 2 and state["tool_calls"] == 1
    assert state["phases"]["execution"]["wall_clock_s"] == 1.5
    assert read_json(directory / "snapshot1.json") == ep.snapshot()
    assert lines(directory / "events.jsonl") == ep.events
    for name in ("snapshot0.json", "snapshot1.json", "grading.json", "result.json"):
        evidence.write_json(tmp_path / name, {})
    for name in ("events.jsonl", "turns.jsonl"):
        evidence.write_events(tmp_path / name, [])
    manifest = evidence.write_manifest(tmp_path, episode_id=ep.episode_id,
                                       contract_sha256="contract", agent_messages="recorded")
    assert manifest["coverage"]["live_journals"] == "recorded"
    declared = {item["path"] for item in manifest["artifacts"]}
    assert {f"attempt-000/{name}" for name in original} <= declared
    assert evidence.verify_manifest(tmp_path / "manifest.json") == []
    manifest["artifacts"] = [item for item in manifest["artifacts"]
                             if item["path"] != "attempt-000/events.live.jsonl"]
    evidence.write_json(tmp_path / "manifest.json", manifest)
    assert {"path": "attempt-000/events.live.jsonl", "reason": "not_declared"} in evidence.verify_manifest(tmp_path / "manifest.json")


def test_attach_cannot_overwrite_an_existing_attempt_or_start_after_tool_use(tmp_path):
    directory = tmp_path / "attempt-000"
    ep = episode()
    ep.attach_journal(directory)
    before = (directory / "attempt.json").read_bytes()
    with pytest.raises(FileExistsError):
        episode().attach_journal(directory)
    assert (directory / "attempt.json").read_bytes() == before
    used = episode()
    used.base64_encode("already observed")
    with pytest.raises(RuntimeError, match="before"):
        used.attach_journal(tmp_path / "attempt-001")
    assert not (tmp_path / "attempt-001").exists()


def test_manifest_provenance_hashes_current_sources_and_records_dependency_version(tmp_path, monkeypatch):
    import hashlib
    import importlib.metadata
    import platform
    sources = ("grader/grade.py", "grader/invariant.py", "wb_world/episode.py",
               "wb_orchestrator/external_runtime.py", "wb_worlds/enterprise_ops/adapter.py",
               "wb_worlds/tau2/adapter.py")
    for relative in sources:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original source", encoding="utf-8")
    monkeypatch.setattr(evidence, "SOURCE_ROOT", tmp_path)
    before = evidence.provenance()
    (tmp_path / "grader/grade.py").write_text("uncommitted repair", encoding="utf-8")
    (tmp_path / "wb_worlds/enterprise_ops/adapter.py").write_text("source checker repair", encoding="utf-8")
    (tmp_path / "wb_orchestrator/external_runtime.py").write_text("runtime repair", encoding="utf-8")
    after = evidence.provenance()
    assert after["python_version"] == platform.python_version()
    assert after["automation_bench_version"] == importlib.metadata.version("automation-bench")
    assert after["dependency_identity_scope"] == "installed_version_only"
    assert after["source_sha256"]["grader/grade.py"] == hashlib.sha256(b"uncommitted repair").hexdigest()
    assert before["source_sha256"]["grader/grade.py"] != after["source_sha256"]["grader/grade.py"]
    assert set(after["source_sha256"]) == set(sources)
    for relative, body in (("wb_worlds/enterprise_ops/adapter.py", b"source checker repair"),
                           ("wb_orchestrator/external_runtime.py", b"runtime repair")):
        assert after["source_sha256"][relative] == hashlib.sha256(body).hexdigest()
        assert after["source_sha256"][relative] != before["source_sha256"][relative]
    assert after["source_sha256"]["wb_worlds/tau2/adapter.py"] == before["source_sha256"]["wb_worlds/tau2/adapter.py"]


def test_write_json_waits_out_a_windows_reader(tmp_path, monkeypatch):
    """A reader holding the target open makes os.replace fail once on Windows; the write retries."""
    import os
    from wb_results import evidence
    calls = {"n": 0}
    real = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(5, "Access denied")
        return real(src, dst)

    monkeypatch.setattr(evidence.os, "name", "nt")
    monkeypatch.setattr(evidence.os, "replace", flaky)
    evidence.write_json(tmp_path / "job.json", {"ok": True})
    assert json.loads((tmp_path / "job.json").read_text(encoding="utf-8")) == {"ok": True}
    assert calls["n"] == 2

