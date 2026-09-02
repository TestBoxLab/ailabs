"""M4/M2 tests: stats, report builder + audience gates, telemetry collector."""
from __future__ import annotations

import math

import pytest

from runner.schema import EpisodeRow, TokenUsage
from wb_report.report import GateError, build_report, gate_arms, load_audiences, render_md, write_report
from wb_results.store import Store
from wb_orchestrator.telemetry import TelemetryWriter, collect, read_events
from wb_stats.stats import cluster_bootstrap, mcnemar, mean_sem, paired_wl, pass_hat_k


def _row(task, arm, trial, passed, run="run-x", termination="completed",
         cost=0.01, prompt=1000, cached=700):
    return EpisodeRow(
        episode_id=f"{run}/{task}/{arm.replace('/', '_')}/t{trial}", run_id=run,
        task_id=task, arm=arm, trial=trial, passed=passed, assertions_passed=passed,
        invariant_passed=passed, invariant_declared=True, termination=termination,
        contract_sha256="abc123def4567890",
        tokens=TokenUsage(prompt=prompt, cached=cached, output=100), cost_usd=cost)


# -- stats --------------------------------------------------------------------

def test_mcnemar_continuity_corrected():
    r = mcnemar(9, 1)
    assert r["b"] == 9 and r["c"] == 1
    assert r["statistic"] == pytest.approx((abs(9 - 1) - 1) ** 2 / 10)
    assert r["p"] == pytest.approx(math.erfc(math.sqrt(4.9 / 2)), abs=1e-6)
    assert mcnemar(0, 0)["p"] == 1.0
    assert mcnemar(5, 5)["statistic"] < mcnemar(9, 1)["statistic"]


def test_pass_hat_k():
    rows = [ _row("t1", "a", i, i < 2).model_dump() for i in range(4) ]  # s=2, n=4
    r = pass_hat_k(rows, k=2)
    assert r["per_task"]["t1"] == pytest.approx(1 / 6)     # comb(2,2)/comb(4,2)
    r1 = pass_hat_k(rows, k=1)
    assert r1["per_task"]["t1"] == pytest.approx(0.5)
    # infra excluded, insufficient trials -> None, never a guess
    rows_infra = [_row("t2", "a", i, True, termination="infra:rate_limit").model_dump()
                  for i in range(4)]
    assert pass_hat_k(rows_infra, k=2)["per_task"] == {}


def test_paired_wl_and_infra_drop():
    a = [_row("t1", "A", 0, True), _row("t2", "A", 0, False),
         _row("t3", "A", 0, True), _row("t4", "A", 0, True, termination="infra:rate_limit")]
    b = [_row("t1", "B", 0, False), _row("t2", "B", 0, True),
         _row("t3", "B", 0, True), _row("t4", "B", 0, True)]
    r = paired_wl([x.model_dump() for x in a], [x.model_dump() for x in b])
    assert (r["wins"], r["losses"], r["both_pass"], r["neither_pass"]) == (1, 1, 1, 0)
    assert r["dropped_infra"] == 1 and r["pairs"] == 3


def test_cluster_bootstrap_deterministic():
    rows = [{"v": float(i % 2), "c": i % 3} for i in range(30)]
    r1 = cluster_bootstrap(rows, lambda r: r["v"], lambda r: r["c"], n_boot=200, seed=7)
    r2 = cluster_bootstrap(rows, lambda r: r["v"], lambda r: r["c"], n_boot=200, seed=7)
    assert r1 == r2
    assert r1["n_clusters"] == 3
    assert r1["ci95"][0] <= r1["mean"] <= r1["ci95"][1]


def test_mean_sem():
    r = mean_sem([1.0, 1.0, 1.0])
    assert r["mean"] == 1.0 and r["sem"] == 0.0
    assert mean_sem([])["mean"] is None


# -- report builder + gates ---------------------------------------------------

@pytest.fixture()
def seeded_store(tmp_path):
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-x", "cfg123", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["bare/api/kimi-k3", "monarch/stock@1.0",
                                                     "monarch/lab@deadbeef"], "k": 2, "n_tasks": 2,
                      "timeout_s": 600})
    for arm, passes in [("bare/api/kimi-k3", [True, False, True, True]),
                        ("monarch/stock@1.0", [True, True, False, True]),
                        ("monarch/lab@deadbeef", [True, True, True, True])]:
        i = 0
        for task in ("t1", "t2"):
            for trial in (0, 1):
                store.record_episode(_row(task, arm, trial, passes[i]))
                i += 1
    store.finish_run("run-x")
    return store


