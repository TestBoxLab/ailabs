"""HTTP front door for one attempt's world (BUILD-SPEC §2.2 Option B; verified
2 Sep 2026: the Monarch executor dispatches plain HTTP, never MCP). Stdlib only.

Two surfaces over the same world. "World" rather than "episode" since feature 026:
any object satisfying `wb_world/adapter.py` is served here, and it asks the world
only three things about its published surface -- which services, what document, what
URL a REST path maps to -- so an AutomationBench world and a world made of tools go
through the same door.

  Tool surface (kept for harnesses that speak the 3-tool contract):
    POST /fetch   {method, url, params?, body?} -> api_fetch result
    POST /search  {query, top_k?}               -> api_search result
    POST /encode  {text}                        -> base64_encode result

  REST surface (what Monarch's engine calls after discovering the OpenAPI docs):
    GET  /openapi/index.json, /openapi/<service>.json
    ANY  /<service>/<real path>?query   JSON body -> api_fetch(baseUrl + path)
         AB error envelopes {"error": {"code": N}} become HTTP status N.

One shim per attempt. WB_SHIM_PUBLIC_URL overrides the advertised server URL
when Monarch runs in Docker (e.g. http://host.docker.internal:PORT).
"""
from __future__ import annotations

import json
import os
import socketserver
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit



# How much of a request and a response body one log line keeps.
LOG_BODY_CHARS = 500
# The largest body this accepts, matching the Studio's front door.
MAX_BODY_BYTES = 8 * 1024 * 1024


class BodyTooLarge(Exception):
    """The request claimed a body this refuses to read."""


class _Server(ThreadingHTTPServer):
    # POSIX needs SO_REUSEADDR to reclaim a fixed port from closed connections.
    # Windows keeps it off because there it can steal an address from a live server.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        # HTTPServer.server_bind resolves the bound host's name (getfqdn), a DNS
        # round trip that stalls for seconds per attempt on a machine with slow
        # or absent name resolution (seen 8 Sep 2026: 40 attempts, minutes of
        # waiting). The front door never uses the name, so bind without it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[0], self.server_address[1]


