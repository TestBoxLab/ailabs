"""Public-API seed folders for Monarch's discovery service, one per simulated app.

Monarch's create + run mode needs a knowledge base it did not have to discover.
`generate` turns the 47 OpenAPI documents of `wb_world.openapi` into the
`public-api-seeds` fixture shape the discovery service imports: one folder per
service holding `_meta.json` and one business action per operation, every URL
pointing back at the episode's front door (the HTTP shim).

Output is deterministic: the same inputs write the same bytes, so a rerun of
`wb monarch setup` is a no-op and the knowledge-base hashes stay comparable.

`validate` is the mechanical half of the runbook's acceptance bar; `generate`
runs it on what it built and refuses to write anything if a gap is found.
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
    """
    props = schema.get("properties") or {}
    if props:
        return {n: f"{prefix}{n}" for n in sorted(props)}
    return {"id": f"{prefix}id"}


def _url_template(base: str, service: str, path: str, op: dict[str, Any]) -> str:
    url = f"{base}/{service}" + _PATH_VAR.sub(lambda m: "{{%s}}" % m.group(1), path)
    required = [p["name"] for p in op.get("parameters", [])
                if p.get("in") == "query" and p.get("required")]
    if required:
        url += "?" + "&".join("%s={{%s}}" % (n, n) for n in sorted(required))
    return url


def _identifier_keys(paths: dict[str, Any], path: str) -> list[str]:
    """Path parameters that sibling operations use to address this resource."""
    prefix = path.rstrip("/") + "/"
    keys: set[str] = set()
    for other in paths:
        if other.startswith(prefix):
            keys.update(_PATH_VAR.findall(other[len(prefix):]))
    return sorted(keys)


def _domain(base: str) -> str:
    return urlsplit(base).hostname or base


# Identifiers and stamps the server owns: never writable in a request body.
READ_ONLY = {"id", "created_at", "createdtime", "created_time", "createdat",
             "updated_at", "updatedat", "modified_at", "etag", "self", "url",
             "object", "resource_type", "created", "updated"}

# ponytail: one example per JSON type, overridden by a real corpus value when the
# resource is one the corpus covers. Ceiling: a field the corpus never shows gets
# a generic literal. Upgrade: per-field examples in the jsonc schemas.
_EXAMPLE_BY_TYPE = {"number": 1, "boolean": True, "object": {}, "string": "example"}


def _example(name: str, type_: str, observed: dict[str, Any]) -> Any:
    """A realistic value: the corpus's own, else a type-shaped literal."""
    type_ = {"integer": "number", "array": "string"}.get(type_, type_)
    value = observed.get(name.replace("_", "").lower())
    if value not in (None, "", [], {}):
        if isinstance(value, list):
            return value[0] if value and not isinstance(value[0], (dict, list)) else "example"
        if isinstance(value, dict):
            return {}
        return value
    low = name.lower()
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
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    return "string"


def _schema_field_type(spec: dict[str, Any]) -> str:
    t = spec.get("type")
    if t in ("integer", "number"):
        return "number"
    if t in ("boolean", "object"):
        return t
    return "string"


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


def _resource_fields(service: str, path: str) -> tuple[str, dict[str, dict[str, Any]]]:
    """(resource name, writable fields) for the resource a write path addresses."""
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


# Lists whose handler projects a stub instead of the record. Gmail's
# `messages.list` hardcodes format="minimal" and returns {id, threadId} only
# (impl/gmail.py, verified against a live front door 4 Sep 2026); advertising
# the full record there would tell the planner it can skip the read -- the very
# step this file exists to make plannable. Slack's lists return whole records.
# ponytail: one observed exception, not a per-handler projection model.
# Upgrade: probe each list once and record what it actually returned.
_STUB_LIST_FIELDS = {("gmail", "messages"): ("id", "threadId")}


