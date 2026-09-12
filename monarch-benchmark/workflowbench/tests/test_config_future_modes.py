"""Future declarations validate without claiming executable capability."""
from dataclasses import asdict

import pytest
import yaml

from wb_orchestrator import config
from tests.test_config import (HARNESS_MONARCH, PRICE_TABLE, PRODUCT, PLAN,
                               MODEL, write, site, paths)


def test_duplicate_mapping_keys_are_rejected(tmp_path):
    with pytest.raises(config.ConfigError, match="duplicate key"):
        config.load_product(write(tmp_path, PRODUCT + "kind: simulated\n"))
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        config.load_yaml("outer:\n  value: 1\n  value: 2\n")


def test_discovery_is_a_valid_definition_but_not_executable(tmp_path, site):
    product = PRODUCT.replace("[full-flow, create-run, run-only]", "[feature-discovery]")
    plan = PLAN.replace("mode: create-run", "mode: feature-discovery")
    assert config.load_product(write(tmp_path, product)).modes == ["feature-discovery"]
    assert config.load_plan(write(tmp_path, plan)).mode == "feature-discovery"
    assert config.load_harness(write(tmp_path, HARNESS_MONARCH.replace(
        "[full-flow, create-run, run-only]", "[feature-discovery]"))).modes == ["feature-discovery"]
    product_path, plan_path = paths(site)
    product_path.write_text(product)
    plan_path.write_text(plan)
    with pytest.raises(config.ConfigError, match="feature-discovery.*not implemented"):
        config.resolve(product_path, plan_path, env={})


def test_family_requirements_are_typed_and_reference_price_metadata(tmp_path):
    table = config.load_price_table(write(tmp_path, PRICE_TABLE))
    harness = config.load_harness(write(tmp_path, HARNESS_MONARCH +
        "model_families: {brain: claude-opus-5, writer: claude-opus-4-8}\n"))
    config.validate_model_families(harness, table, tmp_path / "monarch.yaml")
    assert config._hashed_harness(harness)["model_families"] == harness.model_families
    harness.model_families["writer"] = "unknown-family"
    with pytest.raises(config.ConfigError, match="unknown model family"):
        config.validate_model_families(harness, table, tmp_path / "monarch.yaml")
    for value in ("{unknown: claude-opus-5}", "{brain: 42}", "[]"):
        with pytest.raises(config.ConfigError, match="model_families"):
            config.load_harness(write(tmp_path, HARNESS_MONARCH + "model_families: " + value))


def test_absent_family_requirements_preserve_hashed_shape(tmp_path):
    harness = config.load_harness(write(tmp_path, HARNESS_MONARCH))
    expected = asdict(harness)
    expected.pop("model_families", None)
    expected.pop("authoring_mode")
    assert config._hashed_harness(harness) == expected


def test_family_requirements_refuse_dispatch(site):
    from tests.monarch_helpers import monarch_site, resolve_monarch
    monarch_site(site)
    path = site / "config/harnesses/monarch.yaml"
    path.write_text(path.read_text() + "model_families: {brain: claude-opus-5}\n")
    with pytest.raises(config.ConfigError, match="model-family routing.*not implemented"):
        resolve_monarch(site)


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_nonfinite_plan_money_is_refused(tmp_path, value):
    with pytest.raises(config.ConfigError, match="must be a finite number"):
        config.load_plan(write(tmp_path, PLAN.replace("cost_ceiling_usd: 5", "cost_ceiling_usd: " + value)))


def test_negative_model_price_is_refused(tmp_path):
    with pytest.raises(config.ConfigError, match="must be >= 0"):
        config.load_model(write(tmp_path, MODEL.replace("input: 5.00", "input: -5.00")))


def test_enterprise_picker_also_blocks_family_requirements(site, tmp_path):
    from tests.monarch_helpers import monarch_site
    from tests.test_studio_enterprise import studio_for
    from wb_studio.enterprise import Setup
    monarch_site(site)
    path = site / "config/harnesses/monarch.yaml"
    path.write_text(path.read_text() + "model_families: {writer: claude-opus-5}\n")
    setup = Setup(studio_for(tmp_path, site))
    assert any("model-family routing and verification are not implemented" in p for p in setup.problems)
