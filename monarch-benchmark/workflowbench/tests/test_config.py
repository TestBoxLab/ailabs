"""Loader and validator for the four config kinds (single files, no cross-file resolution)."""
import datetime

import pytest

from wb_orchestrator import config
from wb_orchestrator.config import ConfigError

# One valid example per kind, copied from contracts/config-files.md.
PRODUCT = """\
name: simulated-apps
description: The 47 simulated business apps from AutomationBench.
kind: simulated
data:
  dataset: automationbench-47-apps
  mutable: true
services: [airtable, asana, salesforce, gmail]
side_effects: config/side-effects.yaml
modes: [full-flow, create-run, run-only]
"""

MODEL = """\
name: claude-opus-4-8
provider: anthropic
model: claude-opus-4-8
effort: xhigh
usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}
key_env: ANTHROPIC_API_KEY
cache_min_prompt_tokens: 1024
prices_verified: 2026-09-02
description: Monarch's own authoring brain; the baseline competitor.
"""

MODEL_OPENAI_COMPAT = """\
name: kimi-k3
provider: moonshot
model: kimi-k3
effort: xhigh
usd_per_million: {input: 3.00, cached: 0.30, output: 15.00}
key_env: MOONSHOT_API_KEY
adapter: openai
base_url: https://api.moonshot.ai/v1
cache_min_prompt_tokens: 256
"""

HARNESS_API = """\
name: api
kind: api
accepts: [anthropic, openai, google, zai, moonshot, fireworks]
description: The generic three-tool loop.
"""

HARNESS_CLI = """\
name: claude-code
kind: cli
launcher: claude-code
accepts: [anthropic]
command: claude -p
env:
  ANTHROPIC_MODEL: "{model}"
output: json-stream
description: Claude Code headless.
"""

HARNESS_SCRIPTED = """\
name: oracle
kind: scripted
script: oracle
accepts: none
description: The answer key.
"""

HARNESS_MONARCH = """\
name: monarch
kind: monarch
accepts: none
runnable: false
base_url: ${MONARCH_URL}
credential_env: MONARCH_TOKEN
release: "1.4"
modes: [full-flow, create-run, run-only]
description: The product under comparison.
"""

PLAN = """\
name: smoke-frontier
description: Small run to test the machine.
tasks: tasks
mode: create-run
repetitions: 2
timeout_s: 600
concurrency: 4
competitors:
  - {harness: oracle}
  - {model: claude-opus-4-8, harness: api}
  - {model: gpt-5.6-sol, harness: api}
baseline: claude-opus-4-8/api
audience: internal
cost_ceiling_usd: 5
approved_by: null
"""

EXAMPLES = {
    "product": (config.load_product, PRODUCT),
    "model": (config.load_model, MODEL),
    "model_openai_compat": (config.load_model, MODEL_OPENAI_COMPAT),
    "harness_api": (config.load_harness, HARNESS_API),
    "harness_cli": (config.load_harness, HARNESS_CLI),
    "harness_scripted": (config.load_harness, HARNESS_SCRIPTED),
    "harness_monarch": (config.load_harness, HARNESS_MONARCH),
    "plan": (config.load_plan, PLAN),
}


def write(tmp_path, text, stem=None):
    stem = stem or text.split("\n", 1)[0].split(":", 1)[1].strip()
    p = tmp_path / f"{stem}.yaml"
    p.write_text(text)
    return p


def edit(text, key, value=None):
    """Replace the top-level `key:` block (or drop it when value is None)."""
    lines, skipping = [], False
    for l in text.splitlines():
        if l.startswith(f"{key}:"):
            skipping = True
        elif skipping and l[:1] in (" ", "-"):
            continue  # indented continuation of the dropped block
        else:
            skipping = False
            lines.append(l)
    if value is not None:
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("kind", EXAMPLES)
def test_each_example_loads(tmp_path, kind):
    load, text = EXAMPLES[kind]
    obj = load(write(tmp_path, text))
    assert obj.name == text.split("\n", 1)[0].split(":", 1)[1].strip()


def test_loaded_fields(tmp_path):
    p = config.load_product(write(tmp_path, PRODUCT))
    assert p.kind == "simulated" and p.data.mutable is True and p.data.dataset == "automationbench-47-apps"
    assert p.services[0] == "airtable" and p.modes == ["full-flow", "create-run", "run-only"]

    m = config.load_model(write(tmp_path, MODEL))
    assert m.usd_per_million.cache_write == 6.25 and m.cache_min_prompt_tokens == 1024
    assert m.prices_verified == datetime.date(2026, 9, 2) and m.adapter is None
    m2 = config.load_model(write(tmp_path, MODEL_OPENAI_COMPAT))
    assert m2.usd_per_million.cache_write == 3.0  # defaults to input
    assert m2.adapter == "openai" and m2.header_fallbacks == [] and m2.prices_verified is None

    h = config.load_harness(write(tmp_path, HARNESS_CLI))
    assert h.runnable is True and h.launcher == "claude-code" and h.env == {"ANTHROPIC_MODEL": "{model}"}
    o = config.load_harness(write(tmp_path, HARNESS_SCRIPTED))
    assert o.accepts == "none" and o.script == "oracle"
    mo = config.load_harness(write(tmp_path, HARNESS_MONARCH))
    assert mo.runnable is False and mo.release == "1.4"

    pl = config.load_plan(write(tmp_path, PLAN))
    assert pl.approved_by is None and pl.timeout_s == 600 and pl.repetitions == 2
    assert pl.competitors[0] == config.CompetitorSpec(model=None, harness="oracle")
    assert pl.competitors[1] == config.CompetitorSpec(model="claude-opus-4-8", harness="api")


