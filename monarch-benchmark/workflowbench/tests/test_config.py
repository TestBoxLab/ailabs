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
login_email: dev-root@testbox.com
login_password_env: MONARCH_PASSWORD
fd_url: ${MONARCH_FD_URL}
shim_port: 9105
shim_public_host: host.docker.internal
langfuse_url: ${LANGFUSE_URL}
langfuse_public_key_env: LANGFUSE_PUBLIC_KEY
langfuse_secret_key_env: LANGFUSE_SECRET_KEY
price_table: monarch-team-bedrock
monarch_repo: ../../../monarch
modes: [full-flow, create-run, run-only]
description: The product under comparison.
"""

PRICE_TABLE = """\
name: monarch-team-bedrock
kind: price-table
provider: bedrock
region: us-west-2
prices_verified: 2026-09-03
description: Bedrock prices for the models Monarch may call.
models:
  - family: claude-opus-4-8
    match: [opus-4-8]
    usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}
  - family: claude-opus-5
    match: [opus-5]
    usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}
  - family: claude-sonnet-5
    match: [sonnet-5]
    usd_per_million: {input: 2.00, cached: 0.20, cache_write: 2.50, output: 10.00}
  - family: claude-sonnet-4-6
    match: [sonnet-4-6]
    usd_per_million: {input: 3.00, cached: 0.30, cache_write: 3.75, output: 15.00}
  - family: claude-haiku-4-5
    match: [haiku-4-5]
    usd_per_million: {input: 1.00, cached: 0.10, cache_write: 1.25, output: 5.00}
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
    assert mo.runnable is False and mo.login_email == "dev-root@testbox.com"
    assert mo.shim_port == 9105 and mo.shim_public_host == "host.docker.internal"
    assert mo.login_password_env == "MONARCH_PASSWORD" and mo.fd_url == "${MONARCH_FD_URL}"
    assert mo.langfuse_url == "${LANGFUSE_URL}"
    assert mo.langfuse_public_key_env == "LANGFUSE_PUBLIC_KEY"
    assert mo.langfuse_secret_key_env == "LANGFUSE_SECRET_KEY"
    assert mo.price_table == "monarch-team-bedrock" and mo.monarch_repo == "../../../monarch"

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
    # `release` is gone from the monarch harness (the version is read from the checkout)
    msg = check_error(config.load_harness, write(tmp_path, HARNESS_MONARCH + "release: '1.4'\n"), "release")
    assert "unknown" in msg


@pytest.mark.parametrize("port", ["1023", "65536", "0"])
def test_monarch_shim_port_must_be_a_usable_port(tmp_path, port):
    check_error(config.load_harness, write(tmp_path, edit(HARNESS_MONARCH, "shim_port", port)), "shim_port")


# ---------------------------------------------------------------- price table

def test_price_table_loads_five_families(tmp_path):
    table = config.load_price_table(write(tmp_path, PRICE_TABLE))
    assert table.name == "monarch-team-bedrock" and table.provider == "bedrock"
    assert table.region == "us-west-2" and table.prices_verified == datetime.date(2026, 9, 3)
    assert [e.family for e in table.models] == ["claude-opus-4-8", "claude-opus-5", "claude-sonnet-5",
                                                "claude-sonnet-4-6", "claude-haiku-4-5"]
    assert table.models[0].match == ["opus-4-8"]
    assert table.models[2].usd_per_million == config.Prices(input=2.0, cached=0.2, output=10.0,
                                                            cache_write=2.5)


def test_price_table_needs_all_four_prices(tmp_path):
    text = PRICE_TABLE.replace("{input: 1.00, cached: 0.10, cache_write: 1.25, output: 5.00}",
                               "{input: 1.00, cached: 0.10, output: 5.00}")
    check_error(config.load_price_table, write(tmp_path, text), "models[4].usd_per_million.cache_write")


def test_price_table_family_must_be_unique(tmp_path):
    text = PRICE_TABLE.replace("family: claude-opus-5", "family: claude-opus-4-8")
    msg = check_error(config.load_price_table, write(tmp_path, text), "models[1].family")
    assert "duplicate" in msg


def test_price_table_match_must_be_a_non_empty_list(tmp_path):
    text = PRICE_TABLE.replace("match: [opus-5]", "match: []")
    check_error(config.load_price_table, write(tmp_path, text), "models[1].match")


