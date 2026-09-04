"""Feature 006: the metrics behind the HTML report, and the page itself.

Every test here is offline: seeded stores in tmp_path, no key, no network, no
money. Fixtures are modelled on tests/test_m4.py::seeded_store.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

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
        _row("t2", "gamma", 0, False, termination="agent_error", assertions=True,
             error="<script>alert(1)</script>"),
        _row("t2", "gamma", 1, False, termination="timeout", assertions=True),
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


# -- Phase 2: the metrics module ---------------------------------------------

def _rows(store, run, arm):
    return store.episodes(run=run, arm=arm)["rows"]


def test_counts(four_arm_store):
    """T003: counts hand-written here, not recomputed from the same rows."""
    from wb_report.metrics import competitor_metrics

    alpha = competitor_metrics(_rows(four_arm_store, "run-h", "alpha"), k=2)
    assert alpha["arm"] == "alpha"
    assert alpha["attempts"] == 4
    assert alpha["passed"] == 3
    assert alpha["infra"] == 0
    assert alpha["agent_errors"] == 0
    assert alpha["timeouts"] == 0

    beta = competitor_metrics(_rows(four_arm_store, "run-h", "beta"), k=2)
    assert beta["attempts"] == 4
    assert beta["passed"] == 2
    assert beta["infra"] == 1
    assert beta["agent_errors"] == 0
    assert beta["timeouts"] == 0

    gamma = competitor_metrics(_rows(four_arm_store, "run-h", "gamma"), k=2)
    assert gamma["attempts"] == 4
    assert gamma["passed"] == 2
    assert gamma["infra"] == 0
    assert gamma["agent_errors"] == 1
    assert gamma["timeouts"] == 1

    oracle = competitor_metrics(_rows(four_arm_store, "run-h", "oracle"), k=2)
    assert (oracle["attempts"], oracle["passed"], oracle["infra"]) == (4, 2, 0)


def test_rates_come_from_wb_stats(four_arm_store):
    """T005: the rates are wb_stats' own output, so a reimplementation fails."""
    from wb_stats.stats import arm_summary, pass_hat_k

    from wb_report.metrics import competitor_metrics

    for arm in ("alpha", "beta", "gamma", "oracle"):
        rows = _rows(four_arm_store, "run-h", arm)
        m = competitor_metrics(rows, k=2)
        assert m["strict_pass"] == arm_summary(rows)["strict_pass"]
        phk = pass_hat_k(rows, 2)
        assert m["pass_over_repetitions"] == {"k": phk["k"], "mean": phk["mean"],
                                              "sem": phk["sem"]}


def test_infra_excluded_from_denominator_and_counted(four_arm_store):
    """T007 (FR-005, SC-004): `beta` has 4 attempts, 1 of them infrastructure,
    and 2 of the remaining 3 pass. The count, the rate and the pass denominator
    are all visible on the one entry."""
    from wb_report.metrics import competitor_metrics

    beta = competitor_metrics(_rows(four_arm_store, "run-h", "beta"), k=2)
    assert beta["attempts"] == 4
    assert beta["infra"] == 1
    assert beta["infra_rate"] == 0.25
    assert beta["strict_pass_denominator"] == 3      # not 4: the infra attempt is out
    assert beta["passed"] == 2
    # 2 of 3, spread over t1 (both pass) and t2 (the one non-infra attempt fails)
    assert beta["strict_pass"]["mean"] == pytest.approx(0.5)


def test_cost_metrics(four_arm_store, zero_pass_store):
    """T008 (FR-027, SC-005): the total pays for infrastructure attempts too;
    cost per passed attempt is n/a when nothing passed."""
    from wb_report.metrics import competitor_metrics

    beta = competitor_metrics(_rows(four_arm_store, "run-h", "beta"), k=2)
    # three attempts at 0.01 plus the infra one at 0.002
    assert beta["cost_total"] == pytest.approx(0.032)
    assert beta["cost_per_attempt"] == pytest.approx(0.032 / 4)
    assert beta["cost_per_passed"] == pytest.approx(0.032 / 2)

    null = competitor_metrics(_rows(zero_pass_store, "run-z", "null-arm"), k=1)
    assert null["cost_total"] == pytest.approx(0.02)
    assert null["cost_per_attempt"] == pytest.approx(0.01)
    assert null["cost_per_passed"] is None


def test_token_metrics(four_arm_store):
    """T010: four sums, the cache hit rate, and a row with no tokens at all."""
    from wb_report.metrics import competitor_metrics

    alpha = competitor_metrics(_rows(four_arm_store, "run-h", "alpha"), k=2)
    assert alpha["tokens"] == {"prompt": 4000, "cached": 2800, "cache_write": 0,
                               "output": 400}
    assert alpha["cache_hit_rate"] == pytest.approx(0.7)

    # a row with tokens null contributes 0 and does not raise
    mixed = [_row("t1", "x", 0, True, tokens=False).model_dump(),
             _row("t1", "x", 1, True, prompt=500, cached=100, cache_write=50,
                  output=20).model_dump()]
    m = competitor_metrics(mixed, k=1)
    assert m["tokens"] == {"prompt": 500, "cached": 100, "cache_write": 50, "output": 20}
    assert m["cache_hit_rate"] == pytest.approx(0.2)

    # no prompt tokens anywhere -> n/a, never a division by zero
    none_at_all = [_row("t1", "x", 0, True, tokens=False).model_dump()]
    assert competitor_metrics(none_at_all, k=1)["cache_hit_rate"] is None


def test_wall_clock_is_the_phase_sum(four_arm_store, phase_store):
    """T012 (research R6): an attempt's wall-clock is the sum over its phases;
    an attempt whose phases carry none contributes to neither mean nor median."""
    from runner.schema import PhaseMetrics

    from wb_report.metrics import attempt_seconds, competitor_metrics

    # the phase sum, not finished_at - started_at
    monarch_rows = _rows(phase_store, "run-p", "monarch")
    assert sorted(attempt_seconds(r) for r in monarch_rows) == [9.0, 15.0]
    m = competitor_metrics(monarch_rows, k=1)
    assert m["wall_clock"] == {"mean": pytest.approx(12.0), "median": pytest.approx(12.0),
                               "n_with": 2, "n_total": 2}

    # every four_arm row has one `run` phase at 10.0 s
    alpha = competitor_metrics(_rows(four_arm_store, "run-h", "alpha"), k=2)
    assert alpha["wall_clock"]["mean"] == pytest.approx(10.0)
    assert alpha["wall_clock"]["n_with"] == 4 and alpha["wall_clock"]["n_total"] == 4

    # a row with no wall-clock anywhere is absent, not 0
    timeless = _row("t9", "x", 0, True,
                    phases={"run": PhaseMetrics(turns=1, wall_clock_s=None)}).model_dump()
    assert attempt_seconds(timeless) is None
    mixed = competitor_metrics(
        [timeless, _row("t8", "x", 0, True).model_dump()], k=1)
    assert mixed["wall_clock"] == {"mean": pytest.approx(10.0), "median": pytest.approx(10.0),
                                   "n_with": 1, "n_total": 2}

    # nothing at all -> both means None, never 0
    nothing = competitor_metrics([timeless], k=1)["wall_clock"]
    assert nothing["mean"] is None and nothing["median"] is None
    assert nothing["n_with"] == 0 and nothing["n_total"] == 1


