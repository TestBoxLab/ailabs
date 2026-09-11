"""One readable name per competitor, wherever the run was launched from."""
import pytest

from wb_studio import measures
from wb_studio.app import setup_names, with_setup_names
from wb_studio.report_data import short_name
from wb_studio.runtime_registry import display_name, fit_name


@pytest.mark.parametrize("identifier,expected", [
    # A run launched from a config plan names its competitors model/harness.
    ("kimi-k3-fireworks/api", "Kimi K3 (Fireworks)"),
    ("glm-5.3-fireworks/api", "GLM 5.3 (Fireworks)"),
    ("claude-opus-5/api", "Claude Opus 5"),
    ("gpt-5.6-terra/api", "GPT-5.6 Terra"),
    ("gpt-5.6-sol/api", "GPT-5.6 Sol"),
    # A harness that is not the plain tool loop is worth saying.
    ("claude-opus-5/claude-code", "Claude Opus 5 · Claude Code"),
    ("gpt-5.6-sol/codex", "GPT-5.6 Sol · Codex"),
    # Scripted checks.
    ("oracle", "Scripted reference"),
    ("sloppy", "Near-miss control"),
    # Reasoning effort travels after an @.
    ("claude-opus-5@high", "Claude Opus 5 · high"),
    # The build token a figure label cannot hold.
    ("monarch · 0cf63a74e+feat/railway-dev-deploy* reasoning", "Monarch · reasoning"),
    ("monarch · 9b79557 stock", "Monarch · stock"),
    # An id nobody has catalogued still reads as a name, never as a slug.
    ("some-new-model/api", "Some New Model"),
])
def test_every_identifier_shape_reads_as_a_name(identifier, expected):
    assert display_name(identifier) == expected


def test_a_studio_arm_keeps_its_own_name_without_the_build_token():
    assert display_name("kimi-k3-fireworks@high", "Kimi K3 (Fireworks) · high reasoning") == \
        "Kimi K3 (Fireworks) · high reasoning"
    assert display_name("blueprint.x", "Enrichment v3 · 4f21a9c+draft claude") == "Enrichment v3 · claude"


def test_an_empty_identifier_is_returned_untouched():
    assert display_name("") == "" and display_name(None) == ""


def test_a_figure_label_is_cut_on_a_word_boundary():
    assert fit_name("Kimi K3 (Fireworks) · high reasoning", 34) == "Kimi K3 (Fireworks) · high…"
    assert fit_name("Claude Opus 5", 34) == "Claude Opus 5"


def test_the_report_figure_label_uses_the_same_resolver():
    assert short_name("kimi-k3-fireworks/api") == "Kimi K3 (Fireworks)"
    assert short_name("monarch · 0cf63a74e+feat/railway-dev-deploy* reasoning") == "Monarch · reasoning"


def test_the_run_page_gets_a_name_for_every_competitor():
    job = {"settings": {"models": ["oracle", "kimi-k3-fireworks/api"],
                        "arms": [{"id": "kimi-k3-fireworks/api", "name": "kimi-k3-fireworks/api"},
                                 {"id": "blueprint.x", "name": "Enrichment v3"}]}}
    assert setup_names(job) == {"kimi-k3-fireworks/api": "Kimi K3 (Fireworks)",
                                "blueprint.x": "Enrichment v3",
                                "oracle": "Scripted reference"}


def test_a_report_never_prints_the_internal_token_of_an_unnamed_setup():
    job = {"settings": {"models": ["oracle"], "arms": [{"id": "arch-v1", "name": "Informed worker / v1"}]}}
    assert measures.setup_names(job) == {"arch-v1": "Informed worker / v1", "oracle": "Scripted reference"}


def test_the_run_list_names_every_setup_of_a_run_that_carries_no_arms():
    listed = with_setup_names({"settings": {"models": ["oracle", "claude-opus-5@high"]}})
    assert [a["name"] for a in listed["settings"]["arms"]] == ["Scripted reference", "Claude Opus 5 · high"]
