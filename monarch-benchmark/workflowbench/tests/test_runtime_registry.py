"""Capability matrix: unsupported version × runner cells fail before a job exists."""
from pathlib import Path
import hashlib
import json
import threading
from types import SimpleNamespace

import pytest

from wb_arms import runtime_manifest as rm
from wb_results.evidence import write_json
from wb_studio import blueprints, runtime_registry as rr
from wb_studio.architectures import REPOSITORY, DIRECTORY

ENTERPRISE_CHECKOUT = Path(__file__).resolve().parents[3] / ".references" / "monarch-enterprise-60faf2a"


def models():
    return [{"id": "gemini-3.7-flash", "name": "Gemini", "available": False},
            {"id": "claude-code", "name": "Claude Code", "available": False},
            {"id": "codex", "name": "Codex", "available": False},
            {"id": "oracle", "name": "Scripted", "available": True}]


@pytest.fixture
def studio(tmp_path):
    return SimpleNamespace(directory=tmp_path, lock=threading.RLock(), research_dir=tmp_path / "research", models=models)


def baseline(commit="a" * 40):
    manifest = rm.freeze(rm.build("default-monarch-enterprise",
        source={"kind": "git", "repository": "https://github.com/" + REPOSITORY, "directory": DIRECTORY, "ref": "main", "commit": commit,
                "patch_sha256": None, "lockfile": {"path": "pnpm-lock.yaml", "git_blob": "b" * 40}, "image_digest": None},
        evaluation={"track": "agentic-request", "provider": "bedrock", "model": "claude-opus-4-8", "effort": "default", "harness": "operator"},
        readiness_record=rm.readiness("resolved", "not_applicable", "adapter_required", ["no adapter"])))
    return {"id": "default-monarch-enterprise", "kind": "default", "name": "Default Monarch Enterprise", "repository": "https://github.com/" + REPOSITORY,
            "directory": DIRECTORY, "ref": "main", "commit": commit, "lockfile": {"path": "pnpm-lock.yaml", "git_blob": "b" * 40},
            "url": "x", "verified_at": "now", "readiness": manifest["readiness"], "runtime_manifest": manifest}


@pytest.mark.parametrize("selection,supported,fragment", [
    ("gemini-3.7-flash@high", True, "API control"),
    ("gemini-3.7-flash@max", False, "accepts low, medium, high"),
    ("oracle", True, "Scripted"),
    ({"provider": "fireworks", "model": "accounts/fireworks/models/x", "effort": "default"}, False, "No verified rate card"),
    ({"provider": "bedrock", "model": "claude-opus-4-8", "effort": "default"}, False, "stock Enterprise brain"),
])
def test_without_monarch_runner_support(studio, selection, supported, fragment):
    row = rr.runner_support(studio, "without-monarch", selection)
    assert row["supported"] is supported
    assert fragment in row["reason"]


@pytest.mark.parametrize("selection", ["claude-code", "codex", {"provider": "claude-code", "model": "sonnet", "effort": "high"}])
def test_native_runners_are_the_right_harness_but_blocked_by_the_isolation_preflight(studio, selection):
    row = rr.runner_support(studio, "without-monarch", selection)
    assert row["supported"] is True
    assert "native-isolation-v1" in row["launch_block"]
    assert "filesystem_boundary" in row["launch_block"]


@pytest.mark.parametrize("track,runner,supported,fragment", [
    ("agentic-request", {"provider": "codex", "model": "gpt-5.6-sol", "effort": "medium"}, False, "Bedrock"),
    ("agentic-request", {"provider": "gemini", "model": "gemini-3.7-flash", "effort": "high"}, False, "does not accept gemini"),
    ("agentic-request", {"provider": "bedrock", "model": "claude-opus-4-8", "effort": "default"}, True, "Stock operator"),
    ("agentic-request", {"provider": "bedrock", "model": "claude-opus-4-8", "effort": "medium"}, False, "no per-run reasoning effort"),
    ("agentic-request", {"provider": "bedrock", "model": "claude-opus-5", "effort": "default"}, False, "no per-run model"),
    ("agentic-request", {"provider": "bedrock", "model": "claude-fable-5", "effort": "default"}, False, "barred"),
    ("agentic-request", {"provider": "bedrock", "model": "gpt-5.6-sol", "effort": "default"}, False, "not in the pinned"),
    ("create-and-run", {"provider": "bedrock", "model": "claude-opus-4-8", "effort": "medium"}, True, "opus-medium"),
    ("create-and-run", {"provider": "bedrock", "model": "claude-sonnet-5", "effort": "high"}, True, "sonnet-high"),
    ("create-and-run", {"provider": "bedrock", "model": "claude-opus-4-8", "effort": "default"}, True, "environment default"),
    ("create-and-run", {"provider": "bedrock", "model": "claude-opus-5", "effort": "high"}, False, "only the stock brain presets"),
])
def test_stock_enterprise_accepts_only_what_the_pinned_product_supports(studio, track, runner, supported, fragment):
    row = rr.runner_support(studio, "default-monarch-enterprise", runner, track)
    assert row["supported"] is supported, row
    assert fragment in row["reason"]


