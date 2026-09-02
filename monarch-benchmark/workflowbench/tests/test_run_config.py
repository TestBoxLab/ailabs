"""wb run from product and plan files: Orchestrator.from_config, the shipped
smoke plan, and the name/path resolver and picker (US1, T013/T016/T018)."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests.test_config import PLAN, edit, site, write  # noqa: F401  (site is a fixture)
from wb_orchestrator import config
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.store import Store

ROOT = Path(__file__).resolve().parents[1]

MODEL_MOCK = """\
name: mock
provider: openai
model: mock-1
effort: none
usd_per_million: {input: 1.00, cached: 0.10, output: 2.00}
key_env: WB_MOCK_KEY
"""


# -- T013: from_config runs a plan end to end ---------------------------------

def test_from_config_runs_plan_with_competitor_names(site, tmp_path, mock_server):
    write(site / "config/models", MODEL_MOCK)
    plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
    plan = edit(plan, "baseline", "oracle").replace("repetitions: 2", "repetitions: 1")
    plan += "competitors:\n  - {harness: oracle}\n  - {model: mock, harness: api}\n"
    write(site / "config/plans", plan)
    rc = config.resolve(site / "config/products/simulated-apps.yaml",
                        site / "config/plans/smoke-frontier.yaml", audiences={"internal": ["*"]})

    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator.from_config(store, rc, tmp_path / "out")
    run_id = orch.run("run-from-config")

    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == rc.attempts_total == 4
    assert {r["arm"] for r in rows} == {"oracle", "mock/api"}
    assert {r["test_mode"] for r in rows} == {"create-run"}
    run = store.run(run_id)
    assert run["config_hash"] == rc.hash
    assert '"plan_path"' in run["config_json"]


# -- T016: the shipped smoke plan reproduces smoke-frontier-001 --------------

def test_smoke_plan_reproduces_smoke_frontier_001(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(k, "dummy")
    rc = config.resolve(ROOT / "config/products/simulated-apps.yaml",
                        ROOT / "config/plans/smoke-frontier.yaml")
    assert len(rc.tasks) == 10 and rc.plan.tasks == "tasks"
    assert rc.plan.repetitions == 2 and rc.plan.timeout_s == 600
    assert {c.name for c in rc.competitors} == {"oracle", "claude-opus-4-8/api", "gpt-5.6-sol/api"}
    assert rc.attempts_total == 60


# -- T018: picker and name/path resolution ------------------------------------

class _Tty(io.StringIO):
    def isatty(self):
        return True


def pick(folder, text, tty=True):
    out = io.StringIO()
    stdin = (_Tty if tty else io.StringIO)(text)
    return config.pick("plan", folder, stdin=stdin, stdout=out), out.getvalue()


def test_pick_lists_names_and_accepts_number(site):
    folder = site / "config/plans"
    write(folder, PLAN.replace("smoke-frontier", "big-run", 1), "big-run")
    chosen, out = pick(folder, "2\n")
    assert chosen == folder / "smoke-frontier.yaml"
    assert "Plans:\n  1) big-run\n  2) smoke-frontier\nPick a plan [1-2]: " in out


def test_pick_accepts_name(site):
    folder = site / "config/plans"
    chosen, _ = pick(folder, "smoke-frontier\n")
    assert chosen == folder / "smoke-frontier.yaml"


def test_pick_retries_on_bad_input(site):
    folder = site / "config/plans"
    chosen, out = pick(folder, "7\nnope\n1\n")
    assert chosen == folder / "smoke-frontier.yaml"
    assert out.count("not a choice") == 2 and out.count("Pick a plan") == 3


def test_pick_without_terminal_is_an_error(site):
    with pytest.raises(ConfigError, match="--plan is required without a terminal; available: smoke-frontier"):
        pick(site / "config/plans", "1\n", tty=False)


def test_resolve_name_or_path(site):
    assert config.resolve_name_or_path("smoke-frontier", "plan", site / "config") == \
        site / "config/plans/smoke-frontier.yaml"
    assert config.resolve_name_or_path("smoke-frontier", "plan") == \
        config.DEFAULT_CONFIG_DIR / "plans/smoke-frontier.yaml"
    p = site / "config/plans/smoke-frontier.yaml"
    assert config.resolve_name_or_path(str(p), "plan") == p
    assert config.resolve_name_or_path("x/y.yaml", "plan") == Path("x/y.yaml")
    with pytest.raises(ConfigError, match="unknown plan 'nope'; available: smoke-frontier"):
        config.resolve_name_or_path("nope", "plan", site / "config")
