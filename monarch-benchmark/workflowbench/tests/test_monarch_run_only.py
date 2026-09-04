"""The Monarch competitor in run-only mode (004, US2).

Run-only executes one workflow the bench froze earlier and nothing else: no
authoring request, no delete whatever the outcome, an execution phase and no
authoring phase, and a cost read from the execution trace alone. The tests drive
the real arm against the fake backend, as the create + run tests do.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

from tests.fake_fd import fd_serving
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch, Scenario
from tests.monarch_helpers import (  # noqa: F401  (repo is a fixture)
    KB, KB_SHA_MARKER, MONARCH_ENV, RECIPES, TASKS_MARKER, arm_against, free, free_port, git,
    kb_file_sha, monarch_site, repo, resolve_monarch, run_only_site)
from tests.test_config import (  # noqa: F401  (site is a fixture)
    HARNESS_MONARCH, HARNESS_SCRIPTED, PLAN, PRICE_TABLE, edit, site, write)
from tests.test_monarch_arm import (
    LANGFUSE_ENV, OPUS, SF, TASKS_DIR, USAGE, engine_calls_for, task)
from tests.test_monarch_client import header
from wb_arms.api_loop import EpisodeTimeout, InfraError
from wb_arms.monarch import MonarchArm, bench_episode_id
from wb_orchestrator import config
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import Orchestrator, build_arm_for
from wb_report.report import build_report, render_md
from wb_results.store import Store
from wb_world.episode import Episode, load_suite, load_task_file
from wb_world.seeds import product_slug

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PATH = ROOT / "config/products/simulated-apps.yaml"

# The task the site fixture's recipes name first, and the workflow frozen for it.
TASK_ID = "simple.email_sf_contact_city_update"

# One recipe, for the one task the attempt tests drive, with the real kb
# fingerprint so `prepare()` is happy when a test calls it.
ONE_RECIPE = f"""\
product: simulated-apps
tasks: {TASKS_MARKER}
generated_at: '2026-09-04T12:00:00Z'
kb_hash_file_sha: {KB_SHA_MARKER}
monarch: monarch@1a2b3c4
recipes:
  {TASK_ID}:
    workflow_id: wf-1
    recipe_version: 3
    authored_at: '2026-09-04T12:03:11Z'
    attempts_used: 1
missing:
  simple.sf_opp_closed_won:
    reason: checker_failed
    attempts_used: 3
    detail: 'invariant failed'
"""

LIVE_WF = {"wf-1": {"recipeVersion": 3}}


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """The fakes answer instantly; a 2 s production poll would only add dead time."""
    monkeypatch.setattr(MonarchArm, "POLL_INTERVAL_S", 0.02)


def run_only_arm(site, fake, port, repo, fd=None, recipes=ONE_RECIPE, langfuse=None,
                 env=None):
    """The Monarch arm of a run-only plan, pointed at the fakes on their real ports."""
    env = env or MONARCH_ENV
    arm_against(site, fake, port, repo, fd=fd, langfuse=langfuse, env=env)
    harness = (site / "config/harnesses/monarch.yaml").read_text()
    run_only_site(site, recipes=recipes, monarch_repo=str(repo))
    write(site / "config/harnesses", harness.replace("modes: [create-run]",
                                                     "modes: [create-run, run-only]"))
    rc = resolve_monarch(site, env=env)
    arm = build_arm_for(next(c for c in rc.competitors if c.harness.kind == "monarch"), rc)
    arm.env = env               # build_arm_for hands it os.environ, not the test's
    return arm


def episode(task_id: str = TASK_ID, arm_name: str = "monarch") -> Episode:
    return Episode(load_task_file(TASKS_DIR / f"{task_id}.json"),
                   episode_id=f"run-x/{task_id}/{arm_name}/t0")


def city_of(snapshot: dict, contact_id: str = "003004") -> str:
    return next(c["mailing_city"] for c in snapshot["salesforce"]["contacts"]
                if c["id"] == contact_id)


# -- T016: one run-only attempt ------------------------------------------------

def test_run_only_attempt(site, repo):
    """The frozen workflow runs; nothing is authored, nothing is deleted."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF,
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = run_only_arm(site, fake, port, repo)
        assert arm.mode == "run-only"
        ep = episode()
        result = arm.run(ep, deadline=time.monotonic() + 60)
        snapshot = ep.finish()

    assert city_of(snapshot) == "Denver"          # the engine's changes, taken by the bench
    assert result.termination == "completed" and result.error is None
    assert not [r for r in fake.requests if r["path"] == "/api/workflows/recipe/runs"]
    runs = [r for r in fake.requests if r["method"] == "POST" and r["path"].endswith("/run")]
    assert [r["path"] for r in runs] == ["/api/workflows/wf-1/run"]
    assert header(runs[0], "x-bench-episode-id") == bench_episode_id(ep.episode_id)
    assert fake.deleted_workflows == []
    assert "execution" in result.phases and "authoring" not in result.phases
    assert result.phases["execution"].wall_clock_s > 0
    ids = result.turn_log[0]["monarch"]
    assert ids["workflowId"] == "wf-1" and ids["recipeVersion"] == 3 and ids["runId"] == "run-1"
    assert "recipeRunId" not in ids
    assert not [f for f in result.flags if f.startswith("questions_asked")]


