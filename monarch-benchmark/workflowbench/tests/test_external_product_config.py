"""Product files for an external world (feature 026, contracts/config-files.md).

Refusals happen at configuration load, before anything is reserved and before any
container starts. That ordering is the point of most of these tests: the expensive
mistake is a round that spends money and then discovers its product was wrong.
"""
from __future__ import annotations

import textwrap
from dataclasses import asdict

import pytest

from wb_orchestrator import config as config_mod
from wb_orchestrator.config import ConfigError

SIMULATED = textwrap.dedent("""
    name: p
    kind: simulated
    data: {dataset: d, mutable: true}
    services: [gmail]
    side_effects: config/side-effects.yaml
    modes: [create-run]
""")


def write(tmp_path, body, name="p.yaml"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_the_existing_product_file_is_untouched_by_this_feature():
    """`config/products/simulated-apps.yaml` must stay valid byte for byte."""
    p = config_mod.load_product(config_mod.DEFAULT_CONFIG_DIR / "products" / "simulated-apps.yaml")
    assert p.world is None, "the world we always had is the default, not a value to write"
    assert p.source is None
    assert p.participants == []


def test_a_product_may_name_a_world(tmp_path):
    p = config_mod.load_product(write(tmp_path, SIMULATED + textwrap.dedent("""
        world: automation-bench
    """)))
    assert p.world == "automation-bench"


def test_an_unknown_world_is_refused_by_name(tmp_path):
    with pytest.raises(ConfigError) as e:
        config_mod.load_product(write(tmp_path, SIMULATED + "world: no-such-world\n"))
    assert "no-such-world" in e.value.why
    assert "automation-bench" in e.value.why, "the refusal must say what is known"


def test_a_source_pin_is_read(tmp_path):
    p = config_mod.load_product(write(tmp_path, SIMULATED + textwrap.dedent("""
        world: automation-bench
        source:
          benchmark: enterprise-ops-gym
          version: "1.0.0"
          split: itsm/oracle
          checker: SQL verifiers over the final environment state
          positive_half_is_end_state_only: true
    """)))
    assert p.source.benchmark == "enterprise-ops-gym"
    assert p.source.split == "itsm/oracle"
    assert p.source.positive_half_is_end_state_only is True


def test_a_source_pin_without_a_world_is_refused(tmp_path):
    with pytest.raises(ConfigError) as e:
        config_mod.load_product(write(tmp_path, SIMULATED + textwrap.dedent("""
            source:
              benchmark: enterprise-ops-gym
              version: "1.0.0"
              split: itsm
              checker: SQL
        """)))
    assert "world" in e.value.field or "world" in e.value.why


def test_a_participant_is_read_with_its_model_and_price_table(tmp_path):
    p = config_mod.load_product(write(tmp_path, SIMULATED + textwrap.dedent("""
        world: automation-bench
        participants:
          - role: simulated-user
            model: claude-opus-5
            price_table: current
    """)))
    assert p.participants[0].role == "simulated-user"
    assert p.participants[0].model == "claude-opus-5"


def test_an_unknown_participant_role_is_refused(tmp_path):
    with pytest.raises(ConfigError):
        config_mod.load_product(write(tmp_path, SIMULATED + textwrap.dedent("""
            world: automation-bench
            participants:
              - role: grader
                model: claude-opus-5
                price_table: current
        """)))


def test_declared_services_must_match_the_worlds_own(tmp_path):
    """An approval rule addresses a service by name. A typo here would match
    nothing and every attempt would read as clean."""
    with pytest.raises(ConfigError) as e:
        config_mod.load_product(write(tmp_path, textwrap.dedent("""
            name: p
            kind: simulated
            world: automation-bench
            data: {dataset: d, mutable: true}
            services: [gmial]
            side_effects: config/side-effects.yaml
            modes: [create-run]
        """)))
    assert "gmial" in e.value.why


def test_the_participants_enter_the_configuration_hash(tmp_path):
    """Changing the pinned customer model must change the round's hash, or a
    comparison could silently span two different measurements."""
    base = SIMULATED + textwrap.dedent("""
        world: automation-bench
        participants:
          - role: simulated-user
            model: claude-opus-5
            price_table: current
    """)
    other = base.replace("claude-opus-5", "claude-haiku-4-5")
    a = config_mod.load_product(write(tmp_path / "a", base))
    b = config_mod.load_product(write(tmp_path / "b", other))
    assert asdict(a) != asdict(b), "asdict(product) is what config._hashed() hashes"