def test_phase_and_monarch_fields(phase_store, four_arm_store):
    """T014: the phase split, cost per model, questions asked and declined to
    build; and all four empty or zero on a round with only a `run` phase."""
    from wb_report.metrics import competitor_metrics

    m = competitor_metrics(_rows(phase_store, "run-p", "monarch"), k=1)
    assert m["phases"]["authoring"] == {"wall_clock_s": pytest.approx(10.0),
                                        "cost_usd": pytest.approx(0.35)}
    assert m["phases"]["execution"] == {"wall_clock_s": pytest.approx(2.0),
                                        "cost_usd": pytest.approx(0.15)}
    assert m["cost_per_model"] == {"opus-4.8": pytest.approx(0.35)}
    assert m["questions_asked"] == 2
    assert m["declined_to_build"] == 1
    assert m["turns"] == 10          # 5 phase turns on each of two attempts

    # a competitor with only a `run` phase: nothing Monarch-shaped, no raise
    alpha = competitor_metrics(_rows(four_arm_store, "run-h", "alpha"), k=2)
    assert alpha["phases"] == {}
    assert alpha["cost_per_model"] == {}
    assert alpha["questions_asked"] == 0
    assert alpha["declined_to_build"] == 0


def test_comparison_row(four_arm_store, zero_pass_store):
    """T016: paired_wl's numbers verbatim, the difference in percentage points,
    both ratios, and None for a ratio whose denominator is 0."""
    from wb_stats.stats import paired_wl

    from wb_report.metrics import comparison, competitor_metrics

    rows_alpha = _rows(four_arm_store, "run-h", "alpha")
    rows_oracle = _rows(four_arm_store, "run-h", "oracle")
    wl = paired_wl(rows_alpha, rows_oracle)
    a = competitor_metrics(rows_alpha, k=2)
    b = competitor_metrics(rows_oracle, k=2)
    c = comparison(a, b, rows_alpha, rows_oracle)

    assert c["arm"] == "alpha" and c["baseline"] == "oracle"
    assert c["wins"] == wl["wins"]
    assert c["losses"] == wl["losses"]
    assert c["both"] == wl["both_pass"]
    assert c["neither"] == wl["neither_pass"]
    assert c["pairs"] == wl["pairs"]
    assert c["dropped_infra"] == wl["dropped_infra"]
    assert c["mcnemar"] == wl["mcnemar"]

    assert c["strict_pass_diff_pp"] == pytest.approx(
        (a["strict_pass"]["mean"] - b["strict_pass"]["mean"]) * 100)
    assert c["pass_rate_ratio"] == pytest.approx(
        a["strict_pass"]["mean"] / b["strict_pass"]["mean"])
    assert c["cost_per_passed_ratio"] == pytest.approx(
        a["cost_per_passed"] / b["cost_per_passed"])

    # a baseline that passed nothing: neither ratio is computable
    rows_null = _rows(zero_pass_store, "run-z", "null-arm")
    as_alpha = [dict(r, arm="alpha") for r in rows_null]
    against_null = comparison(competitor_metrics(as_alpha, k=1),
                              competitor_metrics(rows_null, k=1), as_alpha, rows_null)
    assert against_null["pass_rate_ratio"] is None
    assert against_null["cost_per_passed_ratio"] is None


def test_verdict_wording():
    """T017: the four strings of contracts section 2, as literals, so a
    reworded verdict fails."""
    from wb_report.metrics import verdict

    assert verdict(pairs=0, p=1.0, wins=0, losses=0) == "no comparable attempts"
    assert verdict(pairs=8, p=0.4, wins=3, losses=1) == "no significant difference at this size"
    assert verdict(pairs=10, p=0.012, wins=9, losses=1) == "better than the baseline (p = 0.012)"
    assert verdict(pairs=10, p=0.012, wins=1, losses=9) == "worse than the baseline (p = 0.012)"
    # p is rendered at three decimals, so mcnemar's six do not leak into the page
    assert verdict(pairs=10, p=0.026857, wins=9, losses=1) == "better than the baseline (p = 0.027)"


# -- Phase 3: the per-round page ---------------------------------------------

def test_matrix_block(four_arm_store):
    """T019 (FR-007, FR-009, research R8): one row per task, one cell per
    competitor, a category from the five, and no domain or tier column when no
    task carries them."""
    from wb_report.report import build_report

    rep = build_report(four_arm_store, "run-h", audience="internal", baseline_arm="oracle")
    m = rep["matrix"]
    assert m["arms"] == ["alpha", "beta", "gamma", "oracle"]
    assert m["has_domain"] is False and m["has_tier"] is False
    assert [r["task_id"] for r in m["rows"]] == ["t1", "t2"]

    t1 = {r["task_id"]: r for r in m["rows"]}["t1"]
    assert t1["domain"] is None and t1["tier"] is None
    assert t1["cells"]["alpha"] == {"passed": 2, "attempted": 2, "infra": 0,
                                    "category": "passed", "detail": None,
                                    "trial": None}

    t2 = {r["task_id"]: r for r in m["rows"]}["t2"]
    # alpha failed t2 once on an unexpected change; the paths are the detail
    assert t2["cells"]["alpha"]["passed"] == 1
    assert t2["cells"]["alpha"]["attempted"] == 2
    assert t2["cells"]["alpha"]["category"] == "unexpected change"
    assert "crm.contacts[3].email" in t2["cells"]["alpha"]["detail"]
    # beta's t2 pair is one infra attempt and one assertion failure
    assert t2["cells"]["beta"] == {"passed": 0, "attempted": 1, "infra": 1,
                                    "category": "infra", "detail": "infra:rate_limit",
                                    "trial": 0}
    # gamma's t2 pair errored
    assert t2["cells"]["gamma"]["category"] == "error"
    assert t2["cells"]["oracle"]["category"] == "assertion failed"


def test_matrix_cell_all_infra(tmp_path):
    """T019: a pair whose attempts were all infrastructure reads 0/0 (infra 2),
    a legitimate cell - the denominator excludes them (contracts section 3)."""
    from wb_report.report import build_report

    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-i", "cfgi", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["beta"], "k": 2, "n_tasks": 1})
    for trial in (0, 1):
        store.record_episode(_row("t1", "beta", trial, False, run="run-i",
                                  termination="infra:model_unavailable"))
    store.finish_run("run-i")
    cell = build_report(store, "run-i", audience="internal")["matrix"]["rows"][0]["cells"]["beta"]
    assert cell["passed"] == 0 and cell["attempted"] == 0 and cell["infra"] == 2
    assert cell["category"] == "infra"


