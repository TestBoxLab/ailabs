"""Immutable configuration execution: runtime paths, hashes and model prices."""
import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_config import site, ENV, paths, plan_text, edit, resolve as local_resolve
from wb_orchestrator import config
from wb_orchestrator.orchestrator import Orchestrator, ConfigDrift, RunKilled, build_arm_for
from wb_arms import providers
from wb_results.store import Store


def snapshot(site, tmp_path):
    directory = tmp_path / "revision"
    shutil.copytree(site / "config", directory / "config")
    return {"repository": "TestBoxLab/ailabls-benchmark-config", "branch": "main",
            "commit": "a" * 40, "directory": str(directory),
            "files": [{"path": p.relative_to(directory).as_posix(),
                       "text": p.read_bytes().decode("utf-8"),
                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in sorted((directory / "config").rglob("*.yaml"))]}


def external(site, tmp_path):
    plan = paths(site)[1]
    plan.write_text(edit(plan_text(site), "tasks", "tasks"))
    return config.resolve_snapshot(snapshot(site, tmp_path), "simulated-apps", "smoke-frontier",
                                   runtime_root=site, env=ENV)


def test_external_snapshot_preserves_legacy_hash_and_runtime_paths(site, tmp_path):
    rc = external(site, tmp_path)
    legacy = local_resolve(site)
    assert rc.hash == legacy.hash
    assert rc.tasks_dir == str(site / "tasks")
    assert rc.plan.tasks == "tasks"
    assert rc.config_json["config_source"]["commit"] == "a" * 40
    assert "directory" not in rc.config_json["config_source"]
    assert config.from_workflowbench("config/side-effects.yaml", rc.config_dir, rc.runtime_root) == Path(rc.config_dir) / "side-effects.yaml"
    assert config.from_workflowbench("../../../monarch", rc.config_dir, rc.runtime_root) == site / "../../../monarch"
    assert "config_source" not in legacy.config_json


def test_resolved_provider_does_not_follow_global_registry(site, monkeypatch):
    rc = local_resolve(site)
    competitor = rc.competitors[1]
    old = providers.get(competitor.model.name)
    monkeypatch.setitem(providers.REGISTRY, old.key, replace(old, model_id="new-model", price_in=999))
    arm = build_arm_for(competitor, rc)
    assert arm.provider.model_id == competitor.model.model
    assert arm.provider.price_in == competitor.model.usd_per_million.input
    assert arm.provider is not providers.get(old.key)


def test_unknown_global_model_can_execute_from_resolved_config(site):
    rc = local_resolve(site)
    competitor = replace(rc.competitors[1], model=replace(rc.competitors[1].model, name="new-name"))
    assert build_arm_for(competitor, rc).provider.key == "new-name"


def test_external_names_cannot_escape_revision(site, tmp_path):
    revision = snapshot(site, tmp_path)
    with pytest.raises(config.ConfigError):
        config.resolve_snapshot(revision, str(paths(site)[0]), "smoke-frontier", runtime_root=site, env=ENV)


def test_cancellation_preserves_resumable_status(site, tmp_path, monkeypatch):
    rc = local_resolve(site)
    rc.competitors = rc.competitors[:1]
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator.from_config(store, rc, tmp_path / "out")
    orch.cancel()
    monkeypatch.setattr(orch, "_run_episode", lambda *a: pytest.fail("cancelled run dispatched an attempt"))
    with pytest.raises(RunKilled):
        orch.run("cancelled")
    assert store.run("cancelled")["stop_reason"] == "cancelled"


def test_resume_refuses_different_source_even_when_semantic_hash_matches(site, tmp_path, monkeypatch):
    rc = external(site, tmp_path)
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator.from_config(store, rc, tmp_path / "out")
    store.create_run("original", rc.hash, orch.suite, orch._config())
    monkeypatch.setattr(orch, "_arms", lambda: pytest.fail("source drift reached arm construction"))
    rc.config_source["commit"] = "b" * 40
    with pytest.raises(ConfigDrift, match="source"):
        orch.resume("original")


def test_cli_preview_pins_remote_commit_without_launch(site, tmp_path, monkeypatch, capsys):
    from wb_orchestrator import cli
    rc = external(site, tmp_path)
    calls = []
    def selected(product, plan, **kwargs):
        calls.append((product, plan, kwargs))
        return rc
    monkeypatch.setattr(config, "resolve_selection", selected)
    monkeypatch.setattr(Orchestrator, "run", lambda *a: pytest.fail("preview launched"))
    assert cli.main(["preview", "--product", "simulated-apps", "--plan", "smoke-frontier", "--revision", "a" * 40]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["commit"] == "a" * 40
    assert result["attempts_total"] == rc.attempts_total
    assert result["config_hash"] == rc.hash
    assert calls[0][2]["revision"] == "a" * 40


def test_recorded_source_restores_offline_and_refuses_changed_tasks(site, tmp_path, monkeypatch):
    from wb_orchestrator.config_repository import Repository
    rc = external(site, tmp_path)
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator.from_config(store, rc, tmp_path / "out")
    monkeypatch.setattr(orch, "_execute", lambda *a, **kw: None)
    orch.run("frozen")  # evidence recording only; no arm execution
    recorded = json.loads(store.run("frozen")["config_json"])
    assert json.loads((tmp_path / "out/frozen/config-source.json").read_text()) == rc.config_source
    monkeypatch.setenv("WB_CONFIG_CACHE", str(tmp_path / "fresh-cache"))
    monkeypatch.setattr(Repository, "snapshot", lambda *a: pytest.fail("resume used the network"))
    shutil.rmtree(Path(rc.config_dir).parent)
    restored = config.resume_config(recorded, env=ENV)
    assert restored.hash == rc.hash
    assert restored.competitors[1].model == rc.competitors[1].model
    task_path = next((site / "tasks").glob("*.json"))
    task = json.loads(task_path.read_text())
    task["prompt"][1]["content"] += " Changed local task."
    task_path.write_text(json.dumps(task))
    changed = config.resume_config(recorded, env=ENV)
    resumed = Orchestrator.from_config(store, changed, tmp_path / "out")
    monkeypatch.setattr(resumed, "_arms", lambda: pytest.fail("task drift reached an arm"))
    with pytest.raises(ConfigDrift, match="config drift"):
        resumed.resume("frozen")


def test_remote_resume_cannot_raise_ceiling_without_new_run(site, tmp_path, monkeypatch):
    rc = external(site, tmp_path)
    store = Store(tmp_path / "results.sqlite3")
    orch = Orchestrator.from_config(store, rc, tmp_path / "out")
    store.create_run("original", rc.hash, orch.suite, orch._config())
    rc.plan = replace(rc.plan, cost_ceiling_usd=rc.plan.cost_ceiling_usd + 100)
    monkeypatch.setattr(orch, "_arms", lambda: pytest.fail("ceiling drift reached an arm"))
    with pytest.raises(ConfigDrift, match="ceiling"):
        orch.resume("original")


def test_cli_snapshot_environment_uses_shared_selection(monkeypatch):
    from types import SimpleNamespace
    from wb_orchestrator.cli import _selected_config
    monkeypatch.delenv("WB_CONFIG_REPOSITORY", raising=False)
    monkeypatch.setenv("WB_CONFIG_SNAPSHOT", "source.json")
    marker = object()
    monkeypatch.setattr(config, "resolve_selection", lambda *a, **k: marker)
    assert _selected_config(SimpleNamespace(product="simulated-apps", plan="tier-simple")) is marker
