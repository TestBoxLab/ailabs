"""SOTA-hardening edge cases: spend accounting under failure, protocol
malformations, interruptible backoff, regrade provenance, input validation."""
from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from tests.test_m1 import make_orch
from wb_orchestrator.orchestrator import Orchestrator, RunKilled, regrade
from wb_results.store import Store
from wb_arms.api_loop import ArmResult, InfraError

ROOT = Path(__file__).resolve().parents[1]


# -- spend accounting survives every failure mode -----------------------------

def test_spend_survives_timeout(tmp_path, mock_server):
    mock_server.delay_s = 0.4
    store, orch = make_orch(tmp_path, k=1, concurrency=1, timeout_s=0.3)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-timeout-spend")
    r = store.episodes(run=run_id)["rows"][0]
    assert r["termination"] == "timeout"
    assert r["tokens"]["prompt"] > 0            # turn 0's tokens not evaporated
    assert r["cost_usd"] > 0


def test_spend_accumulates_across_retry_attempts(tmp_path, mock_server):
    # Attempt 1 does 2 model turns (reqs 1-2) then req 3 is rate-limited;
    # attempt 2 (reqs 4-6) completes. Every turn's tokens must reach the row.
    mock_server.n_tool_turns = 2
    mock_server.fail_requests = {3}
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-retry-spend")
    r = store.episodes(run=run_id)["rows"][0]
    assert r["termination"] == "completed" and r["retries"] == 1
    # attempt1: 700+900; attempt2: 700+900+1100 (mock's deterministic formula)
    assert r["tokens"]["prompt"] == 4300
    assert "spend_includes_failed_attempts" in r["flags"]
    turns = Path(store.artifacts(r["episode_id"])["turns"]).read_text().strip().splitlines()
    assert len(turns) == 5                      # failed attempt's turns in the artifact


def test_spend_survives_exhausted_infra(tmp_path, mock_server):
    # Attempt 1 completes turn 0 (req 1) then req 2 fails; attempts 2 and 3
    # fail on their first request. Partial spend from attempt 1 is recorded.
    mock_server.fail_requests = {2, 3, 4}
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-exhaust-spend")
    r = store.episodes(run=run_id)["rows"][0]
    assert r["termination"] == "infra:rate_limit" and r["retries"] == 2
    assert r["tokens"]["prompt"] == 700         # attempt 1's turn 0
    assert r["cost_usd"] > 0


def test_zero_cost_infra_partial_preserves_failure_evidence_in_store(tmp_path, mock_server):
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    partial = ArmResult(turn_log=[{'monarch': {'recipeRunId': 'recipe-run'}},
                                  {'authoring_cancel_error': {'ok': False}}],
                        flags=['cost_missing'])
    error = InfraError('infra:harness_crash', 'poll HTTP 500', retryable=False)
    error.partial = partial
    arm = type('Arm', (), {'name': 'prototype', 'provider_key': None,
                           'run': lambda self, ep, deadline: (_ for _ in ()).throw(error)})()
    orch.arm_wrapper = lambda _: arm
    run_id = orch.run('run-zero-cost-evidence')
    row = store.episodes(run=run_id)['rows'][0]
    assert row['flags'] == ['cost_missing']
    turns = Path(store.artifacts(row['episode_id'])['turns']).read_text()
    assert 'recipeRunId' in turns and 'authoring_cancel_error' in turns


# -- protocol malformations don't kill episodes -------------------------------

def test_malformed_tool_args_fed_back_to_model(tmp_path, mock_server):
    mock_server.n_tool_turns = 2
    mock_server.bad_args_requests = {1}         # first tool call: truncated JSON
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-badargs")
    r = store.episodes(run=run_id)["rows"][0]
    assert r["termination"] == "completed"      # episode survived, model recovered
    assert r["error"] is None