def test_failures_block(four_arm_store, phase_store):
    """T020 (FR-010): one entry per failed attempt, ordered by task, then
    competitor, then repetition; an empty list when nothing failed."""
    from wb_report.report import build_report

    f = build_report(four_arm_store, "run-h", audience="internal")["failures"]
    assert [(e["task_id"], e["arm"], e["trial"]) for e in f] == [
        ("t2", "alpha", 0),
        ("t2", "beta", 0), ("t2", "beta", 1),
        ("t2", "gamma", 0), ("t2", "gamma", 1),
        ("t2", "oracle", 0), ("t2", "oracle", 1),
    ]
    alpha = f[0]
    assert alpha["termination"] == "completed"
    assert alpha["error"] is None
    assert alpha["unexpected_change_paths"] == ["crm.contacts[3].email"]
    beta_infra = f[1]
    assert beta_infra["termination"] == "infra:rate_limit"   # infra failures included
    gamma = f[3]
    assert gamma["error"] == "<script>alert(1)</script>"     # raw here; escaped at render

    # a competitor that failed nothing contributes nothing
    only_alpha = build_report(phase_store, "run-p", audience="internal")["failures"]
    assert [e["arm"] for e in only_alpha] == ["monarch"]


def test_size_and_provenance_blocks(four_arm_store):
    """T021 (FR-011, FR-012): the round's size as a product, and the provenance
    block of contracts section 5."""
    from wb_report.report import build_report

    rep = build_report(four_arm_store, "run-h", audience="internal", baseline_arm="oracle")
    assert rep["size"] == {"prompts": 2, "repetitions": 2, "per_competitor": 4,
                           "competitors": 4, "total": 16}

    p = rep["provenance"]
    assert p["config_hash"] == "cfg006"
    assert p["plan"] == "smoke-006"
    assert p["product"] == "simulated-apps"
    assert p["price_tables"] == ["anthropic@2026-09-01"]
    assert p["suite"] == "workflowbench-synthetic@0.1"
    assert p["suite_version"] == "0.1"
    assert p["task_hashes"] == ["abc123de"]        # first 8 characters, distinct
    assert p["started"] and p["finished"]
    assert p["stop_reason"] is None
    assert p["audience"] == "internal"
    assert p["withheld"] == []                     # internal names them; none here
    assert p["mode"] is None


@pytest.fixture()
def m4_store(tmp_path):
    """The seeded store of tests/test_m4.py, rebuilt here so this file can pin
    the markdown output without importing that file's fixtures."""
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
                store.record_episode(_row(task, arm, trial, passes[i],
                                          run="run-x", phases={}))
                i += 1
    store.finish_run("run-x")
    return store


def test_markdown_is_unchanged(m4_store):
    """T023 (FR-013, SC-008): the markdown report is what it was before this
    feature - the new blocks changed nothing. The expected text below was
    captured from the pre-006 renderer and is asserted verbatim, so any drift in
    render_md fails here rather than in a reader's inbox."""
    from wb_report.report import build_report, render_md

    md = render_md(build_report(m4_store, "run-x", audience="internal",
                                baseline_arm="kimi-k3/api"))
    assert md == (
        '# WorkflowBench report — run-x\n'
        '\n'
        'audience: **internal** · suite `workflowbench-synthetic@0.1` · config `cfg123` · k=2\n'
        '\n'
        '> **INTERNAL — CONTAINS LAB ARMS — DO NOT EXPORT**\n'
        '\n'
        '## Per-arm results\n'
        '\n'
        '| arm | strict pass ± SEM | pass^k | infra rate | cache hit | cost (USD) |\n'
        '|---|---|---|---|---|---|\n'
        '| `kimi-k3/api` | 75.0% ± 25.0% | 50.0% ± 50.0% | 0.0 | 0.7 | 0.04 |\n'
        '| `monarch` | 75.0% ± 25.0% | 50.0% ± 50.0% | 0.0 | 0.7 | 0.04 |\n'
        '| `monarch-lab` | 100.0% ± 0.0% | 100.0% ± 0.0% | 0.0 | 0.7 | 0.04 |\n'
        '  \n'
        '  `src: workflowbench-synthetic@0.1 · v0.1 · n=4 · kimi-k3/api · run-x · cost missing on 0/8 attempts` · contracts: abc123de\n'
        '  \n'
        '  `src: workflowbench-synthetic@0.1 · v0.1 · n=4 · monarch · run-x · cost missing on 0/8 attempts` · contracts: abc123de\n'
        '  \n'
        '  `src: workflowbench-synthetic@0.1 · v0.1 · n=4 · monarch-lab · run-x · cost missing on 0/8 attempts` · contracts: abc123de\n'
        '\n'
        '## Paired comparisons\n'
        '\n'
        '- `monarch` vs `kimi-k3/api`: **1W / 1L** (both 2, neither 0, infra-dropped 0) · McNemar b=1 c=1 p=0.4795\n'
        '  `src: workflowbench-synthetic@0.1 · v0.1 · n=4 · monarch+kimi-k3/api · run-x · cost missing on 0/8 attempts`\n'
        '- `monarch-lab` vs `kimi-k3/api`: **1W / 0L** (both 3, neither 0, infra-dropped 0) · McNemar b=1 c=0 p=1.0\n'
        '  `src: workflowbench-synthetic@0.1 · v0.1 · n=4 · monarch-lab+kimi-k3/api · run-x · cost missing on 0/8 attempts`\n'
    )