def check_error(load, path, field):
    with pytest.raises(ConfigError) as exc:
        load(path)
    e = exc.value
    assert e.path == str(path) and e.field == field
    assert str(e).startswith(f"config error in {path}: {field}: ")
    return str(e)


@pytest.mark.parametrize("kind", EXAMPLES)
def test_name_must_equal_stem(tmp_path, kind):
    load, text = EXAMPLES[kind]
    check_error(load, write(tmp_path, text, stem="other"), "name")


@pytest.mark.parametrize("kind", EXAMPLES)
def test_unknown_key_rejected(tmp_path, kind):
    load, text = EXAMPLES[kind]
    msg = check_error(load, write(tmp_path, text + "bogus_key: 1\n"), "bogus_key")
    assert "unknown" in msg


@pytest.mark.parametrize("kind,key", [
    ("product", "kind"), ("product", "services"), ("product", "side_effects"),
    ("model", "provider"), ("model", "key_env"), ("model", "usd_per_million"),
    ("harness_api", "accepts"), ("harness_cli", "command"), ("harness_scripted", "script"),
    ("harness_monarch", "credential_env"),
    ("plan", "tasks"), ("plan", "competitors"), ("plan", "approved_by"), ("plan", "baseline"),
])
def test_missing_required_key(tmp_path, kind, key):
    load, text = EXAMPLES[kind]
    msg = check_error(load, write(tmp_path, edit(text, key)), key)
    assert "required" in msg


def test_missing_nested_key(tmp_path):
    text = MODEL.replace("usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}",
                         "usd_per_million: {input: 5.00, output: 25.00}")
    check_error(config.load_model, write(tmp_path, text), "usd_per_million.cached")
    text = PRODUCT.replace("  mutable: true\n", "")
    check_error(config.load_product, write(tmp_path, text), "data.mutable")


@pytest.mark.parametrize("kind,key,value", [
    ("product", "kind", "imaginary"),
    ("product", "modes", "[full-flow, sideways]"),
    ("model", "adapter", "grpc"),
    ("model", "effort", "maximal"),
    ("model", "provider", "acme"),
    ("harness_api", "kind", "gui"),
    ("harness_cli", "launcher", "vim"),
    ("harness_scripted", "script", "random"),
    ("plan", "mode", "backwards"),
])
def test_bad_enum(tmp_path, kind, key, value):
    load, text = EXAMPLES[kind]
    field = "modes[1]" if key == "modes" else key
    check_error(load, write(tmp_path, edit(text, key, value)), field)


@pytest.mark.parametrize("kind,key,value", [
    ("product", "services", "salesforce"),          # not a list
    ("model", "cache_min_prompt_tokens", "many"),     # not int
    ("harness_cli", "runnable", "yes please"),        # not bool
    ("plan", "repetitions", "0"),                     # int >= 1
    ("plan", "timeout_s", "0"),                       # number > 0
    ("plan", "concurrency", "1.5"),                   # int
    ("plan", "cost_ceiling_usd", "-1"),               # > 0
    ("plan", "approved_by", "7"),                     # str or null
])
def test_bad_type(tmp_path, kind, key, value):
    load, text = EXAMPLES[kind]
    check_error(load, write(tmp_path, edit(text, key, value)), key)


def test_plan_competitor_shape(tmp_path):
    text = PLAN.replace("  - {harness: oracle}\n", "  - {model: x}\n")
    check_error(config.load_plan, write(tmp_path, text), "competitors[0].harness")
    text = PLAN.replace("  - {harness: oracle}\n", "  - {harness: oracle, arm: x}\n")
    check_error(config.load_plan, write(tmp_path, text), "competitors[0].arm")


def test_harness_kind_specific_keys(tmp_path):
    # keys of another kind are rejected
    check_error(config.load_harness, write(tmp_path, HARNESS_API + "script: oracle\n"), "script")
    check_error(config.load_harness, write(tmp_path, HARNESS_CLI + "release: '1'\n"), "release")
    check_error(config.load_harness, write(tmp_path, HARNESS_SCRIPTED + "command: x\n"), "command")
    # monarch modes are enum-checked
    text = HARNESS_MONARCH.replace("modes: [full-flow, create-run, run-only]", "modes: [warp]")
    check_error(config.load_harness, write(tmp_path, text), "modes[0]")


def test_top_level_must_be_mapping(tmp_path):
    p = tmp_path / "api.yaml"
    p.write_text("- just\n- a list\n")
    check_error(config.load_harness, p, "<root>")
