"""wb run from product and plan files: Orchestrator.from_config, the shipped
smoke plan, and the name/path resolver and picker (US1, T013/T016/T018)."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests.test_config import (  # noqa: F401  (site is a fixture)
    ENV, PLAN, PRICE_TABLE, edit, runnable_monarch, site, write)
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
    err = capsys.readouterr().err
    assert "unknown plan 'nope'" in err and "smoke-frontier" in err and "pilot-monarch-create-run" in err


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


# -- T007: Monarch competitor -> knowledge-base hash file + price table ---------

KB = """\
product: simulated-apps
generated_at: 2026-09-04T12:00:00Z
seeds_format: public-api-seeds@1
shim_public_url: http://host.docker.internal:9105
kb:
  bench-airtable: 6d07bde6f1c2
  bench-asana: 272673e3a9b0
  bench-gmail: 9b1f0c4a5e77
  bench-salesforce: 3c2e8d90aa41
"""

MONARCH_ENV = {**ENV, "MONARCH_PASSWORD": "monarch-dev"}


def monarch_site(site, kb=KB, monarch_repo=None):
    """The `site` fixture with a runnable Monarch competitor, its price table and its kb file."""
    runnable_monarch(site, modes="[create-run]", monarch_repo=monarch_repo)
    write(site / "config/models", PRICE_TABLE)
    if kb is not None:
        (site / "config/products/simulated-apps.monarch-kb.yaml").write_text(kb)
    return site


def resolve_monarch(site, env=MONARCH_ENV):
    return config.resolve(site / "config/products/simulated-apps.yaml",
                          site / "config/plans/smoke-frontier.yaml",
                          env=env, audiences={"internal": ["*"]})


def test_resolve_loads_monarch_kb_and_price_table(site):
    rc = resolve_monarch(monarch_site(site))
    assert rc.monarch_kb.product == "simulated-apps"
    assert rc.monarch_kb.seeds_format == "public-api-seeds@1"
    assert rc.monarch_kb.shim_public_url == "http://host.docker.internal:9105"
    assert rc.monarch_kb.kb["bench-asana"] == "272673e3a9b0" and len(rc.monarch_kb.kb) == 4
    table = rc.price_tables["monarch-team-bedrock"]
    assert table.region == "us-west-2" and len(table.models) == 5
    assert rc.config_json["monarch_kb"]["kb"]["bench-gmail"] == "9b1f0c4a5e77"
    assert rc.config_json["price_tables"]["monarch-team-bedrock"]["provider"] == "bedrock"


def test_resolve_without_monarch_has_no_kb_or_price_tables(site):
    rc = config.resolve(*(site / p for p in ("config/products/simulated-apps.yaml",
                                             "config/plans/smoke-frontier.yaml")),
                        env=ENV, audiences={"internal": ["*"]})
    assert rc.monarch_kb is None and rc.price_tables == {}
    assert "monarch_kb" not in rc.config_json and "price_tables" not in rc.config_json


def test_resolve_missing_kb_file_points_at_wb_monarch_setup(site):
    monarch_site(site, kb=None)
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(site)
    assert exc.value.path == str(site / "config/products/simulated-apps.monarch-kb.yaml")
    assert exc.value.field == "kb" and "wb monarch setup" in str(exc.value)


def test_resolve_kb_slug_outside_the_product_services(site):
    monarch_site(site, kb=KB + "  bench-notion: ffffffffffff\n")
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(site)
    assert exc.value.path == str(site / "config/products/simulated-apps.monarch-kb.yaml")
    assert exc.value.field == "kb.bench-notion" and "not a service" in str(exc.value)


def test_resolve_kb_missing_a_product_service(site):
    monarch_site(site, kb=KB.replace("  bench-gmail: 9b1f0c4a5e77\n", ""))
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(site)
    assert exc.value.field == "kb.bench-gmail" and "wb monarch setup" in str(exc.value)


def test_resolve_unknown_price_table(site):
    monarch_site(site)
    runnable_monarch(site, modes="[create-run]", price_table="nowhere")
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(site)
    assert exc.value.field == "price_table" and "nowhere" in str(exc.value)


def test_hash_changes_with_kb_and_prices(site):
    h0 = resolve_monarch(monarch_site(site)).hash
    monarch_site(site, kb=KB.replace("272673e3a9b0", "272673e3a9b1"))
    h_kb = resolve_monarch(site).hash
    monarch_site(site)  # kb back
    assert resolve_monarch(site).hash == h0
    write(site / "config/models", PRICE_TABLE.replace("cached: 0.20", "cached: 0.25"))
    h_price = resolve_monarch(site).hash
    write(site / "config/models", PRICE_TABLE)
    monarch_site(site, kb=KB.replace("2026-09-04T12:00:00Z", "2027-01-01T00:00:00Z"))
    assert resolve_monarch(site).hash == h0  # generated_at is not hashed
    assert len({h0, h_kb, h_price}) == 3


def test_shipped_smoke_frontier_hash_is_unchanged(monkeypatch):
    """The recorded hash of the smoke-frontier plan, from the `runs` row of run-20260903-000243.

    Source: out/wb-smoke-frontier-002.sqlite3, table `runs`, column `config_hash`
    (out/run-20260903-000243/ holds only the episode snapshots, no config.json).
    Adding Monarch fields must not re-hash a plan that has no Monarch competitor.
    """
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(k, "dummy")
    rc = config.resolve(ROOT / "config/products/simulated-apps.yaml",
                        ROOT / "config/plans/smoke-frontier.yaml")
    assert rc.hash == "02bb91bf0f18d1bf"


def test_resolve_accepts_login_password_instead_of_a_token(site):
    monarch_site(site)
    env = {k: v for k, v in MONARCH_ENV.items() if k != "MONARCH_TOKEN"}
    assert resolve_monarch(site, env=env).monarch_kb is not None  # password alone is enough
    env = {k: v for k, v in env.items() if k != "MONARCH_PASSWORD"}
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(site, env=env)
    assert exc.value.field == "credential_env"
    assert "MONARCH_TOKEN" in str(exc.value) and "MONARCH_PASSWORD" in str(exc.value)


def test_build_arm_for_monarch_competitor(site):
    """The Monarch row is named for the checkout, not for the plan (T023/T024).

    The shipped harness points `monarch_repo` at the sibling Monarch clone; this
    repo stands in for it so the test does not depend on that checkout existing.
    """
    from wb_orchestrator.orchestrator import build_arm_for
    rc = resolve_monarch(monarch_site(site, monarch_repo=str(ROOT)))
    competitor = next(c for c in rc.competitors if c.harness.kind == "monarch")
    arm = build_arm_for(competitor, rc)
    assert competitor.name == "monarch"
    assert arm.name.startswith("monarch@") and arm.model_label == arm.name


# -- T029/T030: a drifted knowledge base stops the run before any authoring ----

def test_kb_drift_refuses(site, tmp_path):
    """One app whose hash moved: the run stops naming it, before Monarch is asked anything."""
    from tests.fake_fd import fd_serving
    from tests.fake_monarch import FakeMonarch
    from tests.test_monarch_arm import arm_against, free_port, repo  # noqa: F401
    from wb_arms.api_loop import InfraError

    on_disk = {"bench-airtable": "6d07bde6f1c2", "bench-asana": "272673e3a9b0",
               "bench-gmail": "9b1f0c4a5e77", "bench-salesforce": "DRIFTED"}
    port = free_port()
    with FakeMonarch() as monarch, fd_serving(on_disk) as fd:
        git_repo = tmp_path / "monarch-checkout"
        git_repo.mkdir()
        _git_init(git_repo)
        arm = arm_against(site, monarch, port, git_repo, fd=fd)
        store = Store(tmp_path / "wb.sqlite3")
        rc = resolve_monarch(site)
        orch = Orchestrator.from_config(store, rc, tmp_path / "out")
        with pytest.raises(InfraError) as exc:
            orch.run("run-drift")

    assert "bench-salesforce" in str(exc.value) and not exc.value.retryable
    assert not [r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]


def _git_init(d) -> None:
    import subprocess
    for args in (["init", "-q"],
                 ["-c", "user.email=a@b", "-c", "user.name=t", "commit", "--allow-empty", "-q",
                  "-m", "x"],
                 ["checkout", "-q", "-B", "main"]):
        subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def test_banner_names_the_monarch_build(site, tmp_path):
    """T032: a plan with Monarch says which build, how big the kb is, and which prices."""
    git_repo = tmp_path / "checkout"
    git_repo.mkdir()
    _git_init(git_repo)
    monarch_site(site, monarch_repo=str(git_repo))
    line = _banner(resolve_monarch(site)).splitlines()[-1]
    assert line.startswith("monarch   monarch@")
    assert "kb 4 apps" in line and "price table monarch-team-bedrock@2026-09-03" in line
