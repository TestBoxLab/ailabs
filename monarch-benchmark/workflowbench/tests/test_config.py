"""Tests for wb_orchestrator.config: single-file loading, cross-file resolve, run hash."""
import datetime
import json
import re
import shutil
from pathlib import Path

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
        if re.match(rf"{re.escape(key)}:(\s|$)", l):
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


def test_malformed_yaml(tmp_path):
    p = tmp_path / "api.yaml"
    p.write_text("a: [")
    assert "cannot read" in check_error(config.load_harness, p, "<root>")


# ---------------------------------------------------------------- resolve

MODEL_OPENAI = """\
name: gpt-5.6-sol
provider: openai
model: gpt-5.6-sol
effort: xhigh
usd_per_million: {input: 4.00, cached: 0.40, output: 20.00}
key_env: OPENAI_API_KEY
"""

HARNESS_CODEX = """\
name: codex
kind: cli
launcher: codex
accepts: [openai]
runnable: false
command: codex exec
"""

TASKS = Path(__file__).resolve().parent.parent / "tasks"
TASK_FILES = ("simple.sf_opp_closed_won.json", "simple.email_sf_contact_city_update.json")
ENV = {"ANTHROPIC_API_KEY": "sk-ant-secret", "OPENAI_API_KEY": "sk-oai-secret", "MONARCH_TOKEN": "mon-secret"}
AUDIENCES = {"internal": ["*"], "public-rung2": ["monarch"]}


@pytest.fixture
def site(tmp_path):
    """A config tree and a task dir laid out like the shipped ones."""
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    for name in TASK_FILES:
        shutil.copy(TASKS / name, tasks / name)
    plan = edit(PLAN, "tasks", f'"{tasks.as_posix()}"')
    for sub, texts in {"products": [PRODUCT], "models": [MODEL, MODEL_OPENAI_COMPAT, MODEL_OPENAI],
                       "harnesses": [HARNESS_API, HARNESS_CLI, HARNESS_SCRIPTED, HARNESS_MONARCH, HARNESS_CODEX],
                       "plans": [plan]}.items():
        (tmp_path / "config" / sub).mkdir(parents=True)
        for t in texts:
            write(tmp_path / "config" / sub, t)
    return tmp_path


def paths(site):
    return site / "config/products/simulated-apps.yaml", site / "config/plans/smoke-frontier.yaml"


def resolve(site, env=ENV, audiences=AUDIENCES):
    return config.resolve(*paths(site), env=env, audiences=audiences)


def rewrite(site, sub, text, key, value=None):
    """Rewrite one config file with a top-level key changed."""
    return write(site / "config" / sub, edit(text, key, value))


def plan_text(site):
    return (site / "config/plans/smoke-frontier.yaml").read_text()


def check_resolve_error(site, path, field):
    return check_error(lambda _: resolve(site), path, field)


def test_resolve_names_and_counts(site):
    rc = resolve(site)
    assert [c.name for c in rc.competitors] == ["oracle", "claude-opus-4-8/api", "gpt-5.6-sol/api"]
    assert rc.competitors[0].model is None and rc.competitors[0].harness.script == "oracle"
    assert rc.competitors[1].model.name == "claude-opus-4-8" and rc.competitors[1].harness.kind == "api"
    assert [t["task"] for t in rc.tasks] == ["simple.email_sf_contact_city_update", "simple.sf_opp_closed_won"]
    assert rc.attempts_per_competitor == 4 and rc.attempts_total == 12
    assert set(rc.models) == {"claude-opus-4-8", "gpt-5.6-sol"} and set(rc.harnesses) == {"oracle", "api"}
    assert rc.product.name == "simulated-apps" and rc.plan.name == "smoke-frontier"


def test_resolve_rule3_missing_env(site):
    env = {k: v for k, v in ENV.items() if k != "OPENAI_API_KEY"}
    with pytest.raises(ConfigError) as exc:
        resolve(site, env=env)
    assert exc.value.path == str(site / "config/models/gpt-5.6-sol.yaml") and exc.value.field == "key_env"
    assert "OPENAI_API_KEY" in str(exc.value)


def runnable_monarch(site, modes="[full-flow, create-run, run-only]"):
    text = edit(HARNESS_MONARCH, "runnable", "true").replace(
        "modes: [full-flow, create-run, run-only]", f"modes: {modes}")
    write(site / "config/harnesses", text)
    write(site / "config/plans", plan_text(site).replace("  - {harness: oracle}\n", "  - {harness: monarch}\n"))


def test_resolve_rule3_missing_credential_env(site):
    runnable_monarch(site)
    env = {k: v for k, v in ENV.items() if k != "MONARCH_TOKEN"}
    with pytest.raises(ConfigError) as exc:
        resolve(site, env=env)
    assert exc.value.path == str(site / "config/harnesses/monarch.yaml") and exc.value.field == "credential_env"


def test_resolve_rule4_mode_unsupported_by_product(site):
    rewrite(site, "products", PRODUCT, "modes", "[full-flow]")
    msg = check_resolve_error(site, paths(site)[1], "mode")
    assert "create-run" in msg and "simulated-apps.yaml" in msg


def test_resolve_rule4_mode_unsupported_by_monarch_harness(site):
    runnable_monarch(site, modes="[full-flow]")
    msg = check_resolve_error(site, paths(site)[1], "competitors[0].harness")
    assert "create-run" in msg