def test_bridge_preset_matches_only_the_recovered_setting(studio):
    good = rr.runner_support(studio, "bridge-v2-v9.12", {"provider": "anthropic", "model": "claude-opus-5", "effort": "medium"})
    assert good["supported"] is True
    other = rr.runner_support(studio, "bridge-v2-v9.12", {"provider": "anthropic", "model": "claude-opus-5", "effort": "max"})
    assert other["supported"] is False and "new variant" in other["reason"]


def test_enterprise_facts_match_the_pinned_checkout_when_present():
    if not ENTERPRISE_CHECKOUT.is_dir():
        pytest.skip("pinned Enterprise checkout not present")
    root = ENTERPRISE_CHECKOUT / "monarch-enterprise"
    for relative, digest in rr.ENTERPRISE_FACTS["source_files"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest, relative
    catalog = json.loads((root / "apps/backend/src/config/bedrock-models.json").read_text(encoding="utf-8"))
    assert [m["key"] for m in catalog["models"]] == rr.ENTERPRISE_FACTS["models"]
    presets = (root / "apps/backend/src/workflows/recipe-agent/brain-presets.ts").read_text(encoding="utf-8")
    for name, spec in rr.ENTERPRISE_FACTS["create_run"]["brain_presets"].items():
        assert f"'{name}': {{ model: '{spec['model']}', effort: '{spec['effort']}' }}" in presets
    assert hashlib.sha256((ENTERPRISE_CHECKOUT / "pnpm-lock.yaml").read_bytes()).hexdigest() == rr.ENTERPRISE_FACTS["lockfile"]["sha256"]


def test_versions_report_three_readiness_axes_without_network(studio, monkeypatch):
    monkeypatch.setattr("wb_studio.architectures.resolve_default", lambda: pytest.fail("versions() must not resolve GitHub"))
    rows = {v["id"]: v for v in rr.versions(studio)}
    assert rows["without-monarch"]["readiness"]["launchable"] is True
    enterprise = rows["default-monarch-enterprise"]["readiness"]
    # No GitHub pin yet, and no verified deployment: not launchable, and the reasons say why.
    assert (enterprise["source"], enterprise["publication"]) == ("unavailable", "not_applicable")
    assert enterprise["runtime"] in ("blocked", "preparation_required") and enterprise["launchable"] is False
    assert enterprise["reasons"] and any("official revision" in r for r in enterprise["reasons"])
    assert rows["default-monarch-enterprise"]["commit"] is None
    bridge = rows["bridge-v2-v9.12"]
    assert bridge["readiness"]["source"] == bridge["readiness"]["runtime"] == "source_required"
    assert bridge["settings"]["model"] == "claude-opus-5" and bridge["settings"]["effort"] == "medium"
    write_json(studio.directory / "enterprise-baseline.json", baseline())
    frozen = {v["id"]: v for v in rr.versions(studio)}["default-monarch-enterprise"]
    assert frozen["readiness"]["source"] == "frozen" and frozen["commit"] == "a" * 40
    assert frozen["manifest"]["frozen"] is True


def test_bridge_readiness_reads_the_provenance_inventory(studio):
    folder = studio.research_dir / "architectures" / "bridge-v2-v9.12"
    folder.mkdir(parents=True)
    write_json(folder / "source-manifest.json", {"summary": {"present": 3, "missing": 2},
                                                 "entries": [{"role": "generated_graph", "status": "missing"}, {"role": "actor_contract", "status": "missing"}, {"role": "report", "status": "present"}]})
    status = rr.bridge_status(studio)
    assert status["missing"] == ["generated_graph", "actor_contract"]
    assert "2 required components missing" in status["readiness"]["reasons"][0]
    assert status["readiness"]["launchable"] is False


def node(identity, kind, **config):
    return {"id": identity, "type": kind, "label": identity, "x": 1, "y": 1, "config": config}


def version(middle):
    return {"graph": {"nodes": [node("input", "input"), middle, node("output", "output")], "edges": []}}


def test_blueprint_readiness_distinguishes_unsupported_from_not_yet_executable(studio):
    wrong = rr.blueprint_readiness(studio, version(node("monarch", "monarch", runner={"provider": "codex", "model": "gpt-5.6-sol", "effort": "medium"})))
    assert wrong["readiness"]["runtime"] == "unsupported" and "monarch:" in wrong["readiness"]["reasons"][0]
    stock = rr.blueprint_readiness(studio, version(node("monarch", "monarch", runner={"provider": "bedrock", "model": "claude-opus-4-8", "effort": "default"})))
    assert stock["readiness"]["runtime"] == "adapter_required" and stock["readiness"]["source"] == "frozen"
    native = rr.blueprint_readiness(studio, version(node("worker", "agent", runner={"provider": "claude-code", "model": "sonnet", "effort": "high"})))
    assert native["readiness"]["runtime"] == "blocked"
    assert any("native-isolation-v1" in r for r in native["readiness"]["reasons"])
    assert native["capabilities"][0]["supported"] is True


def test_published_versions_carry_readiness_capabilities_and_a_manifest(studio):
    graph = {"nodes": [node("input", "input"), node("worker", "agent", instructions="Complete the task.", runner={"provider": "claude-code", "model": "sonnet", "effort": "high"}), node("output", "output")],
             "edges": [{"from": "input", "to": "worker"}, {"from": "worker", "to": "output"}]}
    blueprints.save_draft(studio, {"id": "native", "name": "Native agent", "graph": graph})
    published = blueprints.publish(studio, {"id": "native", "revision": 1})
    assert published["execution_status"] == "blocked"
    assert published["readiness"]["launchable"] is False
    assert published["capabilities"][0]["supported"] is True
    assert any("native-isolation-v1" in reason for reason in published["readiness"]["reasons"])
    manifest = rm.validate(published["runtime_manifest"])
    assert manifest["source"]["kind"] == "local" and manifest["source"]["commit"] is None
    assert manifest["artifacts"]["graph"]["sha256"] == published["sha256"]
    assert manifest["artifacts"]["prompts"]["sha256"] == rm.sha256_json({"worker": "Complete the task."})
    assert manifest["evaluation"]["track"] == "agentic-request"
    listed = {v["id"]: v for v in rr.versions(studio)}["blueprint.native.v1"]
    assert listed["readiness"]["runtime"] == "blocked" and listed["sha256"] == published["sha256"]


def test_legacy_published_versions_get_live_readiness_without_file_mutation(studio):
    folder = studio.directory / "blueprints" / "legacy"
    folder.mkdir(parents=True)
    legacy = {"id": "legacy", "name": "Demo", "version": 1, "draft_revision": 1, "execution_status": "adapter_required",
              "graph": version(node("monarch", "monarch", runner={"provider": "codex", "model": "gpt-5.6-sol", "effort": "medium"}))["graph"]}
    write_json(folder / "v0001.json", legacy)
    write_json(folder / "draft.json", {"id": "legacy", "name": "Demo", "revision": 1, "graph": legacy["graph"]})
    items = rr.annotate_listing(studio, blueprints.listing(studio))
    shown = items[0]["versions"][0]
    assert shown["readiness"]["runtime"] == "unsupported" and shown["readiness_computed_live"] is True
    stored = json.loads((folder / "v0001.json").read_text(encoding="utf-8"))
    assert "readiness" not in stored and stored["execution_status"] == "adapter_required"


def test_capability_matrix_marks_every_cell_and_the_native_preflight(studio):
    matrix = rr.capability_matrix(studio)
    assert matrix["native_preflight"]["status"] == "blocked"
    cells = {(c["version"], c["runner"]): c for c in matrix["cells"]}
    assert cells[("without-monarch", "oracle")]["launchable"] is True
    assert cells[("without-monarch", "gemini-3.7-flash")]["launchable"] is False  # unavailable credential
    assert cells[("without-monarch", "claude-code")]["launchable"] is False and "native-isolation-v1" in cells[("without-monarch", "claude-code")]["reason"]
    assert cells[("default-monarch-enterprise", "codex")]["supported"] is False
    assert all(c["launchable"] is False for c in matrix["cells"] if c["version"] != "without-monarch")


@pytest.mark.parametrize("architectures,selected,fragment", [
    ([], ["oracle"], "cannot launch yet"),
    (["default-monarch-enterprise"], ["oracle"], "belongs to the create-and-run track"),
    (["bridge-v2-v9.12"], ["oracle"], "cannot launch yet"),
    (["without-monarch", "without-monarch"], ["oracle"], "cannot launch yet"),
    (["without-monarch"], ["claude-code"], "native-isolation-v1"),
    (["without-monarch"], ["gemini-3.7-flash@max"], "accepts low, medium, high"),
    (["blueprint.missing.v9"], ["oracle"], "Unknown comparison version"),
])
def test_check_launch_refuses_unsupported_cells_before_any_job(studio, architectures, selected, fragment):
    with pytest.raises(ValueError, match=fragment):
        rr.check_launch(studio, architectures, selected)


def test_check_launch_defaults_to_without_monarch_and_returns_the_versions(studio, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-placeholder")
    assert [v["id"] for v in rr.check_launch(studio, None, ["oracle", "gemini-3.7-flash@high"])] == ["without-monarch"]
    assert [v["id"] for v in rr.check_launch(studio, ["without-monarch"], ["oracle"])] == ["without-monarch"]
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        rr.check_launch(studio, None, ["gemini-3.7-flash@high"])
