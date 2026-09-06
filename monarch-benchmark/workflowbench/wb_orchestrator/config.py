"""Load and validate the four config kinds: products, models, harnesses, plans.

Loaders do single-file checks (data-model.md validation rules 1-2);
`resolve` joins a product and a plan into a `RunConfig` and applies the
cross-file rules 3-10. Every error names the file and the field.
Environment variables are referenced by name only; values are never stored.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from wb_world.episode import contract_hash, load_suite
from wb_world.seeds import product_slug

PRODUCT_KINDS = ("simulated", "real-api-ui", "real-api")
MODES = ("full-flow", "create-run", "run-only")
AUTHORING_MODES = ("interactive", "unattended")   # how Monarch is asked to build (002)
PROVIDERS = ("anthropic", "openai", "google", "zai", "moonshot", "fireworks")
EFFORTS = ("xhigh", "high", "medium", "low", "none")
ADAPTERS = ("openai", "openai_responses", "gemini", "anthropic")
HARNESS_KINDS = ("api", "cli", "scripted", "monarch")
LAUNCHERS = ("claude-code", "codex", "gemini-cli", "opencode")
SCRIPTS = ("oracle", "sloppy", "null")
MISSING_REASONS = ("checker_failed", "authoring_error", "run_error", "timeout", "infra")
SMOKE_SCALE_ATTEMPTS = 20  # attempts per competitor a plan may run without approved_by (rule 9)
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SideEffects = list[tuple[str, str | None, list[dict]]]


class ConfigError(Exception):
    def __init__(self, path, field, why):
        self.path, self.field, self.why = str(path), field, why
        super().__init__(f"config error in {path}: {field}: {why}")


@dataclass
class ProductData:
    dataset: str
    mutable: bool


@dataclass
class Product:
    name: str
    kind: str
    data: ProductData
    services: list[str]
    side_effects: str
    modes: list[str]
    description: str | None = None


@dataclass
class Prices:
    input: float
    cached: float
    output: float
    cache_write: float


@dataclass
class Model:
    name: str
    provider: str
    model: str
    effort: str
    usd_per_million: Prices
    key_env: str
    adapter: str | None = None
    base_url: str | None = None
    cache_min_prompt_tokens: int = 0
    header_fallbacks: list[str] = field(default_factory=list)
    prices_verified: datetime.date | None = None
    description: str | None = None


@dataclass
class PriceEntry:
    family: str
    match: list[str]
    usd_per_million: Prices


@dataclass
class PriceTable:
    """Prices for models a competitor calls through someone else's account (e.g. Monarch on Bedrock)."""
    name: str
    provider: str
    region: str
    prices_verified: datetime.date
    models: list[PriceEntry]
    description: str | None = None


@dataclass
class Harness:
    name: str
    kind: str
    accepts: list[str] | str  # list of providers, or the string "none"
    runnable: bool = True
    description: str | None = None
    # kind = cli
    launcher: str | None = None
    command: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    output: str | None = None
    # kind = scripted
    script: str | None = None
    # kind = monarch
    base_url: str | None = None
    credential_env: str | None = None
    login_email: str | None = None
    login_password_env: str | None = None
    fd_url: str | None = None
    fd_api_key_env: str | None = None   # set when the discovery service gates /v1/*
    shim_port: int | None = None
    shim_public_host: str = "host.docker.internal"
    shim_public_url: str | None = None   # full URL when the front door is behind a tunnel (overrides host:port)
    langfuse_url: str | None = None
    langfuse_public_key_env: str | None = None
    langfuse_secret_key_env: str | None = None
    price_table: str | None = None
    monarch_repo: str | None = None
    modes: list[str] = field(default_factory=list)
    authoring_mode: str = "interactive"   # "unattended": the builder does not stop to ask


@dataclass(frozen=True)
class CompetitorSpec:
    model: str | None
    harness: str


@dataclass
class Plan:
    name: str
    tasks: str
    mode: str
    repetitions: int
    timeout_s: float
    concurrency: int
    competitors: list[CompetitorSpec]
    baseline: str
    audience: str
    cost_ceiling_usd: float
    approved_by: str | None
    description: str | None = None
    retry_on_fail: int = 0   # extra attempts a failed prompt gets, on top of `repetitions`


# ---------------------------------------------------------------- checks