def test_create_run_still_authors_and_deletes(site, repo):
    """The create + run attempt is untouched by the mode branch."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        assert arm.mode == "create-run"
        result = arm.run(episode(), deadline=time.monotonic() + 60)

    assert result.termination == "completed"
    assert [r for r in fake.requests if r["path"] == "/api/workflows/recipe/runs"]
    assert fake.deleted_workflows == ["wf-1"]
    assert "authoring" in result.phases


# -- T018: the mode and the recipes reach the arm ------------------------------

def test_a_run_only_plan_without_recipes_fails_at_build_time(site, repo):
    """resolve() refuses first; a hand-built config without them must not run either."""
    port = free_port()
    with FakeMonarch(Scenario()) as fake:
        arm_against(site, fake, port, repo)
        run_only_site(site, recipes=None, monarch_repo=str(repo))
        with pytest.raises(ConfigError) as exc:
            resolve_monarch(site)
    assert "monarch-recipes.yaml" in str(exc.value)
    assert "wb monarch recipes" in str(exc.value)


def test_build_arm_for_refuses_run_only_without_the_recipes_on_the_config(site, repo):
    """The arm builder is the second guard: no recipes, no run-only competitor."""
    port = free_port()
    with FakeMonarch(Scenario()) as fake:
        arm = run_only_arm(site, fake, port, repo)
        rc = resolve_monarch(site)
        object.__setattr__(rc, "monarch_recipes", None)
        with pytest.raises(ConfigError) as exc:
            build_arm_for(next(c for c in rc.competitors if c.harness.kind == "monarch"), rc)
    assert "monarch-recipes.yaml" in str(exc.value) and arm.mode == "run-only"


# -- T019/T020: the recipe survives every outcome ------------------------------

def test_timeout_leaves_the_recipe(site, repo):
    """The engine never finishes: the attempt times out and the workflow stays."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF,
                  run_never_finishes=True)
    with FakeMonarch(sc) as fake:
        arm = run_only_arm(site, fake, port, repo)
        arm.timeout_s = 1.0
        with pytest.raises(EpisodeTimeout) as exc:
            arm.run(episode(), deadline=time.monotonic() + 60)

    assert "execution" in str(exc.value)
    assert fake.deleted_workflows == [] and fake.deleted_at == []
    # The row still says where the deadline passed, and the recipe is still there.
    assert "execution" in exc.value.partial.phases
    assert "authoring" not in exc.value.partial.phases


@pytest.mark.parametrize("name, kwargs", [
    ("a refused run", {"run_refusal": "INPUT_INVALID"}),
    ("a failed run", {"run_outcome": {"status": "failed", "errorCode": "NODE_FAILED"}}),
    ("a succeeded run", {"run_outcome": {"status": "succeeded"}}),
])
def test_no_delete_on_any_outcome(site, repo, name, kwargs):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF, **kwargs)
    with FakeMonarch(sc) as fake:
        arm = run_only_arm(site, fake, port, repo)
        arm.run(episode(), deadline=time.monotonic() + 60)

    assert fake.deleted_workflows == [], f"{name} deleted the frozen recipe"
    assert not [r for r in fake.requests if r["method"] == "DELETE"]


# -- T021: cost from the execution trace alone ---------------------------------