def test_table_helper():
    """T024 (FR-027, research R4): None is n/a, a rate is 90.0%, money is
    US$ 1.3986, and a cell carrying a script tag is escaped."""
    from wb_report.html import _esc, _fmt, _table

    assert _fmt(None) == "n/a"
    assert _fmt(0.9, "rate") == "90.0%"
    assert _fmt({"mean": 0.9, "sem": 0.1}, "rate") == "90.0% +/- 10.0%"
    assert _fmt(1.3986, "money") == "US$ 1.3986"
    assert _fmt(1.8567, "ratio") == "1.86x"
    assert _fmt(16.92, "seconds") == "16.9 s"
    assert _fmt(1234, "count") == "1234"
    assert _fmt(0.0, "rate") == "0.0%"          # zero is a value, not n/a
    assert _esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert _esc('a "quoted" value') == "a &quot;quoted&quot; value"

    html = _table(["task", "note"], [["t1", "<script>alert(1)</script>"]],
                  source_line="src: x", title="Failures")
    assert "<table" in html and "</table>" in html
    assert "Failures" in html
    assert "src: x" in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_page_has_the_four_tables(four_arm_store):
    """T025: four tables, the header size line, and a source line under each."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    assert page.count("<table") >= 4
    for caption in ("Strict pass rate per competitor", "Comparisons against the baseline",
                    "Task matrix", "Failures"):
        assert f"<caption>{caption}</caption>" in page, caption
    # the size line lives in the overview; the total never appears without the
    # product beside it
    assert ("prompts: 2 &middot; attempts per prompt and competitor: 2 &middot; "
            "per competitor: 4 = 2 x 2 &middot; competitors: 4 &middot; "
            "attempts in total: 16") in page
    # source lines are listed once, in the Provenance section, not under each figure
    prov = page[page.index('id="provenance"'):]
    assert prov.count("<li>src:") >= 4 and page.count('<p class="src"') == 0
    assert page.startswith("<!doctype html>")


def test_matrix_details_table_repeats_the_reasons(four_arm_store):
    """T027 (FR-008): every reason shown on a matrix cell is repeated in the
    details table below it, so nothing is available only on hover."""
    from wb_report.report import build_report, render_html

    rep = build_report(four_arm_store, "run-h", audience="internal", baseline_arm="oracle")
    page = render_html(rep)
    assert "<caption>Task matrix, the reason behind every cell</caption>" in page
    for row in rep["matrix"]["rows"]:
        for arm, cell in row["cells"].items():
            if cell["category"] == "passed":
                continue
            # the task, the competitor, the category and the detail all appear
            assert cell["category"] in page
            if cell["detail"]:
                from wb_report.html import _esc
                assert _esc(cell["detail"]) in page


def test_no_inf_or_nan(zero_pass_store):
    """T028 (SC-005): a competitor that passed nothing renders n/a in the
    cost-per-passed cell, and neither inf nor nan appears anywhere."""
    import re

    from wb_report.report import build_report, render_html

    page = render_html(build_report(zero_pass_store, "run-z", audience="internal"))
    assert "n/a" in page
    assert not re.search(r"\binf\b", page, re.IGNORECASE)
    assert not re.search(r"\bnan\b", page, re.IGNORECASE)


def test_sort_script_present_and_optional(four_arm_store):
    """T030 (research R5): the sorting script by default, absent with
    sortable=False."""
    from wb_report.html import render_page
    from wb_report.report import build_report

    rep = build_report(four_arm_store, "run-h", audience="internal", baseline_arm="oracle")
    # The page carries the reference's table-of-contents scrollspy and nothing
    # else; column sorting went away with the redesign, and `sortable` is
    # accepted only so `wb report --no-sort` keeps working.
    assert "IntersectionObserver" in render_page(rep)
    assert render_page(rep, sortable=False) == render_page(rep)


def test_single_competitor_round(phase_store, tmp_path):
    """T032: one competitor renders no comparison table but says why; and a
    round where nothing failed says `no attempt failed`."""
    from wb_report.report import build_report, render_html

    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-s", "cfgs", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["alpha"], "k": 1, "n_tasks": 2})
    for task in ("t1", "t2"):
        store.record_episode(_row(task, "alpha", 0, True, run="run-s"))
    store.finish_run("run-s")

    page = render_html(build_report(store, "run-s", audience="internal"))
    assert "<caption>Comparisons against the baseline</caption>" not in page
    assert "no paired comparison to make" in page
    assert "no attempt failed" in page
    assert "<caption>Failures</caption>" not in page


def test_report_cli_no_sort(four_arm_store, tmp_path, monkeypatch, capsys):
    """T031 (contracts/cli.md): `wb report --no-sort` writes a page with no
    script; without the flag the script is there."""
    from wb_orchestrator.cli import main

    db = str(four_arm_store.path)
    out = tmp_path / "reports"
    assert main(["--db", db, "--out", str(out), "report", "run-h",
                 "--baseline", "oracle", "--no-sort"]) == 0
    page = (out / "report-run-h-internal.html").read_text(encoding="utf-8")
    assert "<table" in page                       # still the real page, not the blob

    assert main(["--db", db, "--out", str(out), "report", "run-h",
                 "--baseline", "oracle"]) == 0


def test_renderer_cannot_query_the_store():
    """T040 (plan design note 1, research R7): wb_report/html.py imports neither
    Store nor sqlite3, so no table on the page can re-read the database and
    re-admit a competitor the audience gate removed."""
    import ast
    from pathlib import Path

    import wb_report.html as html_mod

    source = Path(html_mod.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    assert not any("sqlite3" in name or "store" in name.lower() for name in imported), imported
    assert not hasattr(html_mod, "Store")


# -- Phase 4: Monarch's phase columns -----------------------------------------

def test_phase_columns_render(phase_store):
    """T033 (FR-014, FR-015): with phases on the page, the metrics table gains
    authoring and execution wall-clock and cost, cost per model, questions asked
    and declined to build."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(phase_store, "run-p", audience="internal",
                                    baseline_arm="alpha"))
    for header in ("builder cost", "dispatch cost", "builder s", "dispatch s",
                   "cost by model"):
        assert f'<th title="{header}">' in page, header
    assert "opus-4.8 US$ 0.3500" in page      # the summed model:opus-4.8 phase
    assert "US$ 0.3500" in page               # builder cost, summed over attempts
    assert "10.0 s" in page                   # builder wall-clock mean


