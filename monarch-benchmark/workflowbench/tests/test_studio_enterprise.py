"""Stock Monarch Enterprise in the Studio (feature 011, checkpoint 3).

Offline, against the fake backend, discovery service and Langfuse: the version
is not launchable until a verification probe passes; the probe names the served
build and refuses a custom build the label "stock"; a launched attempt streams
the builder's frames, the recipe's nodes and every front-door call into the
Activity events, reserves its ceiling first and settles with the Langfuse total.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import yaml

from tests.fake_fd import fd_serving
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch, Scenario
from tests.monarch_helpers import KB, MONARCH_ENV, free_port, git, monarch_site, repo  # noqa: F401  (repo is a fixture)
from tests.test_config import edit, site, write  # noqa: F401  (site is a fixture)
from tests.test_monarch_arm import OPUS, SONNET, USAGE, engine_calls_for, task
from tests.test_monarch_live import FRAMES, RECIPE, VIEWS
from wb_arms.monarch import MonarchArm, bench_episode_id
from wb_results.evidence import write_json
from wb_studio import enterprise
from wb_studio.app import Studio
from wb_studio.runtime_registry import check_launch, versions

TASK = "simple.email_sf_contact_city_update"
CEILING = "0.50"


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(MonarchArm, "POLL_INTERVAL_S", 0.05)


def forbidden(*args, **kwargs):
    pytest.fail("An offline Studio test attempted paid model dispatch")


def configured(site, repo, port, monarch_url="http://127.0.0.1:1", fd_url="http://127.0.0.1:2", langfuse_url="http://127.0.0.1:3"):
    """The test config tree with a runnable Monarch harness pointed at the given addresses."""
    monarch_site(site, monarch_repo=str(repo))
    text = (site / "config/harnesses/monarch.yaml").read_text()
    text = (edit(edit(edit(text, "base_url", monarch_url), "fd_url", fd_url), "langfuse_url", langfuse_url)
            .replace("shim_port: 9105", f"shim_port: {port}")
            .replace("shim_public_host: host.docker.internal", "shim_public_host: 127.0.0.1"))
    write(site / "config/harnesses", text)
    return site


def studio_for(tmp_path, site, env=None):
    app = Studio(tmp_path / "studio", tasks=[task(TASK)], gateway_factory=forbidden)
    app.enterprise_config_dir = site / "config"
    app.enterprise_env = {**MONARCH_ENV, "MONARCH_ATTEMPT_CEILING_USD": CEILING, **(env or {})} if env is not None else {**MONARCH_ENV, "MONARCH_ATTEMPT_CEILING_USD": CEILING}
    return app


def enterprise_version(app):
    return next(v for v in versions(app) if v["id"] == "default-monarch-enterprise")


def scenario(port, **overrides):
    return Scenario(shim_url=f"http://127.0.0.1:{port}", frames=[dict(f) for f in FRAMES],
                    engine_calls=engine_calls_for(task(TASK)), run_views=[dict(v) for v in VIEWS], **overrides)


def kb_hashes():
    return yaml.safe_load(KB)["kb"]


def bench_id(job_id):
    return bench_episode_id(f"{job_id}/{TASK}/default-monarch-enterprise/t0")


def add_cost(langfuse, job_id):
    langfuse.add_trace(bench_id(job_id), spans=[("s1", "recipe.plan", None), ("s2", "engine.run", None)],
                       generations=[("g1", "s1", OPUS, USAGE), ("g2", "s2", SONNET, USAGE)])
    opus = (1000 * 5.00 + 500 * 0.50 + 100 * 6.25 + 200 * 25.00) / 1e6
    sonnet = (1000 * 2.00 + 500 * 0.20 + 100 * 2.50 + 200 * 10.00) / 1e6
    return opus + sonnet


# -- readiness ------------------------------------------------------------------------

def test_unverified_or_misconfigured_enterprise_cannot_launch(tmp_path, site, repo):
    port = free_port()
    app = studio_for(tmp_path, configured(site, repo, port))
    version = enterprise_version(app)
    assert version["readiness"]["runtime"] == "preparation_required" and version["readiness"]["launchable"] is False
    assert "Verify the Monarch connection" in version["readiness"]["reasons"][0]
    assert version["served"]["version"] == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}" and version["served"]["stock"] is True
    assert version["request_ceiling_usd"] == CEILING
    with pytest.raises(ValueError, match="cannot launch yet"):
        check_launch(app, ["default-monarch-enterprise"], [])
    with pytest.raises(ValueError, match="cannot launch yet"):
        app.create({"architectures": ["default-monarch-enterprise"], "tasks": [TASK], "maximum_usd": "1.00"}, start=False)
    assert app.jobs() == [] and Decimal(app.budget()["held"]) == 0

    app.enterprise_env = {"MONARCH_ATTEMPT_CEILING_USD": "abc"}
    blocked = enterprise_version(app)["readiness"]
    assert blocked["runtime"] == "blocked"
    assert any("MONARCH_PASSWORD" in r for r in blocked["reasons"])
    assert any("LANGFUSE_PUBLIC_KEY" in r for r in blocked["reasons"])
    assert any("MONARCH_ATTEMPT_CEILING_USD" in r for r in blocked["reasons"])


def test_a_stale_probe_or_a_moved_checkout_requires_verifying_again(tmp_path, site, repo):
    port = free_port()
    app = studio_for(tmp_path, configured(site, repo, port))
    version = enterprise.Setup(app).version
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    write_json(enterprise.probe_path(app), {"checked_at": old, "ok": True, "version": version, "checks": [{"name": "backend", "ok": True}]})
    ready, _ = enterprise.readiness(app)
    assert ready["runtime"] == "preparation_required" and "older than two hours" in ready["reasons"][0]
    write_json(enterprise.probe_path(app), {"checked_at": datetime.now(timezone.utc).isoformat(), "ok": True, "version": "monarch@0000000", "checks": []})
    ready, _ = enterprise.readiness(app)
    assert ready["runtime"] == "preparation_required" and "checkout moved" in ready["reasons"][0]


def test_verify_records_every_check_and_a_passing_probe_makes_the_version_launchable(tmp_path, site, repo):
    port = free_port()
    with FakeMonarch(Scenario()) as fake, fd_serving(kb_hashes()) as fd, FakeLangfuse() as lf:
        app = studio_for(tmp_path, configured(site, repo, port, fake.url, fd.url, lf.url))
        probe = enterprise.verify(app)
        assert probe["ok"] is True, probe
        assert [c["name"] for c in probe["checks"]] == ["configuration", "backend", "session", "knowledge_base", "langfuse"]
        assert probe["backend_host"] == f"127.0.0.1:{fake.port}" and probe["front_door"] == f"http://127.0.0.1:{port}"
        assert probe["price_table"]["name"] == "monarch-team-bedrock" and probe["stock"] is True
        # Verification costs no model money: no authoring run was started.
        assert not [r for r in fake.requests if r["path"] == "/api/workflows/recipe/runs"]
        version = enterprise_version(app)
        assert version["readiness"]["runtime"] == "ready" and version["readiness"]["launchable"] is True
        assert version["manifest"]["frozen"] is True and version["manifest"]["source"]["commit"] == git(repo, "rev-parse", "HEAD")
        assert version["manifest"]["evaluation"]["settings"]["provider_declared_not_observed"] is True
        assert version["name"].startswith("Monarch Enterprise · monarch@")
        assert check_launch(app, ["default-monarch-enterprise"], [])[0]["id"] == "default-monarch-enterprise"

        # A wrong knowledge base blocks the version and says which service drifted.
        (site / "config/products/simulated-apps.monarch-kb.yaml").write_text(KB.replace("9b1f0c4a5e77", "deadbeef0000"))
        failed = enterprise.verify(app)
        assert failed["ok"] is False
        kb = next(c for c in failed["checks"] if c["name"] == "knowledge_base")
        assert kb["ok"] is False and "bench-gmail" in kb["detail"]
        blocked = enterprise_version(app)["readiness"]
        assert blocked["runtime"] == "blocked" and any("knowledge_base" in r for r in blocked["reasons"])


def test_a_branch_or_a_dirty_checkout_is_a_custom_build_never_stock(tmp_path, site, repo):
    port = free_port()
    git(repo, "checkout", "-q", "-b", "railway-dev")
    (repo / "local-change.txt").write_text("x")
    git(repo, "add", "local-change.txt")
    app = studio_for(tmp_path, configured(site, repo, port))
    version = enterprise_version(app)
    served = version["served"]
    assert served["stock"] is False and served["version"].endswith("+railway-dev*")
    assert "(custom build)" in version["name"]
    assert served["checkout"]["branch"] == "railway-dev" and served["checkout"]["patch_sha256"]


# -- an attempt -----------------------------------------------------------------------

def run_enterprise(tmp_path, site, repo, port, fake, fd, lf, request_id="enterprise-run"):
    app = studio_for(tmp_path, configured(site, repo, port, fake.url, fd.url, lf.url))
    assert enterprise.verify(app)["ok"] is True
    job = app.create({"request_id": request_id, "architectures": ["default-monarch-enterprise"], "tasks": [TASK],
                      "maximum_usd": "1.00", "title": "Stock Monarch on one task"}, start=False)
    assert job["settings"]["arms"][0]["kind"] == "enterprise" and job["settings"]["models"] == ["default-monarch-enterprise"]
    assert job["execution_manifests"]["default-monarch-enterprise"]["identity_sha256"]
    return app, job


def test_an_enterprise_attempt_streams_builder_frames_recipe_nodes_and_front_door_calls(tmp_path, site, repo):
    port = free_port()
    with FakeMonarch(scenario(port)) as fake, fd_serving(kb_hashes()) as fd, FakeLangfuse() as lf:
        expected_cost = add_cost(lf, "enterprise-run")
        app, job = run_enterprise(tmp_path, site, repo, port, fake, fd, lf)
        app.execute(job["id"])
        done = app.job(job["id"])
    assert done["status"] == "completed", done
    result = done["results"][0]
    assert result["model"] == "default-monarch-enterprise" and result["passed"] is True, result
    assert result["termination"] == "completed" and result["cost_usd"] == pytest.approx(expected_cost)
    assert "billing=unknown" not in result["flags"] and "Workflow wf-1 version 1, 2 node(s)" in result["output"]

    events = app.events(job["id"])
    by_type = {}
    for event in events:
        by_type.setdefault(event["type"], []).append(event)
    steps = [(e["step"], e["label"]) for e in by_type["step_started"]]
    assert steps == [("authoring", "Build the workflow"), ("execution", "Run the workflow")]
    finished = {e["step"]: e for e in by_type["step_finished"]}
    assert finished["authoring"]["status"] == "completed" and finished["authoring"]["workflow_id"] == "wf-1"
    assert finished["execution"]["status"] == "completed" and "2 done" in finished["execution"]["output"]
    builder = [e for e in by_type["node_started"] if e.get("category") == "builder"]
    assert [e["label"] for e in builder] == ["Builder: plan", "Builder finished"]
    recipe = by_type["workflow_recipe"][0]
    assert [n["id"] for n in recipe["nodes"]] == ["read", "write"] and recipe["nodes"][0]["product"] == "bench-salesforce"
    changes = [(e["node"], e["status"]) for e in by_type["workflow_step"]]
    assert changes == [("wf:read", "running"), ("wf:write", "pending"), ("wf:read", "succeeded"), ("wf:write", "running"), ("wf:write", "succeeded")]
    assert by_type["workflow_step"][-1]["message"] == "MailingCity set"
    tools = [e for e in by_type["node_started"] if e.get("step") == "execution" and e["label"] == "api_fetch"]
    assert tools, "front-door calls must appear as tool nodes of the execution step"
    assert all(e["model"] == "default-monarch-enterprise" and e["task"] == TASK for e in events if "model" in e)
    billing = [e["billing"] for e in by_type["billing"]]
    assert billing[0]["status"] == "reserved" and billing[0]["maximum_usd"] == CEILING
    assert billing[-1]["status"] == "estimated_from_langfuse" and Decimal(billing[-1]["actual_usd"]) == Decimal(str(round(expected_cost, 6)))
    assert Decimal(app.budget()["held"]) == 0 and Decimal(app.budget()["actual"]) == Decimal(str(round(expected_cost, 6)))
    assert fake.deleted_workflows == ["wf-1"] and fake.run_stream_connections == 1


def test_an_attempt_whose_cost_cannot_be_read_keeps_its_reservation_held(tmp_path, site, repo):
    port = free_port()
    with FakeMonarch(scenario(port)) as fake, fd_serving(kb_hashes()) as fd, FakeLangfuse() as lf:
        app, job = run_enterprise(tmp_path, site, repo, port, fake, fd, lf, request_id="no-cost")
        app.execute(job["id"])
        done = app.job(job["id"])
    result = done["results"][0]
    assert result["passed"] is True and "cost_missing" in result["flags"] and "billing=unknown" in result["flags"]
    assert Decimal(app.budget()["held"]) == Decimal(CEILING)
    last = [e for e in app.events(job["id"]) if e["type"] == "billing"][-1]["billing"]
    assert last["status"] == "unknown_hold" and last["actual_usd"] is None


def test_a_run_budget_below_the_attempt_ceiling_is_refused_before_any_job(tmp_path, site, repo):
    port = free_port()
    with FakeMonarch(Scenario()) as fake, fd_serving(kb_hashes()) as fd, FakeLangfuse() as lf:
        app = studio_for(tmp_path, configured(site, repo, port, fake.url, fd.url, lf.url))
        assert enterprise.verify(app)["ok"] is True
        with pytest.raises(ValueError, match="Run budget too low"):
            app.create({"architectures": ["default-monarch-enterprise"], "tasks": [TASK], "maximum_usd": "0.25"}, start=False)
    assert app.jobs() == []


def test_a_moved_checkout_refuses_the_attempt_it_was_not_created_for(tmp_path, site, repo):
    port = free_port()
    with FakeMonarch(scenario(port)) as fake, fd_serving(kb_hashes()) as fd, FakeLangfuse() as lf:
        app, job = run_enterprise(tmp_path, site, repo, port, fake, fd, lf, request_id="drift")
        git(repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "--allow-empty", "-q", "-m", "moved")
        app.execute(job["id"])
        done = app.job(job["id"])
    assert done["status"] == "failed" and "Execution stopped" in done["error"]
    assert (app.directory / job["id"] / "execution.error.log").read_text(encoding="utf-8").count("changed since this run was created")
    assert not [r for r in fake.requests if r["path"] == "/api/workflows/recipe/runs"]


# -- hosted Studio: no git binary, no checkout; the operator declares the build ---------

def test_checkout_identity_without_git_says_so_instead_of_crashing(tmp_path, monkeypatch):
    import subprocess as sp
    from wb_studio.enterprise import checkout_identity

    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")
    monkeypatch.setattr(sp, "run", no_git)
    with pytest.raises(ValueError, match="git is not available here"):
        checkout_identity(tmp_path)


def test_monarch_version_falls_back_to_the_declared_build(tmp_path, monkeypatch):
    import subprocess as sp
    from wb_arms.monarch import monarch_version

    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")
    monkeypatch.setattr(sp, "run", no_git)
    assert monarch_version(tmp_path, "monarch@2ede4b3e+feat/railway-dev-deploy") == "monarch@2ede4b3e+feat/railway-dev-deploy"
    with pytest.raises(ValueError):
        monarch_version(tmp_path, None)


def test_a_declared_build_freezes_a_manifest_with_or_without_its_full_commit(tmp_path, site, repo, monkeypatch):
    """A hosted Studio names the served build from MONARCH_BUILD; the manifest still freezes."""
    import subprocess as sp
    from wb_studio.enterprise import Setup, manifest

    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")
    monkeypatch.setattr(sp, "run", no_git)
    port = free_port()
    app = studio_for(tmp_path, configured(site, repo, port))
    app.enterprise_env = {**app.enterprise_env, "MONARCH_BUILD": "monarch@2ede4b3e+feat/railway-dev-deploy"}
    setup = Setup(app)
    assert setup.ok, setup.problems
    assert setup.checkout["declared"] is True and setup.stock is False and setup.version.endswith("railway-dev-deploy")
    frozen = manifest(setup, None)
    assert frozen["source"]["kind"] == "none" and frozen["source"]["declared_build"] == setup.version
    app.enterprise_env = {**app.enterprise_env, "MONARCH_BUILD_COMMIT": "2ede4b3ee355da81c253087e8c9583ed677c06fa"}
    setup = Setup(app)
    assert setup.ok and setup.checkout["commit"] == "2ede4b3ee355da81c253087e8c9583ed677c06fa"
    assert manifest(setup, None)["source"]["kind"] == "git"
    app.enterprise_env = {**app.enterprise_env, "MONARCH_BUILD_COMMIT": "2ede4b3e"}
    assert any("MONARCH_BUILD_COMMIT" in p for p in Setup(app).problems)