def test_cost_from_execution_trace(site, repo):
    """No authoring means no trace-id shortcut: the reader gets the attempt id only."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF,
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    ep = episode()
    with FakeMonarch(sc) as fake, FakeLangfuse() as langfuse:
        # Only an execution span: nothing authored, so nothing to price for authoring.
        langfuse.add_trace(bench_episode_id(ep.episode_id),
                           spans=[("s1", "engine.run", None)],
                           generations=[("g1", "s1", OPUS, USAGE)])
        arm = run_only_arm(site, fake, port, repo, langfuse=langfuse,
                           env={**MONARCH_ENV, **LANGFUSE_ENV(langfuse)})
        result = arm.run(ep, deadline=time.monotonic() + 60)

    assert result.termination == "completed"
    assert result.cost_usd and result.cost_usd > 0
    assert "cost_missing" not in result.flags
    assert result.phases["execution"].cost_usd == pytest.approx(result.cost_usd)
    assert "authoring" not in result.phases
    # The frames were the only source of trace ids, and there were no frames, so
    # the reader had to fall back to the attempt id in the trace metadata (R8).
    assert arm._trace_ids == []
    # The reader's first read was the metadata filter, not a trace fetched by id.
    assert "metadata" in langfuse.requests[0]["path"], langfuse.requests[0]
    assert not [r for r in langfuse.requests if r["path"].startswith("/api/public/traces/")]


# -- T022: the run-only plan end to end, offline -------------------------------

def run_only_pilot_site(tmp_path, monarch_url, fd_url, port, repo, kb_hashes) -> Path:
    """A config tree on the 10 pilot tasks: answer key and Monarch, run-only."""
    site = tmp_path / "site"
    for sub in ("products", "models", "harnesses", "plans"):
        (site / "config" / sub).mkdir(parents=True)
    (site / "config/products" / PRODUCT_PATH.name).write_text(
        PRODUCT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    write(site / "config/models", PRICE_TABLE)
    write(site / "config/harnesses", HARNESS_SCRIPTED)
    harness = (edit(HARNESS_MONARCH, "runnable", "true")
               .replace("modes: [full-flow, create-run, run-only]", "modes: [run-only]"))
    harness = (edit(edit(edit(harness, "base_url", monarch_url), "fd_url", fd_url),
                    "monarch_repo", str(repo))
               .replace("shim_port: 9105", f"shim_port: {port}")
               .replace("shim_public_host: host.docker.internal", "shim_public_host: 127.0.0.1"))
    write(site / "config/harnesses", harness)
    plan = edit(PLAN, "tasks", f'"{TASKS_DIR.as_posix()}"')
    plan = edit(edit(edit(plan, "competitors"), "baseline", "oracle"), "mode", "run-only")
    plan += "competitors:\n  - {harness: oracle}\n  - {harness: monarch}\n"
    write(site / "config/plans", plan)
    kb_path = site / "config/products/simulated-apps.monarch-kb.yaml"
    kb_path.write_text(yaml.safe_dump(
        {"product": "simulated-apps", "generated_at": "2026-09-04T12:00:00Z",
         "seeds_format": "public-api-seeds@1",
         "shim_public_url": f"http://127.0.0.1:{port}", "kb": kb_hashes}))
    return site


def write_pilot_recipes(site, tasks, excluded: str) -> dict:
    """One recipe per pilot task but `excluded`; returns workflow id -> its detail."""
    ids = {t["task"]: f"wf-{i}" for i, t in enumerate(tasks) if t["task"] != excluded}
    (site / "config/products/simulated-apps.monarch-recipes.yaml").write_text(yaml.safe_dump({
        "product": "simulated-apps", "tasks": TASKS_DIR.as_posix(),
        "generated_at": "2026-09-04T12:00:00Z",
        "kb_hash_file_sha": kb_file_sha(site),
        "monarch": "monarch@1a2b3c4",
        "recipes": {t: {"workflow_id": w, "recipe_version": 1,
                        "authored_at": "2026-09-04T12:00:00Z", "attempts_used": 1}
                    for t, w in ids.items()},
        "missing": {excluded: {"reason": "checker_failed", "attempts_used": 3,
                               "detail": "invariant failed: is_closed, is_won changed"}}}))
    return ids


def test_pilot_plan_offline(tmp_path, repo, monkeypatch):
    """The run-only plan on 9 of the 10 pilot tasks x 2, against fakes on free ports."""
    port = free_port()
    for k, v in MONARCH_ENV.items():
        monkeypatch.setenv(k, v)
    tasks = load_suite(TASKS_DIR)
    excluded = "simple.sf_opp_closed_won"
    kb_hashes = {product_slug(s): f"{i:012x}"
                 for i, s in enumerate(config.load_product(PRODUCT_PATH).services)}
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}")

    with FakeMonarch(sc) as monarch, fd_serving(kb_hashes) as fd:
        site = run_only_pilot_site(tmp_path, monarch.url, fd.url, port, repo, kb_hashes)
        ids = write_pilot_recipes(site, tasks, excluded)
        # Every frozen workflow exists at the recorded version, so prepare() passes.
        sc.workflows = {w: {"recipeVersion": 1} for w in ids.values()}
        rc = config.resolve(site / "config/products/simulated-apps.yaml",
                            site / "config/plans/smoke-frontier.yaml",
                            env={**MONARCH_ENV}, audiences={"internal": ["*"]})
        assert len(rc.tasks) == 9 and rc.excluded_tasks == {excluded: "checker_failed"}
        store = Store(tmp_path / "wb.sqlite3")
        orch = Orchestrator.from_config(store, rc, tmp_path / "out")
        arm = build_arm_for(next(c for c in rc.competitors if c.harness.kind == "monarch"), rc)
        # One story per attempt: the frozen workflow performs that task's answer-key calls.
        sc.engine_calls_by_episode = {
            bench_episode_id(f"run-pilot/{t['task']}/{arm.name}/t{trial}"): engine_calls_for(t)
            for t in rc.tasks for trial in range(2)}
        run_id = orch.run("run-pilot")

    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 36                      # 9 tasks x 2 repetitions x 2 competitors
    assert excluded not in {r["task_id"] for r in rows}
    oracle = [r for r in rows if r["arm"] == "oracle"]
    mon = [r for r in rows if r["arm"] != "oracle"]
    assert len(oracle) == 18 and all(r["passed"] for r in oracle)
    assert len(mon) == 18
    assert all(r["termination"] == "completed" for r in mon), \
        {r["episode_id"]: r["error"] for r in mon if r["termination"] != "completed"}
    assert all(r["test_mode"] == "run-only" for r in mon)
    assert all("snapshot1" in store.artifacts(r["episode_id"]) for r in mon)
    assert all("authoring" not in (r["phases"] or {}) for r in mon)
    assert sum(r["passed"] for r in mon) == 18

    # Nothing was authored and nothing was deleted, on any of the 18 attempts.
    assert not [r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]
    assert monarch.deleted_workflows == []

    md = render_md(build_report(store, run_id, audience="internal"))
    assert "oracle" in md and mon[0]["arm"] in md
    assert "1 task excluded (checker_failed)" in md
    assert ("Monarch executed a fixed known-correct workflow; the other competitors "
            "did the whole task from the request text.") in md
    cfg = json.loads(store.run(run_id)["config_json"])
    assert cfg["mode"] == "run-only" and cfg["excluded_tasks"] == {excluded: "checker_failed"}
    assert len(cfg["monarch_recipes"]["recipes"]) == 9


# -- T024/T025: a run already in flight on the recipe --------------------------

def test_active_run_is_waited_out(site, repo):
    """A leftover run from a timed-out attempt is polled to terminal, then the run starts."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF,
                  active_run_for={"wf-1": 2},
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = run_only_arm(site, fake, port, repo)
        ep = episode()
        result = arm.run(ep, deadline=time.monotonic() + 60)
        snapshot = ep.finish()

    assert result.termination == "completed" and result.error is None
    assert city_of(snapshot) == "Denver"
    # It kept asking until the refusals ran out, and never deleted the recipe.
    runs = [r for r in fake.requests if r["method"] == "POST" and r["path"].endswith("/run")]
    assert len(runs) == 3 and all(r["path"] == "/api/workflows/wf-1/run" for r in runs)
    assert fake.deleted_workflows == []
    assert [r["path"] for r in fake.requests].count("/api/workflows/wf-1/runs") >= 1