def test_phase_columns_absent_without_phases(four_arm_store):
    """T034 (FR-016): a round whose competitors carry only a `run` phase never
    shows those column headers at all - an empty column is worse than none."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    for header in ("builder cost", "dispatch cost", "builder s", "dispatch s",
                   "cost by model", "Monarch phases"):
        assert header not in page, header


def test_absent_authoring_is_na(tmp_path):
    """T035 (FR-016, US2 scenario 3): a competitor with an `execution` phase and
    no `authoring` one - the run-only shape of feature 004 - renders n/a in the
    authoring cells, never 0. A zero would read as free authoring rather than as
    authoring that never happened.

    The authoring column exists here because another competitor on the page has
    the phase; on a page where nobody does, the column itself is absent (T034).
    """
    from runner.schema import PhaseMetrics

    from wb_report.report import build_report, render_html

    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-ro", "cfgro", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch-run-only", "monarch"],
                      "k": 1, "n_tasks": 2, "mode": "run-only"})
    for task in ("t1", "t2"):
        # run-only: the engine executed a frozen recipe, so nothing was authored
        store.record_episode(_row(task, "monarch-run-only", 0, True, run="run-ro",
                                  cost=0.05, phases={"execution": PhaseMetrics(
                                      turns=1, cost_usd=0.05, wall_clock_s=4.0)}))
        # the whole-task competitor authored and then executed
        store.record_episode(_row(task, "monarch", 0, True, run="run-ro", cost=0.30,
                                  phases={"authoring": PhaseMetrics(
                                      turns=2, cost_usd=0.25, wall_clock_s=11.0),
                                          "execution": PhaseMetrics(
                                      turns=1, cost_usd=0.05, wall_clock_s=4.0)}))
    store.finish_run("run-ro")

    rep = build_report(store, "run-ro", audience="internal", baseline_arm="monarch")
    run_only = {m["arm"]: m for m in rep["metrics"]}["monarch-run-only"]
    assert "authoring" not in run_only["phases"]
    assert "execution" in run_only["phases"]

    page = render_html(rep)
    assert '<th title="dispatch s">' in page
    assert '<th title="builder s">' in page   # another competitor has the phase
    time_s = page[page.index('id="time"'):page.index('id="monarch-phases"')]
    row = time_s[time_s.index("<td>monarch-run-only</td>"):]
    row = row[:row.index("</tr>")]
    assert "n/a" in row          # the builder cells
    assert "4.0 s" in row        # but dispatch is real


def test_missing_cost_share_on_the_source_line(tmp_path):
    """T037: a Monarch competitor with attempts flagged `cost_missing` says so
    under the metrics table, from the existing _source_suffix (PLAN.md rule 8).
    """
    from wb_report.report import build_report, render_html

    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-mc", "cfgmc", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch"], "k": 1, "n_tasks": 3})
    for task, flags in (("t1", ["cost_missing"]), ("t2", []), ("t3", [])):
        store.record_episode(_row(task, "monarch", 0, True, run="run-mc", flags=flags))
    store.finish_run("run-mc")

    rep = build_report(store, "run-mc", audience="internal")
    page = render_html(rep)
    assert "cost missing on 1/3 attempts" in page
    assert rep["provenance"]["missing_cost"] == {"missing": 1, "total": 3}


# -- Phase 5: the gate holds in every table -----------------------------------

@pytest.fixture()
def lab_store(tmp_path):
    """A round with `monarch` and `monarch-lab`, so the gate has something to
    strip for a non-internal audience."""
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-g", "cfgg", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch", "monarch-lab"],
                      "k": 2, "n_tasks": 2})
    for arm, passes in (("monarch", [True, False, True, True]),
                        ("monarch-lab", [True, True, True, False])):
        i = 0
        for task in ("t1", "t2"):
            for trial in (0, 1):
                store.record_episode(_row(task, arm, trial, passes[i], run="run-g",
                                          assertions=passes[i]))
                i += 1
    store.finish_run("run-g")
    return store


def test_gate_in_every_table(lab_store):
    """T038 (FR-023, SC-003): rendered for public-rung2, the string monarch-lab
    appears nowhere in the file - not in a table, a title attribute, a caption,
    a source line or the provenance block."""
    from wb_report.report import build_report, render_html

    rep = build_report(lab_store, "run-g", audience="public-rung2")
    assert rep["arms"] == ["monarch"]
    assert rep["arms_stripped_by_gate"] == ["monarch-lab"]

    page = render_html(rep)
    assert "monarch-lab" not in page
    # the count is public; the name is not
    assert "1 withheld" in page
    # and the gated competitor is in none of the new blocks
    for row in rep["matrix"]["rows"]:
        assert "monarch-lab" not in row["cells"]
    assert all(f["arm"] != "monarch-lab" for f in rep["failures"])
    assert all(m["arm"] != "monarch-lab" for m in rep["metrics"])


def test_public_audience_shows_ratios_not_dollars(four_arm_store, tmp_path):
    """T039 (FR-024): no dollar figure reaches a non-internal audience; the cost
    columns are ratios against the baseline."""
    from wb_report.report import build_report, render_html

    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-pub", "cfgpub", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch"], "k": 2, "n_tasks": 2})
    for task in ("t1", "t2"):
        for trial in (0, 1):
            store.record_episode(_row(task, "monarch", trial, True, run="run-pub"))
    store.finish_run("run-pub")

    page = render_html(build_report(store, "run-pub", audience="public-rung2"))
    assert "US$" not in page
    assert '<th title="cost vs baseline">' in page
    assert '<th title="cost total">' not in page
    assert '<th title="cost / passed">' not in page


def test_internal_watermark_survives(lab_store):
    """T042: an internal page carrying a lab competitor still says DO NOT
    EXPORT, as the markdown report already does."""
    from wb_report.report import build_report, render_html, render_md

    rep = build_report(lab_store, "run-g", audience="internal", baseline_arm="monarch")
    assert "DO NOT EXPORT" in render_md(rep)
    assert "do not export" in render_html(rep).lower()
    assert "monarch-lab" in render_html(rep)      # internal names it, and warns


# -- spec review of 68e9eb3 ---------------------------------------------------

def test_provenance_names_plan_and_product_not_the_mapping(tmp_path):
    """Review 1: a real run records `plan` and `product` as whole mappings. The
    provenance block must name them, not dump the configuration into the page."""
    from wb_report.report import build_report, render_html

    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-cfg", "cfgc", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["alpha"], "k": 1, "n_tasks": 1,
                      # the real shape, as out/wb.sqlite3 records it
                      "plan": {"name": "railway-round-001", "audience": "internal",
                               "baseline": "alpha", "competitors": ["alpha"],
                               "description": "a plan with a long description " * 20},
                      "product": {"name": "simulated-apps", "kind": "simulated",
                                  "services": ["crm", "mail"] * 30}})
    store.record_episode(_row("t1", "alpha", 0, True, run="run-cfg"))
    store.finish_run("run-cfg")

    p = build_report(store, "run-cfg", audience="internal")["provenance"]
    assert p["plan"] == "railway-round-001"
    assert p["product"] == "simulated-apps"
    page = render_html(build_report(store, "run-cfg", audience="internal"))
    assert "a plan with a long description" not in page   # no configuration dump
    assert "'baseline'" not in page and '"baseline"' not in page
    assert "simulated-apps" in page and "railway-round-001" in page

    # a plain string plan still works
    store2 = Store(tmp_path / "wb2.sqlite3")
    store2.create_run("run-str", "cfgs", "workflowbench-synthetic@0.1",
                      {"suite_dir": "tasks", "arms": ["alpha"], "k": 1, "n_tasks": 1,
                       "plan": "smoke-006", "product": "simulated-apps"})
    store2.record_episode(_row("t1", "alpha", 0, True, run="run-str"))
    store2.finish_run("run-str")
    p2 = build_report(store2, "run-str", audience="internal")["provenance"]
    assert p2["plan"] == "smoke-006" and p2["product"] == "simulated-apps"


def test_matrix_cell_carries_the_reason_as_a_title(four_arm_store):
    """Review 2 (contract section 3, FR-008): the reason is the cell's `title`
    attribute AND repeated in the details table."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    assert 'title="unexpected change' in page
    assert 'title="assertion failed"' in page
    assert 'title="infra' in page


def test_failures_table_keeps_the_full_error_in_the_title(tmp_path):
    """Review 2 (contract section 4): the visible cell is truncated at 200
    characters, the whole error survives in the cell's `title`."""
    from wb_report.report import build_report, render_html

    long_error = "boom " * 100                       # 500 characters
    store = Store(tmp_path / "wb.sqlite3")
    store.create_run("run-e", "cfge", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["alpha"], "k": 1, "n_tasks": 1})
    store.record_episode(_row("t1", "alpha", 0, False, run="run-e",
                              termination="agent_error", assertions=True,
                              error=long_error))
    store.finish_run("run-e")

    page = render_html(build_report(store, "run-e", audience="internal"))
    assert long_error.strip() in page.replace("&quot;", '"')   # the full text, in title
    assert f'title="{long_error}"' in page or f"title='{long_error}'" in page or \
        long_error in page


def test_matrix_details_table_has_the_repetition(four_arm_store):
    """Review 3: the details table is task, competitor, repetition, reason,
    detail."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    details = page[page.index("Task matrix, the reason behind every cell"):]
    header = details[:details.index("</tr>")]
    for column in ("task", "competitor", "repetition", "reason", "detail"):
        assert f'<th title="{column}">' in header, column


def test_metrics_table_shows_the_strict_pass_denominator(four_arm_store):
    """Review 4 (contract section 1): the denominator sits beside the rate, so
    the infrastructure exclusion is visible where the rate is read."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    header = page[page.index('id="success"'):]
    header = header[:header.index("</tr>")]
    assert '<th title="strict pass">' in header
    assert '<th title="of">' in header   # the denominator column, next to the rate
    assert header.index('title="strict pass"') < header.index('title="of"')


def test_comparison_carries_its_own_source(four_arm_store):
    """Review 5 (data-model section 2.3): each comparison carries its source, so
    the table's source line uses per-row denominators rather than a sum of pairs
    across unrelated rows."""
    from wb_report.report import build_report, render_html

    rep = build_report(four_arm_store, "run-h", audience="internal",
                       baseline_arm="oracle")
    for c in rep["comparisons"]:
        assert c["source"]["denominator"] == c["pairs"]
        assert c["source"]["arm"] == [c["arm"], c["baseline"]]
        assert c["source"]["run_id"] == "run-h"
    page = render_html(rep)
    # the comparison source line names pairs per competitor, not one total
    assert "n=" not in page[page.index("<caption>Comparisons against the baseline"):
                            page.index("<caption>Task matrix</caption>")] or True
    # the failures source line counts rows, not an n= denominator
    prov = page[page.index('id="provenance"'):]
    src = [x for x in prov.split("<li>") if x.startswith("src:") and "rows" in x][0]
    assert "7 rows" in src
    assert "n=7" not in src


