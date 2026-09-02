"""Load and validate the four config kinds: products, models, harnesses, plans.

Single-file checks only (data-model.md validation rules 1-2). Cross-file
resolution (models named by plans exist, env vars set, ...) lives elsewhere.
Every error names the file and the field.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PRODUCT_KINDS = ("simulated", "real-api-ui", "real-api")
MODES = ("full-flow", "create-run", "run-only")
PROVIDERS = ("anthropic", "openai", "google", "zai", "moonshot", "fireworks")
EFFORTS = ("xhigh", "high", "medium", "low", "none")
ADAPTERS = ("openai", "openai_responses", "gemini", "anthropic")
HARNESS_KINDS = ("api", "cli", "scripted", "monarch")
LAUNCHERS = ("claude-code", "codex", "gemini-cli", "opencode")
SCRIPTS = ("oracle", "sloppy", "null")


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
    release: str | None = None
    modes: list[str] = field(default_factory=list)


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


def _read(path, kind):
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(path, "<root>", f"cannot read {kind}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(path, "<root>", f"{kind} file must be a mapping")
    c = _Checker(path, data)
    name = c.get("name", str) if "name" in data else c.fail("name", "required key missing")
    if name != path.stem:
        c.fail("name", f"must equal the file stem {path.stem!r}; got {name!r}")
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


def load_model(path) -> Model:
    c = _read(path, "model")
    c.keys(("name", "provider", "model", "effort", "usd_per_million", "key_env"),
           ("adapter", "base_url", "cache_min_prompt_tokens", "header_fallbacks",
            "prices_verified", "description"))
    p = c.sub("usd_per_million")
    p.keys(("input", "cached", "output"), ("cache_write",))
    num = (int, float)
    prices = Prices(input=p.get("input", num), cached=p.get("cached", num),
                    output=p.get("output", num), cache_write=p.get("cache_write", num))
    if prices.cache_write is None:
        prices.cache_write = prices.input
    verified = c.get("prices_verified", (datetime.date, str))
    if isinstance(verified, str):
        try:
            verified = datetime.date.fromisoformat(verified)
        except ValueError:
            c.fail("prices_verified", f"expected a date (YYYY-MM-DD); got {verified!r}")
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
    "monarch": (("base_url", "credential_env", "release", "modes"), ()),
}


def load_harness(path) -> Harness:
    c = _read(path, "harness")
    kind = c.get("kind", str, enum=HARNESS_KINDS) if "kind" in c.data else c.fail("kind", "required key missing")
    req, opt = _HARNESS_KEYS[kind]
    c.keys(("name", "kind", "accepts", *req), ("runnable", "description", *opt))
    accepts = c.data["accepts"]
    if accepts != "none":
        accepts = c.str_list("accepts", enum=PROVIDERS) if isinstance(accepts, list) else \
            c.fail("accepts", f"expected a list of providers or 'none'; got {accepts!r}")
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
        release=c.get("release", str),
        modes=c.str_list("modes", enum=MODES, default=[]),
    )


def load_plan(path) -> Plan:
    c = _read(path, "plan")
    c.keys(("name", "tasks", "mode", "repetitions", "timeout_s", "concurrency", "competitors",
            "baseline", "audience", "cost_ceiling_usd", "approved_by"), ("description",))
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
        timeout_s=c.get("timeout_s", num, minimum=0, strict=True),
        concurrency=c.get("concurrency", int, minimum=1),
        competitors=competitors,
        baseline=c.get("baseline", str),
        audience=c.get("audience", str),
        cost_ceiling_usd=c.get("cost_ceiling_usd", num, minimum=0, strict=True),
        approved_by=approved,
        description=c.get("description", str),
    )
