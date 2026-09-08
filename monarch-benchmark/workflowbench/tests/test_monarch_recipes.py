"""`wb monarch recipes` (004, US1): making one known-correct recipe per task.

The command drives the create + run attempt up to N times per task on a fresh
world, grades each result with the bench's own checker, keeps the first workflow
that passes and deletes the rest. It is the only paid path of this feature, so
its gate, its idempotence and its accounting are what these tests pin down.
Everything here runs against the fakes; nothing calls a model.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml

from tests.fake_fd import fd_serving
from tests.fake_monarch import FakeMonarch, Scenario
from tests.monarch_helpers import (  # noqa: F401  (repo is a fixture)
    KB, MONARCH_ENV, arm_against, free_port, git, kb_file_sha, monarch_site, repo,
    resolve_monarch)
from tests.test_config import (  # noqa: F401  (site is a fixture)
    edit, site, write)
from tests.test_monarch_arm import SF, TASKS_DIR, engine_calls_for
from wb_orchestrator import monarch_recipes
from wb_orchestrator.cli import main
from wb_world.episode import load_task_file

ROOT = Path(__file__).resolve().parents[1]

# The two tasks the `site` fixture copies; the second is the one the smoke found
# an approval-rule gap on, which makes it the natural "never passes" story.
TASK_A = "simple.email_sf_contact_city_update"
TASK_B = "simple.sf_opp_closed_won"

# The kb hashes the fake discovery service serves, matching the KB helper.
KB_HASHES = {slug: h for slug, h in
             (line.strip().split(": ") for line in KB.splitlines()
              if line.startswith("  bench-"))}


def right_calls(task_id: str) -> list[tuple]:
    """The answer key as REST calls: what a workflow that passes the checker does."""
    return engine_calls_for(load_task_file(TASKS_DIR / f"{task_id}.json"))


WRONG_CALLS = [("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Nowhere"})]


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    from wb_arms.monarch import MonarchArm
    monkeypatch.setattr(MonarchArm, "POLL_INTERVAL_S", 0.02)


def recipes_site(site, monarch, fd, port, repo, kb_hashes=None):
    """A config tree whose Monarch competitor points at the fakes, in create + run."""
    arm_against(site, monarch, port, repo, fd=fd)
    # Fixed bytes, not the run's port: the file's sha is the fingerprint the
    # recipes carry, and a rerun on another free port must still count as the
    # same knowledge base.
    (site / "config/products/simulated-apps.monarch-kb.yaml").write_text(
        yaml.safe_dump({"product": "simulated-apps", "generated_at": "2026-09-04T12:00:00Z",
                        "seeds_format": "public-api-seeds@1",
                        "shim_public_url": "http://127.0.0.1:9105",
                        "kb": kb_hashes or KB_HASHES}))
    return site


def run_recipes(site, out=None, **kw):
    """Call the step directly, capturing what it printed."""
    buf = out or io.StringIO()
    code = monarch_recipes.run(
        product_path=site / "config/products/simulated-apps.yaml",
        harness_path=site / "config/harnesses/monarch.yaml",
        tasks_dir=site / "tasks", env=MONARCH_ENV, stdout=buf, **kw)
    return code, buf.getvalue()


def recipes_file(site) -> dict:
    return yaml.safe_load(
        (site / "config/products/simulated-apps.monarch-recipes.yaml").read_text())


# -- T027: the gate ------------------------------------------------------------

def test_without_a_yes_it_prints_the_cost_band_and_spends_nothing(site, repo):
    port = free_port()
    with FakeMonarch(Scenario()) as monarch, fd_serving(KB_HASHES) as fd:
        recipes_site(site, monarch, fd, port, repo)
        code, out = run_recipes(site, attempts=3)

    assert code == 5
    assert "2 tasks" in out and "3 authoring attempts" in out and "6 attempts" in out
    assert "cost band" in out and "US$" in out
    assert "tasks already covered for this knowledge base: 0" in out
    assert monarch.requests == []      # not one request, let alone one model call


def test_yes_proceeds(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls_by_episode={})
    with FakeMonarch(sc) as monarch, fd_serving(KB_HASHES) as fd:
        recipes_site(site, monarch, fd, port, repo)
        code, out = run_recipes(site, attempts=1, yes=True)

    assert code in (0, 1)              # it ran; what it found is another test's business
    assert [r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]


def test_an_approved_plan_proceeds_without_a_yes(site, repo):
    port = free_port()
    plan = (site / "config/plans/smoke-frontier.yaml").read_text()
    write(site / "config/plans", edit(plan, "approved_by", "carlos"))
    with FakeMonarch(Scenario(shim_url=f"http://127.0.0.1:{free_port()}")) as monarch, \
            fd_serving(KB_HASHES) as fd:
        recipes_site(site, monarch, fd, free_port(), repo)
        write(site / "config/plans", edit(
            (site / "config/plans/smoke-frontier.yaml").read_text(), "approved_by", "carlos"))
        code, out = run_recipes(site, attempts=1,
                                plan_path=site / "config/plans/smoke-frontier.yaml")

    assert code in (0, 1)
    assert [r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]


def test_a_missing_knowledge_base_file_points_at_wb_monarch_setup(site, repo):
    """The gate cannot even price the run without knowing which knowledge base it is."""
    port = free_port()
    with FakeMonarch(Scenario()) as monarch, fd_serving(KB_HASHES) as fd:
        recipes_site(site, monarch, fd, port, repo)
        (site / "config/products/simulated-apps.monarch-kb.yaml").unlink()
        code, out = run_recipes(site, attempts=3, yes=True)

    assert code == 6 and "wb monarch setup" in out
    assert monarch.requests == []


# -- T029: one task, first pass / third pass / never passes --------------------

def drive(site, repo, stories, attempts=3, tasks=(TASK_A,), kb_hashes=None, **kw):
    """Run the command with one engine story per attempt per task."""
    from wb_arms.monarch import bench_episode_id
    port = free_port()
    # Each authoring job gets its own workflow, as the real backend does: the
    # command authors the same task several times and deletes the ones that fail.
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", unique_workflow_ids=True)
    with FakeMonarch(sc) as monarch, fd_serving(kb_hashes or KB_HASHES) as fd:
        recipes_site(site, monarch, fd, port, repo, kb_hashes=kb_hashes)
        for name in list((site / "tasks").glob("*.json")):
            if name.stem not in tasks:
                name.unlink()
        arm = monarch_recipes._arm(site / "config/products/simulated-apps.yaml",
                                   site / "config/harnesses/monarch.yaml", MONARCH_ENV)
        sc.engine_calls_by_episode = {
            bench_episode_id(f"recipes/{task_id}/{arm.name}/t{i}"): calls
            for task_id, per_attempt in stories.items()
            for i, calls in enumerate(per_attempt)}
        code, out = run_recipes(site, attempts=attempts, yes=True, **kw)
        return code, out, monarch, recipes_file(site)


def test_a_first_attempt_that_passes_is_kept(site, repo):
    code, out, monarch, doc = drive(site, repo, {TASK_A: [right_calls(TASK_A)]})

    assert code == 0
    assert len([r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]) == 1
    assert monarch.deleted_workflows == []          # the winner is not deleted
    row = doc["recipes"][TASK_A]
    assert row["workflow_id"] == "wf-1" and row["recipe_version"] == 1
    assert row["attempts_used"] == 1 and row["authored_at"]
    assert doc["missing"] == {}
    assert "kept wf wf-1" in out


def test_a_third_attempt_that_passes_deletes_the_two_before_it(site, repo):
    code, out, monarch, doc = drive(
        site, repo, {TASK_A: [WRONG_CALLS, WRONG_CALLS, right_calls(TASK_A)]})

    assert code == 0
    assert len([r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]) == 3
    assert len(monarch.deleted_workflows) == 2      # the two that failed the checker
    assert doc["recipes"][TASK_A]["attempts_used"] == 3
    assert doc["missing"] == {}


def test_a_task_that_never_passes_is_missing_and_deletes_everything(site, repo):
    code, out, monarch, doc = drive(
        site, repo, {TASK_A: [WRONG_CALLS, WRONG_CALLS, WRONG_CALLS]})

    assert code == 1
    assert len(monarch.deleted_workflows) == 3      # nothing kept
    assert TASK_A not in doc["recipes"]
    row = doc["missing"][TASK_A]
    assert row["reason"] == "checker_failed" and row["attempts_used"] == 3
    assert row["detail"]                            # the last attempt's verdict
    assert "no passing recipe after 3 attempts (checker_failed)" in out


# -- T031: the reasons other than the checker's --------------------------------

def _reason_of(site, repo, scenario_kwargs, attempts=1, **kw) -> tuple:
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", **scenario_kwargs)
    with FakeMonarch(sc) as monarch, fd_serving(KB_HASHES) as fd:
        recipes_site(site, monarch, fd, port, repo)
        for name in list((site / "tasks").glob("*.json")):
            if name.stem != TASK_A:
                name.unlink()
        code, out = run_recipes(site, attempts=attempts, yes=True, **kw)
        return recipes_file(site)["missing"].get(TASK_A), monarch, out


def test_an_authoring_error_is_authoring_error(site, repo):
    row, _, _ = _reason_of(site, repo, {"frames": [
        {"status": "running", "phase": "plan"},
        {"status": "error", "error": "planner gave up"}]})
    assert row["reason"] == "authoring_error" and "planner gave up" in row["detail"]


def test_a_failed_run_is_run_error(site, repo):
    row, _, _ = _reason_of(site, repo, {
        "run_outcome": {"status": "failed", "errorCode": "NODE_FAILED"}})
    assert row["reason"] == "run_error" and "NODE_FAILED" in row["detail"]


def test_an_infrastructure_failure_consumes_no_attempt(site, repo):
    """Monarch's own model provider failing is not the workflow's fault."""
    row, monarch, out = _reason_of(site, repo, {"frames": [
        {"status": "running", "phase": "plan"},
        {"status": "error", "error": "Bedrock AccessDeniedException"}]}, attempts=3)
    assert row["reason"] == "infra" and row["attempts_used"] == 0
    # It stopped at the first one rather than burning the other two.
    assert len([r for r in monarch.requests
                if r["path"] == "/api/workflows/recipe/runs"]) == 1


def test_a_deadline_is_timeout(site, repo):
    row, monarch, out = _reason_of(site, repo, {"run_never_finishes": True}, timeout_s=1.0)
    assert row["reason"] == "timeout"


# -- T032: the file and idempotence -------------------------------------------

def test_the_written_file_matches_the_contract(site, repo):
    code, out, monarch, doc = drive(site, repo, {TASK_A: [right_calls(TASK_A)]})
    path = site / "config/products/simulated-apps.monarch-recipes.yaml"

    assert doc["product"] == "simulated-apps"
    # The task-set NAME a plan writes, not a path: that is what the loader
    # compares a run's plan against.
    assert doc["tasks"] == (site / "tasks").as_posix()
    assert doc["kb_hash_file_sha"] == kb_file_sha(site)
    assert doc["monarch"].startswith("monarch@")
    assert set(doc) == {"product", "tasks", "generated_at", "kb_hash_file_sha", "monarch",
                        "recipes", "missing"}
    # sorted keys, so a rerun's diff is the rows that changed and nothing else
    assert path.read_text() == yaml.safe_dump(doc, sort_keys=True, default_flow_style=False)


def test_a_second_run_makes_no_authoring_request_and_writes_the_same_bytes(site, repo):
    drive(site, repo, {TASK_A: [right_calls(TASK_A)]})
    path = site / "config/products/simulated-apps.monarch-recipes.yaml"
    first = path.read_text()

    port = free_port()
    with FakeMonarch(Scenario(shim_url=f"http://127.0.0.1:{port}")) as m2, \
            fd_serving(KB_HASHES) as fd:
        code2, out2 = run_recipes(site, attempts=3, yes=True)

    assert code2 == 0
    assert m2.requests == []                       # not one call, so not one cent
    assert path.read_text() == first               # identical bytes, generated_at included
    assert "already covered" in out2


def test_a_changed_knowledge_base_remakes_every_recipe(site, repo):
    drive(site, repo, {TASK_A: [right_calls(TASK_A)]})
    path = site / "config/products/simulated-apps.monarch-recipes.yaml"
    before = yaml.safe_load(path.read_text())

    # One app re-imported: a different knowledge base, so every recipe is stale.
    moved = {**KB_HASHES, "bench-salesforce": "ffffffffffff"}
    code, out, monarch, doc = drive(site, repo, {TASK_A: [right_calls(TASK_A)]},
                                    kb_hashes=moved)

    assert doc["kb_hash_file_sha"] != before["kb_hash_file_sha"]
    # It authored again rather than trusting a recipe made against other actions.
    assert [r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]


def test_rows_an_earlier_run_earned_survive_a_rerun(site, repo):
    """An interrupted run's recipes are kept; the rerun continues from them."""
    import shutil

    from tests.test_config import TASKS
    drive(site, repo, {TASK_A: [right_calls(TASK_A)]}, tasks=(TASK_A,))
    path = site / "config/products/simulated-apps.monarch-recipes.yaml"
    earned = yaml.safe_load(path.read_text())["recipes"][TASK_A]

    # The second task appears; the first must not be authored a second time.
    shutil.copy(TASKS / f"{TASK_B}.json", site / "tasks" / f"{TASK_B}.json")
    code, out, monarch, doc = drive(site, repo, {TASK_B: [WRONG_CALLS]},
                                    attempts=1, tasks=(TASK_A, TASK_B))

    assert doc["recipes"][TASK_A] == earned
    assert TASK_B in doc["missing"]
    assert len([r for r in monarch.requests if r["path"] == "/api/workflows/recipe/runs"]) == 1