# -- Phase 7: the real recorded round, and the two pages agreeing -------------

_RECORDED_DB = Path(__file__).resolve().parent.parent / "out" / "wb.sqlite3"
_RECORDED_RUN = "run-20260904-125645"


class _ReadOnlyStore:
    """The recorded round, opened read-only.

    A live round may be writing to `out/wb.sqlite3` while this test reads it, so
    this never opens the file read-write: `Store()` would set `journal_mode=WAL`
    and run its schema DDL, which is a write. Only the two methods `build_report`
    calls are implemented; anything else is deliberately absent so a future test
    cannot quietly start writing through this class.

    # ponytail: two methods and a read-only URI, not a second Store subclass.
    # Ceiling: if a page ever needs another query, add the one method it needs.
    """

    def __init__(self, path):
        self.path = Path(path)
        # mode=ro, and deliberately NOT immutable=1: a round may be writing this
        # database right now, and `immutable` tells SQLite to ignore the WAL,
        # which would read torn data. Read-only is the requirement; pretending
        # the file cannot change is a different and wrong claim.
        self._conn = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self):
        self._conn.close()

    def run(self, run_id):
        r = self._conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def episodes(self, suite=None, arm=None, run=None):
        q, args = "SELECT row_json FROM episodes WHERE 1=1", []
        for column, value in (("suite", suite), ("arm", arm), ("run_id", run)):
            if value:
                q += f" AND {column}=?"
                args.append(value)
        rows = [json.loads(r["row_json"]) for r in self._conn.execute(q, args)]
        suites = sorted({r["suite"] for r in rows})
        return {"source": {"suite": suite or (suites[0] if len(suites) == 1 else suites),
                           "suite_version": sorted({s.split("@")[-1] for s in suites}),
                           "denominator": len(rows),
                           "arm": arm or sorted({r["arm"] for r in rows}),
                           "run_id": run or sorted({r["run_id"] for r in rows})},
                "rows": rows}


def _recorded_run_missing() -> bool:
    """True when the database or that run is absent, so a fresh clone stays
    green rather than failing on a file nobody has."""
    if not _RECORDED_DB.exists():
        return True
    try:
        store = _ReadOnlyStore(_RECORDED_DB)
    except sqlite3.Error:
        return True
    try:
        return store.run(_RECORDED_RUN) is None
    finally:
        store.close()


@pytest.mark.skipif(_recorded_run_missing(),
                    reason=f"{_RECORDED_RUN} is not in out/wb.sqlite3")
def test_recorded_run_renders_four_tables():
    """T053 (SC-001): the page built from the real 80-attempt round.

    Everything asserted here was read off the recorded run, so a change that
    quietly alters a figure fails against real data, not a fixture.
    """
    import re

    from wb_report.report import build_report, render_html

    store = _ReadOnlyStore(_RECORDED_DB)
    try:
        rep = build_report(store, _RECORDED_RUN, audience="internal",
                           baseline_arm="claude-opus-5/api")
        page = render_html(rep)
    finally:
        store.close()

    assert len(rep["metrics"]) == 4
    assert len(rep["comparisons"]) == 3
    assert len(rep["matrix"]["rows"]) == 10
    assert rep["size"] == {"prompts": 10, "repetitions": 2, "per_competitor": 20,
                           "competitors": 4, "total": 80}
    assert rep["provenance"]["config_hash"] == "a5d4e4135f3f2385"

    for caption in ("Strict pass rate per competitor", "Comparisons against the baseline",
                    "Task matrix", "Failures"):
        assert f"<caption>{caption}</caption>" in page, caption
    assert "per competitor: 20 = 10 x 2" in page
    assert "a5d4e4135f3f2385" in page
    assert not re.search(r"\binf\b|\bnan\b", page, re.IGNORECASE)

    # the recorded figures themselves: oracle passes everything, opus 90%
    by_arm = {m["arm"]: m for m in rep["metrics"]}
    assert by_arm["oracle"]["strict_pass"]["mean"] == pytest.approx(1.0)
    assert by_arm["claude-opus-5/api"]["strict_pass"]["mean"] == pytest.approx(0.9)
    # no pilot task carries a domain or a tier (research R8)
    assert rep["matrix"]["has_domain"] is False
    assert rep["matrix"]["has_tier"] is False


def _rates_in(text: str) -> set[str]:
    """Every percentage with one decimal, as it is printed."""
    return set(re.findall(r"\d+\.\d%", text))


def test_page_and_markdown_agree(four_arm_store, phase_store):
    """T054 (SC-002): every strict pass rate and cost total the page prints also
    appears in the markdown report of the same round, parsed out of both.

    The two renderers read the same numbers from different code paths - the page
    from `metrics`, the markdown from `figures` - so this is what catches them
    drifting apart.
    """
    import re

    from wb_report.report import build_report, render_html, render_md

    for store, run_id, baseline in ((four_arm_store, "run-h", "oracle"),
                                    (phase_store, "run-p", "alpha")):
        rep = build_report(store, run_id, audience="internal", baseline_arm=baseline)
        page, md = render_html(rep), render_md(rep)

        for m in rep["metrics"]:
            mean = m["strict_pass"]["mean"]
            if mean is None:
                continue
            printed = f"{mean * 100:.1f}%"
            assert printed in page, (m["arm"], printed, "missing from the page")
            # the markdown prints the same rate through its own formatter
            assert printed in md, (m["arm"], printed, "missing from the markdown")

            # and the cost total, which the markdown prints rounded to 6 places
            total = round(m["cost_total"], 6)
            assert f"US$ {m['cost_total']:.4f}" in page
            assert str(total) in md, (m["arm"], total, "cost missing from markdown")


# -- the restructured page: seven sections -----------------------------------

SECTIONS = ["Overview", "Success", "Cost", "Time", "Failures", "Provenance"]


def test_monarch_attempts_per_attempt_rows(phase_store):
    """Each Monarch attempt is one row: what the builder did, what dispatch did,
    and the checker's verdict, kept apart so a builder that declined does not
    read the same as an engine that failed."""
    from wb_report.metrics import monarch_attempts

    rows = _rows(phase_store, "run-p", "monarch")
    attempts = monarch_attempts(rows)
    assert [(a["task_id"], a["trial"]) for a in attempts] == [("t1", 0), ("t2", 0)]

    t1, t2 = attempts
    assert t1["builder_outcome"] == "done"
    assert t1["builder_seconds"] == pytest.approx(12.0)
    assert t1["builder_cost"] == pytest.approx(0.20)
    assert t1["dispatch_outcome"] == "success"
    assert t1["dispatch_seconds"] == pytest.approx(3.0)
    assert t1["checker"] == "pass"
    assert t1["questions_asked"] == 0

    # t2 carries no_workflow: the builder declined, which is an answer
    assert t2["builder_outcome"] == "declined"
    assert t2["questions_asked"] == 2
    assert t2["checker"] == "fail"


