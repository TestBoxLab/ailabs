"""wb run from product and plan files: Orchestrator.from_config, the shipped
smoke plan, and the name/path resolver and picker (US1, T013/T016/T018)."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests.test_config import PLAN, edit, site, write  # noqa: F401  (site is a fixture)
from wb_orchestrator import config
from wb_orchestrator.cli import _banner, main
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


def test_report_reads_k_from_file_driven_run(site, tmp_path, mock_server):
    from wb_report.report import build_report
    write(site / "config/models", MODEL_MOCK)
    plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
    plan = edit(plan, "baseline", "oracle")
    plan += "competitors:\n  - {harness: oracle}\n"
    write(site / "config/plans", plan)
    rc = config.resolve(site / "config/products/simulated-apps.yaml",
                        site / "config/plans/smoke-frontier.yaml", audiences={"internal": ["*"]})
    assert rc.plan.repetitions == 2
    store = Store(tmp_path / "wb.sqlite3")
    run_id = Orchestrator.from_config(store, rc, tmp_path / "out").run("run-k")
    assert build_report(store, run_id, audience="internal")["k"] == rc.plan.repetitions


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


def test_pick_empty_folder_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="no plan files"):
        pick(tmp_path, "1\n")


def test_resolve_name_or_path(site):
    assert config.resolve_name_or_path("smoke-frontier", "plan", site / "config") == \
        site / "config/plans/smoke-frontier.yaml"
    assert config.resolve_name_or_path("smoke-frontier", "plan") == \
        config.DEFAULT_CONFIG_DIR / "plans/smoke-frontier.yaml"
    p = site / "config/plans/smoke-frontier.yaml"
    assert config.resolve_name_or_path(str(p), "plan") == p
    with pytest.raises(ConfigError, match="unknown plan 'nope'; available: smoke-frontier"):
        config.resolve_name_or_path("nope", "plan", site / "config")


# -- the wb run command itself -------------------------------------------------

def test_run_unknown_plan_name_exits_2(tmp_path, capsys):
    rc = main(["--db", str(tmp_path / "wb.sqlite3"), "run", "--product", "simulated-apps", "--plan", "nope"])
    assert rc == 2
    assert "available: smoke-frontier" in capsys.readouterr().err


def test_banner_matches_contract(site):
    plan = edit(PLAN, "competitors")
    plan = edit(plan, "baseline", "oracle")
    plan = edit(plan, "tasks", f'"{(site / "tasks").as_posix()}"')
    plan += "competitors:\n  - {harness: oracle}\n"
    write(site / "config/plans", plan)
    rc = config.resolve(site / "config/products/simulated-apps.yaml",
                        site / "config/plans/smoke-frontier.yaml", audiences={"internal": ["*"]})
    assert _banner(rc).splitlines() == [
        "product   simulated-apps (simulated, mutable data)",
        "plan      smoke-frontier  mode=create-run  audience=internal",
        f"tasks     2 in {(site / 'tasks').as_posix()}/   repetitions 2   competitors 1   attempts 4",
        "ceiling   US$ 5.00   approved_by: —"]


# -- T037: cli harness env reaches the subprocess ------------------------------

def test_build_arm_for_renders_cli_env_from_model(site, monkeypatch):
    import subprocess
    from wb_arms import cli_claude_code
    from wb_orchestrator.orchestrator import build_arm_for
    from wb_world.episode import Episode, load_suite
    monkeypatch.setattr(cli_claude_code, "claude_version", lambda: "0.0-test")
    harness = config.load_harness(site / "config/harnesses/claude-code.yaml")
    harness.env["WB_KEY_ENV"] = "{key_env}"
    harness.env["WB_PROVIDER"] = "{provider}"
    model = config.load_model(site / "config/models/claude-opus-4-8.yaml")
    arm = build_arm_for(config.Competitor("claude-opus-4-8/claude-code", model, harness))
    assert arm.name == "claude-opus-4-8/claude-code"
    assert arm.env == {"ANTHROPIC_MODEL": "claude-opus-4-8", "WB_KEY_ENV": "ANTHROPIC_API_KEY",
                       "WB_PROVIDER": "anthropic"}

    captured = {}

    def fake_run(cmd, **kw):
        captured.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cli_claude_code.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(cli_claude_code.subprocess, "run", fake_run)
    arm.workdir_root = site / "cc-work"
    arm.run(Episode(load_suite(site / "tasks")[0], "ep-1"))
    assert captured["env"]["ANTHROPIC_MODEL"] == "claude-opus-4-8"
    assert captured["env"]["ANTHROPIC_API_KEY"] == "sk-test"


@pytest.mark.parametrize("value", ['{"a":1}', "{modle}"])
def test_build_arm_for_names_harness_and_key_on_bad_placeholder(site, monkeypatch, value):
    from wb_arms import cli_claude_code
    from wb_orchestrator.orchestrator import build_arm_for
    monkeypatch.setattr(cli_claude_code, "claude_version", lambda: "0.0-test")
    harness = config.load_harness(site / "config/harnesses/claude-code.yaml")
    harness.env["WB_BAD"] = value
    model = config.load_model(site / "config/models/claude-opus-4-8.yaml")
    with pytest.raises(ValueError, match="harness 'claude-code': env 'WB_BAD': bad placeholder"):
        build_arm_for(config.Competitor("claude-opus-4-8/claude-code", model, harness))
