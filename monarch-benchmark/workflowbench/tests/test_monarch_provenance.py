"""Version displays read frozen facts, never today's deployment or environment."""
from copy import deepcopy
from types import SimpleNamespace

from tests.test_studio_benchmark_config import workspace
from wb_studio import monarch_provenance as provenance


def test_historical_run_never_inherits_current_environment(monkeypatch):
    monkeypatch.setenv("MONARCH_BUILD_COMMIT", "a" * 40)
    job = {"settings": {"models": ["monarch"]}, "results": [
        {"model": "monarch@old+branch"}]}
    before = deepcopy(job)
    projected = provenance.project(job)
    assert projected["status"] == "not_recorded"
    assert projected["segments"][0]["commit"] is None
    assert projected["segments"][0]["build_label"] == "monarch@old+branch"
    assert job == before


def test_enterprise_checkout_is_not_deployed_proof():
    job = {"settings": {"arms": [{"id": "default-monarch-enterprise", "kind": "enterprise",
        "served": {"version": "monarch@abc", "checkout": {"commit": "a" * 40,
                     "branch": "main", "dirty": False}}}]},
        "execution_manifests": {"default-monarch-enterprise": {
            "source": {"kind": "git", "commit": "a" * 40},
            "artifacts": {"knowledge_base": {"sha256": "b" * 64}}}}}
    record = provenance.project(job)["segments"][0]
    assert record["status"] == "checkout"
    assert record["commit"] == "a" * 40
    assert record["knowledge_base_sha256"] == "b" * 64
    job["settings"]["arms"][0]["served"]["checkout"]["declared"] = True
    assert provenance.project(job)["segments"][0]["status"] == "declared"


def test_segments_keep_service_evidence_and_do_not_leak_extra_fields():
    evidence = {"status": "verified", "build_label": "monarch@abc", "commit": "a" * 40,
        "services": [{"service": "backend", "commit": "a" * 40,
                      "deployment_id": "deploy-1", "image_digest": "sha256:abc",
                      "status": "verified", "token": "secret"}], "secret": "hidden"}
    job = {"execution_segments": [{"id": "one", "started_at": "then", "monarch_provenance": [evidence]},
        {"id": "two", "started_at": "later", "monarch_provenance": [{"status": "declared", "commit": "b" * 40}]}]}
    result = provenance.project(job)
    assert [r["segment_id"] for r in result["segments"]] == ["one", "two"]
    assert result["segments"][0]["services"][0]["deployment_id"] == "deploy-1"
    assert "secret" not in str(result)
    assert result["segments"][1]["status"] == "declared"


def test_capture_records_declaration_without_claiming_the_checkout_was_deployed(monkeypatch, tmp_path):
    from wb_studio import enterprise
    monkeypatch.setattr(enterprise, "checkout_identity", lambda path: {
        "commit": "c" * 40, "version": "monarch@checkout", "branch": "local",
        "dirty": True, "patch_sha256": "d" * 64})
    harness = SimpleNamespace(kind="monarch", monarch_repo="../monarch", model_families={})
    rc = SimpleNamespace(competitors=[SimpleNamespace(harness=harness)], config_dir=tmp_path,
                         runtime_root=tmp_path, monarch_kb=SimpleNamespace(kb={"app": "hash"}))
    result = provenance.capture(rc, {"MONARCH_BUILD": "monarch@declared", "MONARCH_BUILD_COMMIT": "a" * 40})
    assert result[0]["status"] == "declared"
    assert result[0]["commit"] == "a" * 40
    assert result[0]["checkout"]["commit"] == "c" * 40
    assert result[0]["dirty"] is None
    assert result[0]["knowledge_base_sha256"]


def test_multiple_monarch_competitors_keep_identity_in_capture_and_projection(monkeypatch, tmp_path):
    from wb_studio import enterprise
    monkeypatch.setattr(enterprise, "checkout_identity", lambda path: {"commit": "a" * 40, "version": "monarch@same"})
    competitors = [SimpleNamespace(name=name, harness=SimpleNamespace(
        name=name, kind="monarch", monarch_repo="../monarch", model_families={}))
        for name in ("monarch-stock", "monarch-lab")]
    rc = SimpleNamespace(competitors=competitors, config_dir=tmp_path, runtime_root=tmp_path, monarch_kb=None)
    records = provenance.capture(rc, {})
    assert [r["competitor_id"] for r in records] == ["monarch-stock", "monarch-lab"]
    projected = provenance.project({"execution_segments": [{"id": "one", "monarch_provenance": records}]})
    assert [(r["competitor_id"], r["harness"]) for r in projected["segments"]] == [
        ("monarch-stock", "monarch-stock"), ("monarch-lab", "monarch-lab")]


def test_configured_segment_freezes_capture(workspace, monkeypatch):
    from tests.test_configured_controls import create
    studio, job = create(workspace, "provenance")
    evidence = [{"status": "declared", "build_label": "monarch@frozen"}]
    monkeypatch.setattr(provenance, "capture", lambda rc, env: evidence)
    studio.execute(job["id"])
    assert studio.job(job["id"])["execution_segments"][0]["monarch_provenance"] == evidence


def test_cli_execution_keeps_each_provenance_record_without_rewriting_inputs(tmp_path, monkeypatch):
    import json
    from wb_orchestrator.orchestrator import Orchestrator
    from wb_results.store import Store

    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator(store, tmp_path, [], 1, tmp_path / "out", tasks=[])
    orch.run_config = SimpleNamespace(product=SimpleNamespace(source=None), native_runtimes={})
    monkeypatch.setattr(provenance, "capture", lambda rc, env: [{"status": "declared", "commit": "a" * 40}])
    # No workers or remote services: exercise the common execution seam twice.
    monkeypatch.setattr(store, "finish_run", lambda identity: None)
    orch._execute("identity", set(), arms=[])
    first = list((tmp_path / "out/identity/monarch-provenance").glob("*.json"))
    assert len(first) == 1
    first_bytes = first[0].read_bytes()
    orch._execute("identity", set(), arms=[])
    assert len(list(first[0].parent.glob("*.json"))) == 2
    assert first[0].read_bytes() == first_bytes
    assert json.loads(first_bytes)["monarch_provenance"][0]["commit"] == "a" * 40
    store.close()
