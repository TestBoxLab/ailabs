"""Studio repository workflow uses real frozen tasks and no paid competitor."""
import json
from pathlib import Path

import pytest

from tests.test_config_repository import GitAPI
from wb_orchestrator.config_repository import Repository
from wb_studio.app import Studio
from wb_studio import benchmark_config as bc


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_OPERATOR", "Carlos")
    api = GitAPI()
    api.content["config/plans/free-check.yaml"] = """name: free-check
tasks: tasks/check-collateral
mode: create-run
repetitions: 1
retry_on_fail: 0
timeout_s: 60
concurrency: 1
competitors:
  - {harness: oracle}
baseline: oracle
audience: internal
cost_ceiling_usd: 1
approved_by: null
"""
    api.commits[api.head] = dict(api.content)
    studio = Studio(tmp_path / "studio", gateway_factory=lambda: None)
    studio.config_repository = Repository("TestBoxLab/ailabls-benchmark-config", "test", tmp_path / "cache", request=api)
    return studio, api


def test_catalog_and_preview_do_not_launch_or_reserve(workspace):
    studio, remote = workspace
    catalog = bc.catalog(studio)
    assert catalog["commit"] == remote.head and catalog["writable"]
    preview = bc.preview(studio, {"commit": remote.head, "product": "simulated-apps", "plan": "free-check"})
    assert preview["launchable"] and preview["attempts_max"] == 4
    assert preview["preview_id"] and not studio.jobs()
    assert studio.ledger.status().held_microusd == 0


def test_launch_requires_matching_preview_and_detects_external_task_drift(workspace, monkeypatch):
    studio, remote = workspace
    payload = {"commit": remote.head, "product": "simulated-apps", "plan": "free-check", "operator": "Carlos", "request_id": "repo-free-check"}
    with pytest.raises(ValueError, match="preview"):
        bc.create(studio, payload, start=False)
    preview = bc.preview(studio, payload)
    payload["preview_id"] = preview["preview_id"]
    original = bc.resolve
    def drift(*args, **kwargs):
        rc = original(*args, **kwargs)
        rc.tasks[0]["prompt"][0]["content"] += " Changed after preview."
        return rc
    monkeypatch.setattr(bc, "resolve", drift)
    with pytest.raises(ValueError, match="changed"):
        bc.create(studio, payload, start=False)
    assert not studio.jobs()


def test_configured_studio_run_preserves_source_and_original_semantics(workspace):
    studio, remote = workspace
    payload = {"commit": remote.head, "product": "simulated-apps", "plan": "free-check", "operator": "Carlos", "request_id": "repo-free-check"}
    payload["preview_id"] = bc.preview(studio, payload)["preview_id"]
    job = bc.create(studio, payload, start=False)
    assert job["config_source"]["commit"] == remote.head
    studio.execute(job["id"])
    done = studio.job(job["id"])
    assert done["status"] == "completed", done
    assert done["completed"] == 4
    assert all(row["termination"] == "completed" for row in done["results"])
    assert done["cost_usd"] == 0
    assert (studio.directory / job["id"] / "config-source.json").is_file()


def test_preview_refuses_invalid_or_unsupported_plan_without_money(workspace):
    studio, remote = workspace
    preview = bc.preview(studio, {"commit": remote.head, "product": "simulated-apps", "plan": "achievable-50-request"})
    assert not preview["launchable"] and preview["reasons"]
    assert not studio.jobs() and studio.ledger.status().held_microusd == 0


def test_http_repository_failures_auth_and_permissions_are_explicit(workspace):
    from tests.test_studio_app import server_for, request
    from wb_orchestrator.config_repository import RepositoryError
    studio, remote = workspace
    with server_for(studio) as port:
        headers = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", "X-Studio-Token": studio.token}
        status, _, _ = request(port, "POST", "/api/benchmark-config/validate", body="{}")
        assert status == 403
        studio.genesis.access.add("carlos", "admin")
        status, _, _ = request(port, "POST", "/api/benchmark-config/save", body="{}", headers=headers)
        assert status == 403
        def unavailable(*args, **kwargs):
            raise RepositoryError("Repository access unavailable")
        studio.config_repository.snapshot = unavailable
        status, _, body = request(port, "GET", "/api/benchmark-config")
        assert status == 503
        assert "Repository access unavailable" in body