def test_load_model_rejects_a_price_table(tmp_path):
    msg = check_error(config.load_model, write(tmp_path, PRICE_TABLE), "kind")
    assert "price-table" in msg


def test_load_models_skips_price_tables(tmp_path):
    from wb_arms import providers
    write(tmp_path, MODEL)
    write(tmp_path, PRICE_TABLE)
    assert sorted(providers.load_models(tmp_path)) == ["claude-opus-4-8"]


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


def test_resolve_rule3_empty_env_is_unset(site):
    with pytest.raises(ConfigError) as exc:
        resolve(site, env={**ENV, "OPENAI_API_KEY": ""})
    assert exc.value.field == "key_env" and "OPENAI_API_KEY" in str(exc.value)


def test_resolve_relative_tasks_dir(site, monkeypatch):
    write(site / "config/plans", edit(plan_text(site), "tasks", "tasks"))
    monkeypatch.chdir(site / "config")  # any cwd: relative to the folder above config/
    rc = resolve(site)
    assert rc.attempts_per_competitor == 4 and rc.plan.tasks == "tasks" and rc.config_json["tasks_dir"] == "tasks"


def runnable_monarch(site, modes="[full-flow, create-run, run-only]", price_table=None,
                     monarch_repo=None):
    text = edit(HARNESS_MONARCH, "runnable", "true").replace(
        "modes: [full-flow, create-run, run-only]", f"modes: {modes}")
    if price_table is not None:
        text = edit(text, "price_table", price_table)
    if monarch_repo is not None:
        text = edit(text, "monarch_repo", monarch_repo)
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
    assert "simple.email_sf_contact_city_update" in msg and "service gmail" in msg and "simulated-apps.yaml" in msg


def test_resolve_rule8_names_task_service_and_product_file(site):
    rewrite(site, "products", PRODUCT, "services", "[gmail]")  # every task here seeds salesforce
    msg = check_resolve_error(site, paths(site)[0], "services")
    assert "task simple.email_sf_contact_city_update" in msg and "service salesforce" in msg
    assert "simulated-apps.yaml" in msg and "does not list in services" in msg


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
    write(site / "config/models", MODEL_OPENAI.replace("cached: 0.40", "cached: 0.4"))
    assert resolve(site).hash == h0  # int/float spelling of a price
    write(site / "config/plans", edit(plan_text(site), "timeout_s", "600.0"))
    assert resolve(site).hash == h0
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


# ---------------------------------------------------------------- T034/T039: registry from files

def test_load_models_matches_the_nine_shipped_files():
    from wb_arms import providers
    got = providers.load_models(config.DEFAULT_CONFIG_DIR / "models")
    assert sorted(got) == ["claude-opus-4-8", "claude-opus-5", "gemini-3.7-flash", "glm-5.3", "glm-5.3-fireworks",
                           "gpt-5.6-sol", "gpt-5.6-terra", "kimi-k3", "kimi-k3-fireworks"]
    want = {
        "glm-5.3": dict(model_id="glm-5.3", key_env="ZAI_API_KEY", adapter="openai",
                        base_url="https://api.z.ai/api/paas/v4", price_in=1.40, price_cached=0.26,
                        price_out=4.40, price_cache_write=1.40, cache_min_prompt_tokens=0,
                        header_fallbacks=()),
        "kimi-k3": dict(model_id="kimi-k3", key_env="MOONSHOT_API_KEY", adapter="openai",
                        base_url="https://api.moonshot.ai/v1", price_in=3.00, price_cached=0.30,
                        price_out=15.00, price_cache_write=3.00, cache_min_prompt_tokens=256,
                        header_fallbacks=()),
        "kimi-k3-fireworks": dict(model_id="accounts/fireworks/models/kimi-k3",
                                  key_env="FIREWORKS_API_KEY", adapter="openai",
                                  base_url="https://api.fireworks.ai/inference/v1", price_in=3.00,
                                  price_cached=0.30, price_out=15.00, price_cache_write=3.00,
                                  cache_min_prompt_tokens=0,
                                  header_fallbacks=("fireworks-cached-prompt-tokens",)),
        "claude-opus-4-8": dict(model_id="claude-opus-4-8", key_env="ANTHROPIC_API_KEY",
                                adapter="anthropic", base_url=None, price_in=5.00, price_cached=0.50,
                                price_out=25.00, price_cache_write=6.25, cache_min_prompt_tokens=1024,
                                header_fallbacks=()),
        "gpt-5.6-sol": dict(model_id="gpt-5.6-sol", key_env="OPENAI_API_KEY", adapter="openai_responses",
                            base_url=None, price_in=4.00, price_cached=0.40, price_out=20.00,
                            price_cache_write=4.00, cache_min_prompt_tokens=0, header_fallbacks=()),
        "gpt-5.6-terra": dict(model_id="gpt-5.6-terra", key_env="OPENAI_API_KEY", adapter="openai_responses",
                              base_url=None, price_in=2.00, price_cached=0.20, price_out=12.00,
                              price_cache_write=2.00, cache_min_prompt_tokens=0, header_fallbacks=()),
        "gemini-3.7-flash": dict(model_id="gemini-3.7-flash", key_env="GEMINI_API_KEY", adapter="gemini",
                                 base_url=None, price_in=0.75, price_cached=0.075, price_out=3.75,
                                 price_cache_write=0.75, cache_min_prompt_tokens=4096, header_fallbacks=()),
    }
    for key, fields in want.items():
        p = got[key]
        assert isinstance(p, providers.Provider) and p.key == key and p.effort == "xhigh"
        for f, v in fields.items():
            assert getattr(p, f) == v, (key, f, getattr(p, f), v)