class _Checker:
    """Validates one mapping; `prefix` names nested fields like `data.mutable`."""

    def __init__(self, path, data, prefix=""):
        self.path, self.data, self.prefix = path, data, prefix

    def fail(self, key, why):
        raise ConfigError(self.path, f"{self.prefix}{key}", why)

    def keys(self, required, optional=()):
        for k in self.data:
            if k not in required and k not in optional:
                self.fail(k, f"unknown key; allowed: {', '.join([*required, *optional])}")
        for k in required:
            if k not in self.data:
                self.fail(k, "required key missing")

    def require(self, key, types, **kw):
        if key not in self.data:
            self.fail(key, "required key missing")
        return self.get(key, types, **kw)

    def get(self, key, types, default=None, enum=None, minimum=None, strict=False):
        """Typed lookup. `types` is a type or tuple; bool never passes as int."""
        if key not in self.data:
            return default
        v = self.data[key]
        if isinstance(v, bool) and bool not in (types if isinstance(types, tuple) else (types,)):
            self.fail(key, f"expected {_tname(types)}, got bool")
        if not isinstance(v, types):
            self.fail(key, f"expected {_tname(types)}, got {type(v).__name__}")
        if enum and v not in enum:
            self.fail(key, f"must be one of {', '.join(enum)}; got {v!r}")
        if minimum is not None and (v < minimum if not strict else v <= minimum):
            self.fail(key, f"must be {'>' if strict else '>='} {minimum}; got {v}")
        return v

    def str_list(self, key, enum=None, default=None):
        if key not in self.data:
            return default
        v = self.get(key, list)
        for i, item in enumerate(v):
            if not isinstance(item, str):
                self.fail(f"{key}[{i}]", f"expected str, got {type(item).__name__}")
            if enum and item not in enum:
                self.fail(f"{key}[{i}]", f"must be one of {', '.join(enum)}; got {item!r}")
        return v

    def sub(self, key):
        return _Checker(self.path, self.get(key, dict), f"{self.prefix}{key}.")


def _tname(types):
    return "/".join(t.__name__ for t in (types if isinstance(types, tuple) else (types,)))


def _read(path, kind, name_key: str | None = "name"):
    """Parse a mapping file into a _Checker; `name_key=None` skips the name-equals-stem rule."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(path, "<root>", f"cannot read {kind}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(path, "<root>", f"{kind} file must be a mapping")
    c = _Checker(path, data)
    if name_key:
        name = c.require(name_key, str)
        if name != path.stem:
            c.fail(name_key, f"must equal the file stem {path.stem!r}; got {name!r}")
    return c


# ---------------------------------------------------------------- loaders

def load_product(path) -> Product:
    c = _read(path, "product")
    c.keys(("name", "kind", "data", "services", "side_effects", "modes"), ("description",))
    d = c.sub("data")
    d.keys(("dataset", "mutable"))
    return Product(
        name=c.data["name"],
        kind=c.get("kind", str, enum=PRODUCT_KINDS),
        data=ProductData(dataset=d.get("dataset", str), mutable=d.get("mutable", bool)),
        services=c.str_list("services"),
        side_effects=c.get("side_effects", str),
        modes=c.str_list("modes", enum=MODES),
        description=c.get("description", str),
    )


def load_side_effects(path: str | Path) -> SideEffects:
    """Read a side-effect file (research.md R7; data-model.md Side effects) into (service, when, matchers) tuples."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(path, "<root>", f"cannot read side effects: {e}") from e
    if not isinstance(data, list):
        raise ConfigError(path, "<root>", "side-effects file must be a list")
    out: SideEffects = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ConfigError(path, f"[{i}]", "expected a mapping {service, when?, allowed}")
        c = _Checker(path, entry, f"[{i}].")
        c.keys(("service", "allowed"), ("when",))
        service, cond = c.get("service", str), c.get("when", str)
        matchers = []
        for j, m in enumerate(c.get("allowed", list)):
            if not isinstance(m, dict):
                c.fail(f"allowed[{j}]", "expected a mapping {service, op, path}")
            mc = _Checker(path, m, f"[{i}].allowed[{j}].")
            mc.keys(("service", "op", "path"))
            matchers.append({k: mc.get(k, str) for k in ("service", "op", "path")})
        out.append((service, cond, matchers))
    return out


def _date(c, key) -> datetime.date | None:
    v = c.get(key, (datetime.date, str))
    if isinstance(v, str):
        try:
            return datetime.date.fromisoformat(v)
        except ValueError:
            c.fail(key, f"expected a date (YYYY-MM-DD); got {v!r}")
    return v


