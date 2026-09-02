"""US4 "never spend by accident": smoke-scale approval gate, cost ceiling with
resume, stop_reason in the store, and no arm built before validation (T025-T033)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import wb_orchestrator.orchestrator as orch_mod
from tests.test_config import MODEL, edit, site, write  # noqa: F401  (site is a fixture)
from tests.test_run_config import MODEL_MOCK
from wb_orchestrator import config
from wb_orchestrator.cli import main
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import Orchestrator, RunKilled
from wb_results.store import Store

ROOT = Path(__file__).resolve().parents[1]
ENV = {"ANTHROPIC_API_KEY": "x", "OPENAI_API_KEY": "x"}


# -- T025: smoke-scale guard (rule 9, research.md R9) -------------------------

def _pilot_plan(tmp_path, **changes):
    text = (ROOT / "config/plans/smoke-frontier.yaml").read_text()
    for k, v in changes.items():
        text = edit(text, k, v)
    return write(tmp_path, text)


def test_repetitions_over_smoke_scale_need_approval(tmp_path):
    plan = _pilot_plan(tmp_path, repetitions=3)
    with pytest.raises(ConfigError) as exc:
        config.resolve(ROOT / "config/products/simulated-apps.yaml", plan,
                       config_dir=ROOT / "config", env=ENV)
    msg = str(exc.value)
    assert exc.value.field == "approved_by"
    assert "30" in msg and "20" in msg and "approved_by" in msg


def test_approved_plan_over_smoke_scale_resolves(tmp_path):
    plan = _pilot_plan(tmp_path, repetitions=3, approved_by='"Carlos"')
    rc = config.resolve(ROOT / "config/products/simulated-apps.yaml", plan,
                       config_dir=ROOT / "config", env=ENV)
    assert rc.attempts_per_competitor == 30 and rc.plan.approved_by == "Carlos"


def test_exactly_smoke_scale_passes_without_approval(tmp_path):
    plan = _pilot_plan(tmp_path)  # 10 tasks x 2 repetitions = 20
    rc = config.resolve(ROOT / "config/products/simulated-apps.yaml", plan,
                       config_dir=ROOT / "config", env=ENV)
    assert rc.attempts_per_competitor == config.SMOKE_SCALE_ATTEMPTS == 20


# -- T027: runs.stop_reason column and setter ---------------------------------

OLD_RUNS_TABLE = """
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  config_hash TEXT NOT NULL,
  suite TEXT NOT NULL,
  config_json TEXT NOT NULL,
  started TEXT NOT NULL,
  finished TEXT
);
"""


def test_stop_reason_column_added_to_old_schema(tmp_path):
    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(OLD_RUNS_TABLE)
    conn.execute("INSERT INTO runs VALUES ('r1', 'h', 's', '{}', 't', NULL)")
    conn.commit()
    conn.close()

    store = Store(db)
    cols = {r[1] for r in store._conn.execute("PRAGMA table_info(runs)")}
    assert "stop_reason" in cols
    assert store.run("r1")["stop_reason"] is None
    store.set_stop_reason("r1", "cost_ceiling")
    assert store.run("r1")["stop_reason"] == "cost_ceiling"
    assert store.status("r1")["stop_reason"] == "cost_ceiling"
    assert store.status("r1")["spend_usd"] == 0.0
    store.set_stop_reason("r1", None)
    assert store.run("r1")["stop_reason"] is None
    Store(db)  # reopening an already-migrated DB is fine


# -- T029: cost ceiling stops the run; resume needs a raised ceiling ----------

def _mock_site(site):
    write(site / "config/models", MODEL_MOCK)
    plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
    plan = edit(plan, "baseline", "mock/api").replace("concurrency: 4", "concurrency: 1")
    plan += "competitors:\n  - {model: mock, harness: api}\n"
    return write(site / "config/plans", plan)


def _resolve(site):
    return config.resolve(site / "config/products/simulated-apps.yaml",
                          site / "config/plans/smoke-frontier.yaml", audiences={"internal": ["*"]})


def _set_ceiling(site, value):
    p = site / "config/plans/smoke-frontier.yaml"
    p.write_text(edit(p.read_text(), "cost_ceiling_usd", value))


def test_cost_ceiling_stops_run_and_resume_needs_raised_ceiling(site, tmp_path, mock_server):
    _mock_site(site)
    _set_ceiling(site, 0.0001)
    rc = _resolve(site)
    store = Store(tmp_path / "wb.sqlite3")
    with pytest.raises(RunKilled) as exc:
        Orchestrator.from_config(store, rc, tmp_path / "out").run("run-ceiling")
    msg = str(exc.value)
    assert "exceeds ceiling US$ 0.00" in msg and "wb resume run-ceiling" in msg
    assert "spend US$ " in msg

    run = store.run("run-ceiling")
    assert run["stop_reason"] == "cost_ceiling" and run["finished"] is None
    rows = store.episodes(run="run-ceiling")["rows"]
    assert 0 < len(rows) < rc.attempts_total
    spend = sum(r["cost_usd"] for r in rows)
    assert store.status("run-ceiling")["spend_usd"] == pytest.approx(spend, abs=1e-6)
    assert spend > 0.0001

    # same ceiling: refused, message names both numbers
    with pytest.raises(ConfigError) as exc:
        Orchestrator.from_config(store, _resolve(site), tmp_path / "out").resume("run-ceiling")
    msg = str(exc.value)
    assert f"spend US$ {spend:.2f}" in msg and "ceiling US$ 0.00" in msg
    assert store.run("run-ceiling")["stop_reason"] == "cost_ceiling"

    # raised ceiling: the hash ignores it, so no drift; the run completes
    _set_ceiling(site, 100)
    Orchestrator.from_config(store, _resolve(site), tmp_path / "out").resume("run-ceiling")
    rows = store.episodes(run="run-ceiling")["rows"]
    assert len(rows) == rc.attempts_total
    run = store.run("run-ceiling")
    assert run["stop_reason"] is None and run["finished"] is not None


def test_resume_counts_spend_before_the_interruption(site, tmp_path, mock_server):
    _mock_site(site)
    _set_ceiling(site, 100)
    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator.from_config(store, _resolve(site), tmp_path / "out")
    orch._stop_after = 1
    with pytest.raises(RunKilled):
        orch.run("run-partial")
    spent = store.status("run-partial")["spend_usd"]
    assert 0 < spent and store.run("run-partial")["stop_reason"] is None

    # ceiling between S and 2S: the next attempt after resume must trip it
    _set_ceiling(site, spent * 1.5)
    with pytest.raises(RunKilled) as exc:
        Orchestrator.from_config(store, _resolve(site), tmp_path / "out").resume("run-partial")
    msg = str(exc.value)
    assert "exceeds ceiling" in msg
    assert float(msg.split("spend US$ ")[1].split(" ")[0]) >= round(spent, 2)
    assert store.status("run-partial")["spend_usd"] >= spent * 1.5
    assert store.run("run-partial")["stop_reason"] == "cost_ceiling"


def test_resume_refused_when_spend_meets_ceiling_whatever_stopped_it(site, tmp_path, mock_server):
    _mock_site(site)
    _set_ceiling(site, 100)
    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator.from_config(store, _resolve(site), tmp_path / "out")
    orch._stop_after = 1
    with pytest.raises(RunKilled):
        orch.run("run-stopped")
    spent = store.status("run-stopped")["spend_usd"]
    n_rows = len(store.episodes(run="run-stopped")["rows"])
    assert store.run("run-stopped")["stop_reason"] is None  # not a ceiling stop

    _set_ceiling(site, spent / 2)
    with pytest.raises(ConfigError) as exc:
        Orchestrator.from_config(store, _resolve(site), tmp_path / "out").resume("run-stopped")
    msg = str(exc.value)
    assert f"spend US$ {spent:.2f}" in msg and f"ceiling US$ {spent / 2:.2f}" in msg
    assert len(store.episodes(run="run-stopped")["rows"]) == n_rows


def test_worker_error_sets_stop_reason(site, tmp_path, mock_server, monkeypatch):
    _mock_site(site)

    def die(self, run_id, arm, task, trial):
        raise RuntimeError("worker crashed hard")
    monkeypatch.setattr(orch_mod.Orchestrator, "_run_episode", die)
    store = Store(tmp_path / "wb.sqlite3")
    with pytest.raises(RuntimeError):
        Orchestrator.from_config(store, _resolve(site), tmp_path / "out").run("run-crash")
    assert store.run("run-crash")["stop_reason"] == "worker_error"


# -- T031: an unset key is reported before any arm is built ------------------

def test_run_with_unset_key_exits_before_building_arms(site, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("WB_TEST_UNSET_KEY", raising=False)
    write(site / "config/models", MODEL.replace("key_env: ANTHROPIC_API_KEY", "key_env: WB_TEST_UNSET_KEY"))
    plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
    plan = edit(plan, "baseline", "oracle")
    plan += "competitors:\n  - {harness: oracle}\n  - {model: claude-opus-4-8, harness: api}\n"
    write(site / "config/plans", plan)

    def boom(*a, **kw):
        raise AssertionError("arm built before validation")
    monkeypatch.setattr(orch_mod, "build_arm_for", boom)
    monkeypatch.setattr(orch_mod, "build_arm", boom)

    rc = main(["--db", str(tmp_path / "wb.sqlite3"), "--out", str(tmp_path / "out"), "run",
               "--product", str(site / "config/products/simulated-apps.yaml"),
               "--plan", str(site / "config/plans/smoke-frontier.yaml")])
    assert rc == 2
    err = capsys.readouterr().err
    model_path = site / "config/models/claude-opus-4-8.yaml"
    assert f"config error in {model_path}: key_env: environment variable WB_TEST_UNSET_KEY is not set" in err


# -- T033: wb status prints the stopped: line ---------------------------------

def test_status_prints_stopped_line(site, tmp_path, mock_server, capsys):
    _mock_site(site)
    _set_ceiling(site, 0.0001)
    db = tmp_path / "wb.sqlite3"
    store = Store(db)
    with pytest.raises(RunKilled):
        Orchestrator.from_config(store, _resolve(site), tmp_path / "out").run("run-status")
    spend = store.status("run-status")["spend_usd"]
    capsys.readouterr()
    assert main(["--db", str(db), "status", "run-status"]) == 0
    out = capsys.readouterr().out
    assert f"stopped: cost_ceiling (spend US$ {spend:.2f} / ceiling US$ 0.00)" in out

    store.set_stop_reason("run-status", "interrupted")
    main(["--db", str(db), "status", "run-status"])
    assert "stopped: interrupted\n" in capsys.readouterr().out