@pytest.mark.parametrize("provider,adapter", [("anthropic", "anthropic"), ("openai", "openai_responses"),
                                              ("google", "gemini"), ("zai", "openai"), ("moonshot", "openai")])
def test_load_models_default_adapter_by_provider(tmp_path, provider, adapter):
    from wb_arms import providers
    write(tmp_path, edit(edit(MODEL_OPENAI, "provider", provider), "name", "m"), stem="m")
    assert providers.load_models(tmp_path)["m"].adapter == adapter


def test_load_models_explicit_adapter_and_effort(tmp_path):
    from wb_arms import providers
    write(tmp_path, edit(MODEL_OPENAI_COMPAT, "effort", "low"))
    p = providers.load_models(tmp_path)["kimi-k3"]
    assert p.adapter == "openai" and p.effort == "low"


def test_registry_is_the_seven_files_and_doctor_resolves_through_get(monkeypatch):
    from wb_arms import providers
    from wb_orchestrator import doctor
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert sorted(providers.REGISTRY) == sorted(  # price tables share the folder but are not competitors
        p.stem for p in (config.DEFAULT_CONFIG_DIR / "models").glob("*.yaml") if not config.is_price_table(p))
    assert providers.get("claude-opus-4-8").model_id == "claude-opus-4-8"
    report = doctor.check_provider("claude-opus-4-8")  # no key: fails before any call
    assert report["provider"] == "claude-opus-4-8" and report["error"] == "ANTHROPIC_API_KEY not set"
    assert "unknown provider" in doctor.check_provider("nope")["error"]


# -- T040: the reply to Monarch's questions is code, never config --------------

def test_fixed_reply_not_in_config(tmp_path):
    """Nobody can tune the sentence per run: it would make attempts uncomparable."""
    from wb_arms.monarch import FIXED_REPLY
    for key in ("reply", "fixed_reply"):
        msg = check_error(config.load_harness,
                          write(tmp_path, HARNESS_MONARCH + f"{key}: hello\n"), key)
        assert "unknown" in msg
    shipped = [p for p in (Path(__file__).resolve().parents[1] / "config").rglob("*.yaml")
               if FIXED_REPLY in p.read_text(encoding="utf-8")]
    assert shipped == []


def test_fd_api_key_env_is_optional(tmp_path):
    """The Railway deployment gates /v1/*; a local one does not."""
    h = config.load_harness(write(tmp_path, HARNESS_MONARCH))
    assert h.fd_api_key_env is None
    h = config.load_harness(write(tmp_path, HARNESS_MONARCH
                                  + "fd_api_key_env: FD_API_SHARED_SECRET\n"))
    assert h.fd_api_key_env == "FD_API_SHARED_SECRET"


