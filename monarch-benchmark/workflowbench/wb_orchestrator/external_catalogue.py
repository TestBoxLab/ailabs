"""Source-only Monarch seeds from external adapters' published OpenAPI contracts."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from wb_world import seeds
from wb_world.episode import contract_hash, load_suite, source_identity
from wb_world.registry import resolve as resolve_world

METHODS = {"get", "head", "post", "put", "patch", "delete"}
BODYLESS = {"get", "head", "delete"}
PARAM_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


class Unrepresentable(ValueError):
    """One source operation Monarch's contract cannot express.

    Its own type so `generate` can exclude it and report it without swallowing any
    other ValueError -- a malformed document should still refuse the whole catalogue.
    """


@dataclass
class CatalogueSummary:
    operations_in_spec: int
    files_written: int
    folders: list[str]
    service_slugs: dict[str, str]
    sha256: str
    # Operations left out because Monarch's contract cannot express them, each as
    # {service, method, path, reason}. Reported rather than fatal, and recorded in the
    # pack: what Monarch was not taught belongs in the evidence beside what it was.
    excluded: list[dict] = field(default_factory=list)


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def product_slug(product, service):
    """Namespace every source app, including names shared with AutomationBench."""
    return "bench-" + _slug(product.name) + "-" + _slug(service)


def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n"


def _resolve(value, document, stack=()):
    if isinstance(value, list):
        return [_resolve(item, document, stack) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise ValueError(f"external OpenAPI reference is not a local document reference: {ref!r}")
        if ref in stack:
            raise ValueError(f"recursive OpenAPI reference cannot be flattened for Monarch: {ref}")
        target = document
        try:
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise ValueError(f"unresolved OpenAPI reference: {ref}") from None
        result = _resolve(target, document, (*stack, ref))
        if not isinstance(result, dict):
            raise ValueError(f"OpenAPI reference does not resolve to an object: {ref}")
        return {**result, **_resolve({k:v for k,v in value.items() if k != "$ref"}, document, stack)}
    return {key:_resolve(item, document, stack) for key,item in value.items()}


def _object(schema):
    """Flatten only an unambiguous allOf object intersection."""
    if "allOf" not in schema:
        return schema
    combined = {k:copy.deepcopy(v) for k,v in schema.items() if k != "allOf"}
    for branch in schema["allOf"]:
        for key, value in _object(branch).items():
            if key == "properties":
                props = combined.setdefault(key, {})
                for name, spec in value.items():
                    if name in props and props[name] != spec:
                        raise ValueError(f"conflicting allOf property: {name}")
                    props[name] = spec
            elif key == "required":
                combined[key] = sorted(set(combined.get(key, [])) | set(value))
            elif key in combined and combined[key] != value:
                raise ValueError(f"conflicting allOf constraint: {key}")
            else:
                combined[key] = copy.deepcopy(value)
    return combined


def _type(schema):
    kind = schema.get("type")
    if isinstance(kind, str) and kind in PARAM_TYPES:
        return kind
    candidates = schema.get("anyOf", schema.get("oneOf", []))
    if isinstance(kind, list):
        candidates = [{"type":k} for k in kind]
    candidates = [part for part in candidates if part.get("type") != "null"]
    if len(candidates) == 1:
        return _type(candidates[0])
    if not kind and "properties" in schema:
        return "object"
    raise ValueError(f"source parameter type is not representable without guessing: {schema}")


def _parameter(name, location, schema, required, description):
    kind = _type(schema)
    helper = description or schema.get("description") or name.replace("_", " ")
    # CanonicalParam has a coarse type; keep the complete declared constraints
    # visible to the builder without fabricating fields, examples or bounds.
    helper += "\nSource JSON Schema: " + json.dumps(schema, sort_keys=True, ensure_ascii=True)
    parameter = seeds._param(name, "typed", location,
        f"$.steps[0].{'body' if location == 'body' else 'url'}.{name}", kind, required, helper)
    if "default" in schema:
        parameter["example_value"] = copy.deepcopy(schema["default"])
    elif "example" in schema:
        parameter["example_value"] = copy.deepcopy(schema["example"])
    elif isinstance(schema.get("examples"), list) and schema["examples"]:
        parameter["example_value"] = copy.deepcopy(schema["examples"][0])
    if kind == "array":
        item = schema.get("items")
        if item:
            parameter["items"] = _type(item)
    if schema.get("format") in {"email", "date-time", "date", "uuid", "uri"}:
        parameter["format"] = schema["format"]
    if isinstance(schema.get("enum"), list):
        parameter["constraints"]["enum_options"] = [{"value":str(v)} for v in schema["enum"] if v is not None]
    for source, target in (("minimum", "min"), ("maximum", "max")):
        if source in schema:
            parameter["constraints"][target] = str(schema[source])
    return parameter


def _body_schema(op):
    content = (op.get("requestBody") or {}).get("content", {})
    if not content:
        return {}, None
    media = next((key for key in ("application/json", "application/x-www-form-urlencoded") if key in content), None)
    if media is None:
        raise ValueError(f"source request media type is unsupported by the JSON front door: {sorted(content)}")
    schema = _object(content[media].get("schema") or {})
    return schema, media


def _response(op):
    responses = op.get("responses") or {}
    success = sorted(key for key in responses if re.fullmatch(r"2[0-9][0-9]", str(key)))
    if not success:
        raise ValueError("source operation has no declared numeric successful response")
    code = success[0]
    response = responses[code]
    content = response.get("content") or {}
    body = content.get("application/json")
    if body is None and content:
        body = next(iter(content.values()))
    schema = copy.deepcopy(body.get("schema") or {}) if body else {}
    if not schema:
        schema = {"description":response.get("description") or "The source declares no response schema."}
    properties = schema.get("properties") or {}
    extract = {key:f"$.{key}" for key in sorted(properties) if re.fullmatch(r"\w+", key)}
    if not extract and (schema.get("type") in PARAM_TYPES or "anyOf" in schema or "oneOf" in schema):
        extract = {"result":"$"}
    return {"status":int(code), "extract":extract, "schema":schema}


def _action(product, service, server, path, method, op, public_url):
    slug = product_slug(product, service)
    verb = {"get":"read", "head":"read", "post":"create", "put":"update", "patch":"update", "delete":"delete"}[method]
    identity = _slug(op.get("operationId") or method + "-" + path)
    suffix = hashlib.sha256((method + " " + path).encode()).hexdigest()[:8]
    action_id = f"{slug}:{verb}:{identity[:100]}-{suffix}"
    body_schema, media = _body_schema(op)
    body_fields = body_schema.get("properties") or {}
    root_body = bool(media and (body_schema.get("type", "object") != "object"
                              or (not body_fields and body_schema.get("additionalProperties") is not False)))
    if media and not root_body:
        for schema in body_fields.values():
            try:
                _type(schema)
            except ValueError:
                # A whole JSON object retains mixed scalar unions without
                # coercing a value into one guessed CanonicalParam type.
                root_body = True
                break
    if root_body:
        body_fields = {}
    if method in BODYLESS and (body_fields or root_body):
        raise Unrepresentable(f"{method.upper()} {path}: source body cannot be represented by Monarch's bodyless contract")
    specs = list(op.get("parameters") or [])
    if any(spec.get("in") not in ("path", "query") for spec in specs):
        raise ValueError(f"{method.upper()} {path}: unsupported source parameter location")
    occurrences = {}
    for spec in specs:
        occurrences[spec["name"]] = occurrences.get(spec["name"], 0) + 1
    for name in body_fields:
        if not re.fullmatch(r"\w+", name):
            raise ValueError(f"body parameter name is not a valid Monarch token: {name}")
        occurrences[name] = occurrences.get(name, 0) + 1
    parameters, query, path_tokens = [], [], {}
    used = set(body_fields) | ({"payload"} if root_body else set())
    for spec in sorted(specs, key=lambda item:(item["in"], item["name"])):
        location, original = spec["in"], spec["name"]
        name = re.sub(r"\W+", "_", original)
        if occurrences[original] > 1 or (root_body and name == "payload"):
            name = location + "__" + name
        if name in used:
            raise ValueError(f"colliding parameter token: {name}")
        used.add(name)
        parameters.append(_parameter(name, location, spec.get("schema") or {},
                                     True if location == "path" else bool(spec.get("required")), spec.get("description")))
        if location == "path":
            path_tokens[original] = "{{" + name + "}}"
        else:
            query.append(original + "={{" + name + "}}")
    def replace(match):
        if match[1] not in path_tokens:
            raise ValueError(f"path parameter has no source declaration: {match[1]}")
        return path_tokens[match[1]]
    route = re.sub(r"\{([^{}]+)\}", replace, path)
    url = server.rstrip("/") + route
    if query:
        url += "?" + "&".join(query)
    required = set(body_schema.get("required") or [])
    body = {}
    for name, schema in sorted(body_fields.items()):
        body[name] = "{{" + name + "}}"
        parameters.append(_parameter(name, "body", schema, name in required, schema.get("description")))
    if root_body:
        body = "{{payload}}"
        parameters.append(_parameter("payload", "body", body_schema,
                          bool((op.get("requestBody") or {}).get("required")), body_schema.get("description")))
        parameters[-1]["json_path"] = "$.steps[0].body"
    response = _response(op)
    bodyless = method in BODYLESS or media is None
    return {
        "business_action": {"id":action_id, "label":op.get("summary") or op.get("operationId") or f"{method.upper()} {path}",
            "product_id":slug, "product_domain":urlsplit(public_url).hostname,
            "area":"operations", "state":"active", "verb":verb,
            "description":op.get("description") or op.get("summary") or "",
            "source_url":public_url + f"/openapi/{service}.json", "first_seen_at":seeds.STAMP, "last_seen_at":seeds.STAMP},
        "implementations":[{"id":"impl_" + action_id.replace(":", "_"), "source":"public", "discovered_at":seeds.STAMP,
            "idempotent":method in {"get", "head", "put", "delete"},
            "http_template":{"call_type":"rest", "transport_mode":"header_only", "auth_scheme":"none", "auth_captured":False,
                "steps":[{"method":method.upper(), "url_template":url,
                    "headers_template":{} if bodyless else {"content-type":"application/json"},
                    "body_template":None if bodyless else body, "response_template":response}]},
            "parameters":parameters, "creates_entities":[]}]}


def generate(product, task_dir, out_dir, public_url):
    """Construct and validate the whole source pack before publishing any files.

    The adapter owns hydration and public-surface filtering. No task prompts,
    source answer keys or snapshots enter the pack. The returned mapping is the
    exact service-to-Monarch-product identity that setup must freeze in its KB pin.
    """
    public_url = public_url.rstrip("/")
    parsed = urlsplit(public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("the public front door must be an absolute HTTP URL without query or credentials")
    if isinstance(product, (str, Path)):
        from wb_orchestrator.config import load_product
        product = load_product(product)
    if not product.world or product.world == "automation-bench":
        raise ValueError("external catalogue generation requires an external product")
    out = Path(out_dir).resolve()
    if product.world == "appworld":
        from wb_worlds.appworld.importer import outside_repository
        outside_repository(out)
    tasks = load_suite(task_dir)
    pin = source_identity(tasks)
    if not pin or not product.source or (pin["package"], pin["version"], pin["split"]) != (product.source.benchmark, product.source.version, product.source.split):
        raise ValueError("the task source does not match the product's frozen source")
    for task in tasks:
        if task.get("contract_sha256") != contract_hash(task):
            raise ValueError("a frozen task contract changed before catalogue generation")
    world_type = resolve_world(product.world)
    missing = world_type.prerequisites()
    if missing:
        raise ValueError("; ".join(missing))
    actions, seen_docs, excluded = {}, {}, {}
    selected = set(product.services)
    found = set()
    for task in tasks:
        world = world_type(task, "catalogue-" + task["contract_sha256"])
        try:
            interfaces = world.interfaces()
            for service in sorted(set(interfaces.services()) & selected):
                found.add(service)
                document = interfaces.spec(service, public_url)
                server = (document.get("servers") or [{}])[0].get("url", public_url).rstrip("/")
                if server not in {public_url, public_url + "/" + service}:
                    raise ValueError(f"{service}: published server is outside the front door")
                public_doc = {"openapi":document.get("openapi"), "servers":[{"url":server}], "paths":{}}
                for path, raw in sorted(document.get("paths", {}).items()):
                    if not path.startswith("/") or "?" in path or "#" in path:
                        raise ValueError(f"invalid published operation path: {path}")
                    shared = _resolve(raw.get("parameters") or [], document)
                    for method in sorted(set(raw) & METHODS):
                        op = _resolve(raw[method], document)
                        merged = {(p["in"],p["name"]):p for p in shared + (op.get("parameters") or [])}
                        op["parameters"] = list(merged.values())
                        if op.get("servers"):
                            raise ValueError("operation-specific server overrides are not supported by this front door")
                        try:
                            action = _action(product,service,server,path,method,op,public_url)
                        except Unrepresentable as exc:
                            # Excluded, not fatal, and never published: an operation with
                            # no action must not reach the document Monarch reads either.
                            excluded[(service, method, path)] = str(exc)
                            continue
                        public_doc["paths"].setdefault(path,{})[method] = op
                        key = (service, method, path)
                        if key in actions and actions[key] != action:
                            raise ValueError(f"published operation changed between frozen tasks: {service} {method} {path}")
                        actions[key] = action
                # Keep every successful response and source media declaration,
                # including alternatives the one-step seed cannot select at once.
                encoded = _dump(public_doc)
                seen_docs.setdefault(service,set()).add(encoded)
        finally:
            world.close()
    if found != selected:
        raise ValueError(f"product services are absent from the frozen task interfaces: {sorted(selected-found)}")
    service_slugs = {service:product_slug(product,service) for service in sorted(selected)}
    if len(set(service_slugs.values())) != len(service_slugs):
        raise ValueError("source service names collide after Monarch slug normalization")
    files = {}
    for service, slug in service_slugs.items():
        files[f"{slug}/_meta.json"] = _dump({"display_name":f"{product.name}: {service} (benchmark)",
            "domain":parsed.hostname,"host_pattern":parsed.hostname,"login_url":None,"requires_login":False})
    for (service, method, path), action in sorted(actions.items()):
        validation = action
        template = action["implementations"][0]["http_template"]["steps"][0]["body_template"]
        if isinstance(template, str):
            # The legacy validator assumes named body fields. A root object
            # token has the same one-parameter binding, but no wrapper on wire.
            if template != "{{payload}}":
                raise ValueError("invalid source root-body template")
            validation = copy.deepcopy(action)
            validation["implementations"][0]["http_template"]["steps"][0]["body_template"] = {"payload":"{{payload}}"}
        gaps = seeds._gaps_in(action["business_action"]["id"], validation)
        if gaps:
            raise ValueError("external seed cannot satisfy the Monarch contract: " + "; ".join(gaps))
        relative = f"{service_slugs[service]}/{action['business_action']['id'].replace(':','_')}.json"
        if relative in files:
            raise ValueError("source operations collided in a seed filename")
        files[relative] = _dump(action)
    left_out = [{"service":service, "method":method, "path":path, "reason":reason}
                for (service, method, path), reason in sorted(excluded.items())]
    digest = hashlib.sha256()
    for name, text in sorted(files.items()):
        digest.update(name.encode("utf-8")); digest.update(text.encode("utf-8"))
    sha = digest.hexdigest()
    manifest = {"format":"workflowbench-external-catalogue@1", "product":product.name, "source":pin,
        "task_contracts":[t["contract_sha256"] for t in tasks], "front_door":public_url,
        "service_slugs":service_slugs,"products":len(service_slugs),"actions":len(actions),"sha256":sha,
        **({"excluded_operations":left_out} if left_out else {}),
        "parameter_translation":"Published names, source required flags and declared defaults/examples only; all front-door bodies use JSON.",
        "response_translation":"Lowest declared numeric 2xx status; complete published response alternatives retained in source-contracts.yaml."}
    files["ok.txt"] = _dump(manifest)
    files["source-contracts.yaml"] = _dump({service:[json.loads(doc) for doc in sorted(documents)] for service,documents in sorted(seen_docs.items())})
    for name, text in files.items():
        target = out / name
        if target.exists() and target.read_bytes() != text.encode("utf-8"):
            raise ValueError(f"refusing to replace a frozen external catalogue file: {name}")
    if out.exists():
        extra = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} - set(files)
        if extra:
            raise ValueError(f"external catalogue output contains unrelated files: {sorted(extra)[:4]}")
    for name,text in files.items():
        target = out / name
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists(): target.write_bytes(text.encode("utf-8"))
    return CatalogueSummary(len(actions),len(actions),sorted(service_slugs.values()),service_slugs,sha,left_out)