def _prices(c, key="usd_per_million", cache_write_required=False) -> Prices:
    """The four per-million prices; `cache_write` defaults to `input` unless required.

    float() so `5` and `5.00` are the same price (and the same hash).
    """
    p = c.sub(key)
    p.keys(("input", "cached", "output", *(("cache_write",) if cache_write_required else ())),
           () if cache_write_required else ("cache_write",))
    num = (int, float)
    return Prices(input=float(p.get("input", num)), cached=float(p.get("cached", num)),
                  output=float(p.get("output", num)),
                  cache_write=float(p.get("cache_write", num, default=p.get("input", num))))


def load_model(path) -> Model:
    c = _read(path, "model")
    if c.data.get("kind") == "price-table":
        c.fail("kind", "this is a price-table file, not a model; see load_price_table")
    c.keys(("name", "provider", "model", "effort", "usd_per_million", "key_env"),
           ("adapter", "base_url", "cache_min_prompt_tokens", "header_fallbacks",
            "prices_verified", "description"))
    prices = _prices(c)
    verified = _date(c, "prices_verified")
    return Model(
        name=c.data["name"],
        provider=c.get("provider", str, enum=PROVIDERS),
        model=c.get("model", str),
        effort=c.get("effort", str, enum=EFFORTS),
        usd_per_million=prices,
        key_env=c.get("key_env", str),
        adapter=c.get("adapter", str, enum=ADAPTERS),
        base_url=c.get("base_url", str),
        cache_min_prompt_tokens=c.get("cache_min_prompt_tokens", int, default=0, minimum=0),
        header_fallbacks=c.str_list("header_fallbacks", default=[]),
        prices_verified=verified,
        description=c.get("description", str),
    )


_HARNESS_KEYS = {
    "api": ((), ()),
    "cli": (("launcher", "command"), ("env", "output")),
    "scripted": (("script",), ()),
    "monarch": (("base_url", "credential_env", "login_email", "login_password_env", "fd_url",
                 "shim_port", "langfuse_url", "langfuse_public_key_env", "langfuse_secret_key_env",
                 "price_table", "monarch_repo", "modes"),
                ("shim_public_host", "shim_public_url", "fd_api_key_env", "authoring_mode")),
}


