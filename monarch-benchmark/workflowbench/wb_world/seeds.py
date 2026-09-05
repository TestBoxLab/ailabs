"""Public-API seed folders for Monarch's discovery service, one per simulated app.

Monarch's create + run mode needs a knowledge base it did not have to discover.
`generate` turns the 47 OpenAPI documents of `wb_world.openapi` into the
`public-api-seeds` fixture shape the discovery service imports: one folder per
service holding `_meta.json` and one business action per operation, every URL
pointing back at the episode's front door (the HTTP shim).

Output is deterministic: the same inputs write the same bytes, so a rerun of
`wb monarch setup` is a no-op and the knowledge-base hashes stay comparable.
`ok.txt` records the version, the canonical flag and the digest.

`validate` is the mechanical half of the runbook's acceptance bar; `generate`
runs it on what it built and refuses to write anything if a gap is found.
Monarch's own `validate-seeds.mjs` is the authority and is wired into
`wb monarch setup` behind `MONARCH_SEED_VALIDATOR`.

v5 is Monarch's canonical format (their SPEC.md of 4 Sep 2026). What it changed:

  * GET/HEAD/DELETE carry `body_template: null` and `headers_template: {}`. The
    engine serializes even `{}`, and fetch refuses those methods with a body.
  * Every query parameter is placed in the URL, optional ones included; the
    engine percent-encodes what is filled and drops the rest of the pair.
  * A list extracts the ARRAY itself (`"messages": "$.messages"`). The engine's
    path grammar is `$.a.b` with numeric indices -- v4.1's `$.messages[*].id`
    resolved to nothing at run time, so every list read came back empty.
  * Schemas describe what the front door really returns, read from
    AutomationBench's own models (`to_display_dict` and the Pydantic
    annotations behind it), with `required` for the keys that always survive.
    Where nothing describes a response, the schema stays honest rather than
    inventing fields.
  * `creates_entities[].identifier_path` is always one of the step's extract
    paths, or the action declares no entity at all.
  * `label` is a short verb phrase (the only text the builder ranks on) and
    `area` a lowercase plural noun; the OpenAPI sentence goes to `description`.

v5.1 fixes what v5's shape rules could not catch: the seeds were VALID but not
TRUE. Monarch's planner refused every Google Sheets task ("the catalog doesn't
actually expose the data") because those seeds described AutomationBench's
`Spreadsheet` RECORD where the wire carries something else entirely. The rule
"resource record = response" was wrong for 13 of the 22 services the frozen
task sets use (probed against the real front door, 4 Sep 2026). What changed:

  * The HANDLER THAT SERVES THE REQUEST is now the first source of the response
    shape, not the last. It was already read, but the route key was matched
    against the wrong name -- `routes/<service>.py` maps a route to a key and
    then `_HANDLERS[key]` to a differently-named function, so every service that
    spells the two apart fell through to a guess. The lambda is read for the
    function it calls, and `_HANDLERS: dict[...] = {...}` is parsed as well as
    the bare assignment.
  * A response is an ENVELOPE far more often than a record: `{Customer: {...}}`,
    `{organization: {...}}`, `{success, calendar}`, `{ok, members}`. The
    outermost error-free dict of the handler's return is the body -- v5 took the
    widest, so a Salesforce report published its inner `report_result` as the
    whole response -- plus the keys appended afterwards (`d["envelopeUri"] =
    ...`, six of the DocuSign envelope's eleven fields) and the keys of a helper
    the handler delegates to.
  * The REQUEST body is the endpoint's stated contract, then the handler's own
    arguments, and only then a record schema. Sheets' `values/{range}:append`
    takes `{values: [[...]]}`; v5 sent it `properties`/`sheets`/`spreadsheetUrl`,
    so nothing a planner wrote could reach the wire. A router lambda that never
    forwards the request body (`f(w, ids[0], ids[1])`) declares no body at all.
  * Where a body field is opaque -- Gmail's `raw`, a base64url RFC 2822 message
    -- the endpoint's own request prose is appended to `constraints.helper_text`,
    the only prose the builder sees per parameter.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from wb_world.openapi import build_all

STAMP = "2026-09-03T00:00:00.000Z"   # arbitrary fixed sentinel: the folder's bytes must not move between runs
# The seeds name the host of the front door Monarch actually reaches: the Docker
# host name locally, the tunnel host when Monarch runs elsewhere (verified 4 Sep 2026).
_PATH_VAR = re.compile(r"\{(\w+)\}")
_VERB_BY_METHOD = {"post": "create", "put": "update", "patch": "update", "delete": "delete"}
# Methods whose request carries no body: the engine serializes even `{}` and
# fetch refuses these with one.
_BODYLESS = {"GET", "HEAD", "DELETE"}


@dataclass
class Summary:
    operations_in_spec: int
    files_written: int
    folders: list[str]


@dataclass
class Gap:
    file: str
    gap: str


class SeedGap(Exception):
    def __init__(self, gaps: list[Gap]):
        self.gaps = gaps
        super().__init__(f"{len(gaps)} gap(s) in the generated seeds")


def _verb(method: str, path: str) -> str:
    if method != "get":
        return _VERB_BY_METHOD[method]
    return "read" if path.rstrip("/").endswith("}") else "list"


def _resource(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    return parts[-1] if parts else "root"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "action"


def product_slug(service: str) -> str:
    """The folder name, the product id, and the first facet of every action id.

    The discovery service slugifies the slug it is given but imports a seed
    folder under its directory name verbatim, so an underscore here produced two
    products for the same app (verified 4 Sep 2026).
    """
    return "bench-" + _slugify(service)


def _body_template(op: dict[str, Any]) -> dict[str, str]:
    schema = ((op.get("requestBody") or {}).get("content", {})
              .get("application/json", {}).get("schema") or {})
    return {name: "{{%s}}" % name for name in sorted(schema.get("properties") or {})}


def _extract(schema: dict[str, Any], prefix: str = "$.") -> dict[str, str]:
    """Name every field of the response, so a later step can chain onto any of them.

    v3 named only `$.id`, which is what left Monarch's planner unable to go from
    "read the message" to "its subject/body/sender" (round run-20260904-192933).

    v5: only names that are legal extract identifiers (`\\w+`) and only top-level
    scalars -- the engine's path grammar is `$.a.b` with numeric `[n]` indices
    and nothing else, so a list is extracted whole by `_list_response` instead.
    """
    props = schema.get("properties") or {}
    names = [n for n in sorted(props) if re.fullmatch(r"\w+", n)]
    if names:
        return {n: f"{prefix}{n}" for n in names}
    return {"id": f"{prefix}id"}


def _query_names(op: dict[str, Any]) -> list[str]:
    """Every query parameter the operation declares, required or not.

    All of them belong in the URL: the engine percent-encodes what is filled and
    drops the whole `name=` pair of a token the recipe left unset. v4.1 placed
    only the required ones, so an optional filter (`?q=`, `?maxResults=`) was
    undeclarable and the builder could not narrow a list at all.
    """
    return sorted({p["name"] for p in op.get("parameters", [])
                   if p.get("in") == "query" and re.fullmatch(r"\w+", str(p.get("name") or ""))})


def _url_template(base: str, service: str, path: str, op: dict[str, Any]) -> str:
    url = f"{base}/{service}" + _PATH_VAR.sub(lambda m: "{{%s}}" % m.group(1), path)
    query = _query_names(op)
    if query:
        url += "?" + "&".join("%s={{%s}}" % (n, n) for n in query)
    return url


def _domain(base: str) -> str:
    return urlsplit(base).hostname or base


# Identifiers and stamps the server owns: never writable in a request body.
READ_ONLY = {"id", "created_at", "createdtime", "created_time", "createdat",
             "updated_at", "updatedat", "modified_at", "etag", "self", "url",
             "object", "resource_type", "created", "updated"}

# ponytail: one example per JSON type, overridden by a real corpus value when the
# resource is one the corpus covers. Ceiling: a field the corpus never shows gets
# a generic literal. Upgrade: per-field examples in the jsonc schemas.
_EXAMPLE_BY_TYPE = {"number": 1, "integer": 1, "boolean": True, "object": {},
                    "array": [], "string": "example"}


def _example(name: str, type_: str, observed: dict[str, Any],
             description: str = "") -> Any:
    """A realistic value of the DECLARED type: the corpus's own, else a literal.

    The example must parse as its declared type -- the builder shows it as the
    sample to copy and the engine falls back to it when a required parameter is
    omitted, so a string standing in for an array misleads both.
    """
    value = observed.get(name.replace("_", "").lower())
    if value not in (None, "", [], {}):
        if isinstance(value, list):
            first = value[0] if value and not isinstance(value[0], (dict, list)) else None
            if type_ == "array":
                return [first] if first is not None else []
            return first if first is not None else _EXAMPLE_BY_TYPE.get(type_, "example")
        if isinstance(value, dict):
            return {} if type_ == "object" else _EXAMPLE_BY_TYPE.get(type_, "example")
        if type_ == "array":
            return [value]
        # a corpus value of the wrong declared type would not parse
        if type_ in ("integer", "number") and not isinstance(value, (int, float)):
            return _EXAMPLE_BY_TYPE[type_]
        if type_ == "boolean" and not isinstance(value, bool):
            return True
        if type_ == "string" and not isinstance(value, str):
            return str(value)
        return value
    low = name.lower()
    if type_ in ("integer", "number") and description:
        # "Upper limit on messages to return (default 100, max 500)" -- the
        # documented default is a better sample than a bare 1.
        stated = re.search(r"default\s+(\d+)", description, re.I)
        if stated:
            return int(stated.group(1))
    if type_ == "array":
        # one element of the element type, never []: an empty list shows the
        # builder nothing about what a row looks like
        return [_example(name, "string", {})] if "id" not in low else ["001401"]
    if type_ == "string":
        if "date" in low or low.endswith("_at"):
            return "2026-05-01"
        if "email" in low:
            return "person@example.com"
        if low.endswith("id") or low.endswith("_id"):
            return "001401"
        if "name" in low or "subject" in low or "title" in low:
            return "Acme renewal"
    return _EXAMPLE_BY_TYPE.get(type_, "example")


def _json_type(value: Any) -> str:
    """The JSON type of an observed value, exact: Gmail's `date` really is an
    epoch-millisecond integer and `to`/`cc` really are arrays, and v4.1 typed
    both as strings."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def _schema_field_type(spec: dict[str, Any]) -> str:
    """The declared JSON type, kept exact.

    v4.1 collapsed `integer` to `number` and `array` to `string`. The engine
    re-types the runner's strings by this declaration before rendering, so a
    flattened type sends `"5"` where the API wants 5, or a comma string where it
    wants a list.
    """
    t = spec.get("type")
    return t if t in ("string", "integer", "number", "boolean", "array", "object") else "string"


