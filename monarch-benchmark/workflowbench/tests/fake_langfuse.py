"""Fake Langfuse public API for offline tests (stdlib only).

Serves /api/public/health, /api/public/traces (filtered by
metadata[bench_episode_id]) and /api/public/observations (filtered by traceId)
from an in-memory list the test fills with add_trace(). Basic auth required.
"""
from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class FakeLangfuse:
    def __init__(self, public_key: str = "pk", secret_key: str = "sk"):
        self.expected_auth = "Basic " + base64.b64encode(
            f"{public_key}:{secret_key}".encode()).decode()
        self.requests: list[dict] = []
        self.traces: list[dict] = []
        self.observations: list[dict] = []
        self._n = 0
        self._lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def add_trace(self, episode_id: str | None,
                  spans: list[tuple] = (), generations: list[tuple] = ()) -> str:
        """spans: (span_id, name, parent_span_id|None).
        generations: (gen_id, parent_span_id, model, usage_dict|None)."""
        with self._lock:
            self._n += 1
            trace_id = f"trace-{self._n}"
        metadata = {"bench_episode_id": episode_id} if episode_id else {}
        self.traces.append({"id": trace_id, "metadata": metadata})
        for span_id, name, parent in spans:
            self.observations.append({"id": span_id, "traceId": trace_id, "type": "SPAN",
                                      "name": name, "parentObservationId": parent})
        for gen_id, parent, model, usage in generations:
            obs = {"id": gen_id, "traceId": trace_id, "type": "GENERATION",
                   "name": gen_id, "parentObservationId": parent, "model": model}
            if usage is not None:
                obs["usage"] = usage
            self.observations.append(obs)
        return trace_id

    @staticmethod
    def _page(items: list[dict], q: dict) -> dict:
        page = int(q.get("page", ["1"])[0] or 1)
        limit = int(q.get("limit", ["50"])[0] or 50)
        start = (page - 1) * limit
        total = len(items)
        return {"data": items[start:start + limit],
                "meta": {"page": page, "limit": limit, "totalItems": total,
                         "totalPages": max(1, -(-total // limit))}}

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code: int, obj: dict):
                payload = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                sp = urlsplit(self.path)
                with outer._lock:
                    outer.requests.append({"method": "GET", "path": self.path,
                                           "headers": dict(self.headers), "body": None})
                if self.headers.get("Authorization") != outer.expected_auth:
                    self._reply(401, {"error": "unauthorized"})
                    return
                q = parse_qs(sp.query)
                if sp.path == "/api/public/health":
                    self._reply(200, {"status": "OK"})
                elif sp.path == "/api/public/traces":
                    want = q.get("metadata[bench_episode_id]", [None])[0]
                    items = [t for t in outer.traces
                             if want is None or t["metadata"].get("bench_episode_id") == want]
                    self._reply(200, outer._page(items, q))
                elif sp.path == "/api/public/observations":
                    want = q.get("traceId", [None])[0]
                    items = [o for o in outer.observations
                             if want is None or o["traceId"] == want]
                    self._reply(200, outer._page(items, q))
                else:
                    self._reply(404, {"error": "not_found"})

        return Handler

    def start(self) -> "FakeLangfuse":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
