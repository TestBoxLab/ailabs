"""Feature 006: the summary page over two to six rounds. Offline throughout."""
from __future__ import annotations

import pytest

from tests.test_html_report import _row
from wb_results.store import Store


@pytest.fixture()
def three_round_store(tmp_path):
    """Three runs of the same three competitors on three different task sets.

    One plan is named `random-10` (the random draw the stratification check
    compares against); the other two are tier rounds carrying `info.tier`.
    Pass rates differ per round so a mean over rounds is not the same number as
    any single round.
    """
    store = Store(tmp_path / "wb.sqlite3")
    arms = ["alpha", "beta", "oracle"]
    rounds = [
        ("run-r1", "random-10", ("r1a", "r1b"),
         {"alpha": [True, False], "beta": [True, True], "oracle": [True, True]}),
        ("run-r2", "tier-1", ("r2a", "r2b"),
         {"alpha": [True, True], "beta": [False, False], "oracle": [True, True]}),
        ("run-r3", "tier-2", ("r3a", "r3b"),
         {"alpha": [False, False], "beta": [True, False], "oracle": [True, True]}),
    ]
    for run_id, plan, tasks, passes in rounds:
        store.create_run(run_id, f"cfg-{plan}", "workflowbench-synthetic@0.1",
                         {"suite_dir": "tasks", "arms": arms, "k": 1,
                          "n_tasks": len(tasks), "plan": plan,
                          "product": "simulated-apps"})
        for arm in arms:
            for task, passed in zip(tasks, passes[arm]):
                store.record_episode(_row(task, arm, 0, passed, run=run_id))
        store.finish_run(run_id)
    return store


def _arm(summary, arm):
    return {a["arm"]: a for a in summary["aggregate"]}[arm]


def test_build_summary(three_round_store):
    """T043 (data-model section 3): one entry per round with its own metrics and
    source, the competitor list, and an aggregate that is the mean of per-round
    rates."""
    from wb_report.report import build_summary

    s = build_summary(three_round_store, ["run-r1", "run-r2", "run-r3"],
                      audience="internal", baseline="oracle")
    assert [r["run_id"] for r in s["rounds"]] == ["run-r1", "run-r2", "run-r3"]
    assert [r["plan"] for r in s["rounds"]] == ["random-10", "tier-1", "tier-2"]
    for r in s["rounds"]:
        assert r["size"]["prompts"] == 2
        assert {m["arm"] for m in r["metrics"]} == {"alpha", "beta", "oracle"}
        assert r["source"]
    assert s["arms"] == ["alpha", "beta", "oracle"]
    assert s["audience"] == "internal"

    # alpha: 50% then 100% then 0% -> mean 50%
    alpha = _arm(s, "alpha")
    assert alpha["n_rounds"] == 3
    assert alpha["mean_strict_pass"] == pytest.approx(0.5)
    assert alpha["sem"] is not None
    # oracle passed everything in every round
    assert _arm(s, "oracle")["mean_strict_pass"] == pytest.approx(1.0)
    # beta: 100%, 0%, 50% -> 50%
    assert _arm(s, "beta")["mean_strict_pass"] == pytest.approx(0.5)


def test_aggregate_counts_only_the_rounds_a_competitor_ran(three_round_store, tmp_path):
    """T045 (FR-019, US3 scenario 5): a competitor present in two of three rounds
    has n_rounds == 2 and a mean over those two only."""
    from tests.test_html_report import _row
    from wb_report.report import build_summary
    from wb_results.store import Store

    store = Store(tmp_path / "wb.sqlite3")
    for run_id, arms, passes in (("run-a", ["alpha", "beta"], {"alpha": True, "beta": True}),
                                 ("run-b", ["alpha", "beta"], {"alpha": False, "beta": True}),
                                 ("run-c", ["alpha"], {"alpha": True})):
        store.create_run(run_id, f"cfg-{run_id}", "workflowbench-synthetic@0.1",
                         {"suite_dir": "tasks", "arms": arms, "k": 1, "n_tasks": 1,
                          "plan": run_id})
        for arm in arms:
            store.record_episode(_row("t1", arm, 0, passes[arm], run=run_id))
        store.finish_run(run_id)

    s = build_summary(store, ["run-a", "run-b", "run-c"], audience="internal")
    beta = _arm(s, "beta")
    assert beta["n_rounds"] == 2                     # it did not run the third
    assert beta["mean_strict_pass"] == pytest.approx(1.0)
    assert _arm(s, "alpha")["n_rounds"] == 3
    assert _arm(s, "alpha")["mean_strict_pass"] == pytest.approx(2 / 3)


def test_no_pooled_paired_figures(three_round_store):
    """T046 (FR-021, rule 5): the summary carries no wins, losses or McNemar p,
    and the page never shows one outside a per-round table. The sentence saying
    so is present verbatim."""
    import json

    from wb_report.report import NEVER_POOLED, build_summary, render_summary_html

    s = build_summary(three_round_store, ["run-r1", "run-r2", "run-r3"],
                      audience="internal", baseline="oracle")
    blob = json.dumps(s)
    for banned in ("wins", "losses", "mcnemar", "both_pass", "neither_pass", "pairs"):
        assert banned not in blob, banned
    assert s["statement"] == NEVER_POOLED

    page = render_summary_html(s)
    from wb_report.html import _esc
    assert _esc(NEVER_POOLED) in page      # escaped, but the whole sentence
    assert "McNemar" not in page
    assert "W /" not in page