class EpisodeHTTPShim:
    def __init__(self, episode, port: int = 0, public_url: str | None = None,
                 host: str = "127.0.0.1", access_log: str | Path | None = None):
        # `episode` is any world satisfying the adapter contract; the name is kept
        # because every caller and every test already uses it.
        self.episode = episode
        # One JSON line per request, so a failed step can say what actually
        # arrived instead of only what the engine reported. None = off.
        self.access_log = Path(access_log) if access_log else None
        self._log_lock = threading.Lock()
        self.interfaces = episode.interfaces()
        self.httpd = _Server((host, port), self._handler())
        self.port = self.httpd.server_address[1]
        self.url = f"http://{host}:{self.port}"
        self.public_url = (public_url or os.environ.get("WB_SHIM_PUBLIC_URL") or self.url).rstrip("/")
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def _log(self, method: str, path: str, status: int, req: bytes, resp: bytes,
             episode_id: str | None, elapsed_ms: float) -> None:
        if self.access_log is None:
            return
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": method, "path": path, "status": status,
            "request_bytes": len(req), "response_bytes": len(resp),
            "request_body": req.decode("utf-8", "replace")[:LOG_BODY_CHARS],
            "response_body": resp.decode("utf-8", "replace")[:LOG_BODY_CHARS],
            "episode_id": episode_id,
            "elapsed_ms": round(elapsed_ms, 1),
        })
        # ponytail: one lock and one append per request; the server is threaded
        # and an attempt makes tens of calls. A buffered writer is the upgrade
        # if a run ever makes thousands.
        with self._log_lock:
            with open(self.access_log, "a", encoding="utf-8") as fh:
                print(line, file=fh)

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def handle_one_request(self):
                self._t0 = time.monotonic()
                self._req_body = b""
                try:
                    super().handle_one_request()
                except BodyTooLarge as exc:
                    self._reply(413, {"error": str(exc)})

            def _body(self) -> bytes:
                # The competitor under test is what calls this, and `wb_arms.monarch`
                # binds the shim to 0.0.0.0. An unbounded Content-Length was a request
                # to read as much as the sender claimed. Same 8 MB the Studio's front
                # door allows, so a body it accepts is a body this accepts.
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if not 0 <= n <= MAX_BODY_BYTES:
                    self._req_body = b""
                    raise BodyTooLarge(f"Content-Length must be 0 to {MAX_BODY_BYTES}")
                self._req_body = self.rfile.read(n) if n else b""
                return self._req_body

            def do_GET(self):
                sp = urlsplit(self.path)
                if sp.path == "/openapi/index.json":
                    self._reply(200, {svc: {"url": f"{outer.public_url}/openapi/{svc}.json"}
                                      for svc in outer.interfaces.services()})
                elif sp.path.startswith("/openapi/") and sp.path.endswith(".json"):
                    svc = sp.path[len("/openapi/"):-len(".json")]
                    if svc not in outer.interfaces.services():
                        self._reply(404, {"error": f"unknown service {svc}"})
                        return
                    self._reply(200, outer.interfaces.spec(svc, outer.public_url))
                else:
                    self._rest("GET")

            def do_POST(self):
                if self.path in ("/fetch", "/search", "/encode"):
                    self._tool()
                else:
                    self._rest("POST")

            def do_PUT(self): self._rest("PUT")
            def do_PATCH(self): self._rest("PATCH")
            def do_DELETE(self): self._rest("DELETE")

            def _admin(self, url: str) -> bool:
                """Whether this URL names an administrative operation of the world.

                Both surfaces ask, because both reach the same world: `_rest` builds the
                URL from a path, and `/fetch` takes one the competitor wrote. The world's
                own `admin_paths` are relative to a service, so the service segment comes
                off first -- the same thing an adapter's router does before it checks.
                """
                admin = getattr(outer.interfaces, "admin_paths", ())
                if not admin:
                    return False
                path = url if url.startswith("/") else "/" + url.split("://", 1)[-1].split("/", 1)[-1]
                head, _, rest = path.lstrip("/").partition("/")
                candidates = [path, "/" + rest] if head in outer.interfaces.services() else [path]
                return any(c.startswith(a) for c in candidates for a in admin)

            def _tool(self):
                try:
                    req = json.loads(self._body() or b"{}")
                    ep = outer.episode
                    if self.path == "/fetch":
                        # The tool surface reaches the same world as the REST one, so the
                        # door refuses the same operations on it (feature 026, FR-034).
                        if self._admin(str(req.get("url") or "")):
                            self._reply(403, {"error": f"{req.get('url')} is an administrative "
                                                       "operation of the product under test, "
                                                       "not part of the task"})
                            return
                        out = ep.api_fetch(req["method"], req["url"],
                                           params=_as_json_str(req.get("params")),
                                           body=_as_json_str(req.get("body")))
                    elif self.path == "/search":
                        out = ep.api_search(req["query"], int(req.get("top_k") or 5))
                    else:
                        out = ep.base64_encode(req["text"])
                    self._reply(200, {"result": out})
                except BodyTooLarge:
                    raise          # one refusal, one status, whichever path asked
                except Exception as e:
                    self._reply(400, {"error": str(e)})

            def _rest(self, method: str):
                sp = urlsplit(self.path)
                parts = sp.path.lstrip("/").split("/", 1)
                svc = parts[0]
                if svc not in outer.interfaces.services():
                    self._reply(404, {"error": f"unknown service {svc!r}"})
                    return
                rest = parts[1] if len(parts) > 1 else ""
                url = outer.interfaces.rest_url(svc, rest)
                # A world may expose administrative operations on the same surface as
                # its real work -- seeding, resetting, arbitrary queries. One of those
                # in the competitor's hands writes the expected result directly or
                # erases the evidence, so the door refuses them for every world rather
                # than trusting each adapter to remember (feature 026, FR-034).
                if self._admin(url):
                    self._reply(403, {"error": f"{url} is an administrative operation of "
                                               f"the product under test, not part of the task"})
                    return
                # Single-valued query params, like every AB router expects.
                params = {k: v[-1] for k, v in parse_qs(sp.query, keep_blank_values=True).items()}
                raw = self._body()
                body = raw.decode("utf-8") if raw else None
                try:
                    out = outer.episode.api_fetch(method, url, params=json.dumps(params) if params else None,
                                                  body=body)
                except Exception as e:
                    self._reply(500, {"error": str(e)})
                    return
                self._raw(out)

            def _log_reply(self, status: int, payload: bytes):
                outer._log(self.command or "?", self.path, status,
                           getattr(self, "_req_body", b""), payload,
                           self.headers.get("x-bench-episode-id"),
                           (time.monotonic() - getattr(self, "_t0", time.monotonic())) * 1000)

            def _raw(self, text: str):
                status = 200
                try:
                    data = json.loads(text)
                    err = data.get("error") if isinstance(data, dict) else None
                    if isinstance(err, dict) and isinstance(err.get("code"), int):
                        status = err["code"]
                except (json.JSONDecodeError, AttributeError):
                    pass
                payload = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self._log_reply(status, payload)

            def _reply(self, code: int, obj: dict):
                self._raw_status(code, json.dumps(obj))

            def _raw_status(self, code: int, text: str):
                payload = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self._log_reply(code, payload)

        return Handler

    def start(self) -> "EpisodeHTTPShim":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self._thread.join()
        self.httpd.server_close()


def _as_json_str(v) -> str | None:
    if v is None or isinstance(v, str):
        return v
    return json.dumps(v)


if __name__ == "__main__":   # serve one task's world by hand, for the live checklist
    import argparse
    from pathlib import Path

    from wb_world.episode import load_task_file

    ap = argparse.ArgumentParser(description="Serve one episode's front door.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9105)
    ap.add_argument("--task", default=None, help="task JSON (default: first in tasks/)")
    a = ap.parse_args()
    # Imported here rather than at module scope: the shim serves any world satisfying
    # the adapter contract and must not drag the AutomationBench one into every import.
    # The top-level import went away with feature 026 and took this entry point with it.
    from wb_world.episode import Episode, load_task_file

    tasks = Path(__file__).resolve().parents[1] / "tasks"
    path = Path(a.task) if a.task else sorted(tasks.glob("*.json"))[0]
    shim = EpisodeHTTPShim(Episode(load_task_file(path), episode_id="manual"),
                           port=a.port, host=a.host).start()
    print(f"{shim.url} (advertised: {shim.public_url}) serving {path.name}; Ctrl-C to stop")
    try:
        shim._thread.join()
    except KeyboardInterrupt:
        shim.stop()