def _enum_options(values: Any) -> list[dict[str, str]]:
    """`[{value: "<string>"}]`. A numeric value fails the executor's zod parse and
    makes the whole action unexecutable, so every value is stringified."""
    if not isinstance(values, list):
        return []
    return [{"value": str(v)} for v in values
            if isinstance(v, (str, int, float, bool)) and str(v) != ""]


def _singular(noun: str) -> str:
    """The importer's own singularizeNoun rules (knowledge-base/models/identity.ts)."""
    if noun.endswith("ies"):
        return noun[:-3] + "y"
    if re.search(r"(ses|xes|zes|ches|shes)$", noun):
        return noun[:-2]
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun[:-1]
    return noun


@lru_cache(maxsize=1)
def _display_records() -> dict[str, dict[str, dict[str, Any]]]:
    """service -> lowercased model name -> {wire field: {"type", "required"}}.

    AutomationBench's models carry the wire contract themselves: `to_display_dict`
    lists exactly the keys the front door serves, in the mock's own spelling, and
    the Pydantic annotation behind each key gives its type. Reading them is what
    makes a schema honest rather than a guess -- the jsonc `Message` schema
    describes the real Google API (`snippet`, `payload`, `raw`), which the mock
    never emits, while the model says `body_plain`, `thread_id`, `date: int`.

    A key whose annotation is `Optional[...]` is pruned when empty
    (`{k: v for k, v in d.items() if v is not None}`), so only the rest is
    promised as `required`.
    """
    import ast
    import importlib
    import inspect
    import pkgutil
    import textwrap
    import automationbench.schema as schema_pkg

    out: dict[str, dict[str, dict[str, Any]]] = {}
    for module in pkgutil.walk_packages(schema_pkg.__path__, schema_pkg.__name__ + "."):
        # service = the package right under automationbench.schema, whether the
        # models live in `schema/<service>.py` or `schema/<service>/<model>.py`
        parts = module.name.split(".")
        service = parts[2] if len(parts) > 2 else ""
        try:
            mod = importlib.import_module(module.name)
        except Exception:                       # a model that will not import is simply unknown
            continue
        for name, cls in vars(mod).items():
            if (not isinstance(cls, type) or cls.__module__ != mod.__name__
                    or not hasattr(cls, "to_display_dict")
                    or not hasattr(cls, "model_fields")):
                continue
            fields = _display_fields(cls, ast, inspect, textwrap)
            if fields:
                out.setdefault(service, {}).setdefault(name.lower(), fields)
    return out


def _display_fields(cls: Any, ast: Any, inspect: Any, textwrap: Any) -> dict[str, Any]:
    """The wire fields of one model, from the literal dict `to_display_dict` builds."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(cls.to_display_dict)))
    except (OSError, TypeError, SyntaxError, IndentationError):
        return {}
    model_fields = getattr(cls, "model_fields", {})
    out: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if not re.fullmatch(r"\w+", key.value):
                continue
            attr = value.attr if isinstance(value, ast.Attribute) else None
            field = model_fields.get(attr) if attr else None
            annotation = getattr(field, "annotation", None)
            type_, optional = _annotation_type(annotation)
            out.setdefault(key.value, {"type": type_, "required": not optional})
    return out


def _annotation_type(annotation: Any) -> tuple[str, bool]:
    """(JSON type, is optional) for a Pydantic annotation."""
    import typing
    if annotation is None:
        return "string", True
    optional = False
    args = typing.get_args(annotation)
    if args and type(None) in args:
        optional = True
        annotation = next((a for a in args if a is not type(None)), str)
        args = typing.get_args(annotation)
    origin = typing.get_origin(annotation) or annotation
    if origin in (list, set, tuple):
        return "array", optional
    if origin is dict:
        return "object", optional
    if origin is bool:
        return "boolean", optional
    if origin is int:
        return "integer", optional
    if origin is float:
        return "number", optional
    if origin is str:
        return "string", optional
    return "string", optional


@lru_cache(maxsize=1)
def _world_fields() -> dict[str, dict[str, dict[str, Any]]]:
    """service -> lowercased resource name -> {field: schema}, from the jsonc schemas.

    The jsonc `schemas` map is the wire truth: `runner/arms.py` translates the
    mock's snake_case storage to exactly these names before calling the API.
    """
    from wb_world.openapi import load_schemas
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for service, doc in load_schemas().items():
        out[service] = {name.lower(): (spec.get("properties") or {})
                        for name, spec in (doc.get("schemas") or {}).items()}
    return out


@lru_cache(maxsize=1)
def _corpus_examples() -> dict[tuple[str, str], dict[str, Any]]:
    """(service, collection) -> first non-empty value seen per field, for examples."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    root = Path(__file__).resolve().parents[1] / "corpus" / "imported-simple"
    for f in sorted(root.glob("*.json")) if root.is_dir() else ():
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for service, collections in ((doc.get("info") or {}).get("initial_state") or {}).items():
            if not isinstance(collections, dict):
                continue
            for collection, records in collections.items():
                if not isinstance(records, list):
                    continue
                seen = out.setdefault((service, collection), {})
                for record in records:
                    if isinstance(record, dict):
                        for key, value in record.items():
                            if key not in seen and value not in (None, "", [], {}):
                                seen[key] = value
    return out


def _observed(service: str, resource: str) -> dict[str, Any]:
    """Corpus examples for a resource, keyed by the wire field name.

    The corpus stores snake_case (`stage_name`); the wire uses `StageName`, so a
    field matches when its lowercase-without-underscores form does.
    """
    examples = _corpus_examples()
    for (svc, collection), values in examples.items():
        if svc != service:
            continue
        if _singular(collection.lower()) == _singular(resource.lower()):
            return {k.replace("_", "").lower(): v for k, v in values.items()}
    return {}


def _resource_fields(service: str, path: str,
                     method: str = "") -> tuple[str, dict[str, dict[str, Any]]]:
    """(resource name, writable fields) for the resource a write path addresses.

    v5.1: the HANDLER'S OWN SIGNATURE first. A write is not always a record write
    -- `values/{range}:append` takes `{values: [[...]]}`, and v5 sent it the
    `Spreadsheet` record's `properties`/`sheets`/`spreadsheetUrl`, so nothing the
    planner wrote could reach the wire. Where the handler declares its arguments
    they ARE the request contract; a record schema is the fallback for the
    handlers that take a `**kwargs` bag.
    """
    declared = _handler_body_fields(service, path, method) if method else {}
    if declared:
        return _resource(path), declared
    schemas = _world_fields().get(service) or {}
    segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    for segment in reversed(segments):
        for candidate in (segment, _singular(segment)):
            props = schemas.get(candidate.lower())
            if props:
                return candidate, {name: spec for name, spec in props.items()
                                   if name.lower() not in READ_ONLY}
    # (c) no schema for this resource: fall back to the fields the corpus has
    # actually seen on it, typed from the observed values.
    for segment in reversed(segments):
        values = _corpus_fields(service, segment)
        if values:
            return segment, {name: {"type": _json_type(v)} for name, v in values.items()
                             if name.lower() not in READ_ONLY}
    return (segments[-1] if segments else "root"), {}


