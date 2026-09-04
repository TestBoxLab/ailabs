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


def _body_template(op: dict[str, Any]) -> dict[str, str]:
    schema = ((op.get("requestBody") or {}).get("content", {})
              .get("application/json", {}).get("schema") or {})
    return {name: "{{%s}}" % name for name in sorted(schema.get("properties") or {})}


def _extract(schema: dict[str, Any]) -> dict[str, str]:
    props = schema.get("properties") or {}
    ids = {n: f"$.{n}" for n in sorted(props)
           if n == "id" or n.endswith("_id") or n.endswith("Id")}
    if ids:
        return ids
    if props:
        first = sorted(props)[0]
        return {first: f"$.{first}"}
    # ponytail: today every simulated response schema is a bare {"type": "object"}, so this
    # is the only branch that ever runs and every action extracts $.id. The id-detection
    # above is for when openapi.py starts describing response bodies.
    return {"id": "$.id"}


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


def _singular(noun: str) -> str:
    """The importer's own singularizeNoun rules (knowledge-base/models/identity.ts)."""
    if noun.endswith("ies"):
        return noun[:-3] + "y"
    if re.search(r"(ses|xes|zes|ches|shes)$", noun):
        return noun[:-2]
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun[:-1]
    return noun


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


def _parameters(path: str, op: dict[str, Any], body: dict[str, str]) -> list[dict[str, Any]]:
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
        extra: dict[str, Any] = {"example_value": "{{%s}}" % name}
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
        prop = props.get(name) or {}
        out.append(_param(name, "typed", "body", f"$.{name}", _schema_type(prop),
                          name in required,
                          _helper(prop.get("description") or "", name, "body"),
                          source_form_field=name, example_value=name))
    return out


def _action(base: str, service: str, doc: dict[str, Any], path: str, method: str,
            op: dict[str, Any], action_id: str) -> dict[str, Any]:
    verb, resource = _verb(method, path), _resource(path)
    product_id = f"bench-{service}"
    schema = (op["responses"]["200"]["content"]["application/json"]["schema"]
              if "200" in op.get("responses", {}) else {"type": "object"})
    body = {} if method == "get" else _body_template(op)
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
                "headers_template": {"content-type": "application/json"},
                "body_template": body,
                "response_template": {"status": 200, "extract": _extract(schema),
                                      "schema": schema},
            }],
        },
        # Both arrays are required: seeds-normalize maps over them unguarded.
        "parameters": _parameters(path, op, body),
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
    for path in sorted(doc["paths"]):
        for method in sorted(doc["paths"][path]):
            op = doc["paths"][path][method]
            base_id = f"bench-{service}:{_verb(method, path)}:{_resource(path)}"
            action_id = base_id
            if action_id in used:  # same verb+resource on a different path
                action_id = f"{base_id}-{_slugify(path)}"
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
    folders = {f"bench-{svc}": _service_actions(base, svc, doc) for svc, doc in docs.items()}
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
    if ba.get("verb") == "create":
        ents = impl.get("creates_entities") or []
        if not ents or not ents[0].get("identifier_path"):
            out.append("verb create without creates_entities[0].identifier_path")
        elif not ents[0].get("type"):
            out.append("creates_entities[0].type is empty (the importer reads `type`)")
    # Every {{x}} in the URL and every top-level body key needs exactly one
    # parameter: that array is what binds them to workflow inputs.
    want = set(re.findall(r"\{\{(\w+)\}\}", step.get("url_template", "")))
    want |= set(step.get("body_template") or {})
    names = [p.get("name") for p in impl.get("parameters") or []]
    if sorted(names) != sorted(set(names)) or set(names) != want:
        out.append(f"parameters_incomplete: {sorted(want - set(names))} unbound, "
                   f"{sorted(set(names) - want)} extra")
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