def test_http_accepts_a_bounded_configuration_edit_larger_than_legacy_job_body(workspace):
    from tests.test_studio_app import server_for, request
    studio, remote = workspace
    with server_for(studio) as port:
        headers = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", "X-Studio-Token": studio.token}
        body = json.dumps({"base_commit": remote.head, "changes": [{"path": "config/README.md", "text": "Documentation.\n" * 11000}]})
        status, _, text = request(port, "POST", "/api/benchmark-config/validate", body=body, headers=headers)
        assert status == 200, text
        assert json.loads(text)["valid"]
        assert not remote.writes


def test_configured_pause_is_supported_and_cancel_is_preserved(workspace):
    studio, remote = workspace
    payload = {"commit": remote.head, "product": "simulated-apps", "plan": "free-check", "operator": "Carlos", "request_id": "cancelled-plan"}
    payload["preview_id"] = bc.preview(studio, payload)["preview_id"]
    job = bc.create(studio, payload, start=False)
    assert studio.pause(job["id"])["status"] == "paused"
    studio.cancel(job["id"])
    studio.execute(job["id"])
    assert studio.job(job["id"])["status"] == "cancelled"
    assert not studio.job(job["id"])["results"]


@pytest.mark.parametrize("cost,flags", [(None, []), (0, ["billing=unknown"]), (0.25, ["cost_missing"])])
def test_unknown_attempt_cost_is_not_reported_as_zero(workspace, monkeypatch, cost, flags):
    studio, remote = workspace
    payload = {"commit": remote.head, "product": "simulated-apps", "plan": "free-check", "operator": "Carlos", "request_id": "unknown-cost"}
    payload["preview_id"] = bc.preview(studio, payload)["preview_id"]
    job = bc.create(studio, payload, start=False)
    original = bc.Store.record_episode
    def unknown(self, row):
        return original(self, row.model_copy(update={"cost_usd": cost, "flags": row.flags + flags}))
    monkeypatch.setattr(bc.Store, "record_episode", unknown)
    studio.execute(job["id"])
    assert studio.job(job["id"])["cost_usd"] is None
    store = bc.Store(studio.directory / job["id"] / "results.sqlite3")
    try:
        rows = store.episodes(run=job["id"])["rows"]
    finally:
        store.close()
    assert rows and all(row["cost_usd"] == cost and set(flags) <= set(row["flags"]) for row in rows)


def test_preview_uses_declared_operator_and_queue_rechecks_readiness(workspace, monkeypatch):
    studio, remote = workspace
    monkeypatch.delenv("WB_OPERATOR")
    monkeypatch.setattr(bc, "_readiness", lambda studio, rc, env: [] if env.get("WB_OPERATOR") == "Carlos" else ["Operator missing"])
    payload = {"commit": remote.head, "product": "simulated-apps", "plan": "free-check", "operator": "Carlos", "request_id": "readiness-expired"}
    preview = bc.preview(studio, payload)
    assert preview["launchable"], preview
    payload["preview_id"] = preview["preview_id"]
    job = bc.create(studio, payload, start=False)
    monkeypatch.setattr(bc, "_readiness", lambda *args: ["Verification expired"])
    studio.execute(job["id"])
    result = studio.job(job["id"])
    assert result["status"] == "failed" and "Verification expired" in result["error"]
    assert not result["results"]


def test_retry_returns_existing_job_before_mutable_readiness_checks(workspace, monkeypatch):
    studio, remote = workspace
    payload = {"commit": remote.head, "product": "simulated-apps", "plan": "free-check", "operator": "Carlos", "request_id": "lost-response"}
    payload["preview_id"] = bc.preview(studio, payload)["preview_id"]
    job = bc.create(studio, payload, start=False)
    monkeypatch.setattr(bc, "resolve", lambda *args: (_ for _ in ()).throw(ValueError("Repository unavailable")))
    assert bc.create(studio, payload, start=False)["id"] == job["id"]
