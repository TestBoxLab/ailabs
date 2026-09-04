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
                                    "category": "passed", "detail": None}

    t2 = {r["task_id"]: r for r in m["rows"]}["t2"]
    # alpha failed t2 once on an unexpected change; the paths are the detail
    assert t2["cells"]["alpha"]["passed"] == 1
    assert t2["cells"]["alpha"]["attempted"] == 2
    assert t2["cells"]["alpha"]["category"] == "unexpected change"
    assert "crm.contacts[3].email" in t2["cells"]["alpha"]["detail"]
    # beta's t2 pair is one infra attempt and one assertion failure
    assert t2["cells"]["beta"] == {"passed": 0, "attempted": 1, "infra": 1,
                                    "category": "infra", "detail": "infra:rate_limit"}
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
    for caption in ("Competitors", "Comparisons against the baseline",
                    "Task matrix", "Failures"):
        assert f"<caption>{caption}</caption>" in page, caption
    # the size line: the total never appears without the product beside it
    assert ("prompts: 2 &middot; attempts per prompt and competitor: 2 &middot; "
            "per competitor: 4 = 2 x 2 &middot; competitors: 4 &middot; "
            "attempts in total: 16") in page
    assert page.count('class="src"') >= 4
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
    assert "<script" in render_page(rep)
    assert "addEventListener" in render_page(rep)
    assert "<script" not in render_page(rep, sortable=False)


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
    assert "<script" not in page
    assert "<table" in page                       # still the real page, not the blob

    assert main(["--db", db, "--out", str(out), "report", "run-h",
                 "--baseline", "oracle"]) == 0
    assert "<script" in (out / "report-run-h-internal.html").read_text(encoding="utf-8")


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
    for header in ("authoring wall-clock", "authoring cost", "execution wall-clock",
                   "execution cost", "cost / model", "questions asked",
                   "declined to build"):
        assert f"<th>{header}</th>" in page, header
    assert "opus-4.8 US$ 0.3500" in page      # the summed model:opus-4.8 phase
    assert "US$ 0.3500" in page               # authoring cost, summed over attempts
    assert "10.0 s" in page                   # authoring wall-clock mean


def test_phase_columns_absent_without_phases(four_arm_store):
    """T034 (FR-016): a round whose competitors carry only a `run` phase never
    shows those column headers at all - an empty column is worse than none."""
    from wb_report.report import build_report, render_html

    page = render_html(build_report(four_arm_store, "run-h", audience="internal",
                                    baseline_arm="oracle"))
    for header in ("authoring wall-clock", "authoring cost", "execution wall-clock",
                   "execution cost", "cost / model", "questions asked",
                   "declined to build"):
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
    assert "<th>execution wall-clock</th>" in page
    assert "<th>authoring wall-clock</th>" in page   # another competitor has it
    row = page[page.index('<td class="lbl">monarch-run-only</td>'):]
    row = row[:row.index("</tr>")]
    assert "n/a" in row          # the authoring cells
    assert "4.0 s" in row        # but execution is real


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
    assert "lab" not in page.lower().replace("collaborat", "")
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
    assert "<th>cost vs baseline</th>" in page
    assert "<th>cost total</th>" not in page
    assert "<th>cost / passed</th>" not in page


def test_internal_watermark_survives(lab_store):
    """T042: an internal page carrying a lab competitor still says DO NOT
    EXPORT, as the markdown report already does."""
    from wb_report.report import build_report, render_html, render_md

    rep = build_report(lab_store, "run-g", audience="internal", baseline_arm="monarch")
    assert "DO NOT EXPORT" in render_md(rep)
    assert "DO NOT EXPORT" in render_html(rep)
    assert "monarch-lab" in render_html(rep)      # internal names it, and warns
