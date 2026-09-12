"""Direct plan construction cannot bypass declaration-only capability guards."""
import pytest
from types import SimpleNamespace

from tests.test_config import site
from tests.monarch_helpers import monarch_site, resolve_monarch
from wb_orchestrator import config, monarch_recipes
from wb_orchestrator.orchestrator import build_arm_for


def test_recipe_generation_refuses_family_requirements_before_arm_construction(site, monkeypatch):
    monarch_site(site)
    path = site / "config/harnesses/monarch.yaml"
    path.write_text(path.read_text() + "model_families: {writer: claude-opus-5}\n")
    constructed = []
    monkeypatch.setattr("wb_arms.monarch.monarch_version", lambda *args: "monarch@fixture")
    monkeypatch.setattr("wb_arms.monarch.MonarchArm", lambda **kwargs: (constructed.append(kwargs), SimpleNamespace())[1])
    with pytest.raises(config.ConfigError, match="model-family routing.*not implemented"):
        monarch_recipes._arm(site / "config/products/simulated-apps.yaml", path, {})
    assert constructed == []


def test_manual_discovery_plan_refuses_shared_construction(site, monkeypatch):
    monarch_site(site)
    rc = resolve_monarch(site)
    rc.plan.mode = "feature-discovery"
    constructed = []
    monkeypatch.setattr("wb_arms.monarch.monarch_version", lambda *args: "monarch@fixture")
    monkeypatch.setattr("wb_arms.monarch.MonarchArm", lambda **kwargs: (constructed.append(kwargs), SimpleNamespace())[1])
    with pytest.raises(config.ConfigError, match="feature-discovery.*not implemented"):
        build_arm_for(rc.competitors[0], rc)
    assert constructed == []