def test_audience_gate_allowlists():
    aud = load_audiences()
    assert set(aud) == {"internal", "public-rung2"}
    arms = ["bare/api/kimi-k3", "monarch/stock@1.0", "monarch/lab@deadbeef"]
    assert gate_arms(arms, "internal") == arms
    assert gate_arms(arms, "public-rung2") == ["monarch/stock@1.0"]
    with pytest.raises(GateError):
        gate_arms(arms, "nonexistent")


def test_report_internal_has_everything(seeded_store):
    rep = build_report(seeded_store, "run-x", audience="internal",
                       baseline_arm="bare/api/kimi-k3")
    assert sorted(rep["arms"]) == ["bare/api/kimi-k3", "monarch/lab@deadbeef", "monarch/stock@1.0"]
    md = render_md(rep)
    assert "DO NOT EXPORT" in md            # lab arm watermark
    assert "cost (USD)" in md               # internal sees dollars
    assert "src: workflowbench-synthetic@0.1" in md
    paired = [f for f in rep["figures"] if f["kind"] == "paired"]
    assert paired and all("mcnemar" in f for f in paired)
    for f in rep["figures"]:
        assert "source" in f and f["source"]["denominator"] > 0


def test_report_public_strips_at_query_level(seeded_store):
    rep = build_report(seeded_store, "run-x", audience="public-rung2")
    assert rep["arms"] == ["monarch/stock@1.0"]
    assert sorted(rep["arms_stripped_by_gate"]) == ["bare/api/kimi-k3", "monarch/lab@deadbeef"]
    md = render_md(rep)
    assert "kimi" not in md and "deadbeef" not in md   # gated arms never named publicly
    assert "2 arm(s) withheld" in md
    assert "cost (USD)" not in md            # public: ratios only, no dollars


def test_report_write_files(seeded_store, tmp_path):
    paths = write_report(seeded_store, "run-x", tmp_path, audience="internal")
    md = (tmp_path / "report-run-x-internal.md").read_text()
    assert "WorkflowBench report" in md
    assert (tmp_path / "report-run-x-internal.html").exists()
    assert set(paths) == {"md", "html"}


def test_gate_raises_when_nothing_renderable(tmp_path):
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-b", "cfg", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["bare/api/x"], "k": 1,
                      "n_tasks": 1, "timeout_s": 600})
    store.record_episode(_row("t1", "bare/api/x", 0, True, run="run-b"))
    with pytest.raises(GateError):
        build_report(store, "run-b", audience="public-rung2")


# -- telemetry ----------------------------------------------------------------

def test_telemetry_collect(tmp_path):
    w = TelemetryWriter(tmp_path / "events.jsonl", "ep1")
    w.emit("authoring", "turn_start", "2026-08-31T10:00:00Z")
    w.emit("authoring", "turn_end", "2026-08-31T10:00:10Z",
           tokens={"input": 500, "output": 50}, cost=0.002)
    w.emit("authoring", "workflow_saved", "2026-08-31T10:00:11Z")
    w.emit("execution", "engine_run_start", "2026-08-31T10:00:12Z")
    w.emit("execution", "step_dispatch", "2026-08-31T10:00:13Z")
    w.emit("execution", "gate_decision", "2026-08-31T10:00:14Z",
           decision="refused", reason="scope: gmail.write not granted")
    w.emit("execution", "step_dispatch", "2026-08-31T10:00:15Z")
    w.emit("execution", "retry", "2026-08-31T10:00:16Z")
    w.emit("execution", "engine_run_end", "2026-08-31T10:00:20Z")

    c = collect(read_events(tmp_path / "events.jsonl"))
    assert c["phases"]["authoring"].turns == 1
    assert c["phases"]["authoring"].tokens_input == 500
    assert c["phases"]["authoring"].cost_usd == pytest.approx(0.002)
    assert c["phases"]["authoring"].wall_clock_s == pytest.approx(10.0)
    assert c["phases"]["execution"].tool_calls == 2
    assert c["phases"]["execution"].wall_clock_s == pytest.approx(8.0)
    assert len(c["gate_refusals"]) == 1
    assert "scope" in c["gate_refusals"][0]["reason"]
    assert c["retries"] == 1
    assert c["workflow_outcome"] == "workflow_saved"
    assert c["unknown_events"] == []