def is_price_table(path) -> bool:
    """True for a `kind: price-table` file; they share the models/ folder but are not competitors."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and data.get("kind") == "price-table"


def load_price_table(path) -> PriceTable:
    """Prices for a competitor that bills through its own account (data-model.md: price table)."""
    c = _read(path, "price table")
    c.keys(("name", "kind", "provider", "region", "prices_verified", "models"), ("description",))
    c.get("kind", str, enum=("price-table",))
    entries, seen = [], set()
    for i, item in enumerate(c.get("models", list)):
        if not isinstance(item, dict):
            c.fail(f"models[{i}]", "expected a mapping {family, match, usd_per_million}")
        e = _Checker(c.path, item, f"models[{i}].")
        e.keys(("family", "match", "usd_per_million"))
        family = e.get("family", str)
        if family in seen:
            e.fail("family", f"duplicate family {family!r}")
        seen.add(family)
        match = e.str_list("match")
        if not match:
            e.fail("match", "must list at least one model-id fragment")
        entries.append(PriceEntry(family=family, match=match,
                                  usd_per_million=_prices(e, cache_write_required=True)))
    return PriceTable(
        name=c.data["name"],
        provider=c.get("provider", str),
        region=c.get("region", str),
        prices_verified=_date(c, "prices_verified"),
        models=entries,
        description=c.get("description", str),
    )


def load_harness(path) -> Harness:
    c = _read(path, "harness")
    kind = c.require("kind", str, enum=HARNESS_KINDS)
    req, opt = _HARNESS_KEYS[kind]
    c.keys(("name", "kind", "accepts", *req), ("runnable", "description", *opt))
    accepts = c.data["accepts"]
    if accepts != "none":
        accepts = c.str_list("accepts", enum=PROVIDERS) if isinstance(accepts, list) else \
            c.fail("accepts", f"expected a list of providers or 'none'; got {accepts!r}")
    port = c.get("shim_port", int)
    if port is not None and not 1024 <= port <= 65535:
        c.fail("shim_port", f"must be between 1024 and 65535; got {port}")
    env = c.get("env", dict, default={})
    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            c.fail(f"env.{k}", "env keys and values must be strings")
    return Harness(
        name=c.data["name"],
        kind=kind,
        accepts=accepts,
        runnable=c.get("runnable", bool, default=True),
        description=c.get("description", str),
        launcher=c.get("launcher", str, enum=LAUNCHERS),
        command=c.get("command", str),
        env=env,
        output=c.get("output", str),
        script=c.get("script", str, enum=SCRIPTS),
        base_url=c.get("base_url", str),
        credential_env=c.get("credential_env", str),
        login_email=c.get("login_email", str),
        login_password_env=c.get("login_password_env", str),
        fd_url=c.get("fd_url", str),
        fd_api_key_env=c.get("fd_api_key_env", str),
        shim_port=port,
        shim_public_host=c.get("shim_public_host", str, default=Harness.shim_public_host),
        shim_public_url=c.get("shim_public_url", str),
        langfuse_url=c.get("langfuse_url", str),
        langfuse_public_key_env=c.get("langfuse_public_key_env", str),
        langfuse_secret_key_env=c.get("langfuse_secret_key_env", str),
        price_table=c.get("price_table", str),
        monarch_repo=c.get("monarch_repo", str),
        modes=c.str_list("modes", enum=MODES, default=[]),
        authoring_mode=c.get("authoring_mode", str, default=Harness.authoring_mode,
                             enum=AUTHORING_MODES),
    )


def load_plan(path) -> Plan:
    c = _read(path, "plan")
    c.keys(("name", "tasks", "mode", "repetitions", "timeout_s", "concurrency", "competitors",
            "baseline", "audience", "cost_ceiling_usd", "approved_by"),
           ("description", "retry_on_fail"))
    competitors = []
    for i, item in enumerate(c.get("competitors", list)):
        if not isinstance(item, dict):
            c.fail(f"competitors[{i}]", "expected a mapping {model, harness}")
        s = _Checker(c.path, item, f"competitors[{i}].")
        s.keys(("harness",), ("model",))
        competitors.append(CompetitorSpec(model=s.get("model", str), harness=s.get("harness", str)))
    approved = c.data["approved_by"]
    if approved is not None and not isinstance(approved, str):
        c.fail("approved_by", f"expected str or null; got {type(approved).__name__}")
    num = (int, float)
    return Plan(
        name=c.data["name"],
        tasks=c.get("tasks", str),
        mode=c.get("mode", str, enum=MODES),
        repetitions=c.get("repetitions", int, minimum=1),
        timeout_s=float(c.get("timeout_s", num, minimum=0, strict=True)),
        concurrency=c.get("concurrency", int, minimum=1),
        competitors=competitors,
        baseline=c.get("baseline", str),
        audience=c.get("audience", str),
        cost_ceiling_usd=c.get("cost_ceiling_usd", num, minimum=0, strict=True),
        approved_by=approved,
        description=c.get("description", str),
        retry_on_fail=c.get("retry_on_fail", int, minimum=0, default=0),
    )


# ---------------------------------------------------------------- resolve

@dataclass
class MonarchKb:
    """What Monarch was taught about the product, by `wb monarch setup` (contracts/config-files.md)."""
    product: str
    generated_at: str
    seeds_format: str
    shim_public_url: str
    kb: dict[str, str]  # product_slug(service) -> knowledge-base hash


def load_monarch_kb(path, product: Product) -> MonarchKb:
    """The knowledge-base hashes `wb monarch setup` wrote for one product."""
    c = _read(path, "knowledge-base file", name_key=None)
    c.keys(("product", "generated_at", "seeds_format", "shim_public_url", "kb"))
    if c.get("product", str) != product.name:
        c.fail("product", f"must equal the product under test {product.name!r}; got {c.data['product']!r}")
    kb = c.get("kb", dict)
    for k, v in kb.items():
        if not isinstance(k, str) or not isinstance(v, str):
            c.fail("kb", "keys and hashes must be strings")
    want = {product_slug(s) for s in product.services}
    for slug in sorted(want - set(kb)):
        c.fail(f"kb.{slug}", "no entry; run `wb monarch setup` again")
    for slug in sorted(set(kb) - want):
        c.fail(f"kb.{slug}", f"not a service of {product.name}")
    return MonarchKb(product=c.data["product"],
                     generated_at=str(c.require("generated_at", (str, datetime.datetime))),
                     seeds_format=c.get("seeds_format", str),
                     shim_public_url=c.get("shim_public_url", str), kb=kb)


@dataclass
class RecipeRow:
    """One known-correct workflow Monarch authored and the bench's checker passed."""
    workflow_id: str
    recipe_version: int
    authored_at: str
    attempts_used: int