def test_active_run_never_clears(site, repo, monkeypatch):
    """Nothing can cancel a run, so a wait that expires is infrastructure, retried."""
    monkeypatch.setattr("wb_arms.monarch.ACTIVE_RUN_WAIT_S", 0.3)
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF,
                  active_run_never_clears=True)
    with FakeMonarch(sc) as fake:
        arm = run_only_arm(site, fake, port, repo)
        with pytest.raises(InfraError) as exc:
            arm.run(episode(), deadline=time.monotonic() + 60)

    assert exc.value.kind == "infra:monarch_setup" and exc.value.retryable
    assert "0.3" in str(exc.value) or "waited" in str(exc.value)
    assert fake.deleted_workflows == []
    # The front door let go of its fixed port even though the attempt failed.
    free(port)


# -- T026: the recorded workflow is gone --------------------------------------

def test_workflow_gone_is_infra(site, repo):
    """The run request 404s: the recipe named in the file no longer exists."""
    port = free_port()
    # `workflows` is empty, so prepare() would refuse first; this is the race where
    # the workflow disappears between the check and the attempt.
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", workflows=LIVE_WF)
    with FakeMonarch(sc) as fake:
        arm = run_only_arm(site, fake, port, repo)
        # wf-1 is deleted behind the bench's back; the backend still holds others.
        sc.workflows = {"wf-other": {"recipeVersion": 1}}
        with pytest.raises(InfraError) as exc:
            arm.run(episode(), deadline=time.monotonic() + 60)

    assert exc.value.kind == "infra:harness_crash" and not exc.value.retryable
    assert TASK_ID in str(exc.value) and "monarch-recipes.yaml" in str(exc.value)
    assert fake.deleted_workflows == []