# The noun an RPC verb answers with. Anything unlisted (`info`, `list`, `get`)
# answers about the segment before the dot, which is already the resource.
_RPC_NOUN = {"history": "message", "replies": "message", "messages": "message",
             "members": "user", "lookupbyemail": "user"}


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
    for segment in reversed(segments):
        for candidate in (segment, _singular(segment)):
            declared = schemas.get(candidate.lower())
            if declared:
                props = {name: {"type": _schema_field_type(spec)}
                         for name, spec in declared.items()}
                break
        if props:
            break
    for segment in reversed(segments):
        observed = _corpus_fields(service, segment)
        if observed:
            for name, value in observed.items():
                # pydantic's alias for the reserved word: the wire carries `from`.
                props.setdefault(name.rstrip("_") if name == "from_" else name,
                                 {"type": _json_type(value)})
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
                props.setdefault(name, {"type": _schema_field_type(spec)})
    return {"type": "object", "properties": props} if props else {"type": "object"}


def _collection_key(service: str, path: str) -> str:
    """The wrapper key a list answers under: {"messages": [...]}, never a bare array."""
    segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    return segments[-1] if segments else "items"


def _corpus_fields(service: str, resource: str) -> dict[str, Any]:
    """Raw (unnormalised) corpus fields for a resource, or {} when it has none."""
    for (svc, collection), values in _corpus_examples().items():
        if svc == service and collection.lower().rstrip("s") == resource.lower().rstrip("s"):
            return values
    return {}


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


