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


def load_schemas(schema_dir: Path = SCHEMAS_DIR) -> dict[str, dict[str, Any]]:
    return {p.stem: _load_jsonc(p) for p in sorted(Path(schema_dir).glob("*.jsonc"))}


def real_path(service: str, internal_path: str) -> str:
    """The path Monarch calls: the jsonc path minus AB's routing prefix."""
    return "/" + internal_path.removeprefix(_INTERNAL_PREFIX.get(service, "")).lstrip("/")


def _param_schema(p: dict[str, Any]) -> dict[str, Any]:
    t = p.get("type", "string")
    schema: dict[str, Any] = {"type": t}
    if t == "array":
        schema["items"] = p.get("items", {"type": "string"})
    if "enum" in p:
        schema["enum"] = p["enum"]
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
