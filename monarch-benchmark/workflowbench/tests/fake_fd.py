"""Fake Feature Discovery service for offline tests (stdlib only).

Shape follows the real FD API: /health, /v1/seeds, /v1/products,
/v1/seeds/<slug>/import. A seed is a folder under fixtures_dir; each *.json
file in it (except _meta.json) is one business action, and the seed's hash is
the sha256 of its sorted action ids.
"""
from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def _action_ids(folder: Path) -> list[str]:
    ids = []
    for f in sorted(folder.glob("*.json")):
        if f.name == "_meta.json":
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ids.append(str((doc.get("business_action") or {}).get("id") or f.stem))
    return sorted(ids)


def _hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


class FakeFD:
    def __init__(self, fixtures_dir: Path | None = None):
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None
        self.requests: list[dict] = []
        self.products: dict[str, dict] = {}
        self.imported: dict[str, str] = {}          # slug -> kb_hash last imported
        self._lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    # -- seed bookkeeping ----------------------------------------------------
    def _seed_dir(self, slug: str) -> Path | None:
        if not self.fixtures_dir:
            return None
        d = self.fixtures_dir / slug
        return d if d.is_dir() else None

    def _seeds(self) -> list[dict]:
        if not self.fixtures_dir or not self.fixtures_dir.is_dir():
            return []
        out = []
        for d in sorted(p for p in self.fixtures_dir.iterdir() if p.is_dir()):
            ids = _action_ids(d)
            h = _hash(ids)
            out.append({"slug": d.name, "kb_hash": h, "action_count": len(ids),
                        "in_sync": self.imported.get(d.name) == h})
        return out

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _record(self, body):
                with outer._lock:
                    outer.requests.append({"method": self.command, "path": self.path,
                                           "headers": dict(self.headers), "body": body})

            def _json_body(self):
                n = int(self.headers.get("Content-Length") or 0)
                if not n:
                    return None
                try:
                    return json.loads(self.rfile.read(n))
                except json.JSONDecodeError:
                    return None

            def _reply(self, code: int, obj: dict):
                payload = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                self._record(None)
                path = urlsplit(self.path).path
                if path == "/health":
                    self._reply(200, {"status": "ok"})
                elif path == "/v1/seeds":
                    self._reply(200, {"items": outer._seeds()})
                else:
                    self._reply(404, {"error": "not_found"})

            def do_POST(self):
                body = self._json_body()
                self._record(body)
                path = urlsplit(self.path).path
                if path == "/v1/products":
                    slug = (body or {}).get("slug", "")
                    with outer._lock:
                        prod = outer.products.setdefault(
                            slug, {"slug": slug, "display_name": "", "business_action_count": 0})
                        prod["display_name"] = (body or {}).get("display_name") or prod["display_name"]
                    self._reply(200, {"product": prod})
                elif path.startswith("/v1/seeds/") and path.endswith("/import"):
                    slug = path[len("/v1/seeds/"):-len("/import")]
                    d = outer._seed_dir(slug)
                    if d is None:
                        self._reply(404, {"error": "not_found"})
                        return
                    ids = _action_ids(d)
                    after = _hash(ids)
                    with outer._lock:
                        before_hash = outer.imported.get(slug)
                        before_count = outer.products.get(slug, {}).get("business_action_count", 0)
                        outer.imported[slug] = after
                        prod = outer.products.setdefault(
                            slug, {"slug": slug, "display_name": "", "business_action_count": 0})
                        prod["business_action_count"] = len(ids)
                    self._reply(200, {
                        "slug": slug, "actions_imported": len(ids),
                        "before": {"action_count": before_count, "kb_hash": before_hash},
                        "after": {"action_count": len(ids), "kb_hash": after},
                        "in_sync": True})
                else:
                    self._reply(404, {"error": "not_found"})

        return Handler

    def start(self) -> "FakeFD":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