def _parameters(service: str, path: str, verb: str, op: dict[str, Any],
                body: dict[str, str], fields: dict[str, dict[str, Any]],
                observed: dict[str, Any]) -> list[dict[str, Any]]:
    """One parameter per URL placeholder and per top-level body key.

    This array is what the discovery service binds `{{...}}` to at execution
    time; without it the importer throws on `parameters.map` (seeds-normalize).
    """
    out: list[dict[str, Any]] = []
    for spec in op.get("parameters", []):
        where, name = spec.get("in"), spec.get("name")
        # only required query parameters become placeholders (see _url_template)
        if where not in ("path", "query") or (where == "query" and not spec.get("required")):
            continue
        schema = spec.get("schema") or {}
        entity = _is_id(name) and where == "path"
        # A real id, never "{{name}}": the executor uses it as the sample value.
        # An id addressing this resource takes the resource's own observed id.
        sample = observed if where == "path" else {}
        if entity and name.lower() in ("id", "recordid") and "id" in observed:
            sample = {name.replace("_", "").lower(): observed["id"]}
        extra: dict[str, Any] = {
            "example_value": _example(name, _schema_type(schema), sample)}
        if entity:
            extra["entity_type"] = _entity_type(path, name)
        constraints = {}
        for bound in ("minimum", "maximum"):
            if bound in schema:
                constraints[{"minimum": "min", "maximum": "max"}[bound]] = str(schema[bound])
        p = _param(name, "entity_reference" if entity else "typed", where,
                   f"$.steps[0].url.{name}", _schema_type(schema),
                   bool(spec.get("required")),
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
        p = _param(name, "typed", "body", f"$.steps[0].body.{name}", type_, is_required,
                   _helper(prop.get("description") or "", name, "body"),
                   source_form_field=name,
                   example_value=_example(name, type_, observed))
        if prop.get("enum"):
            p["constraints"]["enum_options"] = [{"value": v} for v in prop["enum"]]
        out.append(p)
    return out


def _action(base: str, service: str, doc: dict[str, Any], path: str, method: str,
            op: dict[str, Any], action_id: str) -> dict[str, Any]:
    verb, resource = _verb(method, path), _resource(path)
    product_id = product_slug(service)
    # Every writable field of the resource must be a token: a field with no token
    # in body_template never reaches the wire (there is no open bag).
    noun, fields = _resource_fields(service, path)
    observed = _observed(service, noun)
    # (a) the spec's own response schema when it describes something; the 47
    # simulated documents carry a bare {"type": "object"}, so in practice (b)+(c)
    # -- the world schema and the corpus -- are what fill this in.
    declared = (op["responses"]["200"]["content"]["application/json"]["schema"]
                if "200" in op.get("responses", {}) else {})
    if declared.get("properties") or declared.get("items"):
        schema, extract = declared, _extract(declared)
    elif verb == "list":
        # The front door wraps a collection under its plural key -- {"messages":
        # [...]}, never a bare array -- so `$[*]` would miss it entirely.
        record, key = _record_schema(service, path), _collection_key(service, path)
        stub = _STUB_LIST_FIELDS.get((service, key))
        if stub:
            props = record.get("properties") or {}
            record = {"type": "object",
                      "properties": {f: props.get(f, {"type": "string"}) for f in stub}}
        schema = {"type": "object",
                  "properties": {key: {"type": "array", "items": record}}}
        extract = _extract(record, f"$.{key}[*].")
    elif verb == "delete":
        schema, extract = {"type": "object"}, {"id": "$.id"}
    else:                       # read, create, update: the response is the record
        schema = _record_schema(service, path)
        extract = _extract(schema)
    # A field that already addresses the record in the path is not a body field.
    in_path = set(_PATH_VAR.findall(path))
    body = {} if method == "get" else (_body_template(op)
                                       or {f: "{{%s}}" % f for f in sorted(fields)
                                           if f not in in_path})
    impl: dict[str, Any] = {
        "id": f"impl_{product_id}_{_slugify(op.get('operationId') or action_id)}_public",
        "source": "public",
        "discovered_at": STAMP,
        "idempotent": method == "get",
        "http_template": {
            "call_type": "rest",
            "transport_mode": "header_only",
            "auth_scheme": "none",
            "auth_captured": False,
            "steps": [{
                "method": method.upper(),
                "url_template": _url_template(base, service, path, op),
                # A GET carries no body and no content-type: an empty body
                # template made the engine send "{}" on GET, which its HTTP
                # client refuses ("GET/HEAD method cannot have body", 4 Sep).
                **({} if method == "get" else
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
        impl["creates_entities"] = [{
            "type": entity,
            "display_name_from": next(("{{%s}}" % k for k in ("name", "title") if k in body),
                                      ""),
            "identifier_path": "$.id",
            "identifier_keys": _identifier_keys(doc["paths"], path) or ["id"]}]
    return {
        "business_action": {
            "id": action_id,
            "label": op.get("summary") or f"{verb.capitalize()} {resource}",
            "product_id": product_id,
            "product_domain": _domain(base),
            "area": resource,
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
                base, service, doc, path, method, op, action_id)
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
    return Summary(operations_in_spec=operations, files_written=written,
                   folders=sorted(folders))


# ---------------------------------------------------------------- validation

_AUTH = {"none", "bearer", "basic", "api_key"}
_ACTION_ID = re.compile(r"[a-z0-9-]+:(create|read|list|update|delete):[a-z0-9-]+")


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
    if not isinstance(extract, dict) or not extract:
        out.append("response_template.extract is empty")
    elif not all(isinstance(v, str) and v.startswith("$.") for v in extract.values()):
        out.append("response_template.extract values must be $. paths")
    elif ba.get("verb") in ("read", "list") and list(extract) == ["id"]:
        # v3's whole read surface looked like this, and the planner could not
        # chain past the id. A gap only when the schema shows there *are* fields
        # to name: a genuinely opaque resource has nothing better to offer.
        props = (rt.get("schema") or {}).get("properties") or {}
        # For a list the fields live on the wrapped record, not on the wrapper:
        # counting the wrapper key itself would call every opaque list a gap.
        collection = next((v for v in props.values()
                           if isinstance(v, dict) and v.get("type") == "array"), None)
        known = ((collection.get("items") or {}).get("properties") or {}
                 if collection is not None else props)
        if known:
            out.append(f"extract_too_thin: only 'id' for a resource with "
                       f"{len(known)} known field(s): {sorted(known)[:6]}")
    if ba.get("verb") == "create":
        ents = impl.get("creates_entities") or []
        if not ents or not ents[0].get("identifier_path"):
            out.append("verb create without creates_entities[0].identifier_path")
        elif not ents[0].get("type"):
            out.append("creates_entities[0].type is empty (the importer reads `type`)")
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