@lru_cache(maxsize=1)
def _handler_signatures() -> dict[tuple[str, str, str], dict[str, str]]:
    """(service, AB path pattern, METHOD) -> {argument: JSON type} of its handler.

    The handler's own parameters are what the front door accepts. Only handlers
    that spell their arguments out are read: one taking a bare `**kwargs` bag
    (`quickbooks_customer_create(w, b)`) says nothing, and its record schema
    remains the better description.
    """
    import importlib
    import inspect
    import typing

    out: dict[tuple[str, str, str], dict[str, str]] = {}
    for service in sorted(_raw_schemas()):
        try:
            routes_mod = importlib.import_module(
                f"automationbench.tools.api.routes.{service}")
            impl_mod = importlib.import_module(
                f"automationbench.tools.api.impl.{service}")
        except Exception:
            continue
        import ast
        import textwrap
        try:
            routes_src = ast.parse(textwrap.dedent(inspect.getsource(routes_mod)))
        except Exception:
            continue
        handlers = _handler_names(routes_src, ast)
        bindings = _handler_bindings(routes_src, ast)
        for method, pattern, key in getattr(routes_mod, "_ROUTES", ()) or ():
            fn = getattr(impl_mod, handlers.get(key, ""), None) or getattr(
                impl_mod, f"{service}_{key}", None)
            forwards_body, url_bound, url_named = bindings.get(key, (False, 0, set()))
            # The router lambda says where each argument comes from:
            # `f(w, ids[0], ids[1], **b)` binds two from the URL and the rest
            # from the body; one that never forwards `**b` (`f(w, ids[0])`)
            # takes no request body at all, and its signature says nothing about
            # one. Salesforce's generic update is exactly that shape, and
            # reading its signature naively published `{object_type, record_id}`
            # -- the routing arguments -- as the record's fields.
            if fn is None or not forwards_body:
                continue
            try:
                sig = inspect.signature(fn)
            except (TypeError, ValueError):
                continue
            fields: dict[str, str] = {}
            positional = [name for name, p in sig.parameters.items()
                          if name != "world" and p.kind in
                          (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            from_url = set(positional[:url_bound]) | url_named
            for name, param in sig.parameters.items():
                if (name == "world" or name in from_url
                        or param.kind is param.VAR_KEYWORD
                        or param.kind is param.VAR_POSITIONAL):
                    continue
                if not re.fullmatch(r"\w+", name) or name.lower() in READ_ONLY:
                    continue
                fields[name] = _annotation_type(
                    None if param.annotation is inspect.Parameter.empty
                    else param.annotation)[0]
            if fields:
                out[(service, pattern, method.upper())] = fields
    return out


def _handler_bindings(routes_src: Any, ast: Any) -> dict[str, tuple[bool, int, set[str]]]:
    """route key -> (the lambda forwards the request body, how many args it takes from the URL).

    `lambda w, ids, p, b: f(w, ids[0], ids[1], **{**p, **b})` -> (True, 2, set()),
    and `f(w, object_type=ids[0], record_id=ids[1], **b)` names them instead.
    """
    out: dict[str, tuple[bool, int, set[str]]] = {}
    for node in ast.walk(routes_src):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if not (targets and any(getattr(t, "id", "") == "_HANDLERS" for t in targets)
                and isinstance(node.value, ast.Dict)):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            call = next((c for c in ast.walk(value)
                         if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)), None)
            if call is None:
                continue
            source = ast.dump(call)
            # `**b` anywhere in the call -- bare, or merged as `**{**p, **b}`
            forwards = "id='b'" in source.replace('"', "'")
            url_bound = sum(1 for a in call.args
                            if isinstance(a, ast.Subscript)
                            and getattr(a.value, "id", "") == "ids")
            named = {kw.arg for kw in call.keywords
                     if kw.arg and isinstance(kw.value, ast.Subscript)
                     and getattr(kw.value.value, "id", "") == "ids"}
            out[key.value] = (forwards, url_bound, named)
    return out


# A top-level `name: <type>` of a stated request body. `?` marks it optional,
# and the value may be an array (`[[cell, ...], ...]`), an object, or a word.
_REQUEST_FIELD = re.compile(r"(?:^\{|,)\s*(\w+)\??\s*:\s*(\[|\{|\w+)")
_PROSE_TYPE = {"[": "array", "{": "object", "int": "integer", "integer": "integer",
               "number": "number", "float": "number", "bool": "boolean",
               "boolean": "boolean", "true": "boolean", "false": "boolean"}


def _stated_body_fields(service: str, path: str) -> dict[str, Any]:
    """The request body AutomationBench states in prose, as field schemas, or {}.

    A stated shape is a CONTRACT the handler ENFORCES, not a description of its
    Python signature: Gmail's send declares "Message with raw (base64url-encoded
    RFC 2822) or payload...", names `to`/`subject`/`body` as arguments, and then
    answers 400 for exactly those (probed 4 Sep 2026). Sheets' append states
    `{range, majorDimension?, values: [[cell, ...], ...]}`, which is the body the
    front door accepts and nothing else describes. Where the prose is a
    top-level object, it outranks both the signature and the record schema.
    """
    prose = _ab_requests().get((service, path), "").strip()
    if not prose.startswith("{"):
        return {}
    in_path = {n.lower() for n in _PATH_VAR.findall(path)}
    out: dict[str, Any] = {}
    for name, token in _REQUEST_FIELD.findall(prose):
        if name.lower() in READ_ONLY or name.lower() in in_path:
            continue
        out[name] = {"type": _PROSE_TYPE.get(token, "string")}
    return out


def _handler_body_fields(service: str, path: str, method: str) -> dict[str, Any]:
    """The handler's arguments that belong in the BODY, as field schemas.

    Everything the URL already carries -- a path placeholder, a declared query
    parameter -- is dropped: a token placed twice is a parameter the engine
    binds twice, and the validator rejects the mismatch.
    """
    if method.upper() in _BODYLESS:
        return {}
    stated = _stated_body_fields(service, path)
    if stated:
        return stated
    if _ab_requests().get((service, path), "").strip():
        # Prose that names a shape rather than listing fields ("Message with raw
        # (base64url-encoded RFC 2822) or payload...") still says the signature
        # is not the contract: Gmail's send answers 400 for the `to`/`subject`/
        # `body` its own arguments name. Fall through to the record schema,
        # which names `raw` and `payload`.
        return {}
    for (svc, pattern, verb), fields in _handler_signatures().items():
        if svc != service or verb != method.upper():
            continue
        try:
            if not re.search(pattern, _ab_path(service, path)):
                continue
        except re.error:
            continue
        in_url = {n.lower() for n in _PATH_VAR.findall(path)}
        # the AB argument for a path segment is often spelled differently
        # (`range_str` for `{range}`), so a prefix match counts as placed
        return {name: {"type": type_} for name, type_ in fields.items()
                if name.lower() not in in_url
                and not any(name.lower().startswith(u) or u.startswith(name.lower())
                            for u in in_url)}
    return {}


# Lists whose handler projects a stub instead of the record. Gmail's
# `messages.list` hardcodes format="minimal" and returns {id, threadId} only
# (impl/gmail.py, verified against a live front door 4 Sep 2026); advertising
# the full record there would tell the planner it can skip the read -- the very
# step this file exists to make plannable. Slack's lists return whole records.
# ponytail: one observed exception, not a per-handler projection model.
# Upgrade: probe each list once and record what it actually returned.
_STUB_LIST_FIELDS = {("gmail", "messages"): ("id", "threadId")}


# The noun an RPC verb answers with. Anything unlisted (`info`, `get`) answers
# about the segment before the dot, which is already the resource.
_RPC_NOUN = {"history": "message", "replies": "message", "messages": "message",
             "members": "user", "lookupbyemail": "user"}

# Where a service names a resource one way and answers under another: Slack's
# `conversations.list` returns `channels` (impl/slack.py:45), never
# `conversations`. Keyed by the resource noun, not by endpoint.
# ponytail: one observed rename. Upgrade: read the handler's literal, as
# `_display_records` already does for record fields.
_COLLECTION_ALIAS = {("slack", "conversations"): "channels"}


def _record_schema(service: str, path: str) -> dict[str, Any]:
    """The record the front door actually returns for the resource `path` addresses.

    Two sources, because neither alone is the wire truth (verified against a live
    `EpisodeHTTPShim`, 4 Sep 2026):

      * the world schema names what Salesforce serves (`Id`, `StageName`);
      * the corpus names what Gmail serves (`subject`, `body_plain`, `from`) --
        the jsonc `Message` schema describes the real Google API (`snippet`,
        `payload`), which the mock never emits.

    So both are merged. A corpus key wins on collision, since it is a value the
    mock demonstrably stored, and `from_` is de-mangled to the served `from`.
    """
    schemas = _world_fields().get(service) or {}
    segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    # An RPC-shaped segment names its resource before the dot: Slack's
    # `conversations.history` answers messages, `users.info` a user.
    if segments and "." in segments[-1]:
        head, _, tail = segments[-1].partition(".")
        noun = _RPC_NOUN.get(tail.lower(), "") or head
        segments = segments[:-1] + [noun]
    props: dict[str, Any] = {}
    # (a) the model's own `to_display_dict`: the exact keys the front door serves.
    models = _display_records().get(service) or {}
    # Some services prefix their model names with the service itself
    # (`IntercomContact` for `contacts`), so both spellings are tried.
    prefix = service.replace("_", "")
    for segment in reversed(segments):
        for candidate in (segment, _singular(segment)):
            fields = (models.get(candidate.lower())
                      or models.get(prefix + candidate.lower()))
            if fields:
                return _model_schema(fields)
    for segment in reversed(segments):
        for candidate in (segment, _singular(segment)):
            declared = schemas.get(candidate.lower())
            if declared:
                props = {name: _declared_field(spec) for name, spec in declared.items()}
                break
        if props:
            break
    for segment in reversed(segments):
        observed = _corpus_fields(service, segment)
        if observed:
            # The corpus REPLACES the declared record rather than extending it:
            # what the mock stored is what the front door serves, and the world
            # schema often describes the real vendor API instead. Gmail's jsonc
            # `Message` declares `snippet`/`payload`/`raw`, none of which the mock
            # emits -- v4.1 advertised both halves and the camelCase one was
            # `undefined` at run time.
            props = {}
            for name, value in observed.items():
                # pydantic's alias for the reserved word: the wire carries `from`.
                key = name.rstrip("_") if name == "from_" else name
                props[key] = _observed_field(value, None)
            break
    if not props and _PATH_VAR.search(path):
        # A generic path picks its record type at runtime
        # (`/sobjects/{sObjectType}/{id}` is Salesforce's only read). No single
        # record fits, so name the union of the service's declared types: a
        # superset the planner can chain on beats the bare id that broke it.
        # ponytail: a union, so it also offers fields the chosen type lacks.
        # Upgrade: branch the seed per sObjectType if that misleads the planner.
        for declared in (schemas or {}).values():
            for name, spec in declared.items():
                props.setdefault(name, _declared_field(spec))
    # Only names the extract grammar can address survive: a key with a dot or a
    # dash is unreachable by `$.a.b`, so declaring it would promise a field the
    # builder cannot wire.
    props = {n: s for n, s in props.items() if re.fullmatch(r"\w+", n)}
    return {"type": "object", "properties": props} if props else {"type": "object"}


def _nested_identifier(schema: dict[str, Any], extract: dict[str, str]) -> str:
    """`$.<key>.<id>` for a record nested one level in an envelope, or "".

    Adds the path to `extract` under the id's own name, because the engine binds
    the created id through an extract and `identifier_path` must be one of them.
    """
    for key, spec in sorted((schema.get("properties") or {}).items()):
        if not (isinstance(spec, dict) and spec.get("type") == "object"):
            continue
        named = _identifier_field(spec.get("properties") or {})
        if not named:
            continue
        path = f"$.{key}.{named}"
        extract.setdefault(named, path)
        return path
    return ""


def _service_identifier(service: str) -> str:
    """How this service spells the id its records carry, or "".

    Taken from the service's own models -- Salesforce's records answer under
    `Id`, Gmail's under `id`. The spelling most of them share wins, and a service
    whose models agree on nothing declares no field rather than the wrong one.
    """
    from collections import Counter
    names = Counter(_identifier_field(fields)
                    for fields in (_display_records().get(service) or {}).values() if fields)
    names.pop("", None)
    if not names:
        return ""
    # a clear majority only: a tie means the service has no single spelling
    (best, count), = names.most_common(1)
    return best if count * 2 > sum(names.values()) else ""


def _model_schema(fields: dict[str, Any]) -> dict[str, Any]:
    """A record schema from a model's wire fields, `required` included.

    `to_display_dict` drops every key whose value is None, so a non-optional
    annotation is the honest definition of "always present".
    """
    props: dict[str, Any] = {}
    for name, spec in sorted(fields.items()):
        prop: dict[str, Any] = {"type": spec["type"]}
        if spec["type"] == "array":
            prop["items"] = {"type": "string"}
        props[name] = prop
    required = sorted(n for n, s in fields.items() if s.get("required"))
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def _declared_field(spec: dict[str, Any]) -> dict[str, Any]:
    """One property of a record, from the world schema."""
    type_ = _schema_field_type(spec)
    out: dict[str, Any] = {"type": type_}
    if type_ == "array":
        out["items"] = {"type": _schema_type(spec.get("items") or {})}
    if spec.get("format") in ("email", "date-time", "uuid", "date", "uri"):
        out["format"] = spec["format"]
    return out


def _observed_field(value: Any, declared: dict[str, Any] | None) -> dict[str, Any]:
    """One property of a record, from a value the mock actually stored."""
    type_ = _json_type(value)
    out: dict[str, Any] = {"type": type_}
    if type_ == "array":
        element = next((v for v in value if not isinstance(v, (dict, list))), None)
        out["items"] = {"type": _json_type(element) if element is not None else "string"}
    elif type_ == "object":
        # an open bag: the mock stores whatever the record carried
        out["additionalProperties"] = True
    # keep a declared format that still fits the observed type
    fmt = (declared or {}).get("format")
    if fmt and type_ == "string":
        out["format"] = fmt
    return out


# AutomationBench states each endpoint's answer in prose (`response` in the
# jsonc): "ListMessagesResponse: {messages: [{id, threadId}], resultSizeEstimate:
# int}". Where that names the wrapper key it is the wire truth -- it corrects 56
# of 180 collections the path heuristic gets wrong (Calendly answers under
# `collection`, Asana under `data`, Airtable under `records`), each confirmed in
# the handler code (impl/calendly.py:245, impl/asana.py:186, impl/airtable.py:209).
# The collection is not always the first key: the SOQL query answers
# `{totalSize: int, done: boolean, records: [record], ...}`, so the array is
# looked for anywhere in the object, not only at its head.
_WRAPPER = re.compile(r"[{,]\s*([A-Za-z_]\w*)\s*:\s*\[")
_EMPTY_RESPONSE = re.compile(r"^\s*(empty|none|no content|\{\}|204)", re.I)


def _declared_response(service: str, path: str, method: str) -> str:
    """AutomationBench's own prose for what this endpoint answers, or ""."""
    return _ab_responses().get((service, path, method.upper()), "")


@lru_cache(maxsize=1)
def _ab_responses() -> dict[tuple[str, str, str], str]:
    """(service, real path, METHOD) -> the jsonc `response` prose."""
    from wb_world.openapi import real_path
    out: dict[tuple[str, str, str], str] = {}
    for service, doc in _raw_schemas().items():
        for ep in doc.get("endpoints") or ():
            response = ep.get("response")
            if isinstance(response, str):
                key = (service, real_path(service, ep["path"]), ep.get("method", "GET").upper())
                out.setdefault(key, response)
    return out


@lru_cache(maxsize=1)
def _raw_schemas() -> dict[str, dict[str, Any]]:
    from wb_world.openapi import load_schemas
    return load_schemas()


def _collection_key(service: str, path: str, method: str = "GET") -> str:
    """The wrapper key a list answers under: {"messages": [...]}, never a bare array.

    The first array wins: where the prose declares a compatibility alias beside
    the real collection (SOQL's `results` next to `records`), the primary is the
    one named first.
    """
    prose = re.sub(r"^\w+:\s*", "", _declared_response(service, path, method).strip())
    declared = _WRAPPER.search(prose)
    if declared:
        return declared.group(1)
    segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    key = segments[-1] if segments else "items"
    # An RPC-shaped segment is the endpoint's name, not a JSON key: Slack's
    # `conversations.history` answers under `messages`, and `conversations.list`
    # under `channels`. The noun before the dot (mapped through _RPC_NOUN, which
    # already knows what each verb answers with) is the collection, pluralised.
    if "." in key:
        head, _, tail = key.partition(".")
        key = _plural(_RPC_NOUN.get(tail.lower(), "") or head)
    # a key the extract grammar cannot address is no key at all
    if not re.fullmatch(r"\w+", key):
        key = _plural(_slugify(key).replace("-", "_"))
    return _COLLECTION_ALIAS.get((service, key), key)


_SCALAR = re.compile(r"[,{]\s*([A-Za-z_]\w*)\s*:\s*(integer|int|boolean|bool|string|str|number)\b")
_SCALAR_TYPE = {"int": "integer", "integer": "integer", "number": "number",
                "bool": "boolean", "boolean": "boolean",
                "string": "string", "str": "string"}


def _declared_scalars(service: str, path: str, method: str, skip: str) -> dict[str, Any]:
    """Top-level scalars the response prose names beside a collection.

    Gmail's list answers `{messages: [...], resultSizeEstimate: int}` and the
    SOQL query `{records: [...], totalSize: int, done: bool}`; both are worth
    extracting, and both are verified against the live front door (4 Sep 2026).
    """
    prose = re.sub(r"^\w+:\s*", "", _declared_response(service, path, method).strip())
    return {m.group(1): {"type": _SCALAR_TYPE[m.group(2)]}
            for m in _SCALAR.finditer(prose) if m.group(1) != skip}


@lru_cache(maxsize=1)
def _handler_envelopes() -> dict[tuple[str, str, str], list[str]]:
    """(service, AB path pattern, METHOD) -> the keys the handler's success dict has.

    The last source of truth left: the function that actually serves the request.
    AutomationBench routes `(method, path regex) -> handler` in
    `tools/api/routes/<service>.py`, and each handler ends in a literal
    `json.dumps({...})`. Slack's `conversations.create` answers
    `{"ok": True, "channel": {...}}`, so the created id lives under `channel` --
    something neither the jsonc prose (silent here) nor a record schema says.

    The success dict is the one carrying no `error` key; where several remain,
    the widest wins (an early return is usually a narrower special case).

    The route key is NOT the handler's name: `routes/<service>.py` maps
    `("GET", r"sheets/v4/spreadsheets/([^/]+)$", "get_spreadsheet")` and then
    `_HANDLERS["get_spreadsheet"] = lambda ...: google_sheets_spreadsheets_get(...)`.
    Guessing `<service>_<key>` missed every service that names the two apart, so
    the lambda is read for the function it calls (v5.1: that alone recovered the
    Sheets read, whose seed was describing the AB record instead of the wire body).
    """
    import ast
    import importlib
    import inspect
    import textwrap

    out: dict[tuple[str, str, str], list[str]] = {}
    for service in sorted(_raw_schemas()):     # `_KEY_TYPES` is filled in this order
        try:
            routes_mod = importlib.import_module(
                f"automationbench.tools.api.routes.{service}")
            impl_mod = importlib.import_module(
                f"automationbench.tools.api.impl.{service}")
            source = ast.parse(textwrap.dedent(inspect.getsource(impl_mod)))
            routes_src = ast.parse(textwrap.dedent(inspect.getsource(routes_mod)))
        except Exception:
            continue
        helpers = {node.name: node for node in source.body
                   if isinstance(node, ast.FunctionDef)}
        _READING.append(service)               # whose keys `_KEY_TYPES` is learning
        try:
            returns = {name: _success_keys(node, ast, helpers)
                       for name, node in helpers.items()}
        finally:
            _READING.pop()
        returns = {name: keys for name, keys in returns.items() if keys}
        handlers = _handler_names(routes_src, ast)
        for method, pattern, key in getattr(routes_mod, "_ROUTES", ()) or ():
            keys = (returns.get(handlers.get(key, ""))
                    or returns.get(f"{service}_{key}") or returns.get(key))
            if keys:
                out[(service, pattern, method.upper())] = keys
    return out


def _handler_names(routes_src: Any, ast: Any) -> dict[str, str]:
    """route key -> the impl function `_HANDLERS[key]`'s lambda calls."""
    out: dict[str, str] = {}
    for node in ast.walk(routes_src):
        # `_HANDLERS = {...}` and the annotated `_HANDLERS: dict[...] = {...}`
        # alike -- half the routes modules write the second, and reading only the
        # first left QuickBooks' companyinfo with no handler at all.
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if not (targets and any(getattr(t, "id", "") == "_HANDLERS" for t in targets)
                and isinstance(node.value, ast.Dict)):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            called = next((c.func.id for c in ast.walk(value)
                           if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)), "")
            if called:
                out[key.value] = called
    return out