def test_resolve_rule5_unknown_model(site):
    write(site / "config/plans", plan_text(site).replace("model: gpt-5.6-sol", "model: gpt-6"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[2].model")
    assert "unknown model 'gpt-6'" in msg and "known: claude-opus-4-8, gpt-5.6-sol, kimi-k3" in msg


def test_resolve_rule5_unknown_harness(site):
    write(site / "config/plans", plan_text(site).replace("{harness: oracle}", "{harness: magic}"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[0].harness")
    assert "unknown harness 'magic'" in msg and "known:" in msg


def test_resolve_rule5_harness_rejects_provider(site):
    write(site / "config/plans", plan_text(site).replace("{model: gpt-5.6-sol, harness: api}",
                                                          "{model: gpt-5.6-sol, harness: claude-code}"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[2].model")
    assert "openai" in msg and "claude-code" in msg


def test_resolve_rule5_model_given_to_none_harness(site):
    write(site / "config/plans", plan_text(site).replace("{harness: oracle}", "{model: kimi-k3, harness: oracle}"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[0].model")
    assert "no model" in msg


def test_resolve_rule5_model_missing_for_api_harness(site):
    write(site / "config/plans", plan_text(site).replace("{harness: oracle}", "{harness: api}"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[0].model")
    assert "needs a model" in msg


def test_resolve_rule6_harness_not_runnable(site):
    write(site / "config/plans", plan_text(site).replace("{model: gpt-5.6-sol, harness: api}",
                                                          "{model: gpt-5.6-sol, harness: codex}"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[2].harness")
    assert "not runnable" in msg


def test_resolve_rule7_duplicate_competitor(site):
    write(site / "config/plans", plan_text(site).replace("  - {harness: oracle}\n",
                                                          "  - {harness: oracle}\n  - {harness: oracle}\n"))
    msg = check_resolve_error(site, paths(site)[1], "competitors[1]")
    assert "duplicate" in msg and "'oracle'" in msg


def test_resolve_rule7_baseline_absent(site):
    write(site / "config/plans", edit(plan_text(site), "baseline", "kimi-k3/api"))
    msg = check_resolve_error(site, paths(site)[1], "baseline")
    assert "kimi-k3/api" in msg and "oracle, claude-opus-4-8/api, gpt-5.6-sol/api" in msg


def test_resolve_rule8_task_service_outside_product(site):
    rewrite(site, "products", PRODUCT, "services", "[salesforce]")
    msg = check_resolve_error(site, paths(site)[0], "services")
    assert "simple.email_sf_contact_city_update" in msg and "'gmail'" in msg and "simulated-apps.yaml" in msg


def test_resolve_rule10_unknown_audience(site):
    write(site / "config/plans", edit(plan_text(site), "audience", "press"))
    msg = check_resolve_error(site, paths(site)[1], "audience")
    assert "'press'" in msg and "internal" in msg


def test_resolve_missing_task_dir(site):
    write(site / "config/plans", edit(plan_text(site), "tasks", f'"{(site / "nowhere").as_posix()}"'))
    check_resolve_error(site, paths(site)[1], "tasks")


# ---------------------------------------------------------------- hash

def test_hash_changes_with_experimental_inputs(site):
    h0 = resolve(site).hash
    assert re.fullmatch(r"[0-9a-f]{16}", h0)
    assert resolve(site).hash == h0  # deterministic

    write(site / "config/models", MODEL_OPENAI.replace("cached: 0.40", "cached: 0.45"))
    h_price = resolve(site).hash
    write(site / "config/models", MODEL_OPENAI)

    write(site / "config/harnesses", edit(HARNESS_API, "description", "Tweaked."))
    h_harness = resolve(site).hash
    write(site / "config/harnesses", HARNESS_API)

    rewrite(site, "products", PRODUCT, "description", "Tweaked.")
    h_product = resolve(site).hash
    write(site / "config/products", PRODUCT)

    write(site / "config/plans", edit(plan_text(site), "timeout_s", "601"))
    h_timeout = resolve(site).hash
    assert len({h0, h_price, h_harness, h_product, h_timeout}) == 5


def test_hash_ignores_guard_fields(site):
    h0 = resolve(site).hash
    write(site / "config/plans", edit(plan_text(site), "cost_ceiling_usd", "500"))
    assert resolve(site).hash == h0
    write(site / "config/plans", edit(plan_text(site), "approved_by", "carlos"))
    assert resolve(site).hash == h0


def test_config_json_has_no_secrets(site):
    rc = resolve(site)
    blob = json.dumps(rc.config_json)  # must be plain JSON (dates as strings)
    for secret in ENV.values():
        assert secret not in blob
    assert "ANTHROPIC_API_KEY" in blob and "OPENAI_API_KEY" in blob  # names only
    j = rc.config_json
    assert j["product_path"] == str(paths(site)[0]) and j["plan_path"] == str(paths(site)[1])
    assert j["tasks_dir"] == rc.plan.tasks and j["n_tasks"] == 2 and j["mode"] == "create-run"
    assert j["attempts_total"] == 12 and "cost_ceiling_usd" not in j["plan"] and "approved_by" not in j["plan"]
    assert j["models"]["claude-opus-4-8"]["prices_verified"] == "2026-09-02"
    assert j["tasks"] == sorted(j["tasks"]) and len(j["tasks"]) == 2
