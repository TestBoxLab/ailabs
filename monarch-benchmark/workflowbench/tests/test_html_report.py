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
    c = comparison(rows_alpha, rows_oracle, k=2)

    assert c["arm"] == "alpha" and c["baseline"] == "oracle"
    assert c["wins"] == wl["wins"]
    assert c["losses"] == wl["losses"]
    assert c["both"] == wl["both_pass"]
    assert c["neither"] == wl["neither_pass"]
    assert c["pairs"] == wl["pairs"]
    assert c["dropped_infra"] == wl["dropped_infra"]
    assert c["mcnemar"] == wl["mcnemar"]

    a = competitor_metrics(rows_alpha, k=2)
    b = competitor_metrics(rows_oracle, k=2)
    assert c["strict_pass_diff_pp"] == pytest.approx(
        (a["strict_pass"]["mean"] - b["strict_pass"]["mean"]) * 100)
    assert c["pass_rate_ratio"] == pytest.approx(
        a["strict_pass"]["mean"] / b["strict_pass"]["mean"])
    assert c["cost_per_passed_ratio"] == pytest.approx(
        a["cost_per_passed"] / b["cost_per_passed"])

    # a baseline that passed nothing: neither ratio is computable
    rows_null = _rows(zero_pass_store, "run-z", "null-arm")
    against_null = comparison(
        [dict(r, arm="alpha") for r in rows_null], rows_null, k=1)
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