def _success_keys(fn: Any, ast: Any, helpers: dict[str, Any] | None = None,
                  depth: int = 0) -> list[str]:
    """The keys of the widest error-free dict a handler returns.

    A handler that hands off to a resource builder (`return
    json.dumps(_envelope_to_resource(envelope))`) has no literal of its own; the
    called helper is followed one level, or the only literal left is the 404
    guard's -- which is exactly what v5 published for the DocuSign envelope read.
    """
    best: list[str] = []
    calls: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return):
            continue
        for literal in ast.walk(node):
            if isinstance(literal, ast.Call) and isinstance(literal.func, ast.Name):
                calls.append(literal.func.id)
        # `return json.dumps(x.to_display_dict())` with NOTHING wrapping it: the
        # body IS the record, and the models describe it far better than a key
        # list can. Gmail's read has a literal too (the `format=minimal`
        # projection), and taking it would publish `{id, threadId}` for the full
        # read the planner needs. A `to_display_dict()` nested inside a dict is
        # the opposite case -- `{"Customer": c.to_display_dict()}` IS an envelope.
        if _returns_bare_record(node, ast):
            return []
        # The OUTERMOST error-free dict of this return is the body; a nested one
        # is a field of it. v5 took the widest, so Salesforce's report read
        # published the inner `report_result` object as if it were the response,
        # while the wire carries `{success, report_result}`.
        keys = _outermost_keys(node, ast, fn)
        # `{"error": {...}}` and the inner `{"code", "message"}` alike: a dict
        # reached from inside an error envelope is not the success body.
        if keys and len(keys) > len(best):
            best = keys
    if not best and helpers and depth < 2:
        for name in calls:
            helper = helpers.get(name)
            if helper is not None:
                keys = _success_keys(helper, ast, helpers, depth + 1)
                if len(keys) > len(best):
                    best = keys
    if not best:
        # A builder that assembles its dict in a local and `return`s the name
        # (`d = {...}; d["x"] = ...; return d`) has no literal under Return, so
        # the widest error-free literal anywhere in the body is the body. Tried
        # last: a handler's own error guard is a literal too, and following the
        # helper it delegates to is the better answer wherever there is one.
        for literal in ast.walk(fn):
            if not isinstance(literal, ast.Dict):
                continue
            keys = [k.value for k in literal.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if keys and "error" not in keys and len(keys) > len(best) and not _under_error(fn, literal, ast):
                best = keys
        # ...plus every key the builder appends afterwards (`d["envelopeUri"] =
        # ...`), which is where six of the DocuSign envelope's eleven wire fields
        # live. Order-stable: source order, appended after the literal's own.
        if best:
            for extra, type_ in _subscript_keys(fn, ast).items():
                if extra not in best:
                    best.append(extra)
                    svc = _READING[-1] if _READING else ""
                    _KEY_TYPES.setdefault((svc, extra), type_)
                    # appended behind an `if`, so present only sometimes
                    _CONDITIONAL.add((svc, extra))
    return best


def _subscript_keys(fn: Any, ast: Any) -> dict[str, str]:
    """{key: type} for every `d["key"] = <value>` assignment in a builder."""
    out: dict[str, str] = {}
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)):
            continue
        value = node.value
        out[target.slice.value] = (
            "array" if isinstance(value, (ast.List, ast.ListComp, ast.Tuple))
            else "object" if isinstance(value, (ast.Dict, ast.DictComp))
            else _json_type(value.value) if isinstance(value, ast.Constant)
            # an f-string builds a URI; anything else (a helper call, an
            # attribute) is a sub-resource the code does not spell out here
            else "string" if isinstance(value, ast.JoinedStr)
            else "object" if isinstance(value, ast.Call)
            else "string")
    return out


