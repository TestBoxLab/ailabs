"""M4/M2 tests: stats, report builder, telemetry collector."""
from __future__ import annotations

import math

import pytest

from runner.schema import EpisodeRow, TokenUsage
from wb_report.report import GateError, build_report, render_md, write_report
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
                     {"suite_dir": "tasks", "arms": ["kimi-k3/api", "monarch",
                                                     "monarch-lab"], "k": 2, "n_tasks": 2,
                      "timeout_s": 600})
    for arm, passes in [("kimi-k3/api", [True, False, True, True]),
                        ("monarch", [True, True, False, True]),
                        ("monarch-lab", [True, True, True, True])]:
        i = 0
        for task in ("t1", "t2"):
            for trial in (0, 1):
                store.record_episode(_row(task, arm, trial, passes[i]))
                i += 1
    store.finish_run("run-x")
    return store


def test_one_report_carries_every_competitor_and_its_dollars(seeded_store):
    """There is one report: no competitor is filtered out of it, lab builds
    included, and cost is always the exact figure rather than a ratio."""
    rep = build_report(seeded_store, "run-x",
                       baseline_arm="kimi-k3/api")
    assert sorted(rep["arms"]) == ["kimi-k3/api", "monarch", "monarch-lab"]
    md = render_md(rep)
    assert "cost (USD)" in md
    assert "monarch-lab" in md
    assert "src: workflowbench-synthetic@0.1" in md
    paired = [f for f in rep["figures"] if f["kind"] == "paired"]
    assert paired and all("mcnemar" in f for f in paired)
    for f in rep["figures"]:
        assert "source" in f and f["source"]["denominator"] > 0


def test_report_names_stop_reason(seeded_store):
    seeded_store.set_stop_reason("run-x", "cost_ceiling")
    md = render_md(build_report(seeded_store, "run-x"))
    assert "stopped: cost_ceiling" in md


def test_report_write_files(seeded_store, tmp_path):
    paths = write_report(seeded_store, "run-x", tmp_path)
    md = (tmp_path / "report-run-x.md").read_text()
    assert "WorkflowBench report" in md
    assert (tmp_path / "report-run-x.html").exists()
    assert set(paths) == {"md", "html"}


def test_a_round_of_one_non_monarch_competitor_renders(tmp_path):
    """This used to raise GateError: the public allowlist held `monarch` alone,
    so a round without it had nothing left to render. There is one report now,
    and a single model is a round like any other."""
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-b", "cfg", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["kimi-k3/api"], "k": 1,
                      "n_tasks": 1, "timeout_s": 600})
    store.record_episode(_row("t1", "kimi-k3/api", 0, True, run="run-b"))
    rep = build_report(store, "run-b")
    assert rep["arms"] == ["kimi-k3/api"]
    assert "kimi-k3/api" in render_md(rep)


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


# -- source line: price table + missing cost (T045) ---------------------------

@pytest.fixture()
def monarch_store(tmp_path):
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-m", "cfg456", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch@abc1234", "oracle"],
                      "k": 1, "n_tasks": 3, "timeout_s": 600,
                      "price_tables": {"monarch-team-bedrock": {
                          "name": "monarch-team-bedrock",
                          "provider": "bedrock", "region": "us-east-1",
                          "prices_verified": "2026-09-03", "models": []}}})
    for i, task in enumerate(("t1", "t2", "t3")):
        row = _row(task, "monarch@abc1234", 0, True, run="run-m")
        if i == 0:
            row.flags = ["cost_missing"]
        store.record_episode(row)
        store.record_episode(_row(task, "oracle", 0, True, run="run-m"))
    store.finish_run("run-m")
    return store


def test_source_line_carries_price_table_and_missing_cost(monarch_store):
    md = render_md(build_report(monarch_store, "run-m"))
    assert "price table monarch-team-bedrock@2026-09-03" in md
    assert "cost missing on 1/3 attempts" in md


def test_source_line_unchanged_without_price_tables_or_monarch(tmp_path):
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-n", "cfg", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["kimi-k3/api"], "k": 1,
                      "n_tasks": 1, "timeout_s": 600})
    store.record_episode(_row("t1", "kimi-k3/api", 0, True, run="run-n"))
    md = render_md(build_report(store, "run-n"))
    assert "price table" not in md and "cost missing" not in md
    assert "`src: workflowbench-synthetic@0.1 · v0.1 · n=1 · kimi-k3/api · run-n`" in md


# -- 004 T014: the run-only source line ---------------------------------------

RUN_ONLY_SENTENCE = ("Monarch executed a fixed known-correct workflow; the other competitors "
                     "did the whole task from the request text.")


@pytest.fixture()
def run_only_store(tmp_path):
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-r", "cfg789", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch@abc1234", "oracle"],
                      "k": 1, "n_tasks": 2, "timeout_s": 600, "mode": "run-only",
                      "excluded_tasks": {"t3": "checker_failed", "t4": "not_attempted"}})
    for task in ("t1", "t2"):
        store.record_episode(_row(task, "monarch@abc1234", 0, True, run="run-r"))
        store.record_episode(_row(task, "oracle", 0, True, run="run-r"))
    store.finish_run("run-r")
    return store


def test_run_only_source_line_states_the_exclusions_and_what_was_compared(run_only_store):
    md = render_md(build_report(run_only_store, "run-r"))
    assert "2 tasks excluded (checker_failed, not_attempted)" in md
    assert RUN_ONLY_SENTENCE in md


def test_create_run_source_line_says_nothing_about_run_only(monarch_store):
    md = render_md(build_report(monarch_store, "run-m"))
    assert "excluded" not in md and RUN_ONLY_SENTENCE not in md