def test_stratification_block(three_round_store, tmp_path):
    """T047 (FR-020): with a `random-10` round and tier rounds, the block gives
    the random rate, the mean of the tiers and the difference in percentage
    points; with no random round the block is absent, not empty."""
    from tests.test_html_report import _row
    from wb_report.report import build_summary
    from wb_results.store import Store

    s = build_summary(three_round_store, ["run-r1", "run-r2", "run-r3"],
                      audience="internal")
    strat = {e["arm"]: e for e in s["stratification"]}
    # alpha: random draw 50%, tiers 100% and 0% -> mean 50%, difference 0 pp
    assert strat["alpha"]["random"] == pytest.approx(0.5)
    assert strat["alpha"]["tier_mean"] == pytest.approx(0.5)
    assert strat["alpha"]["diff_pp"] == pytest.approx(0.0)
    # beta: random 100%, tiers 0% and 50% -> 25%, +75 pp
    assert strat["beta"]["random"] == pytest.approx(1.0)
    assert strat["beta"]["tier_mean"] == pytest.approx(0.25)
    assert strat["beta"]["diff_pp"] == pytest.approx(75.0)

    # no random round: the block is omitted rather than rendered empty
    store = Store(tmp_path / "wb.sqlite3")
    for run_id in ("run-t1", "run-t2"):
        store.create_run(run_id, f"cfg{run_id}", "workflowbench-synthetic@0.1",
                         {"suite_dir": "tasks", "arms": ["alpha"], "k": 1,
                          "n_tasks": 1, "plan": f"tier-{run_id}"})
        store.record_episode(_row("t1", "alpha", 0, True, run=run_id))
        store.finish_run(run_id)
    assert "stratification" not in build_summary(store, ["run-t1", "run-t2"],
                                                 audience="internal")


def test_summary_page_shape(three_round_store):
    """T049: one metrics table per round, each with its own source line, then the
    aggregate table, then the statement."""
    from wb_report.report import NEVER_POOLED, build_summary, render_summary_html

    s = build_summary(three_round_store, ["run-r1", "run-r2", "run-r3"],
                      audience="internal", baseline="oracle")
    page = render_summary_html(s)
    assert page.startswith("<!doctype html>")
    for run_id in ("run-r1", "run-r2", "run-r3"):
        assert run_id in page
    assert page.count("<caption>") >= 4          # three rounds plus the aggregate
    assert "<caption>Mean over the rounds each competitor ran</caption>" in page
    assert page.count("<li>src:") >= 3       # one source line per round, listed once
    # order: the rounds, then the aggregate, then the statement
    assert page.index("run-r1") < page.index("Mean over the rounds")
    from wb_report.html import _esc
    assert page.index("Mean over the rounds") < page.index(_esc(NEVER_POOLED))


def test_summary_refuses_bad_round_counts(three_round_store):
    """T050 (FR-022): one round is refused (wb report is the command for that);
    seven rounds are refused because the page stops being readable."""
    from wb_report.report import build_summary

    with pytest.raises(ValueError, match="two to six"):
        build_summary(three_round_store, ["run-r1"], audience="internal")
    with pytest.raises(ValueError, match="two to six"):
        build_summary(three_round_store, ["run-r1"] * 7, audience="internal")


def test_summary_refuses_an_unknown_run(three_round_store, tmp_path):
    """T050: an unknown run id is a typo; it fails loudly, naming the run, and
    writes nothing."""
    from wb_report.report import build_summary, write_summary

    with pytest.raises(KeyError, match="run-nope"):
        build_summary(three_round_store, ["run-r1", "run-nope"], audience="internal")

    out = tmp_path / "summary.html"
    with pytest.raises(KeyError):
        write_summary(three_round_store, ["run-r1", "run-nope"], out,
                      audience="internal")
    assert not out.exists()          # nothing written


def test_resolve_plans_picks_the_most_recent(tmp_path):
    """T050: --plans uses the most recent run of each plan and says which."""
    from wb_report.report import resolve_plans
    from wb_results.store import Store

    store = Store(tmp_path / "wb.sqlite3")
    for run_id in ("run-old", "run-new"):
        store.create_run(run_id, "cfg", "workflowbench-synthetic@0.1",
                         {"suite_dir": "tasks", "arms": ["alpha"], "k": 1,
                          "n_tasks": 1, "plan": "tier-1"})
        store.record_episode(_row("t1", "alpha", 0, True, run=run_id))
        store.finish_run(run_id)

    picked = resolve_plans(store, ["tier-1"])
    assert len(picked) == 1
    plan, run_id, started = picked[0]
    assert plan == "tier-1" and run_id == "run-new" and started

    with pytest.raises(KeyError, match="no-such-plan"):
        resolve_plans(store, ["no-such-plan"])