_RECORD_CALL = ("to_display_dict", "model_dump", "dict")


def _returns_bare_record(node: Any, ast: Any) -> bool:
    """True for `return json.dumps(x.to_display_dict())` and nothing around it."""
    value = node.value
    while isinstance(value, ast.Call) and not isinstance(value.func, ast.Attribute):
        value = value.args[0] if value.args else None
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        if value.func.attr == "dumps":
            inner = value.args[0] if value.args else None
            return (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in _RECORD_CALL)
        return value.func.attr in _RECORD_CALL
    return False


def _outermost_keys(root: Any, ast: Any, scope: Any = None) -> list[str]:
    """The keys of the shallowest error-free dict literal under `root`, or []."""
    frontier = [root]
    while frontier:
        nxt = []
        for node in frontier:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Dict):
                    keys = [k.value for k in child.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    if keys and "error" not in keys:
                        service = _READING[-1] if _READING else ""
                        for name, type_ in _literal_types(child, ast, scope).items():
                            # first writer wins, and the sweep is over sorted
                            # services: the map is the same on every run
                            _KEY_TYPES.setdefault((service, name), type_)
                        return keys
                    # an error envelope: neither it nor anything under it
                    if keys:
                        continue
                nxt.append(child)
        frontier = nxt
    return []


# (service, key) -> the JSON type the handler's literal assigns it, filled in as
# `_outermost_keys` reads each success dict. The value expression beside a key is
# the only honest statement of its type: a `[...]` literal is an array, a `{...}`
# an object, a bare string a string. Keyed by service because the same name is
# not the same shape everywhere: Sheets' `values` is the row array, Airtable's a
# field object, and one flat map gave the Sheets read an object where the
# planner needed rows.
_KEY_TYPES: dict[tuple[str, str], str] = {}
_READING: list[str] = []            # the service `_handler_envelopes` is on
# Keys a builder appends behind a guard (`if envelope.sender: d["sender"] = ...`):
# typed like the rest, but never promised in `required`.
_CONDITIONAL: set[tuple[str, str]] = set()


def _literal_types(node: Any, ast: Any, scope: Any = None) -> dict[str, str]:
    """{key: JSON type} for the entries of one dict literal whose value says so.

    A key whose value is a plain name (`"values": values`) is resolved to the
    type that name was last built as inside `scope` -- Sheets' values reader
    assembles `values = []` row by row and then returns it, so without following
    the name the row array reads as an untyped object and the planner is told
    there are no rows.
    """
    locals_ = _local_types(scope, ast) if scope is not None else {}
    out: dict[str, str] = {}
    for key, value in zip(node.keys, node.values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        type_ = _expr_type(value, ast)
        if not type_ and isinstance(value, ast.Name):
            type_ = locals_.get(value.id, "")
        if type_:
            out[key.value] = type_
    return out


def _expr_type(value: Any, ast: Any) -> str:
    """The JSON type an expression plainly is, or "" when it does not say."""
    if isinstance(value, (ast.List, ast.ListComp, ast.Tuple)):
        return "array"
    if isinstance(value, (ast.Dict, ast.DictComp)):
        return "object"
    if isinstance(value, ast.JoinedStr):
        return "string"
    if isinstance(value, ast.Constant):
        return _json_type(value.value)
    return ""


def _local_types(scope: Any, ast: Any) -> dict[str, str]:
    """{name: JSON type} for the locals a function assigns a self-describing value."""
    out: dict[str, str] = {}
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign):
            continue
        type_ = _expr_type(node.value, ast)
        if not type_:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                # first assignment wins: `values = []` then `values = [h] + values`
                out.setdefault(target.id, type_)
    return out


def _under_error(root: Any, target: Any, ast: Any) -> bool:
    """True when `target` sits under an `"error"` key of a dict inside `root`."""
    for node in ast.walk(root):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value == "error"
                        and any(child is target for child in ast.walk(value))):
                    return True
    return False


def _envelope_for(service: str, path: str, method: str) -> list[str]:
    """The handler's success keys for one endpoint, matched through its route regex."""
    for (svc, pattern, verb), keys in _handler_envelopes().items():
        if svc != service or verb != method.upper():
            continue
        try:
            # AB matches the pattern against its own internal path
            if re.search(pattern, _ab_path(service, path)):
                return keys
        except re.error:
            continue
    return []


@lru_cache(maxsize=1)
def _ab_paths() -> dict[tuple[str, str], str]:
    """(service, public path) -> the internal path AB routes on.

    Built by inverting `real_path` over the endpoints themselves rather than
    re-deriving the prefix: the jsonc path IS the routing path, and Slack's
    `slack/conversations.create` publishes as `/conversations.create`.
    """
    from wb_world.openapi import real_path
    return {(service, real_path(service, ep["path"])): ep["path"]
            for service, doc in _raw_schemas().items()
            for ep in doc.get("endpoints") or ()}


def _ab_path(service: str, path: str) -> str:
    """The internal path AB routes on, from the public one the seeds publish."""
    return _ab_paths().get((service, path), path.lstrip("/"))


_FLAT_FIELD = re.compile(r"([A-Za-z_]\w*)\s*:\s*(string|int|bool|number|true|false)\b")


def _declared_envelope(service: str, path: str, method: str) -> dict[str, Any]:
    """A flat object of scalars the prose declares, as a schema, or {}.

    Salesforce's creates answer `{id: string, success: true}` -- an envelope, not
    the record. v4.1 declared the whole record there, so the builder wired fields
    (`StageName`, `Email`) that a create response never carries. Confirmed in the
    handler code: impl/salesforce.py:177 returns exactly `{"id", "success"}`.
    """
    prose = re.sub(r"^\w+:\s*", "", _declared_response(service, path, method).strip())
    # only a flat `{a: t, b: t}` with no nesting: anything else is a record
    if not (prose.startswith("{") and prose.endswith("}")) or "[" in prose or "{" in prose[1:]:
        return {}
    fields = _FLAT_FIELD.findall(prose)
    if not fields or len(fields) != prose.count(":"):
        return {}
    types = {"string": "string", "int": "integer", "number": "number",
             "bool": "boolean", "true": "boolean", "false": "boolean"}
    return {name: {"type": types[t]} for name, t in fields}


def _envelope_schema(service: str, path: str, method: str) -> dict[str, Any]:
    """A schema for the envelope the handler returns, or {}.

    Each key is typed from the service's own record when its name matches one
    (Slack's `channel` is a channel), else from the JSON type the handler's own
    literal gives it (`"values": [...]` is an array, `"tableRange": "..."` a
    string) -- the keys AND their types are read from the code, never guessed.
    """
    keys = _envelope_for(service, path, method)
    if not keys:
        return {}
    _handler_envelopes()                       # `_KEY_TYPES` is filled by the sweep
    models = _display_records().get(service) or {}
    props: dict[str, Any] = {}
    for key in keys:
        if not re.fullmatch(r"\w+", key):
            continue
        if key in ("ok", "success", "done", "isLast", "incompleteSearch"):
            props[key] = {"type": "boolean"}
            continue
        record = models.get(key.lower()) or models.get(_singular(key.lower()))
        literal = _KEY_TYPES.get((service, key))
        if record and literal != "string":
            row = _model_schema(record)
            props[key] = ({"type": "array", "items": row}
                          if key != _singular(key) or literal == "array" else row)
        elif literal == "array":
            # a row shape the code does not state: an open row, so the builder is
            # told to use what it gets and never to invent names under it
            props[key] = {"type": "array",
                          "items": {"type": "object", "additionalProperties": True}}
        elif literal in ("string", "integer", "number", "boolean"):
            props[key] = {"type": literal}
        else:
            props[key] = {"type": "object", "additionalProperties": True}
    return {"type": "object", "properties": props} if props else {}


def _answers_empty(service: str, path: str, method: str) -> bool:
    """True when AutomationBench says this endpoint answers no body worth typing.

    The front door serves `{}` at status 200 for these (probed 4 Sep 2026: the
    Salesforce PATCH and the Gmail DELETE both answer `{}`), so there is no field
    to name and the honest schema is the empty object.
    """
    return bool(_EMPTY_RESPONSE.match(_declared_response(service, path, method).strip()))


def _corpus_fields(service: str, resource: str) -> dict[str, Any]:
    """Raw (unnormalised) corpus fields for a resource, or {} when it has none."""
    for (svc, collection), values in _corpus_examples().items():
        if svc == service and collection.lower().rstrip("s") == resource.lower().rstrip("s"):
            return values
    return {}


JSON_SCHEMA = "https://json-schema.org/draft/2020-12/schema"

def _identifier_field(props: dict[str, Any]) -> str:
    """The record's own identifier among its fields, or "".

    `id`/`Id` first, else the service's own spelling (`InvoiceID`, `ContactID`,
    `gid`, `envelopeId`). Verified in AutomationBench's models: the identifier
    sits in `to_display_dict`'s unconditional base dict while every other field
    is appended only `if value` (schema/xero.py:42, :108), so it is the one field
    the front door always emits.
    """
    for name in ("id", "Id", "ID", "gid", "uuid", "key"):
        if name in props:
            return name
    ids = sorted(n for n in props if re.fullmatch(r"\w*[iI][dD]", n))
    return ids[0] if ids else ""


def _with_required(schema: dict[str, Any]) -> dict[str, Any]:
    """Give an object schema a `required` list, so presence is not `unknown`.

    Only the identifier is promised. AutomationBench's `to_display_dict` prunes
    empty values (probed 4 Sep 2026: a Contact answered 10 of its 20 declared
    fields), so listing more would tell the builder a field is guaranteed when
    the response may well omit it -- the "wrong" the spec forbids over "honest".
    """
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return schema
    if isinstance(schema.get("required"), list):
        return schema          # a model already said exactly which keys survive
    identifier = _identifier_field(props)
    return {**schema, "required": [identifier]} if identifier else schema