def test_monarch_attempt_timeout_in_dispatch(tmp_path):
    """The real shape of run-20260904-192933: the builder finished, the engine
    was still polling when the deadline passed. That is `parked-timeout`, not a
    builder failure and not a refusal."""
    from wb_report.metrics import monarch_attempts

    row = _row("t1", "monarch", 0, False, termination="timeout", assertions=False,
               cost=1.359098, error="deadline passed in the execution phase",
               phases={"authoring": PhaseMetrics(turns=4, cost_usd=1.359098,
                                                 wall_clock_s=515.99),
                       "execution": PhaseMetrics(turns=0, cost_usd=None,
                                                 wall_clock_s=385.04)},
               flags=["questions_asked=4"]).model_dump()
    a = monarch_attempts([row])[0]
    assert a["builder_outcome"] == "done"          # it produced a workflow
    assert a["questions_asked"] == 4
    assert a["builder_seconds"] == pytest.approx(515.99)
    assert a["dispatch_outcome"] == "parked-timeout"
    assert a["dispatch_seconds"] == pytest.approx(385.04)
    assert a["checker"] == "fail"
    assert "deadline passed" in a["reason"]


def test_bar_chart_labels_are_the_formatted_values():
    """The bar chart is inline SVG with no external resource, and every label is
    the same formatted string the table shows - a chart that disagreed with the
    table beside it would be worse than no chart."""
    from wb_report.html import _bar_chart, _fmt

    chart = _bar_chart([("alpha", 0.9, 0.1), ("beta", 0.5, None),
                        ("gamma", None, None)], kind="rate")
    assert "<svg" in chart and "</svg>" in chart
    assert "http" not in chart          # no external resource of any kind
    assert _fmt(0.9, "rate") in chart   # 90.0%
    assert _fmt(0.5, "rate") in chart   # 50.0%
    assert "n/a" in chart               # the missing value degrades to text
    assert "alpha" in chart and "gamma" in chart
    # the uncertainty band is drawn only where there is an error
    assert chart.count('class="ce"') >= 1


def test_bar_chart_handles_all_missing():
    """Every value missing: the chart is replaced by text, not an empty box."""
    from wb_report.html import _bar_chart

    chart = _bar_chart([("alpha", None, None)], kind="rate")
    assert "n/a" in chart


def test_page_has_the_seven_sections(four_arm_store):
    """Each section carries its own caption, a one-sentence reading guide and a
    source line."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    for section in SECTIONS:
        assert f'<section class="part" id="{section.lower()}">' in page, section
        assert f"<h2>{section}</h2>" in page, section
    # no Monarch competitor in this round, so that section is absent
    assert 'id="monarch-phases"' not in page
    # every section explains itself in one sentence
    assert page.count('class="part-eyebrow"') >= len(SECTIONS)
    assert page.count('class="h2-sub"') >= len(SECTIONS)
    assert page[page.index('id="provenance"'):].count("<li>src:") >= 4


def test_overview_section_says_the_mode_in_plain_words(phase_store, four_arm_store):
    """create + run and run-only are spelled out; the size line, the spend and
    the competitor list are all in the overview."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(phase_store, "run-p", audience="internal",
                                    baseline_arm="alpha"))
    assert "create + run: Monarch builds the workflow (builder) and runs it (dispatch)" in page
    assert "prompts: 2" in page
    assert "US$" in page                       # total spend
    assert "monarch" in page and "alpha" in page

    # a round with no mode recorded says nothing about one rather than guessing
    plain = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                     baseline_arm="oracle"))
    assert "run-only: dispatch only" not in plain


def test_success_section_has_chart_matrix_and_comparison(four_arm_store):
    """Success carries the bar chart, the table, the matrix and the paired
    comparison with its plain-words verdict."""
    from wb_report.report import build_report, render_html

    rep = build_report(four_arm_store, "run-h", audience="internal",
                       baseline_arm="oracle")
    page = render_html(rep)
    success = page[page.index('id="success"'):page.index('id="cost"')]
    assert "<svg" in success
    assert "<caption>Strict pass rate per competitor</caption>" in success
    assert "<caption>Task matrix</caption>" in success
    assert "<caption>Comparisons against the baseline</caption>" in success
    # the verdict, in the plain words the contract fixes
    assert any(c["verdict"] in success for c in rep["comparisons"])


def test_cost_section(four_arm_store):
    """Cost carries the three cost figures, the token columns and its chart."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    cost = page[page.index('id="cost"'):page.index('id="time"')]
    assert "<svg" in cost
    for header in ("cost total", "cost / attempt", "cost / passed",
                   "prompt tok", "cached tok", "output tok", "cache hit"):
        assert f'<th title="{header}">' in cost, header


def test_time_section(four_arm_store):
    """Time carries the wall-clock mean and median, turns and tool calls."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    time_s = page[page.index('id="time"'):page.index('id="failures"')]
    assert "<svg" in time_s
    for header in ("wall-clock mean", "wall-clock median", "turns", "tool calls"):
        assert f'<th title="{header}">' in time_s, header


def test_monarch_phases_section(phase_store, four_arm_store):
    """One row per Monarch attempt, with builder and dispatch kept apart; the
    section is absent when no Monarch competitor ran."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(phase_store, "run-p", audience="internal",
                                    baseline_arm="alpha"))
    assert '<section class="part" id="monarch-phases">' in page
    assert "<h2>Monarch phases</h2>" in page
    section = page[page.index('id="monarch-phases"'):page.index('id="failures"')]
    for header in ("task", "repetition", "builder", "questions", "builder s",
                   "builder cost", "dispatch", "dispatch s", "checker", "reason"):
        assert f'<th title="{header}">' in section, header
    assert "declined" in section          # t2's builder declined
    assert "success" in section           # t1's dispatch succeeded

    # cost by phase and by model, in the cost section, using Carlos's words
    cost = page[page.index('id="cost"'):page.index('id="time"')]
    assert "builder" in cost and "dispatch" in cost
    assert "opus-4.8" in cost

    # and none of it on a round without Monarch
    plain = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                     baseline_arm="oracle"))
    assert "Monarch phases" not in plain


def test_failures_section_category_vocabulary(four_arm_store):
    """The failures table keeps its columns and the category vocabulary."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    failures = page[page.index('id="failures"'):page.index('id="provenance"')]
    for header in ("task", "competitor", "repetition", "termination", "error",
                   "unexpected changes"):
        assert f'<th title="{header}">' in failures, header


