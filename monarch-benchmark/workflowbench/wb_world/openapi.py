"""OpenAPI 3.1 documents for the 47 simulated services, one per service.

Same source files that drive api_search/api_fetch (parity by construction).
Consumers: Monarch's Feature Discovery `api_spec` handler (full-flow test mode)
and its seed generator (create + run mode). `servers[0].url` is the HTTP shim,
so every operation Monarch derives dispatches back into the episode's world.

  python -m wb_world.openapi --out out/openapi --server http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from automationbench.tools.api.search import SCHEMAS_DIR, _INTERNAL_PREFIX

from ingester.graph_ingest import _load_jsonc

_PATH_VAR = re.compile(r"\{(\w+)\}")
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Five services carry a `{var}` in their own baseUrl -- the tenant segment
# BambooHR spells `{companyDomain}` and Recruitee `{company_id}`. The front door
# is one flat `{host}/{service}/{rest}`, so that segment has nowhere to live
# unless the published path carries it: v5.1 left it in the baseUrl only, and
# the shim rebuilt `baseUrl + rest` with the placeholder still literal, so no AB
# router ever matched (132 bamboohr + recruitee actions `not_executable`).
# It becomes the FIRST segment of the published path, an ordinary path
# parameter, and `world_url` puts it back where the baseUrl wants it.
_BASE_VARS: dict[str, str] = {}


def base_var(service: str, schemas: dict[str, dict[str, Any]] | None = None) -> str:
    """The placeholder the service's baseUrl leaves for the caller, or ""."""
    if service not in _BASE_VARS:
        docs = schemas if schemas is not None else load_schemas()
        found = _PATH_VAR.findall((docs.get(service) or {}).get("baseUrl", ""))
        _BASE_VARS[service] = found[0] if found else ""
    return _BASE_VARS[service]


def load_schemas(schema_dir: Path = SCHEMAS_DIR) -> dict[str, dict[str, Any]]:
    return {p.stem: _load_jsonc(p) for p in sorted(Path(schema_dir).glob("*.jsonc"))}


def _ab_prefix(service: str) -> str:
    """AB's routing prefix. The five placeholder services have no `_INTERNAL_PREFIX`
    entry, yet their jsonc paths still start with `<service>/`; leaving it on
    published `/bamboohr/bamboohr/v1/...`, which routes nowhere."""
    declared = _INTERNAL_PREFIX.get(service, "")
    return declared or (service + "/")


def real_path(service: str, internal_path: str) -> str:
    """The path Monarch calls: the jsonc path minus AB's routing prefix.

    For a service whose baseUrl carries a placeholder, that placeholder leads the
    path instead, so the front-door URL names every segment the world needs.
    """
    rest = internal_path.removeprefix(_ab_prefix(service)).lstrip("/")
    var = base_var(service)
    if not var:
        return "/" + rest
    # Recruitee's own paths already spell the segment (`v1/c/{company_id}/...`);
    # BambooHR's do not. Either way it appears exactly once, at the front.
    marker = "{%s}" % var
    if marker in rest:
        # Recruitee spells the tenant inside its own path
        # (`v1/c/{company_id}/offers`) AND in its baseUrl (`.../c/{company_id}`).
        # The baseUrl already supplies everything up to and including the tenant,
        # so only what follows it belongs on the path -- publishing both would
        # send the segment twice and route nowhere.
        rest = rest.partition(marker)[2].strip("/")
    return f"/{marker}/{rest}" if rest else f"/{marker}"


def world_url(service: str, rest: str, schemas: dict[str, dict[str, Any]]) -> str:
    """The world URL for a front-door path, substituting the baseUrl placeholder.

    `bamboohr/acme/v1/employees` -> `https://api.bamboohr.com/api/gateway.php/acme/v1/employees`.
    The AB router matches the tenant segment as `[^/]+`, so any value routes; what
    it cannot do is match a literal `{companyDomain}`.
    """
    base = (schemas.get(service) or {}).get("baseUrl", "").rstrip("/")
    var = base_var(service, schemas)
    if var:
        # The first published segment IS the tenant: it fills the baseUrl's slot
        # (wherever in the baseUrl that sits) and the rest follows.
        tenant, _, tail = rest.partition("/")
        if tenant:
            base, rest = base.replace("{%s}" % var, tenant), tail
    return f"{base}/{rest}" if rest else base


def _param_schema(p: dict[str, Any]) -> dict[str, Any]:
    t = p.get("type", "string")
    schema: dict[str, Any] = {"type": t}
    if t == "array":
        schema["items"] = p.get("items", {"type": "string"})
    if "enum" in p:
        schema["enum"] = p["enum"]
    # The documented default is what makes a parameter `selected` in the seeds
    # (Gmail's userId = "me"): the builder sees it auto-filled and may override.
    if "default" in p:
        schema["default"] = p["default"]
    return schema


