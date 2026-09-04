"""Feature 006: the metrics behind the HTML report, and the page itself.

Every test here is offline: seeded stores in tmp_path, no key, no network, no
money. Fixtures are modelled on tests/test_m4.py::seeded_store.
"""
from __future__ import annotations

import pytest

from runner.schema import EpisodeRow, PhaseMetrics, TokenUsage
from wb_results.store import Store


def _row(task, arm, trial, passed, run="run-h", termination="completed",
         cost=0.01, prompt=1000, cached=700, cache_write=0, output=100,
         phases=None, flags=None, error=None, unexpected=None,
         assertions=None, tool_calls=0, tokens=True):
    """One attempt row. Defaults mirror test_m4.py; every extra is optional so a
    test can name exactly the field it is about."""
    return EpisodeRow(
        episode_id=f"{run}/{task}/{arm.replace('/', '_')}/t{trial}", run_id=run,
        task_id=task, arm=arm, trial=trial, passed=passed,
        assertions_passed=passed if assertions is None else assertions,
        invariant_passed=passed, invariant_declared=True, termination=termination,
        contract_sha256="abc123def4567890",
        unexpected_changes=unexpected or [],
        n_changes=len(unexpected or []),
        phases=phases if phases is not None else {"run": PhaseMetrics(
            turns=3, tool_calls=tool_calls, cost_usd=cost, wall_clock_s=10.0)},
        tool_calls=tool_calls,
        flags=flags or [],
        error=error,
        tokens=TokenUsage(prompt=prompt, cached=cached, cache_write=cache_write,
                          output=output) if tokens else None,
        cost_usd=cost)


@pytest.fixture()
def four_arm_store(tmp_path):
    """2 tasks x 4 competitors x 2 repetitions = 16 attempts.

    - `alpha`  passes 3 of 4 (t2/1 fails on an unexpected change)
    - `beta`   4 attempts, 1 of them `infra:rate_limit`, 2 of the other 3 pass
    - `gamma`  1 `agent_error` and 1 `timeout`; passes t1 twice
    - `oracle` passes everything except task `t2`, which nobody passes
    """
    store = Store(tmp_path / "wb.sqlite3")
    arms = ["alpha", "beta", "gamma", "oracle"]
    store.create_run("run-h", "cfg006", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": arms, "k": 2, "n_tasks": 2,
                      "timeout_s": 600, "plan": "smoke-006", "product": "simulated-apps",
                      "price_tables": {"anthropic": {"name": "anthropic",
                                                     "prices_verified": "2026-09-01"}}})
    rows = [
        # alpha: t1 both pass, t2 one pass one fail (unexpected change)
        _row("t1", "alpha", 0, True), _row("t1", "alpha", 1, True),
        _row("t2", "alpha", 0, False, assertions=True,
             unexpected=[{"path": "crm.contacts[3].email"}]),
        _row("t2", "alpha", 1, True),
        # beta: one infra attempt; 2 of the remaining 3 pass
        _row("t1", "beta", 0, True), _row("t1", "beta", 1, True),
        _row("t2", "beta", 0, False, termination="infra:rate_limit", cost=0.002),
        _row("t2", "beta", 1, False, assertions=False),
        # gamma: an agent error and a timeout
        _row("t1", "gamma", 0, True), _row("t1", "gamma", 1, True),
        _row("t2", "gamma", 0, False, termination="agent_error",
             error="<script>alert(1)</script>"),
        _row("t2", "gamma", 1, False, termination="timeout"),
        # oracle: t1 always, t2 never (the task everyone fails)
        _row("t1", "oracle", 0, True), _row("t1", "oracle", 1, True),
        _row("t2", "oracle", 0, False, assertions=False),
        _row("t2", "oracle", 1, False, assertions=False),
    ]
    for r in rows:
        store.record_episode(r)
    store.finish_run("run-h")
    return store


@pytest.fixture()
def phase_store(tmp_path):
    """One Monarch-shaped competitor: authoring + execution + model:opus-4.8
    phases, `questions_asked=2` on one attempt and `no_workflow` on another."""
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-p", "cfgp06", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch", "alpha"], "k": 1,
                      "n_tasks": 2, "mode": "create-run"})
    def monarch_phases(auth_s, auth_c, exec_s, exec_c, model_c):
        return {"authoring": PhaseMetrics(turns=2, cost_usd=auth_c, wall_clock_s=auth_s),
                "execution": PhaseMetrics(turns=1, cost_usd=exec_c, wall_clock_s=exec_s),
                "model:opus-4.8": PhaseMetrics(turns=2, cost_usd=model_c, wall_clock_s=None)}
    store.record_episode(_row("t1", "monarch", 0, True, run="run-p", cost=0.30,
                              phases=monarch_phases(12.0, 0.20, 3.0, 0.10, 0.20)))
    store.record_episode(_row("t2", "monarch", 0, False, run="run-p", cost=0.20,
                              flags=["questions_asked=2", "no_workflow"],
                              phases=monarch_phases(8.0, 0.15, 1.0, 0.05, 0.15)))
    store.record_episode(_row("t1", "alpha", 0, True, run="run-p"))
    store.record_episode(_row("t2", "alpha", 0, True, run="run-p"))
    store.finish_run("run-p")
    return store


@pytest.fixture()
def zero_pass_store(tmp_path):
    """A competitor that passes nothing: cost per passed attempt is n/a."""
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-z", "cfgz06", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["null-arm"], "k": 1, "n_tasks": 2})
    for task in ("t1", "t2"):
        store.record_episode(_row(task, "null-arm", 0, False, run="run-z", assertions=False))
    store.finish_run("run-z")
    return store
