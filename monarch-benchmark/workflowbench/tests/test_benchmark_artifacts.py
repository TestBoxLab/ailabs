"""Artifact boundaries and authenticated history, without live GitHub writes."""
import base64
import json

import pytest

from tests.test_config_repository import repo
from tests.test_studio_benchmark_config import workspace
from tests.test_studio_app import server_for, request
from wb_orchestrator import config_repository as cr
from wb_studio import benchmark_config as bc


ACTOR = {"id": "basic:admin", "name": "admin", "source": "basic"}
MODEL = "config/models/gpt-5.6-sol.yaml"


@pytest.mark.parametrize("path", ["config/README.md", "config/products/simulated-apps.monarch-kb.yaml",
                                  "config/products/simulated-apps.monarch-recipes.yaml"])
@pytest.mark.parametrize("text", ["name: replacement\n", None])
def test_noneditable_files_cannot_be_changed_but_snapshots_restore(tmp_path, path, text):
    repository, remote = repo(tmp_path)
    original = repository.snapshot()
    assert any(f["path"] == "config/README.md" for f in original["files"])
    with pytest.raises(ValueError, match="editable|generated"):
        repository.validate(remote.head, [{"path": path, "text": text}])
    assert repository.snapshot(original["commit"])["files"] == original["files"]
    assert not remote.writes


def test_catalog_only_exposes_recognized_artifacts_and_manifest_guidance(workspace):
    studio, _ = workspace
    catalog = bc.catalog(studio)
    assert all(f["path"].endswith(".yaml") for f in catalog["files"])
    assert {f["artifact"]["group"] for f in catalog["files"]} == {"harnesses", "models", "plans", "products"}
    assert not next(f for f in catalog["files"] if f["path"].endswith(".monarch-kb.yaml"))["artifact"]["editable"]
    model = next(t for t in catalog["artifact_types"] if t["id"] == "model")
    assert "provider" in model["required_fields"] and "name:" in model["template"]
    assert catalog["actor"] is None


def test_duplicate_keys_are_rejected_by_repository_validation(tmp_path):
    repository, remote = repo(tmp_path)
    checked = repository.validate(remote.head, [{"path": MODEL, "text": remote.content[MODEL] + "\neffort: low\n"}])
    assert not checked["valid"] and any("duplicate" in error.lower() for error in checked["errors"])
    assert not remote.writes


def test_side_effect_reference_must_name_a_side_effect_artifact(tmp_path):
    repository, remote = repo(tmp_path)
    path = "config/products/simulated-apps.yaml"
    content = remote.content[path].replace("side_effects: config/side-effects.yaml",
                                          "side_effects: config/models/gpt-5.6-sol.yaml")
    result = repository.validate(remote.head, [{"path": path, "text": content}])
    assert not result["valid"]
    assert any("side-effect artifact" in error for error in result["errors"])
    assert not remote.writes


@pytest.mark.parametrize("change", [None, [], {}, {"path": MODEL},
    {"path": MODEL, "text": {"name": "invalid"}}, {"path": MODEL, "text": ["name: invalid"]},
    {"path": MODEL, "text": 42}, {"path": MODEL, "text": "", "actor": "spoof"}])
def test_malformed_changes_have_controlled_validation_errors(tmp_path, change):
    repository, remote = repo(tmp_path)
    with pytest.raises(ValueError, match="file change|content"):
        repository.validate(remote.head, [change])
    assert not remote.writes


def test_save_records_authenticated_author_separate_from_credential_committer(tmp_path):
    repository, remote = repo(tmp_path)
    repository.save(remote.head, [{"path": MODEL, "text": remote.content[MODEL] + "\n# Reviewed.\n"}], "Review model", ACTOR)
    commit = next(body for _, path, body in remote.writes if path == "git/commits")
    assert commit["author"]["name"] == "admin"
    assert commit["author"]["email"].endswith("@users.ailabs.invalid")
    assert "Config-Actor: basic:admin" in commit["message"]
    assert "Config-Authentication: basic" in commit["message"]
    assert commit["committer"] == {"name": "AI Labs Studio", "email": "studio@users.ailabs.invalid"}