def _operation(service: str, ep: dict[str, Any]) -> dict[str, Any]:
    path = real_path(service, ep["path"])
    params: list[dict[str, Any]] = []
    body_props: dict[str, Any] = {}
    body_required: list[str] = []
    declared = ep.get("parameters") or {}
    for name, p in declared.items():
        loc = p.get("location", "query")
        if loc == "body":
            body_props[name] = {**_param_schema(p), "description": p.get("description", "")}
            if p.get("required"):
                body_required.append(name)
            continue
        params.append({
            "name": name, "in": loc if loc in ("path", "query", "header") else "query",
            "required": True if loc == "path" else bool(p.get("required")),
            "description": p.get("description", ""),
            "schema": _param_schema(p),
        })
    # Two AB endpoints use a {var} in the path without declaring it.
    for var in _PATH_VAR.findall(path):
        if var not in declared:
            params.append({"name": var, "in": "path", "required": True,
                           "description": f"Path parameter {var}.", "schema": {"type": "string"}})

    op: dict[str, Any] = {
        "operationId": ep["id"],
        "summary": ep.get("description", "")[:120],
        "description": ep.get("description", ""),
        "parameters": params,
        "responses": {"200": {"description": _as_text(ep.get("response")) or "Success.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}},
    }
    req = ep.get("request")
    if body_props or req:
        schema: dict[str, Any] = {"type": "object"}
        if body_props:
            schema["properties"] = body_props
            if body_required:
                schema["required"] = body_required
        elif isinstance(req, dict) and req.get("type") == "object":
            schema = req
        op["requestBody"] = {
            "description": _as_text(req) or "JSON request body.",
            "required": bool(body_required),
            "content": {"application/json": {"schema": schema}},
        }
    return op


def _merge(ops: list[dict[str, Any]], eps: list[dict[str, Any]]) -> dict[str, Any]:
    if len(ops) == 1:
        return ops[0]
    base = ops[0]
    base["operationId"] = eps[0]["id"].rsplit(".", 1)[0]
    base["summary"] = f"{len(ops)} variants: " + ", ".join(e["id"].rsplit(".", 1)[-1] for e in eps)
    base["description"] = "\n\n".join(f"[{e['id']}] {e.get('description', '')}" for e in eps)
    seen = {(p["name"], p["in"]) for p in base["parameters"]}
    props: dict[str, Any] = {}
    for op in ops:
        for p in op["parameters"]:
            if (p["name"], p["in"]) not in seen:
                base["parameters"].append({**p, "required": False})
                seen.add((p["name"], p["in"]))
        rb = op.get("requestBody")
        if rb:
            props.update(rb["content"]["application/json"]["schema"].get("properties", {}))
    if props:
        base["requestBody"] = {"description": "JSON request body (fields vary by variant).",
                               "required": False,
                               "content": {"application/json": {"schema": {"type": "object", "properties": props}}}}
    return base


def _as_text(v: Any) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v)


def _fix_refs(node: Any) -> Any:
    """AB schemas reference '#/schemas/X'; OpenAPI needs '#/components/schemas/X'."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#/components/"):
                name = v.removeprefix("#/schemas/").lstrip("#/")   # '#/schemas/X' or bare 'X'
                v = "#/components/schemas/" + name
            out[k] = _fix_refs(v)
        return out
    if isinstance(node, list):
        return [_fix_refs(x) for x in node]
    return node


def build_spec(service: str, schema: dict[str, Any], server_url: str) -> dict[str, Any]:
    # AB distinguishes some operations only by a query value or body field
    # (QuickBooks ?operation=update, Intercom message_type). OpenAPI allows one
    # operation per method+path, so those are merged: variants listed in the
    # description, parameters and body properties unioned. Nothing is dropped.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ep in schema.get("endpoints", []):
        m = ep.get("method", "GET").upper()
        if m in _METHODS:
            groups.setdefault((real_path(service, ep["path"]), m.lower()), []).append(ep)
    paths: dict[str, dict[str, Any]] = {}
    for (path, method), eps in groups.items():
        paths.setdefault(path, {})[method] = _merge([_operation(service, e) for e in eps], eps)
    api = schema.get("api", service)
    return _fix_refs({
        "openapi": "3.1.0",
        "info": {
            "title": f"{api} (WorkflowBench simulated)",
            "version": str(schema.get("version", "1")),
            "description": (schema.get("notes") or f"Simulated {api} API for benchmarking. "
                            "Derived from public documentation; no live service is called."),
        },
        # The shim mounts every service under its own prefix: {server}/{service}/...
        "servers": [{"url": f"{server_url.rstrip('/')}/{service}"}],
        "paths": paths,
        "components": {"schemas": schema.get("schemas", {})},
    })


class SchemaInterfaces:
    """The AutomationBench world's published surface, for the front door.

    The three questions the shim asks any world: which services exist, what is the
    document for one of them, and what URL does a REST path map to inside the world.
    A world whose surface is tools rather than REST resources answers the same three
    through `wb_world.adapter.ToolInterfaces` (feature 026).
    """

    def __init__(self, schemas: dict[str, dict[str, Any]] | None = None):
        self.schemas = schemas if schemas is not None else load_schemas()

    def services(self) -> list[str]:
        return list(self.schemas)

    def spec(self, service: str, public_url: str) -> dict[str, Any]:
        return build_spec(service, self.schemas[service], public_url)

    def rest_url(self, service: str, rest: str) -> str:
        return f"{self.schemas[service].get('baseUrl', '').rstrip('/')}/{rest}"


def build_all(server_url: str, schema_dir: Path = SCHEMAS_DIR) -> dict[str, dict[str, Any]]:
    return {svc: build_spec(svc, s, server_url) for svc, s in load_schemas(schema_dir).items()}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--server", required=True, help="shim base URL, e.g. http://127.0.0.1:8765")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    specs = build_all(a.server)
    for svc, spec in specs.items():
        (out / f"{svc}.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    (out / "index.json").write_text(json.dumps(
        {svc: {"url": f"{a.server.rstrip('/')}/openapi/{svc}.json",
               "operations": sum(len(v) for v in spec["paths"].values())}
         for svc, spec in specs.items()}, indent=1), encoding="utf-8")
    print(f"wrote {len(specs)} specs to {out}")


if __name__ == "__main__":
    main()
