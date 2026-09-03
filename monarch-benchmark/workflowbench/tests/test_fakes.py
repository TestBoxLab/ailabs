"""Smoke tests for the offline fakes: every route answers, records what the
stories will assert on, and the stateful bits (SSE reply gate, engine calls)
actually work."""
from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.fake_fd import FakeFD
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch, Scenario


def _http(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def _seed(tmp_path, slug: str, ids: list[str]):
    d = tmp_path / slug
    d.mkdir(parents=True)
    (d / "_meta.json").write_text("{}", encoding="utf-8")
    for i in ids:
        (d / f"{i}.json").write_text(json.dumps({"business_action": {"id": i}}), encoding="utf-8")
    return d


def test_fake_fd_routes(tmp_path):
    _seed(tmp_path, "acme", ["a1", "a2"])
    with FakeFD(fixtures_dir=tmp_path) as fd:
        assert _http("GET", f"{fd.url}/health") == (200, {"status": "ok"})

        status, seeds = _http("GET", f"{fd.url}/v1/seeds")
        assert status == 200
        item = seeds["items"][0]
        assert item["slug"] == "acme" and item["action_count"] == 2 and item["in_sync"] is False

        status, prod = _http("POST", f"{fd.url}/v1/products",
                             {"slug": "acme", "display_name": "Acme"})
        assert status == 200 and prod["product"]["display_name"] == "Acme"

        status, out = _http("POST", f"{fd.url}/v1/seeds/acme/import", {})
        assert status == 200 and out["actions_imported"] == 2
        assert out["before"]["kb_hash"] is None and out["after"]["kb_hash"] == item["kb_hash"]

        _, seeds = _http("GET", f"{fd.url}/v1/seeds")
        assert seeds["items"][0]["in_sync"] is True

        assert _http("POST", f"{fd.url}/v1/seeds/nope/import", {})[0] == 404
        assert [r["method"] for r in fd.requests].count("POST") == 3


def test_fake_fd_without_fixtures_shows_no_seeds():
    with FakeFD() as fd:
        assert _http("GET", f"{fd.url}/v1/seeds") == (200, {"items": []})


def test_fake_langfuse_routes():
    with FakeLangfuse() as lf:
        auth = {"Authorization": "Basic " + base64.b64encode(b"pk:sk").decode()}
        assert _http("GET", f"{lf.url}/api/public/health")[0] == 401       # no auth
        assert _http("GET", f"{lf.url}/api/public/health", headers=auth) == (200, {"status": "OK"})

        tid = lf.add_trace("ep-1", spans=[("s1", "authoring", None), ("s2", "plan", "s1")],
                           generations=[("g1", "s2", "claude-opus", {"input": 10, "output": 2})])
        lf.add_trace(None)                                                # unrelated trace

        status, traces = _http(
            "GET", f"{lf.url}/api/public/traces?metadata%5Bbench_episode_id%5D=ep-1",
            headers=auth)
        assert status == 200 and [t["id"] for t in traces["data"]] == [tid]
        assert traces["meta"]["totalItems"] == 1

        status, obs = _http("GET", f"{lf.url}/api/public/observations?traceId={tid}&page=1&limit=2",
                            headers=auth)
        assert status == 200 and len(obs["data"]) == 2 and obs["meta"]["totalPages"] == 2
        _, page2 = _http("GET", f"{lf.url}/api/public/observations?traceId={tid}&page=2&limit=2",
                         headers=auth)
        gen = page2["data"][0]
        assert gen["type"] == "GENERATION" and gen["usage"]["input"] == 10
        assert len(lf.requests) == 5


def test_fake_monarch_routes_and_engine_calls():
    hits: list[str] = []

    class Engine(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_PATCH(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    engine = ThreadingHTTPServer(("127.0.0.1", 0), Engine)
    threading.Thread(target=engine.serve_forever, daemon=True).start()
    shim_url = f"http://127.0.0.1:{engine.server_address[1]}"

    sc = Scenario(
        frames=[{"status": "running", "phase": "plan"},
                {"status": "awaiting_input",
                 "awaiting_reply": {"requestId": "req-1", "questions": [{"id": "q1", "text": "?"}]}},
                {"status": "done", "workflowId": "wf-1", "recipeVersion": 1}],
        engine_calls=[("PATCH", "/salesforce/x", {"MailingCity": "Denver"})],
        shim_url=shim_url)
    try:
        with FakeMonarch(sc) as m:
            sess = {"x-monarch-session": m.token}
            assert _http("GET", f"{m.url}/api/health")[0] == 401          # session required
            with urllib.request.urlopen(f"{m.url}/api", timeout=10) as r:
                assert r.status == 200 and r.read() == b"Hello World!"     # /api is open
            assert _http("POST", f"{m.url}/api/auth/login",
                         {"email": "a@b.c", "password": "p"})[0] == 200
            assert _http("GET", f"{m.url}/api/health", headers=sess) == (200, {"ok": True})

            status, run = _http("POST", f"{m.url}/api/workflows/recipe/runs", {"goal": "g"},
                                headers={**sess, "x-bench-episode-id": "ep-9"})
            assert status == 201 and run["runId"] == "rr-1"
            assert m.episode_headers == ["ep-9"]

            # the stream blocks on awaiting_input until a reply is posted
            frames: list[dict] = []
            req = urllib.request.Request(
                f"{m.url}/api/workflows/recipe/runs/rr-1/stream", headers=sess)
            resp = urllib.request.urlopen(req, timeout=15)
            assert resp.headers["Content-Type"] == "text/event-stream"
            replied = False
            for raw in resp:
                line = raw.decode().strip()
                if not line.startswith("data: "):
                    continue
                frame = json.loads(line[len("data: "):])
                frames.append(frame)
                if frame.get("status") == "awaiting_input" and not replied:
                    replied = True
                    assert _http("POST", f"{m.url}/api/workflows/recipe/runs/rr-1/reply",
                                 {"requestId": "req-1", "answers": [{"id": "q1", "text": "yes"}]},
                                 headers=sess)[0] == 200
                if frame.get("status") == "done":
                    break
            assert [f["status"] for f in frames] == ["running", "awaiting_input", "done"]
            assert m.replies_received[0]["requestId"] == "req-1"

            status, started = _http("POST", f"{m.url}/api/workflows/wf-1/run", {"mode": "test"},
                                    headers=sess)
            assert status == 201 and started["engine"]["status"] == "running"
            deadline = time.monotonic() + 20           # poll to a deadline, no fixed sleep
            while time.monotonic() < deadline:
                status, poll = _http("GET", f"{m.url}/api/workflows/runs/run-1", headers=sess)
                if poll["status"] != "running":
                    break
            assert poll == {"status": "succeeded"}
            assert hits == ["/salesforce/x"] and m.engine_responses[0]["status"] == 200

            assert _http("POST", f"{m.url}/api/workflows/recipe/runs/rr-1/cancel", {},
                         headers=sess) == (200, {"status": "cancelled"})
            assert _http("DELETE", f"{m.url}/api/workflows/wf-1", headers=sess)[0] == 200
            assert _http("DELETE", f"{m.url}/api/workflows/wf-1", headers=sess)[0] == 404
            assert m.deleted_workflows == ["wf-1"]
    finally:
        engine.shutdown()
        engine.server_close()


def test_fake_monarch_refusal_and_server_error():
    with FakeMonarch(Scenario(run_refusal="RUN_HOST_BLOCKED")) as m:
        sess = {"x-monarch-session": "t"}
        status, err = _http("POST", f"{m.url}/api/workflows/wf-1/run", {"mode": "test"},
                            headers=sess)
        assert status == 422 and err["code"] == "RUN_HOST_BLOCKED"
        m.scenario.run_refusal = "RUN_ALREADY_ACTIVE"
        assert _http("POST", f"{m.url}/api/workflows/wf-1/run", {}, headers=sess)[0] == 409
        m.scenario.server_error = True
        assert _http("GET", f"{m.url}/api/health", headers=sess)[0] == 500


def test_fake_monarch_login_failure():
    with FakeMonarch(Scenario(login_ok=False)) as m:
        status, err = _http("POST", f"{m.url}/api/auth/login", {"email": "a", "password": "b"})
        assert status == 401 and err["error"] == "invalid_credentials"