def test_summary_applies_the_gate_per_round(tmp_path):
    """T052 (FR-025): a public summary omits a lab competitor from every round,
    and refuses when the gate leaves a round empty."""
    from wb_report.report import GateError, build_summary
    from wb_results.store import Store

    store = Store(tmp_path / "wb.sqlite3")
    # round one has monarch and a lab arm; round two has only monarch
    store.create_run("run-1", "cfg1", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch", "monarch-lab"],
                      "k": 1, "n_tasks": 1, "plan": "p1"})
    store.record_episode(_row("t1", "monarch", 0, True, run="run-1"))
    store.record_episode(_row("t1", "monarch-lab", 0, True, run="run-1"))
    store.finish_run("run-1")
    store.create_run("run-2", "cfg2", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch"], "k": 1,
                      "n_tasks": 1, "plan": "p2"})
    store.record_episode(_row("t1", "monarch", 0, True, run="run-2"))
    store.finish_run("run-2")

    s = build_summary(store, ["run-1", "run-2"], audience="public-rung2")
    assert s["arms"] == ["monarch"]
    for rnd in s["rounds"]:
        assert all(m["arm"] != "monarch-lab" for m in rnd["metrics"])
    from wb_report.report import render_summary_html
    assert "monarch-lab" not in render_summary_html(s)

    # a round the gate empties refuses the whole summary
    store.create_run("run-3", "cfg3", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["monarch-lab"], "k": 1,
                      "n_tasks": 1, "plan": "p3"})
    store.record_episode(_row("t1", "monarch-lab", 0, True, run="run-3"))
    store.finish_run("run-3")
    with pytest.raises(GateError):
        build_summary(store, ["run-2", "run-3"], audience="public-rung2")


def test_summary_cli(three_round_store, tmp_path, capsys):
    """T050 (contracts/cli.md): --runs writes the file; --plans prints the run
    it picked; the two together are refused; an unknown run is refused naming
    it, and writes nothing; --out defaults to out/summary-<stamp>-<audience>."""
    from wb_orchestrator.cli import main

    db = str(three_round_store.path)
    out = tmp_path / "summary.html"

    # --runs writes the page
    assert main(["--db", db, "summary", "--runs", "run-r1,run-r2,run-r3",
                 "--out", str(out), "--baseline", "oracle"]) == 0
    assert out.exists()
    page = out.read_text(encoding="utf-8")
    assert "<table" in page and "run-r1" in page
    assert "wrote" in capsys.readouterr().out

    # --plans names the run it picked for each plan
    assert main(["--db", db, "summary", "--plans", "random-10,tier-1",
                 "--out", str(tmp_path / "byplan.html")]) == 0
    printed = capsys.readouterr().out
    assert "random-10" in printed and "run-r1" in printed
    assert "tier-1" in printed and "run-r2" in printed

    # both selectors at once is refused
    assert main(["--db", db, "summary", "--runs", "run-r1,run-r2",
                 "--plans", "tier-1,tier-2", "--out", str(tmp_path / "x.html")]) == 1
    assert "exactly one" in capsys.readouterr().err

    # neither is refused too
    assert main(["--db", db, "summary", "--out", str(tmp_path / "y.html")]) == 1

    # one round is refused; wb report is the command for that
    assert main(["--db", db, "summary", "--runs", "run-r1",
                 "--out", str(tmp_path / "one.html")]) == 1
    assert "two to six" in capsys.readouterr().err

    # an unknown run is refused, naming it, and writes nothing
    missing = tmp_path / "missing.html"
    assert main(["--db", db, "summary", "--runs", "run-r1,run-nope",
                 "--out", str(missing)]) == 1
    assert "run-nope" in capsys.readouterr().err
    assert not missing.exists()

    # an unknown plan is refused as well
    assert main(["--db", db, "summary", "--plans", "no-such-plan,tier-1",
                 "--out", str(tmp_path / "z.html")]) == 1
    assert "no-such-plan" in capsys.readouterr().err


def test_summary_cli_default_out_path(three_round_store, tmp_path, capsys):
    """T050 (FR-017): the default file is out/summary-<timestamp>-<audience>."""
    import re
    from pathlib import Path

    from wb_orchestrator.cli import main

    assert main(["--db", str(three_round_store.path), "--out", str(tmp_path),
                 "summary", "--runs", "run-r1,run-r2"]) == 0
    written = capsys.readouterr().out.strip().removeprefix("wrote ")
    assert re.search(r"summary-\d{8}-\d{6}-internal\.html$", written), written
    assert (tmp_path / Path(written).name).exists()


def test_summary_cli_no_sort(three_round_store, tmp_path):
    """T050: --no-sort ships the summary as pure markup."""
    from wb_orchestrator.cli import main

    out = tmp_path / "nosort.html"
    assert main(["--db", str(three_round_store.path), "summary",
                 "--runs", "run-r1,run-r2", "--out", str(out), "--no-sort"]) == 0
    # --no-sort is still accepted; the redesigned page has no sorting script to
    # omit, so it simply writes the same page.
    assert "<table" in out.read_text(encoding="utf-8")
