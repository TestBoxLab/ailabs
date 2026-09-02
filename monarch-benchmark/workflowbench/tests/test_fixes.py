"""Regression tests for the adversarial-review fixes:
1. harness crash in grade/record -> recorded row, not silent loss
2. crashed episode worker -> run raises, never marked finished
3. missing API key -> no pointless retries
4. Gemini-style absent-then-present cache field -> no absent flag
5. legacy passed gated on completed termination
"""
from __future__ import annotations

from pathlib import Path

import pytest

import wb_orchestrator.orchestrator as orch_mod
from legacy.importer import _row_from_summary
from tests.mock_openai import MockOpenAIServer
from tests.test_m1 import make_orch
from wb_arms import providers
from wb_arms.providers import Provider

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def mock_server(monkeypatch):
    server = MockOpenAIServer()
    monkeypatch.setenv("WB_MOCK_KEY", "mock-key")
    providers.register(Provider(
        key="mock", model_id="mock-1", key_env="WB_MOCK_KEY", adapter="openai",
        base_url=server.base_url, price_in=1.0, price_cached=0.1, price_out=2.0))
    yield server
    server.shutdown()
    providers.REGISTRY.pop("mock", None)


def test_grade_crash_records_harness_crash_row(tmp_path, mock_server, monkeypatch):
    def boom(task, s0, s1):
        raise RuntimeError("grader exploded")
    monkeypatch.setattr(orch_mod, "grade", boom)
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-gradecrash")
    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 1                                  # episode NOT lost
    assert rows[0]["termination"] == "infra:harness_crash"
    assert "grader exploded" in rows[0]["error"]
    assert rows[0]["passed"] is False


def test_worker_crash_fails_run_loudly(tmp_path, mock_server, monkeypatch):
    def die(self, run_id, arm, task, trial):
        raise RuntimeError("worker crashed hard")
    monkeypatch.setattr(orch_mod.Orchestrator, "_run_episode", die)
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:2]
    with pytest.raises(RuntimeError, match="worker crashed hard"):
        orch.run("run-workercrash")
    assert store.run("run-workercrash")["finished"] is None   # never marked done


def test_missing_key_is_not_retried(tmp_path, mock_server, monkeypatch):
    monkeypatch.delenv("WB_MOCK_KEY", raising=False)
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-nokey")
    rows = store.episodes(run=run_id)["rows"]
    assert rows[0]["termination"] == "infra:harness_crash"
    assert rows[0]["retries"] == 0                         # retrying can't help
    assert "not set" in rows[0]["error"]


def test_absent_first_cache_field_not_flagged(tmp_path, mock_server):
    mock_server.cache_mode = "absent_first"
    mock_server.n_tool_turns = 2
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-absentfirst")
    rows = store.episodes(run=run_id)["rows"]
    assert "cache_reporting=absent" not in rows[0]["flags"], rows[0]["flags"]
    assert rows[0]["tokens"]["cached"] > 0                 # later turns counted


def test_infra_excluded_from_pass_denominator(tmp_path, mock_server):
    # Episode 1: three attempts, all 429 -> infra. Episode 2: completes.
    mock_server.fail_requests = {1, 2, 3}
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:2]
    run_id = orch.run("run-infra-denom")
    a = store.status(run_id)["arms"]["bare/api/mock"]
    assert a["episodes"] == 2 and a["infra"] == 1 and a["non_infra"] == 1
    assert a["strict_pass_rate"] == 0.0        # 0/1 graded, NOT 0/2


def test_all_infra_pass_rate_is_none_not_zero(tmp_path, mock_server):
    mock_server.fail_requests = set(range(1, 20))
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-all-infra")
    a = store.status(run_id)["arms"]["bare/api/mock"]
    assert a["infra"] == 1 and a["non_infra"] == 0
    assert a["strict_pass_rate"] is None       # no graded episodes -> no rate


def test_resume_reattempts_infra_episodes(tmp_path, mock_server):
    mock_server.fail_requests = set(range(1, 20))
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    orch.run("run-infra-resume")
    rows = store.episodes(run="run-infra-resume")["rows"]
    assert rows[0]["termination"] == "infra:rate_limit"

    mock_server.fail_requests = set()          # the API recovered
    store2, orch2 = make_orch(tmp_path, k=1, concurrency=1)
    orch2.tasks = orch2.tasks[:1]
    orch2.resume("run-infra-resume")
    rows = store2.episodes(run="run-infra-resume")["rows"]
    assert len(rows) == 1                      # replaced, not duplicated
    assert rows[0]["termination"] == "completed"


def test_legacy_passed_requires_completed():
    rec = {"arm": "a", "model": "m", "status": "timeout", "task_id": "t",
           "position": 0, "replicate": 0,
           "canonical": {"strict_min": True, "strict_max": True,
                         "positive_passed": 1, "positive_total": 1,
                         "guard_violations": 0}}
    row = _row_from_summary(rec, "legacy/x", 0)
    assert row.termination == "timeout"
    assert row.passed is False                             # strict_min alone insufficient