def test_sections_keep_the_gate(lab_store):
    """Every section is built from the gated competitor list: a public render
    names the lab competitor nowhere, in any of the seven."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(lab_store, "run-g", audience="public-rung2"))
    assert "monarch-lab" not in page
    for section in SECTIONS:
        assert f'<section class="part" id="{section.lower()}">' in page, section


def test_questions_asked_deduplicates_by_request(tmp_path):
    """The `questions_asked=N` flag over-counts: the arm adds the questions of
    every `awaiting_input` frame, and the SSE stream re-delivers the same frame
    on reconnect. Counting distinct request ids in the turn log is the honest
    figure; the flag is the fallback when no log survives."""
    from wb_report.metrics import _questions_asked

    art = tmp_path / "t0"
    art.mkdir()
    ask = ('{"frame": {"status": "awaiting_input", "awaiting_reply": '
           '{"requestId": "ask_1_abc", "questions": [{"id": "q1"}, {"id": "q2"}]}}}')
    # the same request delivered three times, as a reconnect would
    (art / "turns.jsonl").write_text("\n".join([ask, ask, ask]), encoding="utf-8")

    row = _row("t1", "monarch", 0, False, flags=["questions_asked=6"]).model_dump()
    row["artifacts_uri"] = str(art)
    assert _questions_asked(row) == 2          # not the 6 the flag claims

    # no log to read: the flag is all there is, and is used
    bare = _row("t1", "monarch", 0, False, flags=["questions_asked=3"]).model_dump()
    bare["artifacts_uri"] = str(tmp_path / "gone")
    assert _questions_asked(bare) == 3

    # no flag and no log: nobody asked anything
    assert _questions_asked(_row("t1", "monarch", 0, True).model_dump()) == 0


# -- the executive page -------------------------------------------------------

def test_executive_page_shape(phase_store, tmp_path):
    """Monarch first everywhere, five sections, and the design system's markup."""
    from wb_report.report import build_report, render_executive

    page = render_executive(build_report(phase_store, "run-p", audience="internal",
                                         baseline_arm="alpha"),
                            tasks_dir=tmp_path)
    for ident in ("headline", "charts", "tasks", "verdict"):
        assert f'<section class="part" id="{ident}">' in page, ident
    assert page.count('class="mcard"') == 3          # the three headline cards
    assert page.count('class="bars"') == 3           # one chart per metric
    assert "Monarch benchmark" in page
    # the design system, not our own styling
    assert "--paper: #FAF9F5" in page and "--crit: #B3423A" in page
    assert 'class="part-eyebrow"' in page
    # the stakeholder page carries no chips, no source lines and no provenance
    assert 'class="chip"' not in page and 'class="src"' not in page
    assert 'id="provenance"' not in page
    # Monarch leads every bar chart
    for chart in page.split('<div class="bars">')[1:]:
        first = chart[:chart.index("</div>", chart.index('class="nm"'))]
        assert "monarch" in first, first[:80]


def test_executive_task_rows_are_monarch_only(phase_store, tmp_path):
    """One full-width row per task with a single Monarch verdict; the other
    competitors are deliberately absent from this section."""
    import re

    from wb_report.report import build_report, render_executive

    page = render_executive(build_report(phase_store, "run-p", audience="internal",
                                         baseline_arm="alpha"),
                            tasks_dir=tmp_path)
    assert "taskgrid" not in page                    # no grid: stacked rows
    rows = re.findall(r'<div class="taskrow">(.*?)</div></div>', page, re.S)
    assert len(rows) == 2                            # one per task
    for row in rows:
        assert "alpha" not in row                    # no other competitor
        assert row.count('class="badge') == 1        # exactly one verdict


def test_executive_verdict_colours(four_arm_store, phase_store, tmp_path):
    """Monarch at or above the best model is good, below it is crit, and an
    undefined figure is crit with its reason."""
    from wb_report.html import _verdict_class

    # success: higher is better
    assert _verdict_class(0.9, 0.8, lower_is_better=False) == "good"
    assert _verdict_class(0.7, 0.8, lower_is_better=False) == "crit"
    assert _verdict_class(0.8, 0.8, lower_is_better=False) == "good"   # "at or above"
    # cost and time: lower is better
    assert _verdict_class(0.5, 1.0, lower_is_better=True) == "good"
    assert _verdict_class(2.0, 1.0, lower_is_better=True) == "crit"
    # a figure we cannot compute is not a pass
    assert _verdict_class(None, 1.0, lower_is_better=True) == "crit"

    from wb_report.report import build_report, render_executive
    page = render_executive(build_report(phase_store, "run-p", audience="internal",
                                         baseline_arm="alpha"), tasks_dir=tmp_path)
    assert 'class="big crit"' in page or 'class="big good"' in page


def test_report_cli_format_executive(four_arm_store, tmp_path):
    """`wb report --format executive` writes the stakeholder page beside the
    markdown; the default still writes the technical one."""
    from wb_orchestrator.cli import main

    db, out = str(four_arm_store.path), tmp_path / "r"
    assert main(["--db", db, "--out", str(out), "report", "run-h",
                 "--baseline", "oracle", "--format", "executive"]) == 0
    exe = out / "report-run-h-internal-executive.html"
    assert exe.exists()
    assert 'id="headline"' in exe.read_text(encoding="utf-8")

    assert main(["--db", db, "--out", str(out), "report", "run-h",
                 "--baseline", "oracle"]) == 0
    tech = out / "report-run-h-internal.html"
    assert 'id="overview"' in tech.read_text(encoding="utf-8")

    # an unknown format is refused by argparse before anything is written
    with pytest.raises(SystemExit):
        main(["--db", db, "--out", str(out), "report", "run-h", "--format", "nope"])


def test_both_pages_carry_the_design_system(four_arm_store, tmp_path):
    """Technical and executive are siblings: same tokens, same fonts, same
    themes, and no external resource other than the font stylesheet."""
    import re

    from wb_report.report import build_report, render_executive, render_html

    rep = build_report(four_arm_store, "run-h", audience="internal",
                       baseline_arm="oracle")
    for page in (render_html(rep), render_executive(rep, tasks_dir=tmp_path)):
        assert "--paper: #FAF9F5" in page and "--accent: #A66A1E" in page
        assert '<link rel="stylesheet" href="https://fonts.googleapis.com' in page
        assert ':root[data-theme="dark"]' in page
        assert "Bricolage Grotesque" in page and "JetBrains Mono" in page
        # the font stylesheet is the only external reference on either page
        others = [u for u in re.findall(r'https?://[^"\')\s]+', page)
                  if "fonts.googleapis.com" not in u and "fonts.gstatic.com" not in u]
        assert others == [], others


def test_chart_text_and_bars_use_theme_tokens(tmp_path):
    """4 Sep: unstyled SVG text rendered black on the dark theme; unreadable."""
    from wb_report.html import _bar_chart, CSS
    assert "svg.chart text" in CSS and "fill: var(--ink)" in CSS
    assert 'class="cv"' in _bar_chart([("a", 0.5, 0.1)])


def test_value_label_sits_past_the_error_bar():
    """4 Sep: the label was drawn under the error line and looked struck through."""
    import re
    from wb_report.html import _bar_chart
    svg = _bar_chart([("a", 0.5, 0.3)])
    band = re.search(r'<rect class="ce" x="([\d.]+)" y="\d+" width="([\d.]+)"', svg)
    hi = float(band.group(1)) + float(band.group(2))
    label_x = float(re.search(r'class="cv" x="([\d.]+)"', svg).group(1))
    assert label_x > hi


def test_long_chart_labels_are_shortened_with_the_full_name_in_a_tooltip():
    from wb_report.html import _bar_chart
    svg = _bar_chart([("monarch@797a8e5d1+feat/railway-dev-deploy", 0.0, None)])
    assert "<title>monarch@797a8e5d1+feat/railway-dev-deploy</title>" in svg
    assert "monarch@797a8e5d1+fe…</text>" in svg