@lru_cache(maxsize=1)
def _ab_requests() -> dict[tuple[str, str], str]:
    """(service, real path) -> AutomationBench's prose for the REQUEST body.

    The only place that says how to BUILD an opaque field: Gmail's send takes
    `raw`, "base64url-encoded RFC 2822", and nothing in the parameter's own
    description tells a planner what bytes go in it. Five endpoints across the 47
    carry such a field; the prose is copied into their helper text verbatim.
    """
    from wb_world.openapi import real_path
    out: dict[tuple[str, str], str] = {}
    for service, doc in sorted(_raw_schemas().items()):
        for ep in doc.get("endpoints") or ():
            request = ep.get("request")
            if isinstance(request, str) and request.strip():
                out.setdefault((service, real_path(service, ep["path"])), request.strip())
    return out


def _body_helper(service: str, path: str, name: str, description: str) -> str:
    """The parameter's own description, plus how the endpoint says to build a body.

    Appended only when the field is opaque -- a blob the planner must assemble
    (base64, RFC 2822, an octet stream) rather than a plain value it can supply.
    """
    helper = _helper(description, name, "body")
    prose = _ab_requests().get((service, path), "")
    if prose and re.search(r"base64|rfc\s*2822|octet-stream", prose, re.I):
        return f"{helper} The endpoint's request body: {prose}"
    return helper


def _is_id(name: str) -> bool:
    return name == "id" or name.lower().endswith("id") or name.endswith("_id")


def _entity_type(path: str, param: str) -> str:
    """The resource an id addresses: the path segment before its placeholder.

    ponytail: naive -- the segment before `{param}`, singularised. Ceiling: a
    path whose preceding segment is not the resource noun (none in the 47 specs)
    reads as the wrong entity. Upgrade: a per-service entity map.
    """
    segments = [s for s in path.strip("/").split("/") if s]
    for i, seg in enumerate(segments):
        if seg == "{%s}" % param:
            for prev in reversed(segments[:i]):
                if not prev.startswith("{"):
                    return _slugify(_singular(prev)).replace("-", "_")
            break
    # no preceding segment: fall back to the id's own name (baseId -> base)
    stem = re.sub(r"(_id|Id|ID|id)$", "", param) or param
    return _slugify(_singular(stem)).replace("-", "_")


def _helper(description: str, name: str, where: str) -> str:
    return description.strip() or f"The {name} to use in the request {where}."


def _param(name: str, classification: str, location: str, json_path: str,
           type_: str, required: bool, helper: str, **extra: Any) -> dict[str, Any]:
    """One CanonicalParam. Key order is irrelevant: the importer sorts by name."""
    out = {"name": name, "classification": classification, "location": location,
           "json_path": json_path, "type": type_, "required": required}
    out.update(extra)
    out["constraints"] = {"helper_text": helper}
    return out


def _schema_type(schema: dict[str, Any]) -> str:
    t = schema.get("type")
    return t if t in {"string", "number", "integer", "boolean", "array", "object"} else "string"


def _default_value(service: str, path: str, name: str, schema: dict[str, Any]) -> Any:
    """The documented default of a parameter, or None.

    Gmail's `userId` is the case the spec calls out: AutomationBench declares
    `"default": "me"`, so it is a `selected` parameter with that preset -- not an
    `entity_reference` to a `user` no action ever creates, which is what made
    v4.1 tell the builder to find an id it could never resolve.
    """
    value = schema.get("default")
    return value if isinstance(value, (str, int, float, bool)) and value != "" else None


def _parameters(service: str, path: str, verb: str, op: dict[str, Any],
                body: dict[str, str], fields: dict[str, dict[str, Any]],
                observed: dict[str, Any]) -> list[dict[str, Any]]:
    """One parameter per URL placeholder and per top-level body key.

    This array is what the discovery service binds `{{...}}` to at execution
    time; without it the importer throws on `parameters.map` (seeds-normalize).
    """
    out: list[dict[str, Any]] = []
    placed = set(_query_names(op)) | set(_PATH_VAR.findall(path))
    for spec in op.get("parameters", []):
        where, name = spec.get("in"), spec.get("name")
        # every token the URL carries needs exactly one parameter, and nothing
        # else does: an unplaced parameter is silently dropped by the engine.
        if where not in ("path", "query") or name not in placed:
            continue
        schema = spec.get("schema") or {}
        default = _default_value(service, path, name, schema)
        entity = _is_id(name) and where == "path" and default is None
        # A real id, never "{{name}}": the executor uses it as the sample value.
        # An id addressing this resource takes the resource's own observed id.
        sample = observed if where == "path" else {}
        if entity and name.lower() in ("id", "recordid") and "id" in observed:
            sample = {name.replace("_", "").lower(): observed["id"]}
        type_ = _schema_type(schema)
        extra: dict[str, Any] = {
            "example_value": default if default is not None
            else _example(name, type_, sample, spec.get("description") or "")}
        if entity:
            extra["entity_type"] = _entity_type(path, name)
        if type_ == "array":
            # the element type, or the builder cannot tell what a row holds
            extra["items"] = _schema_type(schema.get("items") or {})
        if schema.get("format") in ("email", "date-time", "uuid", "date", "uri"):
            extra["format"] = schema["format"]
        constraints = {}
        for bound in ("minimum", "maximum"):
            if bound in schema:
                constraints[{"minimum": "min", "maximum": "max"}[bound]] = str(schema[bound])
        enum = _enum_options(schema.get("enum"))
        if default is not None and not enum:
            enum = [{"value": str(default)}]
        if enum:
            constraints["enum_options"] = enum
        # A path parameter is always required: an unfilled path token is
        # substituted literally and the request dispatches to a nonsense URL.
        classification = ("selected" if default is not None else
                          "entity_reference" if entity else "typed")
        p = _param(name, classification, where,
                   f"$.steps[0].url.{name}", type_,
                   True if where == "path" else bool(spec.get("required")),
                   _helper(spec.get("description") or "", name, where), **extra)
        p["constraints"].update(constraints)
        out.append(p)

    schema = ((op.get("requestBody") or {}).get("content", {})
              .get("application/json", {}).get("schema") or {})
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    for name in body:                       # body_template's own top-level keys
        prop = props.get(name) or fields.get(name) or {}
        # A create may declare its required fields; an update must not -- a
        # missing field is pruned, while `required` makes the engine invent one.
        is_required = verb == "create" and name in required
        type_ = _schema_field_type(prop)
        extra: dict[str, Any] = {"example_value": _example(name, type_, observed)}
        if type_ == "array":
            extra["items"] = _schema_type(prop.get("items") or {})
        if prop.get("format") in ("email", "date-time", "uuid", "date", "uri"):
            extra["format"] = prop["format"]
        # `source_form_field` is dropped: it is for captured HTML forms and only
        # feeds the entity-type resolver, giving the builder nothing.
        p = _param(name, "typed", "body", f"$.steps[0].body.{name}", type_, is_required,
                   _body_helper(service, path, name,
                                prop.get("description") or ""), **extra)
        enum = _enum_options(prop.get("enum"))
        if enum:
            p["constraints"]["enum_options"] = enum
        out.append(p)
    return out


# The verb phrase each action verb opens with, and whether it names one record
# or many. This plus the resource noun is the whole label.
_LABEL_VERB = {"create": ("Create", "a"), "read": ("Read", "a"), "list": ("List", "many"),
               "update": ("Update", "a"), "delete": ("Delete", "a")}
_ARTICLE = re.compile(r"^[aeiou]", re.I)


def _label(verb: str, resource: str, op: dict[str, Any], obj: str = "") -> str:
    """A short verb phrase, <= 80 chars: "Update a contact", "List messages".

    This is the ONLY text `search_actions` shows the builder per action (with
    area and verb), and the headline of `inspect_action_schema`; `description` is
    never served at build time. v4.1 put the OpenAPI sentence here, so 555 labels
    equalled their description and 277 ran past 80 chars -- the builder ranked
    and chose on truncated prose.
    """
    word, number = _LABEL_VERB.get(verb, ("Use", "a"))
    # The id's object facet already carries whatever distinguishes this action
    # from its siblings (`employees-files` vs `files`); the bare resource does
    # not, and two actions a product cannot tell apart are two the builder
    # cannot choose between.
    noun = _slugify(obj or resource).replace("-", " ")
    noun = _singular(noun) if number == "a" else noun
    article = "" if number == "many" else ("an " if _ARTICLE.match(noun) else "a ")
    label = f"{word} {article}{noun}".strip()
    return label[:80]


def _area(resource: str) -> str:
    """A lowercase kebab plural noun: the search filter and the entity-matching key.

    v4.1 emitted 220 capitalized sObject names (`Contact`), which the full-text
    index and the entity resolver both read literally. The plural is the spec's
    convention (`messages`, `contacts`); the resolver singularizes it again when
    it matches entities, so the two spellings of one resource collapse to one
    area rather than splitting the search index.
    """
    return _plural(_slugify(resource) or "root")


def _plural(noun: str) -> str:
    """The inverse of `_singular`, for the nouns those rules can undo."""
    if not noun or noun.endswith("s"):
        return noun
    if re.search(r"(ch|sh|x|z)$", noun):
        return noun + "es"
    if re.search(r"[^aeiou]y$", noun):
        return noun[:-1] + "ies"
    return noun + "s"


