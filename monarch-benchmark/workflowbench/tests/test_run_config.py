"""wb run from product and plan files: Orchestrator.from_config, the shipped
smoke plan, and the name/path resolver and picker (US1, T013/T016/T018)."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests.monarch_helpers import (  # noqa: F401  (repo is a fixture)
    KB, MONARCH_ENV, RECIPES, git, monarch_site, repo, resolve_monarch, run_only_site)
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
        f"tasks     2 in {(site / 'tasks').as_posix()}/",
        "prompts: 2; attempts per prompt and competitor: 2; "
        "attempts per competitor: 4 = 2 x 2",
        "competitors: 1; attempts in the round: 4",
        "ceiling   US$ 5.00   attempt cap US$ 3.00"]


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

    from unittest.mock import Mock
    from wb_arms.api_loop import InfraError
    process = Mock(side_effect=AssertionError("unverified native launch"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(subprocess, "run", process)
    arm.workdir_root = site / "cc-work"
    with pytest.raises(InfraError, match="verified isolated runtime") as error:
        arm.run(Episode(load_suite(site / "tasks")[0], "ep-1"))
    assert error.value.retryable is False
    process.assert_not_called()
    assert not arm.workdir_root.exists()


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
    from tests.monarch_helpers import arm_against, free_port
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
    """A one-commit checkout on `main`, for the version the arm is named after."""
    git(d, "init", "-q")
    git(d, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "--allow-empty", "-q", "-m", "x")
    git(d, "checkout", "-q", "-B", "main")


def test_banner_names_the_monarch_build(site, tmp_path):
    """T032: a plan with Monarch says which build, how big the kb is, and which prices."""
    git_repo = tmp_path / "checkout"
    git_repo.mkdir()
    _git_init(git_repo)
    monarch_site(site, monarch_repo=str(git_repo))
    line = _banner(resolve_monarch(site)).splitlines()[-1]
    assert line.startswith("monarch   monarch@")
    assert "kb 4 apps" in line and "price table monarch-team-bedrock@2026-09-03" in line


def test_monarch_needs_its_addresses_and_langfuse_keys(site):
    """FR-029: a variable the competitor will need stops the run before it starts."""
    monarch_site(site)
    for name, field in (("MONARCH_URL", "base_url"), ("MONARCH_FD_URL", "fd_url"),
                        ("LANGFUSE_URL", "langfuse_url"),
                        ("LANGFUSE_PUBLIC_KEY", "langfuse_public_key_env"),
                        ("LANGFUSE_SECRET_KEY", "langfuse_secret_key_env")):
        env = {k: v for k, v in MONARCH_ENV.items() if k != name}
        with pytest.raises(ConfigError) as exc:
            resolve_monarch(site, env=env)
        assert exc.value.path == str(site / "config/harnesses/monarch.yaml")
        assert exc.value.field == field and name in str(exc.value)


# -- 004 T008: the recipes file in resolve() and in the hash --------------------

# Moved on 4 Sep 2026 from df58417a1d17288a: the knowledge-base file now keys
# apps by their hyphenated product slug (bench-google-ads, not bench-google_ads),
# because the discovery service slugifies and was creating two products per app.
# A deliberate input change: rows from before this date are not regradable against
# runs after it. Pre-registration (PLAN.md rule 5) -- needs Lucas's sign-off.
CREATE_RUN_HASH = "9e23c3dfb31f241a"   # 8 Sep: seeds v5.3 knowledge base, unattended authoring

# The fixture's second task moved from `recipes` to `missing`: the same file with
# one fewer known-correct recipe, used by the hash tests and the exclusion tests.
RECIPES_WITH_MISSING = RECIPES.replace("""  simple.sf_opp_closed_won:
    workflow_id: wf-2
    recipe_version: 2
    authored_at: '2026-09-04T12:09:40Z'
    attempts_used: 3
missing: {}
""", """missing:
  simple.sf_opp_closed_won:
    reason: checker_failed
    attempts_used: 3
    detail: 'invariant failed'
