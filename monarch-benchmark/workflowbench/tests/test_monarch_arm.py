"""The Monarch competitor: its name, and one attempt end to end (US1, T023-T032).

The row name is the version read from the Monarch repo -- `monarch@<sha>`, plus
`+<branch>` off main -- so a report always says which build was measured. A
`monarch_repo` that is not a git checkout is a config error, not a crash.

The attempt tests drive the real arm against the fake backend: a completed
attempt writes to the `Episode` through the front door, the module lock keeps
two attempts from overlapping, a busy port is infrastructure, and the whole
pilot plan runs offline beside the answer key.
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from runner.arms import _sf_updates_from_assertions
from tests.fake_monarch import FakeMonarch, Scenario
from tests.test_config import (  # noqa: F401  (site is a fixture)
    HARNESS_MONARCH, HARNESS_SCRIPTED, PLAN, PRICE_TABLE, edit, site, write)
from tests.test_monarch_client import header
from tests.test_run_config import KB, MONARCH_ENV, fd_serving, monarch_site, resolve_monarch
from wb_arms.api_loop import InfraError
from wb_arms.monarch import MonarchArm
from wb_orchestrator import config
from wb_orchestrator.config import ConfigError, load_product
from wb_orchestrator.orchestrator import Orchestrator, build_arm_for
from wb_report.report import build_report, render_md
from wb_results.store import Store
from wb_world.episode import Episode, load_suite, load_task_file

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PATH = ROOT / "config/products/simulated-apps.yaml"


def git(repo, *args) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A one-commit git repo standing in for the Monarch checkout, on `main`."""
    d = tmp_path / "monarch"
    d.mkdir()
    git(d, "init", "-q")
    git(d, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "--allow-empty", "-q", "-m", "x")
    git(d, "checkout", "-q", "-B", "main")
    return d


def monarch_arm(site, repo_path):
    """Build the Monarch competitor of a resolved plan pointed at `repo_path`."""
    monarch_site(site, monarch_repo=str(repo_path))
    rc = resolve_monarch(site)
    competitor = next(c for c in rc.competitors if c.harness.kind == "monarch")
    return build_arm_for(competitor, rc)


def test_arm_is_named_for_the_checked_out_commit(site, repo):
    arm = monarch_arm(site, repo)
    assert arm.name == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}"
    assert arm.model_label == arm.name


def test_a_branch_off_main_is_part_of_the_name(site, repo):
    git(repo, "checkout", "-q", "-b", "lab")
    arm = monarch_arm(site, repo)
    assert arm.name == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}+lab"
    assert arm.model_label == arm.name


def test_a_path_that_is_not_a_checkout_is_a_config_error(site, tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    with pytest.raises(ConfigError) as exc:
        monarch_arm(site, not_a_repo)
    assert exc.value.path == str(site / "config/harnesses/monarch.yaml")
    assert exc.value.field == "monarch_repo"
    assert "version" in str(exc.value)


# -- T025/T026: one attempt end to end ----------------------------------------

TASKS_DIR = ROOT / "tasks"
SF = "/salesforce/services/data/v61.0/sobjects"


def free_port() -> int:
    """A port nothing listens on right now (the front door binds a fixed one)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def task(name: str = "simple.email_sf_contact_city_update") -> dict:
    return load_task_file(TASKS_DIR / f"{name}.json")


def arm_against(site, fake, port, repo, fd=None, kb=KB):
    """A Monarch arm whose harness points at the fakes on their real ports."""
    monarch_site(site, kb=kb, monarch_repo=str(repo))
    text = (site / "config/harnesses/monarch.yaml").read_text()
    text = (edit(text, "base_url", fake.url)
            .replace("shim_port: 9105", f"shim_port: {port}")
            .replace("shim_public_host: host.docker.internal", "shim_public_host: 127.0.0.1"))
    if fd is not None:
        text = edit(text, "fd_url", fd.url)
    write(site / "config/harnesses", text)
    rc = resolve_monarch(site)
    competitor = next(c for c in rc.competitors if c.harness.kind == "monarch")
    arm = build_arm_for(competitor, rc)
    arm.POLL_INTERVAL_S = 0.02
    return arm


def city_of(snapshot: dict, contact_id: str = "003004") -> str:
    return next(c["mailing_city"] for c in snapshot["salesforce"]["contacts"]
                if c["id"] == contact_id)


def test_completed_attempt(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        ep = Episode(task(), episode_id="run-x/simple.email_sf_contact_city_update/monarch/t0")
        result = arm.run(ep, deadline=time.monotonic() + 60)
        snap1 = ep.finish()

    assert city_of(snap1) == "Denver"
    assert result.termination == "completed" and result.error is None
    ids = result.turn_log[0]["monarch"]
    assert ids["workflowId"] == "wf-1" and ids["runId"] == "run-1" and ids["recipeVersion"] == 1
    starts = [r for r in fake.requests
              if r["path"] == "/api/workflows/recipe/runs" or r["path"].endswith("/run")]
    assert len(starts) == 2
    assert all(header(r, "x-bench-episode-id") == ep.episode_id for r in starts)
    assert fake.deleted_workflows == ["wf-1"]
    assert result.phases["authoring"].wall_clock_s > 0
    assert result.phases["execution"].wall_clock_s > 0
    # The front door let go of its fixed port.
    s = socket.socket()
    s.bind(("0.0.0.0", port))
    s.close()


# -- T027/T028: one Monarch at a time, and a port that is already taken -------

def test_lock_serialises(site, repo):
    """Two attempts overlap in time; Monarch sees them one after the other."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})],
                  delay_s={"frame": 0.05})
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        errors = []

        def attempt(i):
            try:
                arm.run(Episode(task(), episode_id=f"run-x/t/monarch/t{i}"),
                        deadline=time.monotonic() + 60)
            except BaseException as e:            # noqa: BLE001  reported below
                errors.append(e)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

    assert not errors, errors
    assert len(fake.authoring_started_at) == 2 and len(fake.deleted_at) == 2
    # No overlap: the second authoring request only lands after the first
    # attempt finished, which its delete marks.
    assert fake.authoring_started_at[1] >= fake.deleted_at[0]


