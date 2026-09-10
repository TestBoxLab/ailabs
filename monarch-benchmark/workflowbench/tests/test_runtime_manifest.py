"""Runtime manifests: identity moves with executable inputs, readiness never launches anything."""
from copy import deepcopy

import pytest

from wb_arms import runtime_manifest as rm


def manifest(**changes):
    source = {"kind": "git", "repository": "https://github.com/TestBoxLab/monarch", "directory": "monarch-enterprise",
              "commit": "a" * 40, "patch_sha256": None, "lockfile": {"path": "pnpm-lock.yaml", "git_blob": "b" * 40}, "image_digest": None}
    evaluation = {"track": "agentic-request", "provider": "bedrock", "model": "claude-opus-4-8", "effort": "default", "harness": "operator"}
    artifacts = {"graph": {"status": "present", "sha256": "c" * 64}}
    ready = rm.readiness("resolved", "not_applicable", "adapter_required", ["No adapter yet"])
    values = dict(source=source, evaluation=evaluation, artifacts=artifacts, readiness_record=ready)
    values.update(changes)
    return rm.build("default-monarch-enterprise", **values)


def test_build_validates_and_identity_ignores_readiness_notes_and_timestamps():
    first = manifest()
    assert rm.validate(first) is first
    relabelled = manifest(readiness_record=rm.readiness("frozen", "not_applicable", "blocked", ["other reason"]), notes="different")
    assert relabelled["identity_sha256"] == first["identity_sha256"]
    assert first["readiness"]["launchable"] is False and first["frozen"] is False


@pytest.mark.parametrize("change", ["commit", "graph", "effort", "lockfile", "provider"])
def test_identity_moves_with_every_executable_input(change):
    base = manifest()
    other = deepcopy(base)
    if change == "commit":
        other["source"]["commit"] = "d" * 40
    if change == "graph":
        other["artifacts"]["graph"]["sha256"] = "e" * 64
    if change == "effort":
        other["evaluation"]["effort"] = "high"
    if change == "lockfile":
        other["source"]["lockfile"]["git_blob"] = "f" * 40
    if change == "provider":
        other["evaluation"]["provider"] = "anthropic"
    assert rm.identity_hash(other) != base["identity_sha256"]
    with pytest.raises(ValueError, match="moved identity"):
        rm.assert_unchanged(other)


def test_freeze_pins_commit_and_marks_source_frozen():
    frozen = rm.freeze(manifest())
    assert frozen["frozen"] is True and frozen["frozen_at"]
    assert frozen["readiness"]["source"] == "frozen"
    assert rm.validate(frozen)["identity_sha256"] == frozen["identity_sha256"]
    unpinned = manifest()
    unpinned["source"]["commit"] = None
    unpinned["identity_sha256"] = rm.identity_hash(unpinned)
    with pytest.raises(ValueError, match="full commit"):
        rm.freeze(unpinned)


@pytest.mark.parametrize("source,publication,runtime", [("odd", "published", "ready"), ("frozen", "odd", "ready"), ("frozen", "published", "odd")])
def test_unknown_readiness_states_are_refused(source, publication, runtime):
    with pytest.raises(ValueError, match="Unknown"):
        rm.readiness(source, publication, runtime, ["x"])


def test_not_ready_needs_a_reason_and_ready_is_the_only_launchable_state():
    with pytest.raises(ValueError, match="say why"):
        rm.readiness("frozen", "published", "adapter_required")
    assert rm.readiness("not_applicable", "not_applicable", "ready")["launchable"] is True
    assert rm.readiness("frozen", "published", "blocked", ["sandbox"])["launchable"] is False


@pytest.mark.parametrize("mutation", ["schema", "short-commit", "present-without-hash", "bad-effort", "bad-track", "tampered-identity", "bad-surface"])
def test_invalid_manifests_are_rejected(mutation):
    value = manifest()
    if mutation == "schema":
        value["schema_version"] = "other"
    if mutation == "short-commit":
        value["source"]["commit"] = "abc123"
    if mutation == "present-without-hash":
        value["artifacts"]["graph"] = {"status": "present", "sha256": None}
    if mutation == "bad-effort":
        value["evaluation"]["effort"] = "unlimited"
    if mutation == "bad-track":
        value["evaluation"]["track"] = "browser"
    if mutation == "tampered-identity":
        value["identity_sha256"] = "0" * 64
    if mutation == "bad-surface":
        value["public_surface"] = {"tool_surface_sha256": "not-a-hash"}
    if mutation != "tampered-identity":
        value["identity_sha256"] = rm.identity_hash(value)
    with pytest.raises(ValueError):
        rm.validate(value)


def test_local_sources_need_no_commit_and_missing_artifacts_are_allowed():
    value = rm.build("bridge-v2-v9.12",
                     source={"kind": "local", "repository": None, "directory": "Monarch_Main", "commit": None, "patch_sha256": None, "lockfile": None, "image_digest": None},
                     evaluation={"track": "agentic-request", "provider": "anthropic", "model": "claude-opus-5", "effort": "medium", "harness": "shim"},
                     artifacts={"generated_graph": {"status": "missing", "sha256": None}},
                     readiness_record=rm.readiness("source_required", "not_applicable", "source_required", ["graph missing"]))
    assert value["artifacts"]["generated_graph"]["status"] == "missing"
    assert value["readiness"]["launchable"] is False