""")


def test_resolve_loads_the_recipes_file_in_run_only(site):
    rc = resolve_monarch(run_only_site(site))
    assert rc.plan.mode == "run-only"
    assert set(rc.monarch_recipes.recipes) == {"simple.email_sf_contact_city_update",
                                               "simple.sf_opp_closed_won"}
    assert rc.monarch_recipes.recipes["simple.sf_opp_closed_won"].recipe_version == 2
    assert rc.monarch_recipes.monarch == "monarch@1a2b3c4"


def test_resolve_create_run_does_not_load_the_recipes_file(site):
    """Create + run never reads it, even when one is sitting beside the product."""
    run_only_site(site)
    plan = (site / "config/plans/smoke-frontier.yaml").read_text()
    write(site / "config/plans", plan.replace("mode: run-only", "mode: create-run"))
    rc = resolve_monarch(site)
    assert rc.monarch_recipes is None and "monarch_recipes" not in rc.config_json


def test_resolve_missing_recipes_file_points_at_wb_monarch_recipes(site):
    run_only_site(site, recipes=None)
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(site)
    assert exc.value.path == str(site / "config/products/simulated-apps.monarch-recipes.yaml")
    assert "wb monarch recipes" in str(exc.value)


def _hash_with(site, recipes):
    return resolve_monarch(run_only_site(site, recipes=recipes)).hash


@pytest.mark.parametrize("old,new", [
    ("workflow_id: wf-1", "workflow_id: wf-9"),
    ("recipe_version: 3", "recipe_version: 4"),
    ("kb_hash_file_sha: 9f2c", "kb_hash_file_sha: 8e1b"),
])
def test_hash_changes_with_a_recipe_input(site, old, new):
    base = _hash_with(site, RECIPES)
    assert _hash_with(site, RECIPES.replace(old, new)) != base


def test_hash_changes_when_a_missing_key_appears(site):
    base = _hash_with(site, RECIPES)
    moved = RECIPES_WITH_MISSING
    assert _hash_with(site, moved) != base


@pytest.mark.parametrize("old,new", [
    ("generated_at: '2026-09-04T12:00:00Z'", "generated_at: '2027-01-01T00:00:00Z'"),
    ("detail: 'invariant failed'", "detail: 'something else entirely'"),
])
def test_hash_ignores_generated_at_and_a_missing_detail(site, old, new):
    """A resume must not refuse because the file was rewritten or the reason text changed."""
    with_missing = RECIPES_WITH_MISSING
    base = _hash_with(site, with_missing)
    assert _hash_with(site, with_missing.replace(old, new)) == base


def test_shipped_create_run_pilot_hash_is_unchanged(monkeypatch):
    """Adding the recipes file must not move a create + run plan's hash."""
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FIREWORKS_API_KEY", "MONARCH_TOKEN",
              "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(k, "dummy")
    for k, v in (("MONARCH_URL", "http://x"), ("MONARCH_FD_URL", "http://x"),
                 ("LANGFUSE_URL", "http://x")):
        monkeypatch.setenv(k, v)
    rc = config.resolve(ROOT / "config/products/simulated-apps.yaml",
                        ROOT / "config/plans/pilot-monarch-create-run.yaml")
    assert rc.hash == CREATE_RUN_HASH


# -- 004 T010: tasks with no recipe leave the task set of every competitor ------

def test_missing_tasks_leave_the_task_set_of_every_competitor(site):
    rc = resolve_monarch(run_only_site(site, recipes=RECIPES_WITH_MISSING))
    assert [t["task"] for t in rc.tasks] == ["simple.email_sf_contact_city_update"]
    assert rc.excluded_tasks == {"simple.sf_opp_closed_won": "checker_failed"}
    # rule 7: the reduced set is what every competitor is measured on.
    assert rc.attempts_per_competitor == 1 * rc.plan.repetitions
    assert rc.attempts_total == rc.attempts_per_competitor * len(rc.competitors)


def test_a_task_in_neither_map_is_excluded_as_not_attempted(site):
    """The union need not cover the task set; what is uncovered was never attempted."""
    only_one = RECIPES.replace("""  simple.sf_opp_closed_won:
    workflow_id: wf-2
    recipe_version: 2
    authored_at: '2026-09-04T12:09:40Z'
    attempts_used: 3
""", "")
    rc = resolve_monarch(run_only_site(site, recipes=only_one))
    assert rc.excluded_tasks == {"simple.sf_opp_closed_won": "not_attempted"}
    assert [t["task"] for t in rc.tasks] == ["simple.email_sf_contact_city_update"]


def test_create_run_excludes_nothing(site):
    """Create + run never reads the file, so its task set is untouched."""
    rc = resolve_monarch(monarch_site(site))
    assert rc.excluded_tasks == {} and len(rc.tasks) == 2


def test_every_task_missing_refuses_an_empty_comparison(site):
    empty = RECIPES.replace("""recipes:
  simple.email_sf_contact_city_update:
    workflow_id: wf-1
    recipe_version: 3
    authored_at: '2026-09-04T12:03:11Z'
    attempts_used: 1
  simple.sf_opp_closed_won:
    workflow_id: wf-2
    recipe_version: 2
    authored_at: '2026-09-04T12:09:40Z'
    attempts_used: 3
missing: {}
""", """recipes: {}
missing:
  simple.email_sf_contact_city_update:
    reason: checker_failed
    attempts_used: 3
    detail: 'no'
  simple.sf_opp_closed_won:
    reason: checker_failed
    attempts_used: 3
    detail: 'no'
""")
    with pytest.raises(ConfigError) as exc:
        resolve_monarch(run_only_site(site, recipes=empty))
    assert "every task" in str(exc.value) and "wb monarch recipes" in str(exc.value)


