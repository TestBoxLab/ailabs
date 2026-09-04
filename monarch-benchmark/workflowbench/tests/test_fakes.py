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
        assert out["before"]["kb_hash"] is None and out["after"]["kb_hash"] == item["kb"]["kb_hash"]

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

        # Cloud ignores the metadata filter and returns every trace, so the fake
        # does too; the episode's own traces are told apart by their metadata.
        status, traces = _http(
            "GET", f"{lf.url}/api/public/traces?metadata%5Bbench_episode_id%5D=ep-1",
            headers=auth)
        assert status == 200 and traces["meta"]["totalItems"] == 2
        assert [t["id"] for t in traces["data"]] == [tid, "trace-2"]
        assert [t["metadata"].get("bench_episode_id") for t in traces["data"]] == ["ep-1", None]

        status, obs = _http("GET", f"{lf.url}/api/public/observations?traceId={tid}&page=1&limit=2",
                            headers=auth)
        assert status == 200 and len(obs["data"]) == 2 and obs["meta"]["totalPages"] == 2
        _, page2 = _http("GET", f"{lf.url}/api/public/observations?traceId={tid}&page=2&limit=2",
                         headers=auth)
        gen = page2["data"][0]
        assert gen["type"] == "GENERATION" and gen["usage"]["input"] == 10
        assert gen["usageDetails"]["input"] == 10      # both shapes, as Cloud serves them
        assert len(lf.requests) == 5


