"""Admission controls drain real offline attempts and preview the same pending work."""
import threading
from pathlib import Path

import pytest

from wb_orchestrator.orchestrator import Orchestrator, RunKilled
from wb_results.store import Store
from wb_world.episode import load_suite


TASKS = Path(__file__).resolve().parents[1] / "tasks"


def orchestrator(tmp_path, *, count=1, retry=0, competitor="null", concurrency=1):
    store = Store(tmp_path / "results.sqlite3")
    runner = Orchestrator(store, TASKS, [competitor], 1, tmp_path / "evidence",
                          tasks=load_suite(TASKS)[:count], retry_on_fail=retry,
                          provider_concurrency=concurrency)
    arm = runner._arms()[0]
    arm.name = competitor
    runner._arms = lambda: [arm]
    return store, runner


def test_pause_denies_earned_retry_and_resume_preserves_final_initial_row(tmp_path):
    store, runner = orchestrator(tmp_path, retry=2)
    admitted, released = [], []

    def admit(task, competitor, trial):
        if trial:
            return "paused"
        admitted.append((task, competitor, trial))

    runner.attempt_admission = admit
    runner.attempt_release = lambda *identity: released.append(identity)
    with pytest.raises(RunKilled, match="paused"):
        runner.run("pause-retry")
    before = store.episodes(run="pause-retry")["rows"]
    assert len(before) == 1 and admitted == released
    assert store.run("pause-retry")["stop_reason"] == "paused"
    summary = runner.pending_work("pause-retry", competitor_names=["null"])
    assert summary == dict(required_initial=0, earned_retries=1, required_attempts=1,
                           conditional_retries=1, maximum_attempts=2)
    _, resumed = orchestrator(tmp_path, retry=2)
    resumed.resume("pause-retry")
    after = store.episodes(run="pause-retry")["rows"]
    assert len(after) == 3 and after[0] == before[0]
    assert resumed.pending_work("pause-retry", competitor_names=["null"])["maximum_attempts"] == 0


def test_pause_drains_two_admitted_worlds_without_starting_third(tmp_path):
    store, runner = orchestrator(tmp_path, count=3, competitor="oracle", concurrency=2)
    arm = runner._arms()[0]
    original = arm.run
    lock, both_started, drain = threading.Lock(), threading.Event(), threading.Event()
    state = dict(started=0, active=0, paused=False)
    failures = []

    def run(ep, deadline=None):
        with lock:
            state["started"] += 1
            if state["started"] == 2:
                both_started.set()
        assert drain.wait(15), "test did not release admitted attempts"
        return original(ep, deadline)

    def admit(*identity):
        with lock:
            if state["paused"]:
                return "paused"
            state["active"] += 1

    def release(*identity):
        with lock:
            state["active"] -= 1

    def execute():
        try:
            runner.run("drain")
        except BaseException as error:
            failures.append(error)

    arm.run = run
    runner._arms = lambda: [arm]
    runner.attempt_admission, runner.attempt_release = admit, release
    worker = threading.Thread(target=execute)
    worker.start()
    try:
        assert both_started.wait(15)
        with lock:
            state["paused"] = True
    finally:
        drain.set()
        worker.join(20)
    assert not worker.is_alive()
    rows = store.episodes(run="drain")["rows"]
    assert len(rows) == 2, "pause must stop the third attempt before it enters the world"
    assert all(row["passed"] for row in rows)
    assert state["active"] == 0 and state["started"] == 2
    assert len(failures) == 1 and isinstance(failures[0], RunKilled)
    assert store.run("drain")["stop_reason"] == "paused"


def test_pending_preview_never_builds_adapter_and_uses_recorded_identity(tmp_path):
    store, runner = orchestrator(tmp_path, count=2, retry=1)
    runner.run("preview")

    def forbidden():
        raise AssertionError("preview must not construct provider adapters")

    runner._arms = forbidden
    assert runner.pending_work("preview", competitor_names=["null"])["required_attempts"] == 0
    assert runner.pending_work("new-run", competitor_names=["monarch@frozen"]) == dict(
        required_initial=2, earned_retries=0, required_attempts=2,
        conditional_retries=2, maximum_attempts=4)


def test_cancel_at_admission_is_terminal_and_releases_only_admitted_attempts(tmp_path):
    store, runner = orchestrator(tmp_path, retry=1)
    released = []
    runner.attempt_admission = lambda *identity: "cancelled"
    runner.attempt_release = lambda *identity: released.append(identity)
    with pytest.raises(RunKilled):
        runner.run("cancelled")
    assert store.run("cancelled")["stop_reason"] == "cancelled"
    assert not store.episodes(run="cancelled")["rows"] and not released
    _, resumed = orchestrator(tmp_path, retry=1)
    with pytest.raises(RunKilled, match="cancelled"):
        resumed.resume("cancelled")
    assert not store.episodes(run="cancelled")["rows"]


def test_pause_after_last_admitted_attempt_finishes_instead_of_empty_pause(tmp_path):
    store, runner = orchestrator(tmp_path, competitor="oracle")
    state = dict(paused=False, released=0)

    def release(*identity):
        state["paused"] = True
        state["released"] += 1

    runner.attempt_admission = lambda *identity: "paused" if state["paused"] else None
    runner.attempt_release = release
    runner.run("last")
    assert state["released"] == 1
    assert store.run("last")["finished"] and store.run("last")["stop_reason"] is None


def test_admission_release_runs_even_if_recording_real_world_result_fails(tmp_path, monkeypatch):
    store, runner = orchestrator(tmp_path, competitor="oracle")
    admitted, released = [], []
    runner.attempt_admission = lambda *identity: admitted.append(identity)
    runner.attempt_release = lambda *identity: released.append(identity)

    def fail(row):
        assert row.passed and row.n_changes > 0
        raise OSError("result store unavailable")

    monkeypatch.setattr(store, "record_episode", fail)
    with pytest.raises(OSError, match="result store unavailable"):
        runner.run("record-failure")
    assert len(admitted) == 1 and admitted == released
    assert store.run("record-failure")["stop_reason"] == "worker_error"