# -- 004 T012: per-recipe drift stops a run-only run before any run request -----

RECIPES_LIVE_KB = RECIPES.replace(
    "kb_hash_file_sha: 9f2c1d0ea3b47856c9d2e0f1a4b6c8d90e2f4a6b8c0d2e4f6a8b0c2d4e6f8a0b",
    "kb_hash_file_sha: <the kb file sha>")

# The two workflows the fixture's recipes name, as Monarch would serve them.
LIVE_WORKFLOWS = {"wf-1": {"recipeVersion": 3}, "wf-2": {"recipeVersion": 2}}


def _run_only_arm(site, tmp_path, recipes, workflows, kb=KB):
    """Build the run-only Monarch arm against the fakes; returns (arm, rc, fake, fd)."""
    from tests.fake_fd import fd_serving
    from tests.fake_monarch import FakeMonarch, Scenario
    from tests.monarch_helpers import arm_against, free_port

    git_repo = tmp_path / "monarch-checkout"
    git_repo.mkdir()
    _git_init(git_repo)
    on_disk = {slug: h for slug, h in
               (line.strip().split(": ") for line in kb.splitlines()
                if line.startswith("  bench-"))}
    port = free_port()
    monarch, fd = FakeMonarch(Scenario(workflows=workflows)).start(), fd_serving(on_disk).start()
    try:
        arm_against(site, monarch, port, git_repo, fd=fd, kb=kb)
        run_only_site(site, recipes=recipes, kb=kb, monarch_repo=str(git_repo))
        # run_only_site rewrites the harness from the template, so point it back
        # at the fakes and keep the free port.
        text = (site / "config/harnesses/monarch.yaml").read_text()
        from tests.test_config import edit as _edit
        text = (_edit(_edit(text, "base_url", monarch.url), "fd_url", fd.url)
                .replace("shim_port: 9105", f"shim_port: {port}")
                .replace("shim_public_host: host.docker.internal",
                         "shim_public_host: 127.0.0.1"))
        write(site / "config/harnesses", text)
        rc = resolve_monarch(site)
        store = Store(tmp_path / "wb.sqlite3")
        orch = Orchestrator.from_config(store, rc, tmp_path / "out")
        yield orch, monarch
    finally:
        monarch.stop()
        fd.stop()


def _refuses(site, tmp_path, recipes, workflows, kb=KB) -> tuple:
    """Run the orchestrator and return (the InfraError, the fake's requests)."""
    from wb_arms.api_loop import InfraError
    gen = _run_only_arm(site, tmp_path, recipes, workflows, kb=kb)
    orch, monarch = next(gen)
    try:
        with pytest.raises(InfraError) as exc:
            orch.run("run-drift")
        return exc.value, list(monarch.requests)
    finally:
        gen.close()


def test_recipe_drift_refuses(site, tmp_path):
    """A recipe version that moved: the run stops naming the task and both versions."""
    live = {"wf-1": {"recipeVersion": 4}, "wf-2": {"recipeVersion": 2}}
    err, requests = _refuses(site, tmp_path, RECIPES_LIVE_KB, live)
    assert err.kind == "infra:harness_crash" and not err.retryable
    assert "simple.email_sf_contact_city_update" in str(err)
    assert "3" in str(err) and "4" in str(err)
    assert "monarch-recipes.yaml" in str(err)
    assert not [r for r in requests if r["path"].endswith("/run")]


def test_a_gone_workflow_refuses_and_says_to_rerun_the_command(site, tmp_path):
    err, requests = _refuses(site, tmp_path, RECIPES_LIVE_KB, {"wf-1": {"recipeVersion": 3}})
    assert err.kind == "infra:harness_crash" and not err.retryable
    assert "simple.sf_opp_closed_won" in str(err) and "wb monarch recipes" in str(err)
    assert not [r for r in requests if r["path"].endswith("/run")]


def test_a_changed_knowledge_base_file_refuses(site, tmp_path):
    """The recipes were made against another kb file, so they must be remade."""
    err, requests = _refuses(site, tmp_path, RECIPES, LIVE_WORKFLOWS)   # the fixture's fake sha
    assert err.kind == "infra:harness_crash" and not err.retryable
    assert "the recipes must be remade" in str(err)
    assert not [r for r in requests if r["path"].endswith("/run")]