def test_empty_choices_is_retryable_infra(tmp_path, mock_server):
    mock_server.empty_choices_requests = {1}    # anomaly once, then healthy
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-emptychoices")
    r = store.episodes(run=run_id)["rows"][0]
    assert r["termination"] == "completed" and r["retries"] == 1


def test_cache_overreport_flagged_and_cost_clamped(tmp_path, mock_server):
    mock_server.cache_mode = "overreport"
    mock_server.n_tool_turns = 2
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-overreport")
    r = store.episodes(run=run_id)["rows"][0]
    assert "cache_overreport" in r["flags"]
    # clamped cost: never cheaper than all-cached, never negative
    assert r["cost_usd"] >= r["tokens"]["prompt"] * 0.1 / 1e6


# -- abort during backoff is prompt --------------------------------------------

def test_abort_interrupts_retry_backoff(tmp_path, mock_server):
    mock_server.fail_requests = set(range(1, 20))
    mock_server.retry_after_header = False      # forces 2^attempt backoff sleeps
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    t0 = time.monotonic()
    threading.Timer(0.3, orch._abort.set).start()
    with pytest.raises(RunKilled):
        orch.run("run-abort-backoff")
    assert time.monotonic() - t0 < 1.5          # did not sit out the 2s backoff
    rows = store.episodes(run="run-abort-backoff")["rows"]
    assert rows and rows[0]["termination"] == "infra:rate_limit"   # resumable


# -- partial writes visible ----------------------------------------------------

def test_partial_writes_before_failure_flagged(tmp_path, mock_server):
    task = json.loads(sorted((ROOT / "tasks").glob("*.json"))[0].read_text())
    a = task["info"]["assertions"][0]
    rid = a.get("contact_id") or a.get("record_id")
    mock_server.override_tool_call = {
        "name": "api_fetch",
        "args": {"method": "PATCH",
                 "url": f"https://yourinstance.salesforce.com/services/data/v61.0/sobjects/Contact/{rid}",
                 "body": json.dumps({"Department": "Sabotage"})}}
    mock_server.fail_requests = {2, 4, 6}       # each attempt: write, then die
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-partialwrite")
    r = store.episodes(run=run_id)["rows"][0]
    assert r["termination"] == "infra:rate_limit"
    assert r["n_changes"] > 0
    assert "partial_writes_before_failure" in r["flags"]


# -- regrade provenance --------------------------------------------------------

def test_regrade_refuses_contract_drift(tmp_path, mock_server):
    suite = tmp_path / "suite"
    suite.mkdir()
    src = sorted((ROOT / "tasks").glob("*.json"))[0]
    shutil.copy(src, suite / src.name)
    store, _ = make_orch(tmp_path, k=1, concurrency=1)
    orch = Orchestrator(store, suite, ["mock"], 1, out_dir=tmp_path / "out",
                        provider_concurrency=1)
    run_id = orch.run("run-drift-regrade")

    res = regrade(store, run_id, suite)
    assert res["regraded"] == 1 and res["contract_drift"] == 0

    task = json.loads((suite / src.name).read_text())
    task["info"]["assertions"][0]["value"] = "TAMPERED"
    (suite / src.name).write_text(json.dumps(task))
    res2 = regrade(store, run_id, suite)
    assert res2["regraded"] == 0 and res2["contract_drift"] == 1   # refused, loud


# -- input validation ----------------------------------------------------------

def test_orchestrator_rejects_bad_inputs(tmp_path, mock_server):
    store = Store(tmp_path / "wb.sqlite3")
    with pytest.raises(ValueError, match="k must be"):
        Orchestrator(store, ROOT / "tasks", ["mock"], 0, out_dir=tmp_path)
    with pytest.raises(ValueError, match="duplicate arms"):
        Orchestrator(store, ROOT / "tasks", ["mock", "mock"], 1, out_dir=tmp_path)
    with pytest.raises(ValueError, match="unknown arm"):
        Orchestrator(store, ROOT / "tasks", ["gpt-9-turbo"], 1, out_dir=tmp_path)