def test_shim_public_url_is_optional_and_overrides_host_port(tmp_path):
    from wb_orchestrator.monarch_setup import public_front_door_url
    text = HARNESS_MONARCH
    path = tmp_path / "monarch.yaml"
    path.write_text(text)
    h = config.load_harness(path)
    assert h.shim_public_url is None
    assert public_front_door_url(h, {}) == "http://host.docker.internal:9105"
    path.write_text(text + "shim_public_url: ${FRONT_DOOR_URL}\n")
    h = config.load_harness(path)
    env = {"FRONT_DOOR_URL": "https://example.ngrok-free.dev/"}
    assert public_front_door_url(h, env) == "https://example.ngrok-free.dev"


# -- 004 T006: the recipes file -----------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures"

RECIPES = """\
product: simulated-apps
tasks: tasks
generated_at: '2026-09-04T12:00:00Z'
kb_hash_file_sha: aa11bb22
monarch: monarch@1a2b3c4
recipes:
  simple.email_sf_contact_city_update:
    workflow_id: wf-1
    recipe_version: 3
    authored_at: '2026-09-04T12:03:11Z'
    attempts_used: 1
missing:
  simple.sf_opp_closed_won:
    reason: checker_failed
    attempts_used: 3
    detail: 'invariant failed: is_closed, is_won changed'
"""

RECIPE_TASKS = ("simple.email_sf_contact_city_update", "simple.sf_opp_closed_won")


def recipes_file(tmp_path, text=RECIPES):
    p = tmp_path / "simulated-apps.monarch-recipes.yaml"
    p.write_text(text)
    return p


def load_recipes(tmp_path, text=RECIPES, tasks=RECIPE_TASKS, product="simulated-apps"):
    return config.load_monarch_recipes(recipes_file(tmp_path, text), product, tasks)


def test_load_monarch_recipes_returns_the_rows(tmp_path):
    r = load_recipes(tmp_path)
    assert r.product == "simulated-apps" and r.tasks == "tasks"
    assert r.kb_hash_file_sha == "aa11bb22" and r.monarch == "monarch@1a2b3c4"
    row = r.recipes["simple.email_sf_contact_city_update"]
    assert row.workflow_id == "wf-1" and row.recipe_version == 3 and row.attempts_used == 1
    assert row.authored_at == "2026-09-04T12:03:11Z"
    gone = r.missing["simple.sf_opp_closed_won"]
    assert gone.reason == "checker_failed" and gone.attempts_used == 3
    assert "is_closed" in gone.detail


def test_load_monarch_recipes_reads_the_shipped_sample():
    """The fixture the offline run-only tests use: 9 recipes, 1 missing, the 10 pilot tasks."""
    tasks = sorted(p.stem for p in (Path(__file__).resolve().parents[1] / "tasks").glob("*.json"))
    r = config.load_monarch_recipes(FIXTURES / "monarch-recipes-sample.yaml",
                                    "simulated-apps", tasks)
    assert len(r.recipes) == 9 and len(r.missing) == 1
    assert set(r.recipes) | set(r.missing) == set(tasks)


def test_load_monarch_recipes_task_in_both_maps(tmp_path):
    text = RECIPES.replace("  simple.sf_opp_closed_won:\n    reason",
                           "  simple.email_sf_contact_city_update:\n    reason")
    with pytest.raises(ConfigError) as exc:
        load_recipes(tmp_path, text)
    assert "simple.email_sf_contact_city_update" in str(exc.value) and "both" in str(exc.value)


@pytest.mark.parametrize("key", ["recipes", "missing"])
def test_load_monarch_recipes_task_outside_the_task_set(tmp_path, key):
    text = RECIPES.replace("simple.email_sf_contact_city_update" if key == "recipes"
                           else "simple.sf_opp_closed_won", "simple.not_a_task")
    with pytest.raises(ConfigError) as exc:
        load_recipes(tmp_path, text)
    assert exc.value.field == f"{key}.simple.not_a_task" and "not a task" in str(exc.value)