def test_fake_monarch_routes_and_engine_calls():
    hits: list[str] = []

    class Engine(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_PATCH(self):
            # Drain the body before answering: replying to an unread request
            # makes Windows reset the connection, which reached the caller as a
            # transport error instead of the 200 this stub means to send.
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
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
            # Wait on the run's own completion signal, not a guessed deadline:
            # the engine call is allowed ENGINE_CALL_TIMEOUT_S, so any shorter
            # wait here races it and reports an empty engine_responses instead.
            assert m.wait_for_run("run-1"), "run never turned terminal"
            assert m.engine_responses[0]["status"] == 200, m.engine_responses
            _, poll = _http("GET", f"{m.url}/api/workflows/runs/run-1", headers=sess)
            assert poll == {"status": "succeeded"}
            assert hits == ["/salesforce/x"]

            assert _http("POST", f"{m.url}/api/workflows/recipe/runs/rr-1/cancel", {},
                         headers=sess) == (200, {"status": "cancelled"})
            assert _http("DELETE", f"{m.url}/api/workflows/wf-1", headers=sess)[0] == 200
            assert _http("DELETE", f"{m.url}/api/workflows/wf-1", headers=sess)[0] == 404
            assert m.deleted_workflows == ["wf-1"]
    finally:
        engine.shutdown()
        engine.server_close()


def test_fake_monarch_cancel_ends_a_stream_parked_on_the_account_prompt():
    sc = Scenario(frames=[
        {"status": "awaiting_input", "awaiting_reply": {"requestId": "req-2", "kind": "account"}},
        {"status": "done", "workflowId": "wf-1"}])   # never reached: cancel ends the stream
    with FakeMonarch(sc) as m:
        sess = {"x-monarch-session": m.token}
        frames: list[dict] = []

        def read():
            req = urllib.request.Request(
                f"{m.url}/api/workflows/recipe/runs/rr-1/stream", headers=sess)
            with urllib.request.urlopen(req, timeout=10) as resp:
                for raw in resp:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        frames.append(json.loads(line[len("data: "):]))

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline = time.monotonic() + 10       # wait for the account prompt, no fixed sleep
        while not frames and time.monotonic() < deadline:
            time.sleep(0.01)
            assert reader.is_alive()
        assert frames[0]["awaiting_reply"]["kind"] == "account"

        assert _http("POST", f"{m.url}/api/workflows/recipe/runs/rr-1/cancel", {},
                     headers=sess) == (200, {"status": "cancelled"})
        reader.join(timeout=2)
        assert not reader.is_alive()           # the stream ended, it did not hit the reply gate
        assert frames[-1] == {"status": "error", "error": "cancelled"}
        assert len(frames) == 2                # the frame after the prompt is never sent


def test_fake_monarch_run_fails_when_an_engine_call_never_lands():
    """An engine call that never reaches the front door must not report success:
    that used to surface as a confusing empty-hits failure in the caller."""
    dead = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = dead.server_address[1]
    dead.server_close()                        # nothing listens on this port now

    sc = Scenario(engine_calls=[("PATCH", "/salesforce/x", {"c": "Denver"})],
                  shim_url=f"http://127.0.0.1:{port}")
    with FakeMonarch(sc) as m:
        sess = {"x-monarch-session": m.token}
        assert _http("POST", f"{m.url}/api/workflows/wf-1/run", {}, headers=sess)[0] == 201
        assert m.wait_for_run("run-1"), "run never turned terminal"
        _, poll = _http("GET", f"{m.url}/api/workflows/runs/run-1", headers=sess)
        assert poll["status"] == "failed" and poll["errorCode"] == "ENGINE_CALL_FAILED"
        assert m.engine_responses[0]["status"] is None


def test_fake_monarch_wait_for_run_outlasts_a_slow_engine_call():
    """A slow engine call must still be observed, not raced.

    The old test polled to a hand-picked 20 s deadline while the engine call is
    allowed ENGINE_CALL_TIMEOUT_S (60 s); on a loaded box the loop gave up first
    and the caller died on an empty engine_responses. Here the call is slower
    than any such deadline would be, so waiting on the run's own signal is the
    only thing that works.
    """
    started = threading.Event()

    class SlowEngine(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_PATCH(self):
            started.set()
            time.sleep(1.0)                    # outlives a tight poll deadline
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    engine = ThreadingHTTPServer(("127.0.0.1", 0), SlowEngine)
    threading.Thread(target=engine.serve_forever, daemon=True).start()
    sc = Scenario(engine_calls=[("PATCH", "/salesforce/x", {"c": "Denver"})],
                  shim_url=f"http://127.0.0.1:{engine.server_address[1]}")
    try:
        with FakeMonarch(sc) as m:
            sess = {"x-monarch-session": m.token}
            assert _http("POST", f"{m.url}/api/workflows/wf-1/run", {}, headers=sess)[0] == 201
            # A 0.1 s budget is the old racy shape: it gives up while the call runs.
            assert not m.wait_for_run("run-1", timeout=0.1)
            assert started.is_set() and m.engine_responses == []
            # The real wait outlasts the call and sees the response.
            assert m.wait_for_run("run-1"), "run never turned terminal"
            assert m.engine_responses[0]["status"] == 200
            _, poll = _http("GET", f"{m.url}/api/workflows/runs/run-1", headers=sess)
            assert poll == {"status": "succeeded"}
    finally:
        engine.shutdown()
        engine.server_close()


def test_fake_monarch_refusal_and_server_error():
    # preset_token: this story skips login, like the MONARCH_TOKEN path
    with FakeMonarch(Scenario(run_refusal="RUN_HOST_BLOCKED", preset_token="t")) as m:
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


# -- 004 T004: the three run-only routes --------------------------------------

def test_fake_monarch_workflow_read_serves_the_recipe_version():
    """GET /api/workflows/<id> answers {recipeVersion} for a known workflow, 404 otherwise."""
    with FakeMonarch(Scenario(workflows={"wf-1": {"recipeVersion": 3}})) as m:
        sess = {"x-monarch-session": m.token}
        # The detail route is behind the session, like every other read.
        assert _http("GET", f"{m.url}/api/workflows/wf-1")[0] == 401
        _http("POST", f"{m.url}/api/auth/login", {"email": "a@b.c", "password": "p"})
        status, body = _http("GET", f"{m.url}/api/workflows/wf-1", headers=sess)
        assert status == 200 and body["recipeVersion"] == 3
        assert _http("GET", f"{m.url}/api/workflows/wf-nope", headers=sess)[0] == 404


def test_fake_monarch_active_run_refuses_then_accepts():
    """A workflow in active_run_for refuses the first N run requests with 409."""
    sc = Scenario(workflows={"wf-1": {"recipeVersion": 1}}, active_run_for={"wf-1": 2},
                  engine_calls=[])
    with FakeMonarch(sc) as m:
        sess = {"x-monarch-session": m.token}
        for _ in range(2):
            status, body = _http("POST", f"{m.url}/api/workflows/wf-1/run", {"mode": "live"},
                                 headers=sess)
            assert status == 409 and body["code"] == "RUN_ALREADY_ACTIVE"
        status, started = _http("POST", f"{m.url}/api/workflows/wf-1/run", {"mode": "live"},
                                headers=sess)
        assert status == 201 and started["engine"]["status"] == "running"


def test_fake_monarch_active_run_never_clears_keeps_polling_running():
    """active_run_never_clears: the run polls as running forever, so a bounded wait expires."""
    sc = Scenario(workflows={"wf-1": {"recipeVersion": 1}}, active_run_never_clears=True,
                  engine_calls=[])
    with FakeMonarch(sc) as m:
        sess = {"x-monarch-session": m.token}
        assert _http("POST", f"{m.url}/api/workflows/wf-1/run", {"mode": "live"},
                     headers=sess)[0] == 409
        # the leftover run is discoverable and stays running
        status, runs = _http("GET", f"{m.url}/api/workflows/wf-1/runs", headers=sess)
        assert status == 200 and runs["items"][0]["status"] == "running"
        run_id = runs["items"][0]["id"]
        for _ in range(3):
            assert _http("GET", f"{m.url}/api/workflows/runs/{run_id}",
                         headers=sess)[1]["status"] == "running"
