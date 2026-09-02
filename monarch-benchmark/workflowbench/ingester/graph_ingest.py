"""Graph ingester: the 47 endpoint-schema .jsonc files -> product-graph JSON.

Output shape (intermediate, documented; Monarch-side loader maps it into the
real product graph — open question for Deyton in the T0 spec):
  services: [{key, api, base_url, notes, n_endpoints}]
  actions:  [{id, service, method, url, description, parameters, request, response}]
  edges:    [{from: service_key, to: action_id, rel: "exposes"}]

Same files that drive api_search/api_fetch — parity by construction.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_LINE_COMMENT = re.compile(r'^\s*//.*$', re.MULTILINE)


def _load_jsonc(path: Path) -> dict[str, Any]:
    raw = path.read_text()
    # Only strip whole-line comments: inline '//' would corrupt URLs.
    return json.loads(_LINE_COMMENT.sub("", raw))


def build_graph(schema_dir: Path) -> dict[str, Any]:
    services, actions, edges = [], [], []
    files = sorted(schema_dir.glob("*.jsonc"))
    for f in files:
        d = _load_jsonc(f)
        key = f.stem
        base = d.get("baseUrl", "")
        eps = d.get("endpoints", [])
        services.append({
            "key": key, "api": d.get("api", key), "base_url": base,
            "notes": d.get("notes", ""), "n_endpoints": len(eps),
        })
        for e in eps:
            path = e.get("path", "")
            # api_search renders urls as baseUrl + path minus the routing prefix
            url_path = path[len(key) + 1:] if path.startswith(key + "/") else path
            aid = e["id"]
            actions.append({
                "id": aid, "service": key, "method": e.get("method", "GET"),
                "url": f"{base}/{url_path}",
                "description": e.get("description", ""),
                "parameters": e.get("parameters", {}),
                "request": e.get("request"), "response": e.get("response"),
            })
            edges.append({"from": key, "to": aid, "rel": "exposes"})
    return {"schema_version": "wb-graph/0.1", "source": "automationbench/tools/api/schemas",
            "n_files": len(files), "services": services, "actions": actions, "edges": edges}


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--schema-dir", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    g = build_graph(Path(a.schema_dir))
    Path(a.out).write_text(json.dumps(g, indent=1))
    print(f"wrote {a.out}: {len(g['services'])} services, {len(g['actions'])} actions")


if __name__ == "__main__":
    main()
