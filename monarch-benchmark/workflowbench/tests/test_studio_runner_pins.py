"""Queued API controls keep the model and effort reviewed at creation, offline."""
import json
import threading
from decimal import Decimal

import pytest

from wb_studio.app import LiveArm, ROOT, Studio
from wb_studio.runtime_registry import api_controls
from wb_world.episode import load_suite


@pytest.fixture
def studio(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "FIREWORKS_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "offline-only")
    def forbidden(*args, **kwargs):
        pytest.fail("No provider dispatch is permitted")
    return Studio(tmp_path, tasks=load_suite(ROOT / "tasks")[:1], gateway_factory=forbidden, adapter_factory=forbidden)


def create(studio, models, **extra):
    return studio.create({"models": models, "tasks": list(studio.tasks), "maximum_usd": "10.00", **extra}, start=False)


def live(studio, job, model):
    return LiveArm(studio, job["id"], model, list(studio.tasks)[0], threading.Event(), Decimal("10"))


def saved_runner(studio):
    path = studio.directory / "runner-configs" / "chosen.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"id": "chosen", "name": "Reviewed GPT configuration", "provider": "openai",
                                "model": "gpt-5.6-sol", "effort": "high"}), encoding="utf-8")
    return path


@pytest.mark.parametrize("change", ["replace", "delete"])
def test_queued_runner_uses_frozen_provider_model_and_effort_after_config_change(studio, change):
    path = saved_runner(studio)
    job = create(studio, ["config-chosen"])
    original_bytes = (studio.directory / job["id"] / "job.json").read_bytes()
    if change == "replace":
        path.write_text(json.dumps({"id": "chosen", "name": "Changed Claude", "provider": "anthropic",
                                    "model": "claude-opus-5", "effort": "low"}), encoding="utf-8")
    else:
        path.unlink()
    arm = live(studio, job, "config-chosen")
    assert arm.runner() == {"provider": "openai", "model": "gpt-5.6-sol", "effort": "high"}
    # Verify the actual gateway receives the frozen choice; creating it sends no request.
    gateway = studio.gateway_for(arm.runner())
    assert (gateway.describe()["provider"], gateway.describe()["model"], gateway.describe()["effort"]) == ("gpt-5.6-sol", "gpt-5.6-sol", "high")
    assert Decimal(studio.budget()["actual"]) == 0
    assert Decimal(studio.budget()["held"]) == 10  # Full-run liability is held before dispatch.
    assert (studio.directory / job["id"] / "job.json").read_bytes() == original_bytes


def test_default_effort_is_materialized_and_raw_api_manifest_is_never_native_bare(studio):
    job = create(studio, ["gpt-5.6-sol", "gpt-5.6-sol@high", "kimi-k3-fireworks"])
    controls = api_controls()
    manifests = studio.job(job["id"])["runner_manifests"]
    assert manifests["gpt-5.6-sol"]["runner"]["effort"] == controls["gpt-5.6-sol"]["default_effort"]
    assert manifests["gpt-5.6-sol@high"]["runner"]["effort"] == "high"
    assert manifests["kimi-k3-fireworks"]["runner"]["effort"] is None
    assert manifests["kimi-k3-fireworks"]["runner"]["model"] == "accounts/fireworks/models/kimi-k3"
    for manifest in manifests.values():
        assert manifest["kind"] == "api-control"
        assert manifest["native_harness"] is False
        assert manifest["comparison_class"] == "raw-api-control"
        assert manifest["harness"] == "studio-api-loop"
        assert manifest["rate_card"].startswith("config/models/")
        assert "not a native-harness Bare baseline" in manifest["qualification"]


def test_runner_comparison_hash_changes_with_experiment_prompt_and_selected_effort(studio):
    standard = create(studio, ["gpt-5.6-sol@low"])
    prompt = create(studio, ["gpt-5.6-sol@low"], configuration={"prompt": "Verify entity IDs before writing", "max_turns": 20})
    effort = create(studio, ["gpt-5.6-sol@high"])
    repeat = create(studio, ["gpt-5.6-sol@low"])
    hashes = [next(iter(j["runner_manifests"].values()))["configuration_sha256"] for j in (standard, prompt, effort, repeat)]
    assert len(set(hashes[:3])) == 3
    assert hashes[0] == hashes[3]


@pytest.mark.parametrize("selection", ["config-chosen", "gpt-5.6-sol@high"])
def test_historical_jobs_without_runner_pins_keep_legacy_resolution(studio, selection):
    saved_runner(studio)
    job = create(studio, [selection])
    for arm in job["settings"]["arms"]:
        arm.pop("runner", None)
    job.pop("runner_manifests")
    studio.save(job)
    assert live(studio, job, selection).runner() == {"provider": "openai", "model": "gpt-5.6-sol", "effort": "high"}


def test_scripted_controls_do_not_gain_an_api_runner_manifest(studio):
    job = create(studio, ["oracle"])
    assert "runner_manifests" not in job
    assert "runner" not in job["settings"]["arms"][0]


def test_reusing_request_id_after_runner_configuration_changes_cannot_replace_frozen_job(studio):
    path = saved_runner(studio)
    job = create(studio, ["config-chosen"], request_id="immutable-run")
    assert create(studio, ["config-chosen"], request_id="immutable-run") == job
    path.write_text(json.dumps({"id": "chosen", "name": "Reviewed GPT configuration", "provider": "openai",
                                "model": "gpt-5.6-sol", "effort": "low"}), encoding="utf-8")
    with pytest.raises(ValueError, match="different comparison"):
        create(studio, ["config-chosen"], request_id="immutable-run")
    assert studio.job(job["id"])["runner_manifests"] == job["runner_manifests"]
    assert Decimal(studio.budget()["actual"]) == 0
    assert Decimal(studio.budget()["held"]) == 10  # Full-run liability is held before dispatch.