def test_recipes_that_match_do_not_refuse(site, tmp_path):
    """Every recorded workflow is read, and a matching set lets the run proceed."""
    gen = _run_only_arm(site, tmp_path, RECIPES_LIVE_KB, LIVE_WORKFLOWS)
    orch, monarch = next(gen)
    try:
        arm = orch._arm_for_prepare() if hasattr(orch, "_arm_for_prepare") else None
        from wb_orchestrator.orchestrator import build_arm_for
        arm = build_arm_for(next(c for c in orch.run_config.competitors
                                 if c.harness.kind == "monarch"), orch.run_config)
        arm.env = MONARCH_ENV
        arm.prepare()
    finally:
        gen.close()
    reads = [r["path"] for r in monarch.requests if r["method"] == "GET"
             and r["path"].startswith("/api/workflows/wf-")]
    assert sorted(reads) == ["/api/workflows/wf-1", "/api/workflows/wf-2"]


# -- 004 T015: the run-only banner line ----------------------------------------

def test_banner_states_the_mode_the_recipes_and_the_exclusions(site, tmp_path):
    """contracts/cli.md: a run-only run says what it will run and what it dropped."""
    git_repo = tmp_path / "checkout"
    git_repo.mkdir()
    _git_init(git_repo)
    run_only_site(site, recipes=RECIPES_WITH_MISSING, monarch_repo=str(git_repo))
    line = _banner(resolve_monarch(site)).splitlines()[-1]
    assert line.startswith("monarch   monarch@")
    assert "mode run-only" in line
    assert "1 recipe," in line and "1 task excluded (checker_failed)" in line


def test_banner_of_a_create_run_plan_says_nothing_about_recipes(site, tmp_path):
    git_repo = tmp_path / "checkout"
    git_repo.mkdir()
    _git_init(git_repo)
    monarch_site(site, monarch_repo=str(git_repo))
    line = _banner(resolve_monarch(site)).splitlines()[-1]
    assert "run-only" not in line and "recipe" not in line and "excluded" not in line


def test_banner_states_the_arithmetic(site):
    """T031: the round's size in the agreed words, for every plan.

    A bare per-competitor total is never printed on its own: the banner shows
    where the number comes from, so nobody has to recompute it before spending.
    """
    plan = edit(PLAN, "competitors")
    plan = edit(plan, "baseline", "oracle")
    plan = edit(plan, "tasks", f'"{(site / "tasks").as_posix()}"')
    plan += "competitors:\n  - {harness: oracle}\n"
    write(site / "config/plans", plan)
    rc = config.resolve(site / "config/products/simulated-apps.yaml",
                        site / "config/plans/smoke-frontier.yaml", audiences={"internal": ["*"]})
    out = _banner(rc)

    # 2 prompts x 2 repetitions = 4 per competitor, 1 competitor, 4 in the round
    assert ("prompts: 2; attempts per prompt and competitor: 2; "
            "attempts per competitor: 4 = 2 x 2") in out
    assert "competitors: 1; attempts in the round: 4" in out

    # the arithmetic is always spelled out, never a bare per-competitor total
    for line in out.splitlines():
        if "attempts per competitor" in line:
            assert "=" in line and " x " in line



# -- unblock plan M2: the evaluation track is a plan field and part of the hash ---

MOCK_COMPETITORS = """competitors:
  - {harness: oracle}
  - {model: mock, harness: api}
"""


def _mock_plan(site, extra: str = "") -> str:
    write(site / "config/models", MODEL_MOCK)
    plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
    plan = edit(plan, "baseline", "oracle") + MOCK_COMPETITORS + extra
    write(site / "config/plans", plan)
    return plan


def _resolve_smoke(site):
    return config.resolve(site / "config/products/simulated-apps.yaml",
                          site / "config/plans/smoke-frontier.yaml", audiences={"internal": ["*"]})


def test_plan_track_defaults_to_create_run_and_keeps_the_hash(site, monkeypatch):
    monkeypatch.setenv("WB_MOCK_KEY", "set")
    _mock_plan(site)
    rc = _resolve_smoke(site)
    assert rc.plan.track == "create-run"
    h0 = rc.hash
    _mock_plan(site, "track: create-run" + chr(10))
    assert _resolve_smoke(site).hash == h0, "writing the default track must not move the hash"


def test_plan_track_agentic_request_is_a_different_measurement(site, monkeypatch):
    monkeypatch.setenv("WB_MOCK_KEY", "set")
    _mock_plan(site)
    h0 = _resolve_smoke(site).hash
    _mock_plan(site, "track: agentic-request" + chr(10))
    rc = _resolve_smoke(site)
    assert rc.plan.track == "agentic-request"
    assert rc.hash != h0


def test_plan_track_rejects_unknown_values(site, monkeypatch):
    monkeypatch.setenv("WB_MOCK_KEY", "set")
    _mock_plan(site, "track: browsing" + chr(10))
    with pytest.raises(ConfigError, match="track"):
        _resolve_smoke(site)