def _action(base: str, service: str, path: str, method: str,
            op: dict[str, Any], action_id: str) -> dict[str, Any]:
    verb, resource = _verb(method, path), _resource(path)
    product_id = product_slug(service)
    # Every writable field of the resource must be a token: a field with no token
    # in body_template never reaches the wire (there is no open bag).
    noun, fields = _resource_fields(service, path, method)
    observed = _observed(service, noun)
    # The spec's own response schema when it describes something; the 47
    # simulated documents carry a bare {"type": "object"}, so in practice the
    # sources below -- AutomationBench's models, its response prose and its
    # handler code -- are what describe the body.
    declared = (op["responses"]["200"]["content"]["application/json"]["schema"]
                if "200" in op.get("responses", {}) else {})
    if _answers_empty(service, path, method):
        # AutomationBench says this endpoint answers nothing worth typing, and
        # the front door serves `{}` at 200. Nothing to extract, nothing to name:
        # the builder reads this as known_empty, "run for effect".
        schema = {"$schema": JSON_SCHEMA, "type": "object",
                  "description": "Empty object on success; no record is echoed back.",
                  "properties": {}, "additionalProperties": False}
        extract = {}
    elif declared.get("properties") or declared.get("items"):
        schema, extract = _with_required(declared), _extract(declared)
    elif _envelope_for(service, path, method):
        # v5.1: the handler that serves the request is the FIRST source, not the
        # last. Every other source describes a RECORD, and the wire is very often
        # an envelope around one -- `{Customer: {...}}`, `{organization: {...}}`,
        # `{success, calendar}` -- or something the record does not resemble at
        # all: the Sheets read answers `{spreadsheetId, properties, sheets}`,
        # not the AB `Spreadsheet` record's `{id, title, worksheets}`, which is
        # why Monarch's planner said the catalog "doesn't expose the data" and
        # refused every Sheets task (4 Sep 2026).
        schema = _envelope_schema(service, path, method)
        # a collection under a key keeps the service's own record as its rows,
        # instead of the open row `_envelope_schema` falls back to
        for key, prop in (schema.get("properties") or {}).items():
            if prop.get("type") != "array":
                continue
            row = _record_schema(service, path if _singular(key) == key
                                 else f"{path}/{key}")
            stub = _STUB_LIST_FIELDS.get((service, key))
            if stub:
                # the handler projects a stub, not the record: Gmail's list
                # hardcodes format="minimal" and answers {id, threadId} only.
                # Advertising the record here tells the planner it can skip the
                # read -- the very step this file exists to make plannable.
                fields = row.get("properties") or {}
                row = {"type": "object",
                       "properties": {f: fields.get(f, {"type": "string"}) for f in stub}}
            if row.get("properties"):
                prop["items"] = _with_required(row)
        # ...and an envelope holding ONE open object is holding the record: type
        # it, or a create's id is unreachable and the action declares no entity
        # at all (Asana answers `{data: {gid, name, ...}}`).
        objects = [k for k, p in (schema.get("properties") or {}).items()
                   if p.get("type") == "object" and not p.get("properties")]
        if len(objects) == 1:
            record = _record_schema(service, path)
            if record.get("properties"):
                schema["properties"][objects[0]] = _with_required(record)
        schema = {"$schema": JSON_SCHEMA, **_with_required(schema)}
        # The handler writes an envelope's keys unconditionally into its success
        # literal, so every one of them IS present -- unlike a record's fields,
        # which `to_display_dict` prunes when empty. Saying so is what turns the
        # builder's presence from `unknown` into `required` (SPEC.md 6.3).
        # Every key of the literal is certain whether or not its VALUE said what
        # type it is: the handler writes them all on the success path. Only the
        # ones appended behind a guard are left out.
        certain = sorted(k for k in (schema.get("properties") or {})
                         if (service, k) not in _CONDITIONAL)
        if certain:
            schema["required"] = certain
        # Every top-level key is an output: an array is extracted whole (the
        # grammar has no `[*]`), a scalar or nested object by its own name.
        extract = {n: f"$.{n}" for n in (schema.get("properties") or {})
                   if re.fullmatch(r"\w+", n)}
    elif verb == "list":
        # The front door wraps a collection under its key -- {"messages": [...]},
        # never a bare array. The ARRAY ITSELF is the output: the engine's path
        # grammar has no `[*]`, so v4.1's `$.messages[*].id` resolved to nothing
        # at run time. The builder iterates via the node's `items.path`, which the
        # lint grounds on exactly this extract path plus the schema's rows.
        record, key = _record_schema(service, path), _collection_key(service, path, method)
        stub = _STUB_LIST_FIELDS.get((service, key))
        if stub:
            props = record.get("properties") or {}
            record = {"type": "object",
                      "properties": {f: props.get(f, {"type": "string"}) for f in stub}}
        if not (record.get("properties") or {}):
            # A row whose shape the caller chooses: a SOQL/SOSL record carries
            # exactly the SELECTed fields, so no fixed record describes it. Mark
            # the row an open map -- the builder is then told to use the row it
            # actually gets and never to invent names under it -- and declare the
            # identifier the service spells its records with, when it has one.
            record = {"type": "object", "additionalProperties": True}
            identifier = _service_identifier(service)
            if identifier:
                record["properties"] = {identifier: {"type": "string"}}
        props: dict[str, Any] = {key: {"type": "array", "items": _with_required(record)}}
        # the paging/count scalars the same prose declares beside the collection
        props.update(_declared_scalars(service, path, method, skip=key))
        schema = {"$schema": JSON_SCHEMA, "type": "object",
                  "properties": props, "required": [key]}
        extract = ({key: f"$.{key}"} if re.fullmatch(r"\w+", key) else {})
        extract.update({n: f"$.{n}" for n in props if n != key})
    else:                       # read, create, update: the response is the record
        # ...unless the prose declares a flat envelope instead (a Salesforce
        # create answers `{id, success}`, never the record it just wrote).
        envelope = _declared_envelope(service, path, method)
        schema = ({"type": "object", "properties": envelope} if envelope
                  else _record_schema(service, path))
        if not (schema.get("properties") or {}):
            # Nothing described the body, so read the handler that serves it:
            # Slack answers `{ok, channel: {...}}`, and the created id lives
            # under `channel` -- the only place that says so is the code.
            schema = _envelope_schema(service, path, method) or schema
        extract = _extract(schema)
        schema = {"$schema": JSON_SCHEMA, **_with_required(schema)}
        # Every extract path must be reachable in the schema, or the builder
        # wires a field the response will not carry.
        props = schema.get("properties") or {}
        extract = {n: p for n, p in extract.items() if n in props}
    # A field the URL already carries -- a path placeholder or a declared query
    # parameter -- is not a body field: one token in two places is one parameter
    # the engine binds twice.
    in_path = set(_PATH_VAR.findall(path)) | set(_query_names(op))
    # GET, HEAD and DELETE carry no body at all: the engine serializes any
    # non-null body_template, `{}` included, and fetch rejects those methods with
    # a body ("Request with GET/HEAD method cannot have body"). v4.1 still sent
    # `{}` plus a content-type on 60 DELETE steps.
    bodyless = method.upper() in _BODYLESS
    body = {} if bodyless else (_body_template(op)
                                or {f: "{{%s}}" % f for f in sorted(fields)
                                    if f not in in_path})
    impl: dict[str, Any] = {
        "id": f"impl_{product_id}_{_slugify(op.get('operationId') or action_id)}_public",
        "source": "public",
        "discovered_at": STAMP,
        # true for GET/PUT/PATCH/DELETE, false only for a POST create
        "idempotent": method.upper() != "POST",
        "http_template": {
            "call_type": "rest",
            "transport_mode": "header_only",
            "auth_scheme": "none",
            "auth_captured": False,
            "steps": [{
                "method": method.upper(),
                "url_template": _url_template(base, service, path, op),
                # Explicit null, never an omitted key: both hash the same after
                # import, but the canonical form says the absence is deliberate.
                # No content-type on a bodyless step either -- harmless, but noise
                # the builder reads as a promise of a request body.
                **({"headers_template": {}, "body_template": None} if bodyless else
                   {"headers_template": {"content-type": "application/json"},
                    "body_template": body}),
                "response_template": {"status": 200, "extract": extract,
                                      "schema": schema},
            }],
        },
        # Both arrays are required: seeds-normalize maps over them unguarded.
        "parameters": _parameters(service, path, verb, op, body, fields, observed),
        "creates_entities": [],
    }
    if verb == "create":
        entity = _slugify(_singular(resource)).replace("-", "_")
        # `type`, not `entity`: buildKnownEntityTypes reads ce.type, and an
        # undefined there is what made /v1/seeds answer 500 (4 Sep 2026).
        #
        # identifier_path MUST be one of this step's extract paths: the engine
        # binds the created id through that extract, and a path matching none
        # falls back to the first extract name -- usually the wrong field. v4.1
        # wrote `$.id` unconditionally, so 70 creates were unchainable.
        paths = set(extract.values())
        # the same identifier the schema promises, so the two never disagree
        named = _identifier_field({n: None for n in extract})
        identifier = f"$.{named}" if named and f"$.{named}" in paths else ""
        if not identifier:
            # An envelope keeps the record one level down (`{ok, channel: {id}}`),
            # and the engine's grammar reaches it: `$.channel.id`. The key that
            # holds it also names the entity better than an RPC path segment
            # does (`channel`, not `conversations_create`).
            identifier = _nested_identifier(schema, extract)
            if identifier:
                entity = _slugify(_singular(identifier.split(".")[1])).replace("-", "_")
        paths = set(extract.values())      # _nested_identifier may have added one
        impl["creates_entities"] = [{
            "type": entity,
            # the response FIELD holding the human name, not a token
            "display_name_from": next((k for k in ("name", "title", "Name", "subject")
                                       if f"$.{k}" in paths), ""),
            "identifier_path": identifier,
            "identifier_keys": []}] if identifier else []
    return {
        "business_action": {
            "id": action_id,
            "label": _label(verb, resource, op, action_id.split(":")[-1]),
            "product_id": product_id,
            "product_domain": _domain(base),
            "area": _area(resource),
            "state": "active",
            "verb": verb,
            "description": op.get("description") or op.get("summary") or "",
            "source_url": f"{base}/openapi/{service}.json",
            "first_seen_at": STAMP,
            "last_seen_at": STAMP,
        },
        "implementations": [impl],
    }


def _service_actions(base: str, service: str, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """file name -> action document, ids unique within the folder."""
    out: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    slug = product_slug(service)
    for path in sorted(doc["paths"]):
        for method in sorted(doc["paths"][path]):
            op = doc["paths"][path][method]
            # Three facets, all [a-z0-9-]: the importer keeps a well-formed id
            # verbatim and re-mints anything else, which collides (4 Sep 2026).
            verb = _verb(method, path)
            action_id = f"{slug}:{verb}:{_slugify(_resource(path))}"
            if action_id in used:
                # Same verb+resource on another path: discriminate with the
                # segments that differ, shortest suffix that is still unique.
                segments = [_slugify(s) for s in path.strip("/").split("/")
                            if s and not s.startswith("{")]
                candidates = [f"{slug}:{verb}:{'-'.join(segments[-size:])}"
                              for size in range(2, len(segments) + 1)]
                # A one-segment path (POST /tags vs POST /x/{id}/tags) cannot be
                # widened, so the whole path -- always distinct -- is the last resort.
                candidates.append(f"{slug}:{verb}:{_slugify(path)}")
                # method included last: two verbs can slugify a path the same way
                candidates.append(f"{slug}:{verb}:{_slugify(path + '-' + method)}")
                action_id = next(c for c in candidates if c not in used)
            used.add(action_id)
            out[action_id.replace(":", "_") + ".json"] = _action(
                base, service, path, method, op, action_id)
    return out


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def _meta(service: str, base: str) -> dict[str, Any]:
    domain = _domain(base)
    return {"display_name": f"{service.replace('_', ' ').title()} (benchmark)",
            "domain": domain, "host_pattern": domain,
            "login_url": None, "requires_login": False}


def generate(out_dir, shim_public_url: str) -> Summary:
    """Write one folder per service. Raises SeedGap without writing if anything is off."""
    base = shim_public_url.rstrip("/")
    docs = build_all(base)
    operations = sum(len(m) for d in docs.values() for m in d["paths"].values())
    folders = {product_slug(svc): _service_actions(base, svc, doc) for svc, doc in docs.items()}
    files = {name: doc for actions in folders.values() for name, doc in actions.items()}
    gaps = [g for actions in folders.values() for g in _validate_actions(actions)]
    if gaps:
        raise SeedGap(gaps)
    if len(files) != operations:  # a duplicate file name would silently drop an operation
        raise SeedGap([Gap("<set>", f"{len(files)} files for {operations} operations")])

    out = Path(out_dir)
    written = 0
    for folder, actions in sorted(folders.items()):
        d = out / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "_meta.json").write_text(_dump(_meta(folder.removeprefix("bench-"), base)), encoding="utf-8")
        for name, doc in sorted(actions.items()):
            (d / name).write_text(_dump(doc), encoding="utf-8")
            written += 1
    _write_manifest(out, base, folders)
    return Summary(operations_in_spec=operations, files_written=written,
                   folders=sorted(folders))