@dataclass
class MissingRow:
    """One task `wb monarch recipes` could not get a passing workflow for."""
    reason: str
    attempts_used: int
    detail: str


@dataclass
class MonarchRecipes:
    """The frozen recipes `wb monarch recipes` wrote for one product (data-model.md §1)."""
    product: str
    tasks: str
    generated_at: str
    kb_hash_file_sha: str
    monarch: str
    recipes: dict[str, RecipeRow]
    missing: dict[str, MissingRow]


def load_monarch_recipes(path, product: str, tasks, tasks_name: str | None = None) -> MonarchRecipes:
    """The recipes file for one product; `tasks` is the task ids the plan resolved to."""
    c = _read(path, "recipes file", name_key=None)
    c.keys(("product", "tasks", "generated_at", "kb_hash_file_sha", "monarch", "recipes", "missing"))
    if c.get("product", str) != product:
        c.fail("product", f"must equal the product under test {product!r}; got {c.data['product']!r}")
    written_for = c.get("tasks", str)
    if tasks_name is not None and written_for != tasks_name:
        c.fail("tasks", f"made for task set {written_for!r}, but the plan runs {tasks_name!r}; "
                        "run `wb monarch recipes` for this task set")
    known_tasks = set(tasks)
    recipes, missing = {}, {}
    for key, kind in (("recipes", RecipeRow), ("missing", MissingRow)):
        for task, row in (c.get(key, dict) or {}).items():
            if task not in known_tasks:
                c.fail(f"{key}.{task}", f"not a task of {written_for}")
            if not isinstance(row, dict):
                c.fail(f"{key}.{task}", f"expected a mapping, got {type(row).__name__}")
            r = _Checker(path, row, f"{key}.{task}.")
            if kind is RecipeRow:
                r.keys(("workflow_id", "recipe_version", "authored_at", "attempts_used"))
                recipes[task] = RecipeRow(
                    workflow_id=r.get("workflow_id", str),
                    recipe_version=r.get("recipe_version", int),
                    authored_at=str(r.require("authored_at", (str, datetime.datetime))),
                    attempts_used=r.get("attempts_used", int, minimum=1))
            else:
                r.keys(("reason", "attempts_used", "detail"))
                missing[task] = MissingRow(
                    reason=r.get("reason", str, enum=MISSING_REASONS),
                    # minimum 0: an infrastructure failure consumes no attempt
                    attempts_used=r.get("attempts_used", int, minimum=0),
                    detail=r.get("detail", str))
    for task in sorted(set(recipes) & set(missing)):
        c.fail("recipes", f"task {task} is in both recipes and missing; it must be in one only")
    return MonarchRecipes(product=c.data["product"], tasks=written_for,
                          generated_at=str(c.require("generated_at", (str, datetime.datetime))),
                          kb_hash_file_sha=c.get("kb_hash_file_sha", str),
                          monarch=c.get("monarch", str), recipes=recipes, missing=missing)


@dataclass
class Competitor:
    name: str  # "model/harness", or the harness name alone
    model: Model | None
    harness: Harness


_PRE_002_MONARCH_KEYS = ("base_url", "credential_env", "modes")  # also on the pre-002 Harness
_MONARCH_ONLY = tuple(k for k in sum(_HARNESS_KEYS["monarch"], ()) if k not in _PRE_002_MONARCH_KEYS)


def _hashed_harness(h: Harness) -> dict:
    """Keep the pre-002 shape for non-Monarch harnesses so their run hashes stay regradable.

    Every Monarch-only field is dropped here, so adding one to `_HARNESS_KEYS["monarch"]`
    never moves the hash of a plan without Monarch.

    ponytail: the dropped `release` is spelled back in as null rather than rehashing every
    stored run; drop that line the next time the hash is allowed to move.
    """
    d = asdict(h)
    if h.kind != "monarch":
        for k in _MONARCH_ONLY:
            del d[k]
        d["release"] = None
    elif d["authoring_mode"] == Harness.authoring_mode:
        # ponytail: the default is dropped so runs frozen before this key stay
        # regradable; only asking for the unattended builder moves the hash.
        del d["authoring_mode"]
    return d