@pytest.mark.parametrize("person", [False, True])
def test_http_uses_verified_identity_and_ignores_spoofed_author(workspace, monkeypatch, person):
    studio, remote = workspace
    remote.content = {MODEL: remote.content[MODEL], "config/README.md": "Retained historical documentation.\n"}
    remote.commits[remote.head] = dict(remote.content)
    monkeypatch.setenv("STUDIO_AUTH_USER", "admin")
    monkeypatch.setenv("STUDIO_AUTH_PASSWORD", "test-password")
    authorization = "Basic " + base64.b64encode(b"admin:test-password").decode()
    key = studio.genesis.access.add("lucas", "admin")["key"] if person else None
    with server_for(studio) as port:
        headers = {"Authorization": authorization, "Content-Type": "application/json", "X-Studio-Token": studio.token}
        if key:
            headers["X-Person-Key"] = key
        status, _, body = request(port, "GET", "/api/benchmark-config", headers=headers)
        assert status == 200
        expected = {"id": "person:lucas", "name": "lucas", "source": "person-key"} if person else ACTOR
        assert json.loads(body).get("actor") == expected
        payload = {"base_commit": remote.head, "changes": [{"path": MODEL, "text": remote.content[MODEL] + "\n# Reviewed.\n"}],
                   "message": "Review model", "operator": "Carlos", "actor": {"name": "Carlos"}}
        status, _, body = request(port, "POST", "/api/benchmark-config/save", headers=headers, body=json.dumps(payload))
        assert status == 200, body
    commit = next(body for _, path, body in remote.writes if path == "git/commits")
    assert commit["author"]["name"] == expected["name"]
    assert "Carlos" not in commit["message"]


def test_local_session_token_cannot_claim_config_author(workspace, monkeypatch):
    studio, remote = workspace
    monkeypatch.delenv("STUDIO_AUTH_USER", raising=False)
    monkeypatch.delenv("STUDIO_AUTH_PASSWORD", raising=False)
    with server_for(studio) as port:
        payload = {"base_commit": remote.head, "changes": [{"path": MODEL, "text": remote.content[MODEL] + "\n# Reviewed.\n"}],
                   "message": "Review model", "operator": "Carlos"}
        status, _, body = request(port, "POST", "/api/benchmark-config/save", headers={"X-Studio-Token": studio.token}, body=json.dumps(payload))
        assert status == 403 and "authenticated" in body.lower()
    assert not remote.writes


def test_history_is_bounded_and_preserves_author_and_committer(tmp_path):
    repository, _ = repo(tmp_path)
    calls = []
    def history_request(method, path, body=None):
        calls.append((method, path))
        return [{"sha": "d" * 40, "commit": {"message": "Review model\n\nConfig-Actor: basic:admin",
                 "author": {"name": "admin", "date": "2026-09-11T00:00:00Z"},
                 "committer": {"name": "technical-account", "date": "2026-09-11T00:00:00Z"}}}] * 40
    repository.request = history_request
    rows = repository.history()
    assert len(rows) == 20 and calls == [("GET", "commits?sha=main&path=config&per_page=20")]
    assert rows[0]["author"] == "admin" and rows[0]["committer"] == "technical-account"
    assert rows[0]["url"].endswith("/commit/" + "d" * 40)


def test_history_failure_is_separate_from_editing(workspace):
    studio, _ = workspace
    def failed(*args, **kwargs):
        raise cr.RepositoryError("History unavailable")
    studio.config_repository.history = failed
    with server_for(studio) as port:
        status, _, body = request(port, "GET", "/api/benchmark-config/history")
        assert status == 200 and json.loads(body) == {"history": [], "error": "History unavailable"}
        status, _, body = request(port, "GET", "/api/benchmark-config")
        assert status == 200 and json.loads(body)["files"]


def test_job_endpoint_projects_retained_monarch_identity_without_rewriting_history(workspace):
    studio, _ = workspace
    job = {"id": "recorded-source", "status": "completed", "settings": {"models": ["monarch"], "tasks": []},
           "execution_segments": [{"id": "original", "monarch_provenance": [
               {"status": "declared", "commit": "d" * 40, "build_label": "retained-build"}]}]}
    studio.save(job)
    path = studio.directory / job["id"] / "job.json"
    before = path.read_bytes()
    with server_for(studio) as port:
        status, _, body = request(port, "GET", "/api/jobs/recorded-source")
        assert status == 200
        result = json.loads(body)
        assert result["monarch_provenance"]["segments"][0]["commit"] == "d" * 40
        assert result["monarch_provenance"]["segments"][0]["status"] == "declared"
    assert path.read_bytes() == before