VERSION = "v5.1"


def folder_sha256(folder) -> str:
    """sha256 over sorted relative paths and bytes of every *.json under `folder`.

    The knowledge base's fingerprint: the same inputs must produce the same
    digest, so a rerun of `wb monarch setup` is a no-op and two rounds' seeds are
    comparable. `ok.txt` itself is excluded -- it carries the digest.
    """
    import hashlib
    h = hashlib.sha256()
    root = Path(folder)
    for f in sorted(root.rglob("*.json"), key=lambda p: p.relative_to(root).as_posix()):
        h.update(f.relative_to(root).as_posix().encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()


def _write_manifest(out: Path, base: str, folders: dict[str, dict[str, Any]]) -> None:
    """`ok.txt`: what was written, and the digest that identifies it."""
    actions = [doc for acts in folders.values() for doc in acts.values()]
    steps = [d["implementations"][0]["http_template"]["steps"][0] for d in actions]
    manifest = {
        "version": VERSION,
        "canonical": True,
        "products": len(folders),
        "actions": len(actions),
        "actions_with_response_schema": sum(
            1 for s in steps if (s["response_template"].get("schema") or {}).get("properties")),
        "front_door": base,
        "generated_from": "wb monarch setup",
        "sha_rule": "sha256 over sorted relative paths and bytes of every *.json under the folder",
        "sha256": folder_sha256(out),
        # the canonical rules this set was written to, each checkable in the bytes
        "bodyless_body_null": all(s["body_template"] is None for s in steps
                                  if s["method"] in _BODYLESS),
        "no_wildcard_extracts": all("[*]" not in v for s in steps
                                    for v in s["response_template"]["extract"].values()),
        "enum_options_are_strings": all(
            isinstance(o.get("value"), str)
            for d in actions for p in d["implementations"][0]["parameters"]
            for o in (p.get("constraints") or {}).get("enum_options") or ()),
        "hyphen_slugs": all(re.fullmatch(r"bench-[a-z0-9-]+", f) for f in folders),
    }
    (out / "ok.txt").write_text(_dump(manifest), encoding="utf-8")


# ---------------------------------------------------------------- validation

_AUTH = {"none", "bearer", "basic", "api_key"}
_ACTION_ID = re.compile(r"[a-z0-9-]+:(create|read|list|update|delete):[a-z0-9-]+")
# The executor's dot-path grammar (engine/extract.ts): `$`, `$.a.b`, numeric
# `[n]` indices. No `[*]`, no filter, no wildcard.
_EXTRACT_PATH = re.compile(r"\$(?:\.[A-Za-z0-9_-]+|\[\d+\])*")
_SEGMENT = re.compile(r"\.[A-Za-z0-9_-]+|\[\d+\]")


def _schema_at(schema: Any, path: str) -> Any:
    """Walk a JSON Schema along an extract path; None when it is unreachable.

    Mirrors the Monarch validator's own walker, so a path this accepts is one the
    builder can wire to a field the response really carries.
    """
    if not isinstance(schema, dict):
        return None
    node: Any = schema
    for seg in _SEGMENT.findall(path[1:]):
        if not isinstance(node, dict):
            return None
        if seg.startswith("["):
            if node.get("type") != "array" or not isinstance(node.get("items"), dict):
                return None
            node = node["items"]
            continue
        key = seg[1:]
        props = node.get("properties")
        if isinstance(props, dict) and key in props:
            node = props[key]
        elif node.get("additionalProperties") is True:
            node = {}
        elif isinstance(node.get("additionalProperties"), dict):
            node = node["additionalProperties"]
        else:
            return None
    return node if node is not None else {}


def _gaps_in(name: str, doc: Any) -> list[str]:
    out = []
    try:
        ba = doc["business_action"]
        impl = doc["implementations"][0]
        tpl = impl["http_template"]
        step = tpl["steps"][0]
        rt = step["response_template"]
    except (KeyError, IndexError, TypeError) as e:
        return [f"missing {e}"]
    if tpl.get("auth_scheme") not in _AUTH:
        out.append(f"auth_scheme {tpl.get('auth_scheme')!r} is not one of {sorted(_AUTH)}")
    if not isinstance(rt.get("schema"), dict) or not rt["schema"]:
        out.append("response_template.schema is empty")
    extract = rt.get("extract")
    if not isinstance(extract, dict):
        # {} is canonical: a response with no body has nothing to name, and the
        # builder reads that as known_empty ("run for effect").
        out.append("response_template.extract must be an object")
    elif not all(isinstance(v, str) and _EXTRACT_PATH.fullmatch(v) for v in extract.values()):
        bad = sorted(v for v in extract.values()
                     if not (isinstance(v, str) and _EXTRACT_PATH.fullmatch(str(v))))
        # `[*]` is the v4.1 defect: the engine's grammar is `$.a.b` with numeric
        # indices only, so a wildcard path resolved to nothing at run time.
        out.append(f"extract_path_ungrammatical: {bad[:4]}")
    elif not all(re.fullmatch(r"\w+", n) for n in extract):
        out.append(f"extract_name_not_word: "
                   f"{sorted(n for n in extract if not re.fullmatch(r'\w+', n))[:4]}")
    else:
        # every extract path must be reachable in the schema, or the builder
        # wires a field the response will not carry
        unreachable = sorted(p for p in extract.values()
                             if _schema_at(rt.get("schema"), p) is None)
        if unreachable:
            out.append(f"extract_not_in_schema: {unreachable[:4]}")
    if ba.get("verb") == "create":
        # A create with nothing extractable declares no entity rather than a
        # dangling identifier_path: the engine would bind the created id to the
        # first extract name, usually the wrong field.
        for ce in impl.get("creates_entities") or []:
            if not ce.get("type"):
                out.append("creates_entities[].type is empty (the importer reads `type`)")
            ident = ce.get("identifier_path")
            if ident and ident not in set((extract or {}).values()):
                out.append(f"identifier_path_not_extracted: {ident!r} is not one of "
                           f"{sorted(set((extract or {}).values()))[:4]}")
    method = str(step.get("method") or "").upper()
    if method in _BODYLESS and step.get("body_template") is not None:
        out.append(f"{method} carries a body_template: the engine serializes even "
                   "{} and fetch rejects the request")
    headers = step.get("headers_template") or {}
    has_body = step.get("body_template") is not None
    ctype = any(k.lower() == "content-type" for k in headers)
    if not has_body and ctype:
        out.append("content-type on a bodyless step")
    if has_body and not ctype:
        out.append("body_template without a content-type header")
    for p in impl.get("parameters") or []:
        enum = (p.get("constraints") or {}).get("enum_options")
        if enum is not None and not (isinstance(enum, list) and all(
                isinstance(o, dict) and isinstance(o.get("value"), str) for o in enum)):
            # a numeric value fails the executor's zod parse: the action becomes
            # unexecutable, not merely degraded
            out.append(f"enum_options_not_string: {p.get('name')!r}")
        if p.get("location") == "path" and p.get("required") is not True:
            out.append(f"path_parameter_optional: {p.get('name')!r}")
    # Every {{x}} in the URL and every top-level body key needs exactly one
    # parameter: that array is what binds them to workflow inputs.
    if not _ACTION_ID.fullmatch(str(ba.get("id") or "")):
        out.append(f"id_malformed: {ba.get('id')!r} is not "
                   "<product-slug>:<verb>:<object> in [a-z0-9-]")
    want = set(re.findall(r"\{\{(\w+)\}\}", step.get("url_template", "")))
    want |= set(step.get("body_template") or {})
    names = [p.get("name") for p in impl.get("parameters") or []]
    if sorted(names) != sorted(set(names)) or set(names) != want:
        out.append(f"parameters_incomplete: {sorted(want - set(names))} unbound, "
                   f"{sorted(set(names) - want)} extra")
    # The same mismatch, named per side: a body key nothing binds never reaches
    # the wire, and a parameter with no token is dead weight the engine may fill.
    body_keys = set(step.get("body_template") or {})
    body_params = {p.get("name") for p in impl.get("parameters") or []
                   if p.get("location") == "body"}
    if body_keys - body_params:
        out.append(f"body_field_without_parameter: {sorted(body_keys - body_params)}")
    if body_params - body_keys:
        out.append(f"parameter_without_token: {sorted(body_params - body_keys)}")
    url = step.get("url_template", "")
    if not url.startswith("http"):
        out.append(f"url_template {url!r} is not an absolute URL")
    # ponytail: a file alone cannot say which parameters the operation declared, so only
    # the placeholder syntax is checked here; generate() builds them from the spec.
    if url.count("{") != url.count("}") or not all(re.fullmatch(r"\w+", p)
                                                   for p in re.findall(r"\{\{(.*?)\}\}", url)):
        out.append(f"malformed placeholder in url_template {url!r}")
    return out


def _validate_actions(actions: dict[str, dict[str, Any]]) -> list[Gap]:
    return [Gap(name, g) for name, doc in sorted(actions.items()) for g in _gaps_in(name, doc)]


def validate(folder) -> list[Gap]:
    """Check every action file under `folder` (recursively) against the acceptance bar."""
    gaps: list[Gap] = []
    for f in sorted(Path(folder).rglob("*.json")):
        if f.name == "_meta.json":
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            gaps.append(Gap(f.name, f"unreadable: {e}"))
            continue
        gaps.extend(Gap(f.name, g) for g in _gaps_in(f.name, doc))
    return gaps