@dataclass
class RunConfig:
    product: Product
    plan: Plan
    competitors: list[Competitor]
    tasks: list[dict]
    product_path: str
    plan_path: str
    models: dict[str, Model]
    harnesses: dict[str, Harness]
    tasks_dir: str  # absolute; `plan.tasks` as written stays in the hash
    monarch_kb: MonarchKb | None = None      # only when a Monarch competitor runs
    monarch_recipes: MonarchRecipes | None = None   # only in run-only, with a Monarch competitor
    excluded_tasks: dict[str, str] = field(default_factory=dict)  # task id -> why it was dropped
    price_tables: dict[str, PriceTable] = field(default_factory=dict)
    config_dir: str = ""                     # where models/ and harnesses/ were read from

    @property
    def attempts_per_competitor(self) -> int:
        """The most attempts one competitor can make: every prompt failing every
        planned repetition and spending every retry. Retries only happen on
        failures, so the floor is `len(tasks) x repetitions`; the ceiling counts
        this number, because it counts every attempt that could be paid for."""
        return len(self.tasks) * (self.plan.repetitions + self.plan.retry_on_fail)

    @property
    def attempts_per_competitor_min(self) -> int:
        """With no failure, nothing is retried."""
        return len(self.tasks) * self.plan.repetitions

    @property
    def attempts_total(self) -> int:
        return self.attempts_per_competitor * len(self.competitors)

    def _hashed(self) -> dict:
        """Everything the hash covers (research.md R2): guard fields out, secrets by name."""
        plan = asdict(self.plan)
        del plan["cost_ceiling_usd"], plan["approved_by"]
        if not plan["retry_on_fail"]:
            # A plan that asks for no retry is the plan it was before the key
            # existed, and keeps the hash its stored runs were recorded under.
            del plan["retry_on_fail"]
        d = {"tasks": sorted(contract_hash(t) for t in self.tasks),
             "product": asdict(self.product), "plan": plan,
             "models": {k: asdict(v) for k, v in self.models.items()},
             "harnesses": {k: _hashed_harness(v) for k, v in self.harnesses.items()}}
        if self.monarch_kb:  # absent for plans without Monarch, so their hashes do not move
            d["monarch_kb"] = {"kb": self.monarch_kb.kb,  # generated_at is not an input
                               "seeds_format": self.monarch_kb.seeds_format,
                               "shim_public_url": self.monarch_kb.shim_public_url}
        if self.monarch_recipes:  # absent otherwise, so those plans' hashes do not move
            r = self.monarch_recipes
            d["monarch_recipes"] = {  # generated_at and a missing row's detail are not inputs
                "product": r.product, "tasks": r.tasks,
                "kb_hash_file_sha": r.kb_hash_file_sha,
                "recipes": {k: asdict(v) for k, v in r.recipes.items()},
                "missing": sorted(r.missing)}
        if self.price_tables:
            d["price_tables"] = {k: asdict(v) for k, v in self.price_tables.items()}
        return json.loads(json.dumps(d, default=str))  # dates -> ISO strings

    @property
    def hash(self) -> str:
        blob = json.dumps(self._hashed(), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    @property
    def config_json(self) -> dict:
        return {**self._hashed(), "product_path": self.product_path, "plan_path": self.plan_path,
                "tasks_dir": self.plan.tasks, "n_tasks": len(self.tasks), "mode": self.plan.mode,
                "excluded_tasks": self.excluded_tasks,  # not hashed; the report's source line
                "attempts_total": self.attempts_total,
                "cost_ceiling_usd": self.plan.cost_ceiling_usd,  # not hashed; wb status reads it
                "suite_dir": self.tasks_dir,  # ponytail: old readers (wb grade) key on suite_dir
                "k": self.plan.repetitions}  # ponytail: old readers (wb report) key on k


def from_workflowbench(p, config_dir=DEFAULT_CONFIG_DIR) -> Path:
    """Absolute stays; relative is rooted at the folder above `config_dir` (the workflowbench dir)."""
    p = Path(p)
    return p if p.is_absolute() else Path(config_dir).parent / p


def known(folder) -> str:
    """Names of the config files in `folder`, comma-joined (messages and the picker)."""
    return ", ".join(sorted(p.stem for p in Path(folder).glob("*.yaml")))


_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


def _check_monarch_env(h, hpath, env) -> None:
    """Every address and key the Monarch competitor needs, before a cent is spent.

    An address is only checked when it is written as a `${VAR}` placeholder; a
    literal one needs nothing from the environment. Checked here rather than at
    first use so a missing variable stops the run at `wb run`, not halfway
    through it (FR-029).
    """
    for field in ("base_url", "fd_url", "langfuse_url"):
        for name in _PLACEHOLDER.findall(getattr(h, field) or ""):
            if not env.get(name):
                raise ConfigError(hpath, field, f"environment variable {name} is not set")
    for field in ("langfuse_public_key_env", "langfuse_secret_key_env"):
        name = getattr(h, field)
        if name and not env.get(name):
            raise ConfigError(hpath, field, f"environment variable {name} is not set")


def resolve(product_path, plan_path, config_dir=None, env=None, audiences=None) -> RunConfig:
    """Join a product and a plan; apply validation rules 3-10 (data-model.md).

    Models and harnesses are read from `config_dir` (default: the folder above
    the product file). `env` is only asked whether a name is set. A relative `plan.tasks` is
    taken from the folder above `config_dir`; the hash keeps the string as written.
    """
    product_path, plan_path = Path(product_path), Path(plan_path)
    config_dir = Path(config_dir) if config_dir else product_path.parent.parent
    env = os.environ if env is None else env
    if audiences is None:
        from wb_report.report import load_audiences
        audiences = load_audiences()
    product, plan = load_product(product_path), load_plan(plan_path)
    c = _Checker(plan_path, {})

    if plan.mode not in product.modes:
        c.fail("mode", f"{plan.mode!r} is not in the modes of {product_path}: {', '.join(product.modes)}")
    if plan.audience not in audiences:
        c.fail("audience", f"unknown audience {plan.audience!r}; known: {', '.join(audiences)}")

    models, harnesses, competitors = {}, {}, []
    for i, spec in enumerate(plan.competitors):
        name = f"{spec.model}/{spec.harness}" if spec.model else spec.harness
        if any(x.name == name for x in competitors):
            c.fail(f"competitors[{i}]", f"duplicate competitor {name!r}")
        hpath = config_dir / "harnesses" / f"{spec.harness}.yaml"
        if not hpath.exists():
            c.fail(f"competitors[{i}].harness",
                   f"unknown harness {spec.harness!r}; known: {known(hpath.parent)}")
        h = harnesses.get(spec.harness) or load_harness(hpath)
        model = None
        if spec.model is None:
            if h.accepts != "none":
                c.fail(f"competitors[{i}].model", f"harness {h.name!r} needs a model (accepts {', '.join(h.accepts)})")
        else:
            mpath = config_dir / "models" / f"{spec.model}.yaml"
            if not mpath.exists():
                c.fail(f"competitors[{i}].model", f"unknown model {spec.model!r}; known: {known(mpath.parent)}")
            model = models.get(spec.model) or load_model(mpath)
            if h.accepts == "none":
                c.fail(f"competitors[{i}].model", f"harness {h.name!r} takes no model")
            if model.provider not in h.accepts:
                c.fail(f"competitors[{i}].model", f"harness {h.name!r} accepts {', '.join(h.accepts)}; "
                       f"model {model.name!r} is from {model.provider!r}")
            if not env.get(model.key_env):
                raise ConfigError(mpath, "key_env", f"environment variable {model.key_env} is not set")
        if not h.runnable:
            c.fail(f"competitors[{i}].harness", f"harness {h.name!r} is not runnable yet")
        if h.kind == "monarch" and plan.mode not in h.modes:
            c.fail(f"competitors[{i}].harness",
                   f"mode {plan.mode!r} is not in the modes of {hpath}: {', '.join(h.modes)}")
        has_token = bool(h.credential_env and env.get(h.credential_env))
        has_password = bool(h.login_password_env and env.get(h.login_password_env))
        if h.credential_env and not has_token and not has_password:
            names = h.credential_env + (f" or {h.login_password_env}" if h.login_password_env else "")
            raise ConfigError(hpath, "credential_env", f"environment variable {names} is not set")
        if h.kind == "monarch":
            _check_monarch_env(h, hpath, env)
        competitors.append(Competitor(name, model, h))
        harnesses[h.name] = h
        if model:
            models[model.name] = model

    monarch_kb, monarch_recipes, price_tables = None, None, {}
    for h in harnesses.values():
        if h.kind != "monarch":
            continue
        if monarch_kb is None:
            kb_path = config_dir / "products" / f"{product.name}.monarch-kb.yaml"
            if not kb_path.exists():
                raise ConfigError(kb_path, "kb", "file is missing; run `wb monarch setup` first")
            monarch_kb = load_monarch_kb(kb_path, product)
        tpath = config_dir / "models" / f"{h.price_table}.yaml"
        if not tpath.exists():
            raise ConfigError(config_dir / "harnesses" / f"{h.name}.yaml", "price_table",
                              f"unknown price table {h.price_table!r}; known: {known(tpath.parent)}")
        price_tables[h.price_table] = load_price_table(tpath)

    names = [x.name for x in competitors]
    if plan.baseline not in names:
        c.fail("baseline", f"{plan.baseline!r} is not a competitor; have: {', '.join(names)}")

    tasks_dir = from_workflowbench(plan.tasks, config_dir)  # whatever the cwd
    try:
        tasks = load_suite(tasks_dir)
    except (OSError, ValueError) as e:
        c.fail("tasks", str(e))
    for t in tasks:
        for service in t["info"]["initial_state"]:
            if service == "meta":            # the world's own header, not a service
                continue
            if service not in product.services:
                raise ConfigError(product_path, "services",
                                  f"task {t['task']} touches service {service}, which {product_path} "
                                  f"does not list in services")

    excluded_tasks = {}
    if monarch_kb is not None and plan.mode == "run-only":
        rpath = config_dir / "products" / f"{product.name}.monarch-recipes.yaml"
        if not rpath.exists():
            raise ConfigError(rpath, "recipes",
                              "file is missing; run `wb monarch recipes` first")
        monarch_recipes = load_monarch_recipes(rpath, product.name,
                                               [t["task"] for t in tasks], plan.tasks)
        # ponytail: exclusion at the top -- per-competitor filtering is what rule 7
        # forbids, not an optimisation left undone (research R6). A task in neither
        # map was simply never attempted, and is excluded on the same footing.
        excluded_tasks = {t["task"]: (r.reason if (r := monarch_recipes.missing.get(t["task"]))
                                      else "not_attempted")
                          for t in tasks if t["task"] not in monarch_recipes.recipes}
        tasks = [t for t in tasks if t["task"] not in excluded_tasks]
        if not tasks:
            raise ConfigError(rpath, "recipes",
                              "every task of the set is missing a known-correct recipe, so there "
                              "is nothing to compare; run `wb monarch recipes` first")

    # The gate counts the most a competitor can attempt, retries included: the
    # approval is for what the round could cost, not for its best case.
    per_competitor = len(tasks) * (plan.repetitions + plan.retry_on_fail)
    if per_competitor > SMOKE_SCALE_ATTEMPTS and not plan.approved_by:
        c.fail("approved_by", f"{per_competitor} attempts per competitor exceed smoke scale "
                              f"({SMOKE_SCALE_ATTEMPTS}); set approved_by")

    return RunConfig(product=product, plan=plan, competitors=competitors, tasks=tasks,
                     product_path=str(product_path), plan_path=str(plan_path),
                     models=models, harnesses=harnesses, tasks_dir=str(tasks_dir),
                     monarch_kb=monarch_kb, monarch_recipes=monarch_recipes,
                     excluded_tasks=excluded_tasks, price_tables=price_tables,
                     config_dir=str(config_dir))


def resolve_name_or_path(value, kind, config_dir=DEFAULT_CONFIG_DIR) -> Path:
    """`smoke-frontier` -> config/plans/smoke-frontier.yaml; a path is used as given."""
    p = Path(value)
    if p.is_file():
        return p
    folder = Path(config_dir) / ("harnesses" if kind == "harness" else f"{kind}s")
    if not (folder / f"{value}.yaml").is_file():
        raise ConfigError(folder, f"--{kind}", f"unknown {kind} {value!r}; available: {known(folder)}")
    return folder / f"{value}.yaml"


def pick(kind, folder, stdin=None, stdout=None) -> Path:
    """Numbered picker for a missing --product/--plan (research.md R8)."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    names = [p.stem for p in sorted(Path(folder).glob("*.yaml"))]
    if not names:
        raise ConfigError(folder, f"--{kind}", f"no {kind} files in {folder}")
    if not stdin.isatty():
        raise ConfigError(folder, f"--{kind}", f"--{kind} is required without a terminal; available: {known(folder)}")
    print(f"{kind.capitalize()}s:", file=stdout)
    for i, name in enumerate(names, 1):
        print(f"  {i}) {name}", file=stdout)
    while True:
        print(f"Pick a {kind} [1-{len(names)}]: ", end="", file=stdout, flush=True)
        raw = stdin.readline()
        if not raw:  # EOF
            raise ConfigError(folder, f"--{kind}", f"no {kind} chosen; available: {known(folder)}")
        answer = raw.strip()
        if answer in names:
            return Path(folder) / f"{answer}.yaml"
        if answer.isdigit() and 1 <= int(answer) <= len(names):
            return Path(folder) / f"{names[int(answer) - 1]}.yaml"
        print(f"not a choice: {answer!r}", file=stdout)