# -- T034: the subcommand ------------------------------------------------------

def test_main_blocks_authoring_until_foundation_ready(site, repo, monkeypatch):
    for k, v in MONARCH_ENV.items():
        monkeypatch.setenv(k, v)
    port = free_port()
    with FakeMonarch(Scenario(shim_url=f"http://127.0.0.1:{port}")) as monarch, \
            fd_serving(KB_HASHES) as fd:
        recipes_site(site, monarch, fd, port, repo)
        code = main(["monarch", "recipes",
                     "--product", str(site / "config/products/simulated-apps.yaml"),
                     "--harness", str(site / "config/harnesses/monarch.yaml"),
                     "--tasks", str(site / "tasks")])
    assert code == 2        # foundation gate precedes paid recipe creation
    assert not monarch.requests


def test_plan_and_tasks_together_are_refused(site, capsys):
    code = main(["monarch", "recipes",
                 "--product", str(site / "config/products/simulated-apps.yaml"),
                 "--plan", str(site / "config/plans/smoke-frontier.yaml"),
                 "--tasks", str(site / "tasks")])
    assert code == 2
    assert "one of" in (capsys.readouterr().err.lower())


# -- T035: the bench-side name -------------------------------------------------

def test_the_bench_side_name_is_printed_with_the_note(site, repo):
    code, out, monarch, doc = drive(site, repo, {TASK_A: [right_calls(TASK_A)]})
    assert f"bench:{TASK_A}" in out
    assert "no route to rename" in out
    # No patch call was made: an ignored rename would be a lie in the log.
    assert not [r for r in monarch.requests if r["method"] == "PATCH"]


# -- the two commands agree on the file ---------------------------------------

def test_a_file_the_command_wrote_loads_on_a_run_only_plan(site, repo):
    """The end of US1 is the start of US2: what `recipes` writes, `wb run` reads.

    The task-set field is the seam -- the command records a name, the loader
    compares it with the plan's -- so a path here would refuse every run.
    """
    from tests.monarch_helpers import resolve_monarch, run_only_site
    drive(site, repo, {TASK_A: [right_calls(TASK_A)]}, tasks=(TASK_A,))
    written = (site / "config/products/simulated-apps.monarch-recipes.yaml").read_text()

    # The same site as a run-only plan, keeping the file the command just wrote.
    run_only_site(site, recipes=None, monarch_repo=str(repo))
    (site / "config/products/simulated-apps.monarch-recipes.yaml").write_text(written)
    rc = resolve_monarch(site)

    assert set(rc.monarch_recipes.recipes) == {TASK_A}
    assert rc.monarch_recipes.recipes[TASK_A].workflow_id == "wf-1"
    assert [t["task"] for t in rc.tasks] == [TASK_A]
    assert rc.excluded_tasks == {}