def test_port_busy_is_infra(site, repo):
    port = free_port()
    # A real server, like a second front door would be: SO_REUSEADDR (which
    # HTTPServer sets) lets a bare socket steal a bound port on Windows.
    busy = ThreadingHTTPServer(("0.0.0.0", port), BaseHTTPRequestHandler)
    try:
        with FakeMonarch(Scenario()) as fake:
            arm = arm_against(site, fake, port, repo)
            with pytest.raises(InfraError) as exc:
                arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                        deadline=time.monotonic() + 60)
    finally:
        busy.server_close()
    assert exc.value.kind == "infra:harness_crash" and exc.value.retryable
    assert str(port) in str(exc.value)


# -- T031/T032: the pilot plan end to end, offline ----------------------------

def engine_calls_for(t: dict) -> list[tuple]:
    """The answer key as REST calls on the front door: what a correct workflow does."""
    return [("PATCH", f"{SF}/{obj}/{rid}", {field: value})
            for obj, rid, field, value in _sf_updates_from_assertions(t)]


def pilot_site(tmp_path, monarch_url, fd_url, port, repo) -> Path:
    """A config tree on the 10 pilot tasks with two competitors: answer key and Monarch."""
    site = tmp_path / "site"
    for sub in ("products", "models", "harnesses", "plans"):
        (site / "config" / sub).mkdir(parents=True)
    # The shipped product: the pilot tasks and the 47-app knowledge base are its.
    (site / "config/products" / PRODUCT_PATH.name).write_text(
        PRODUCT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    write(site / "config/models", PRICE_TABLE)
    write(site / "config/harnesses", HARNESS_SCRIPTED)
    harness = (edit(HARNESS_MONARCH, "runnable", "true")
               .replace("modes: [full-flow, create-run, run-only]", "modes: [create-run]"))
    harness = (edit(edit(edit(harness, "base_url", monarch_url), "fd_url", fd_url),
                    "monarch_repo", str(repo))
               .replace("shim_port: 9105", f"shim_port: {port}")
               .replace("shim_public_host: host.docker.internal", "shim_public_host: 127.0.0.1"))
    write(site / "config/harnesses", harness)
    plan = edit(PLAN, "tasks", f'"{TASKS_DIR.as_posix()}"')
    plan = edit(edit(plan, "competitors"), "baseline", "oracle")
    plan += "competitors:\n  - {harness: oracle}\n  - {harness: monarch}\n"
    write(site / "config/plans", plan)
    return site


def test_pilot_plan_offline(tmp_path, repo, monkeypatch):
    """Answer key and Monarch on the 10 pilot tasks x 2, against fakes on free ports."""
    # The orchestrator builds its own arms, so the poll interval is set on the class.
    monkeypatch.setattr(MonarchArm, "POLL_INTERVAL_S", 0.02)
    port = free_port()
    tasks = load_suite(TASKS_DIR)
    kb_hashes = {f"bench-{s}": f"{i:012x}" for i, s in enumerate(load_product(PRODUCT_PATH).services)}
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}")

    with FakeMonarch(sc) as monarch, fd_serving(kb_hashes) as fd:
        site = pilot_site(tmp_path, monarch.url, fd.url, port, repo)
        (site / "config/products/simulated-apps.monarch-kb.yaml").write_text(yaml.safe_dump(
            {"product": "simulated-apps", "generated_at": "2026-09-04T12:00:00Z",
             "seeds_format": "public-api-seeds@1",
             "shim_public_url": f"http://127.0.0.1:{port}", "kb": kb_hashes}))
        rc = config.resolve(site / "config/products/simulated-apps.yaml",
                            site / "config/plans/smoke-frontier.yaml",
                            env={**MONARCH_ENV}, audiences={"internal": ["*"]})
        store = Store(tmp_path / "wb.sqlite3")
        orch = Orchestrator.from_config(store, rc, tmp_path / "out")
        # One story per attempt: the workflow Monarch is pretended to have
        # authored performs that task's answer-key calls. The row is named for
        # the checkout, so the episode ids come from the built arm.
        monarch_arm = build_arm_for(
            next(c for c in rc.competitors if c.harness.kind == "monarch"), rc)
        sc.engine_calls_by_episode = {
            f"run-pilot/{t['task']}/{monarch_arm.name}/t{trial}": engine_calls_for(t)
            for t in tasks for trial in range(2)}
        run_id = orch.run("run-pilot")

    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 40
    oracle = [r for r in rows if r["arm"] == "oracle"]
    mon = [r for r in rows if r["arm"] != "oracle"]
    assert len(oracle) == 20 and all(r["passed"] for r in oracle)
    assert len(mon) == 20
    assert all(r["termination"] == "completed" for r in mon), \
        {r["episode_id"]: r["error"] for r in mon if r["termination"] != "completed"}
    assert all(r["test_mode"] == "create-run" for r in mon)
    assert all("snapshot1" in store.artifacts(r["episode_id"]) for r in mon)
    assert sum(r["passed"] for r in mon) == 20

    md = render_md(build_report(store, run_id, audience="internal"))
    assert "oracle" in md and mon[0]["arm"] in md
    cfg = json.loads(store.run(run_id)["config_json"])
    assert len(cfg["monarch_kb"]["kb"]) == 47
    assert "monarch-team-bedrock" in cfg["price_tables"]