def test_load_monarch_recipes_product_mismatch(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_recipes(tmp_path, product="other-product")
    assert exc.value.field == "product" and "other-product" in str(exc.value)


def test_load_monarch_recipes_task_set_mismatch(tmp_path):
    with pytest.raises(ConfigError) as exc:
        config.load_monarch_recipes(recipes_file(tmp_path), "simulated-apps", RECIPE_TASKS,
                                    tasks_name="corpus")
    assert exc.value.field == "tasks" and "corpus" in str(exc.value)


def test_load_monarch_recipes_bad_reason(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_recipes(tmp_path, RECIPES.replace("reason: checker_failed", "reason: gave_up"))
    assert exc.value.field == "missing.simple.sf_opp_closed_won.reason" and "gave_up" in str(exc.value)


def test_load_harness_accepts_run_only_among_the_modes(tmp_path):
    h = config.load_harness(write(tmp_path, edit(HARNESS_MONARCH, "modes",
                                                 "[create-run, run-only]")))
    assert h.modes == ["create-run", "run-only"]


def test_tier_plans():
    """Feature 005: the four difficulty plans differ only in the task set."""
    site = Path(__file__).resolve().parents[1]
    plans = {n: config.load_plan(site / "config/plans" / f"{n}.yaml")
             for n in ("tier-simple", "tier-medium", "tier-complex", "random-10")}

    for name, pl in plans.items():
        assert pl.name == name and pl.tasks == f"tasks/{name}"        # each names its own task set
        assert pl.mode == "create-run"
        assert pl.repetitions == 1 and pl.retry_on_fail == 1
        assert pl.baseline == "claude-opus-5/api"
        assert pl.audience == "internal"
        assert pl.approved_by is None                      # Carlos approves each round
        assert pl.timeout_s == 1800 and pl.concurrency == 4
        assert pl.cost_ceiling_usd == 60
        # the size in the agreed words, never a bare per-competitor total
        assert ("prompts: 10; attempts per prompt: 1 plus 1 retry on failure; "
                "attempts per competitor: 10 to 20; competitors: 7; attempts in "
                "the round: 70 to 140") in " ".join(pl.description.lower().split())

    # all four carry the same seven competitors, in the same order
    shapes = {n: [(c.model, c.harness) for c in pl.competitors] for n, pl in plans.items()}
    assert len(set(map(tuple, shapes.values()))) == 1
    assert len(next(iter(shapes.values()))) == 7

    # and they are the pilot's seven, so the four rounds and the pilot can be
    # read side by side (contracts/config-files.md)
    pilot = config.load_plan(site / "config/plans/pilot-monarch-create-run.yaml")
    assert [(c.model, c.harness) for c in pilot.competitors] == next(iter(shapes.values()))
    assert pilot.mode == "create-run" and pilot.baseline == "claude-opus-5/api"


def test_monarch_kb_keys_are_hyphenated_product_slugs(tmp_path):
    """The discovery service slugifies `[^a-z0-9]+`; underscores made two products."""
    import yaml
    from wb_world.seeds import product_slug
    product = config.load_product(config.DEFAULT_CONFIG_DIR / "products" / "simulated-apps.yaml")
    kb = {product_slug(s): f"{i:064x}" for i, s in enumerate(product.services)}
    path = tmp_path / "simulated-apps.monarch-kb.yaml"

    def write(mapping):
        path.write_text(yaml.safe_dump(
            {"product": "simulated-apps", "generated_at": "2026-09-04T00:00:00Z",
             "seeds_format": "public-api-seeds@1",
             "shim_public_url": "http://host.docker.internal:9105",
             "kb": mapping}), encoding="utf-8")
        return path

    assert config.load_monarch_kb(write(kb), product).kb == kb
    assert "bench-google-ads" in kb and not any("_" in k for k in kb)
    # the old underscored spelling is refused rather than silently accepted
    underscored = {("bench-" + s): h for s, h in zip(product.services, kb.values())}
    with pytest.raises(ConfigError) as exc:
        config.load_monarch_kb(write(underscored), product)
    assert "no entry" in str(exc.value) and "-" in exc.value.field


def test_builder_experiment_is_allowlisted_and_only_explicit_selection_changes_hash(tmp_path):
    original = config.load_harness(write(tmp_path, HARNESS_MONARCH))
    assert original.builder_experiment is None
    assert 'builder_experiment' not in config._hashed_harness(original)
    selected = config.load_harness(write(tmp_path, HARNESS_MONARCH + '\nbuilder_experiment: sections-parallel\n'))
    assert config._hashed_harness(selected)['builder_experiment'] == 'sections-parallel'
    check_error(config.load_harness, write(tmp_path, HARNESS_MONARCH + '\nbuilder_experiment: typo\n'), 'builder_experiment')
