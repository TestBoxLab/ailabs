"""Fake Monarch backend for offline tests (stdlib only).

Routes follow the real backend (data-model §7): session login, the authoring
recipe run with its SSE stream and reply channel, the workflow run against a
front door, run polling, and workflow deletion. Everything a test may want to
assert is recorded on the server object.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


@dataclass
class Scenario:
    """One authoring/run story for the fake to play.

    A frame list with no ``done``/``error`` frame is how a test says "the
    stream closed without a terminal frame": the stream closes after the last
    frame either way.

    Assumption: the real backend reports a cancelled job as an ``error`` frame.
    """

    login_ok: bool = True
    frames: list[dict] = field(default_factory=lambda: [
        {"status": "running", "phase": "plan"},
        {"status": "done", "workflowId": "wf-1", "recipeVersion": 1}])
    run_refusal: str | None = None            # e.g. "RUN_HOST_BLOCKED"
    run_outcome: dict = field(default_factory=lambda: {"status": "succeeded"})
    engine_calls: list[tuple] = field(default_factory=list)   # (method, path, json|None)
    # Per-episode override of engine_calls, keyed by the x-bench-episode-id the
    # workflow run carried. A run whose episode is not listed falls back to
    # engine_calls, so a one-story scenario needs neither key nor lookup.
    engine_calls_by_episode: dict[str, list[tuple]] = field(default_factory=dict)
    shim_url: str | None = None
    delay_s: dict[str, float] = field(default_factory=dict)   # login/authoring/frame/run/poll
    run_never_finishes: bool = False
    # Railway's edge cuts a long SSE response: the first connection stops after N
    # frames without a terminal one, and the next resumes where it left off.
    stream_cut_after: int | None = None
    stream_404_after: int | None = None       # connection N+1 onwards answers 404
    # The stream never sends the terminal frame, on any connection: the job
    # finished server-side but the client never heard (live session 25ade669,
    # 8 Sep 2026). Only the run view says so.
    drop_terminal_frame: bool = False
    # With `drop_terminal_frame`, the connection also stays open after the job
    # ended, so nothing at all tells the client to go and look at the view.
    hold_open_after_terminal: bool = False
    # The stream sends nothing at all and never closes, so only the reader's own
    # beat wakes it.
    stream_silent: bool = False
    delete_fails_once: bool = False
    preset_token: str | None = None           # accept this session token without a login
    server_error: bool = False                # every route answers 500
    # -- run-only (004) --------------------------------------------------------
    # workflow id -> the detail GET /api/workflows/:id serves; an id absent answers 404
    workflows: dict[str, dict] = field(default_factory=dict)
    # workflow id -> how many run requests are refused with RUN_ALREADY_ACTIVE first
    active_run_for: dict[str, int] = field(default_factory=dict)
    # The leftover run polls as running forever, so a bounded wait expires. Like
    # `active_run_for`, it only refuses workflows listed in `workflows`.
    active_run_never_clears: bool = False
    # Each authoring job produces its own workflow (wf-1, wf-2, ...), as the real
    # backend does, instead of replaying the frame list's fixed id. `wb monarch
    # recipes` needs it: it authors the same task several times and must be able
    # to tell one attempt's workflow from another's.
    unique_workflow_ids: bool = False
    # -- inputs and the LLM-loop stamp (002) -----------------------------------
    # The recipe's declared inputs: [{name, label, type, required, default?}, ...].
    # Served on the done frame's `recipe` and on the workflow detail.
    recipe_inputs: list[dict] = field(default_factory=list)
    # The builder's own decisions, served on the done frame's `recipe`
    # (unattended authoring; backend 2ede4b3ee).
    recipe_assumptions: list[str] = field(default_factory=list)
    # The recipe version has an LLM loop, so it must be acked before it may run.
    has_llm_loop: bool = False


class _ClientGone(Exception):
    """The reader hung up mid-stream; everything it waited for was already sent."""


_REFUSAL_STATUS = {"RUN_ALREADY_ACTIVE": 409, "product_not_granted": 403}

_JSON_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool}


def _input_errors(declared: list[dict], sent: dict) -> list[dict]:
    """The backend's INPUT_INVALID detail: one {name, reason} per bad input."""
    by_name = {d["name"]: d for d in declared}
    bad = [{"name": k, "reason": "not declared by the recipe"}
           for k in sent if k not in by_name]
    for d in declared:
        value = sent.get(d["name"])
        if value is None:                       # missing or explicitly null
            if d.get("required") and "default" not in d:
                bad.append({"name": d["name"], "reason": "required input not provided"})
            continue
        want = _JSON_TYPES.get(d.get("type", "string"), str)
        # bool is a subclass of int, so a boolean must never satisfy `number`
        if not isinstance(value, want) or (isinstance(value, bool) and want is not bool):
            bad.append({"name": d["name"],
                        "reason": f"expected {d.get('type')}, got {type(value).__name__}"})
    return bad

# ponytail: a cap so a test that never replies still ends; lower it in a test if needed
REPLY_GATE_TIMEOUT_S = 30.0

# A stream that says nothing holds its connection this long, or until the server
# stops -- long enough for any test's deadline, short enough not to hang one.
HOLD_OPEN_S = 120.0

# Generous on purpose: a loaded CI box can take many seconds to answer a
# localhost request, and a timeout here used to surface as a confusing
# "hits == []" failure in the caller rather than as an engine error.
ENGINE_CALL_TIMEOUT_S = 60.0


class FakeMonarch:
    def __init__(self, scenario: Scenario | None = None):
        self.scenario = scenario or Scenario()
        self.requests: list[dict] = []
        self.replies_received: list[dict] = []
        self.deleted_workflows: list[str] = []
        self.deleted_at: list[float] = []          # monotonic clock of every delete request
        self.episode_headers: list[str] = []
        self.engine_responses: list[dict] = []
        self.authoring_started_at: list[float] = []
        self.stream_connections = 0                # how often the stream was opened
        self.run_started_at: list[float] = []
        self.llm_acks: list[tuple[str, str]] = []   # (workflow id, version) acked
        self.run_bodies: list[dict] = []            # every POST .../run body, in order
        self.authoring_bodies: list[dict] = []      # every POST recipe/runs body, in order
        self._acked: set[tuple[str, str]] = set()
        self.token = "sess-1"
        self._reply_events: dict[str, threading.Event] = {}
        self._run_done: dict[str, bool] = {}
        self._run_error: dict[str, dict] = {}      # run id -> outcome when an engine call failed
        self._run_events: dict[str, threading.Event] = {}   # run id -> set when it turns terminal
        self._cancelled: set[str] = set()          # recipe run ids cancelled by the client
        self._delete_failed_once = False
        self._run_n = 0                            # workflow runs get run-1, run-2, ...
        self._refusals_left = dict(self.scenario.active_run_for)
        self._leftover_runs: dict[str, str] = {}   # workflow id -> its active run id
        # Resume point per recipe run: a reconnected stream carries on where the
        # cut one stopped, while a second attempt starts from the beginning.
        self._frames_sent: dict[str, int] = {}
        self._connections: dict[str, int] = {}     # stream opens, per recipe run
        self._authoring_jobs = 0                   # POSTs to recipe/runs, so far
        self._workflow_for_job: dict[int, str] = {}
        self._lock = threading.Lock()
        self._stopping = threading.Event()   # released so held-open streams end
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def _event(self, request_id: str) -> threading.Event:
        with self._lock:
            return self._reply_events.setdefault(request_id, threading.Event())

    def _fire_engine_calls(self, run_id: str, episode_id: str = "") -> None:
        sc = self.scenario
        time.sleep(sc.delay_s.get("run", 0))
        transport_error = None
        for method, path, body in sc.engine_calls_by_episode.get(episode_id, sc.engine_calls):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request((sc.shim_url or "") + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=ENGINE_CALL_TIMEOUT_S) as r:
                    out = {"path": path, "status": r.status, "body": r.read().decode("utf-8", "replace")}
            except urllib.error.HTTPError as e:                     # the front door answered
                out = {"path": path, "status": e.code, "body": e.read().decode("utf-8", "replace")}
            except Exception as e:                                  # noqa: BLE001  never reached it
                out = {"path": path, "status": None, "error": str(e)}
                transport_error = transport_error or f"{path}: {e}"
            with self._lock:
                self.engine_responses.append(out)
        if not sc.run_never_finishes:
            with self._lock:
                # A call that never reached the front door is a failed run, not a
                # succeeded one: reporting success here would hide the real error
                # behind whatever run_outcome the scenario asked for.
                if transport_error:
                    self._run_error[run_id] = {"status": "failed",
                                               "errorCode": "ENGINE_CALL_FAILED",
                                               "error": transport_error}
                self._run_done[run_id] = True
            self._run_finished(run_id).set()

    def _workflow_of(self, recipe_run_id: str) -> str:
        """The workflow this authoring job produced: one per job, `wf-<n>`.

        The fake reuses the recipe-run id across attempts, so the job counter --
        bumped by POST /api/workflows/recipe/runs -- is what tells them apart.
        """
        with self._lock:
            return self._workflow_for_job.setdefault(self._authoring_jobs,
                                                     f"wf-{self._authoring_jobs}")

    def _run_finished(self, run_id: str) -> threading.Event:
        """Set once the engine calls for this run are done and it turned terminal."""
        with self._lock:
            return self._run_events.setdefault(run_id, threading.Event())

    def wait_for_run(self, run_id: str, timeout: float | None = None) -> bool:
        """Block until the run turns terminal. Tests use this instead of polling
        against a hand-picked deadline: the engine call may take up to
        ENGINE_CALL_TIMEOUT_S, so any shorter wait is a race by construction."""
        budget = ENGINE_CALL_TIMEOUT_S + 5 if timeout is None else timeout
        return self._run_finished(run_id).wait(timeout=budget)

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _json_body(self):
                n = int(self.headers.get("Content-Length") or 0)
                if not n:
                    return None
                try:
                    return json.loads(self.rfile.read(n))
                except json.JSONDecodeError:
                    return None

            def _json_body_recorded(self) -> dict:
                """The body do_POST already read for this request (it is recorded)."""
                with outer._lock:
                    return outer.requests[-1].get("body") or {}

            def _record(self, body):
                ep = self.headers.get("x-bench-episode-id")
                with outer._lock:
                    outer.requests.append({"method": self.command, "path": self.path,
                                           "headers": dict(self.headers), "body": body})
                    if ep:
                        outer.episode_headers.append(ep)

            def _reply(self, code: int, obj, extra_headers: tuple = ()):
                payload = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
                self.send_response(code)
                for k, v in extra_headers:
                    self.send_header(k, v)
                self.send_header("Content-Type",
                                 "text/plain" if isinstance(obj, str) else "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _authed(self) -> bool:
                got = self.headers.get("x-monarch-session")
                return bool(got) and got in {outer.token, outer.scenario.preset_token}

            # -- routing ------------------------------------------------------
            def do_GET(self):
                self._record(None)
                path = urlsplit(self.path).path
                if outer.scenario.server_error:
                    self._reply(500, {"error": "internal"})
                    return
                if path == "/api":
                    self._reply(200, "Hello World!")
                    return
                if not self._authed():
                    self._reply(401, {"error": "unauthenticated"})
                    return
                if path == "/api/health":
                    self._reply(200, {"ok": True})
                elif path.startswith("/api/workflows/recipe/runs/") and path.endswith("/stream"):
                    try:
                        self._stream()
                    except _ClientGone:
                        self.close_connection = True
                elif path.startswith("/api/workflows/recipe/runs/"):
                    self._authoring_view(path.rsplit("/", 1)[-1])
                elif path.startswith("/api/workflows/") and path.endswith("/runs"):
                    wfid = path[len("/api/workflows/"):-len("/runs")]
                    with outer._lock:
                        run_id = outer._leftover_runs.get(wfid)
                        done = outer._run_done.get(run_id, False) if run_id else None
                    items = ([] if run_id is None else
                             [{"id": run_id, "status": "succeeded" if done else "running"}])
                    self._reply(200, {"items": items})
                elif path.startswith("/api/workflows/runs/"):
                    run_id = path.rsplit("/", 1)[-1]
                    time.sleep(outer.scenario.delay_s.get("poll", 0))
                    with outer._lock:
                        done = outer._run_done.get(run_id, False)
                        failed = outer._run_error.get(run_id)
                    if not done:
                        self._reply(200, {"status": "running"})
                    else:
                        self._reply(200, dict(failed or outer.scenario.run_outcome))
                elif path.startswith("/api/workflows/"):
                    # The workflow detail. Must stay LAST of the /api/workflows/
                    # branches: its prefix also matches every route above it.
                    wfid = path[len("/api/workflows/"):]
                    detail = outer.scenario.workflows.get(wfid)
                    if detail is None:
                        self._reply(404, {"error": "not_found"})
                    else:
                        recipe = {"inputs": outer.scenario.recipe_inputs}
                        self._reply(200, {"id": wfid, "recipe": recipe, **detail})
                else:
                    self._reply(404, {"error": "not_found"})

            def do_POST(self):
                body = self._json_body()
                self._record(body)
                path = urlsplit(self.path).path
                sc = outer.scenario
                if sc.server_error:
                    self._reply(500, {"error": "internal"})
                    return
                if path == "/api/auth/login":
                    time.sleep(sc.delay_s.get("login", 0))
                    if not sc.login_ok:
                        self._reply(401, {"error": "invalid_credentials"})
                        return
                    self._reply(200, {"user": {"id": "u1", "email": (body or {}).get("email")}},
                                extra_headers=(("Set-Cookie",
                                                f"monarch_session={outer.token}; HttpOnly"),))
                    return
                if not self._authed():
                    self._reply(401, {"error": "unauthenticated"})
                    return
                if path == "/api/workflows/recipe/runs":
                    time.sleep(sc.delay_s.get("authoring", 0))
                    with outer._lock:
                        outer.authoring_started_at.append(time.monotonic())
                        outer.authoring_bodies.append(body or {})
                        outer._authoring_jobs += 1
                        # A new job replays its frames from the start, even though
                        # the fake reuses the run id across attempts.
                        outer._frames_sent.pop("rr-1", None)
                        outer._connections.pop("rr-1", None)
                    self._reply(201, {"runId": "rr-1", "token": "t"})
                elif path.startswith("/api/workflows/recipe/runs/") and path.endswith("/reply"):
                    rid = (body or {}).get("requestId", "")
                    with outer._lock:
                        outer.replies_received.append(body or {})
                    outer._event(rid).set()
                    self._reply(200, {})
                elif path.startswith("/api/workflows/recipe/runs/") and path.endswith("/cancel"):
                    run_id = path[len("/api/workflows/recipe/runs/"):-len("/cancel")]
                    with outer._lock:
                        outer._cancelled.add(run_id)
                        pending = list(outer._reply_events.values())
                    for ev in pending:          # release the stream from any reply gate
                        ev.set()
                    self._reply(200, {"status": "cancelled"})
                elif path.startswith("/api/workflows/") and path.endswith("/llm-ack"):
                    self._llm_ack()
                elif path.startswith("/api/workflows/") and path.endswith("/run"):
                    self._workflow_run()
                else:
                    self._reply(404, {"error": "not_found"})

            def do_DELETE(self):
                self._record(None)
                path = urlsplit(self.path).path
                sc = outer.scenario
                if sc.server_error:
                    self._reply(500, {"error": "internal"})
                    return
                if not self._authed():
                    self._reply(401, {"error": "unauthenticated"})
                    return
                wfid = path.rsplit("/", 1)[-1]
                with outer._lock:          # decide under the lock, answer outside it
                    outer.deleted_at.append(time.monotonic())
                    if sc.delete_fails_once and not outer._delete_failed_once:
                        outer._delete_failed_once = True
                        answer = (500, {"error": "delete_failed"})
                    elif wfid in outer.deleted_workflows:
                        answer = (404, {"error": "not_found"})
                    else:
                        outer.deleted_workflows.append(wfid)
                        answer = (200, {})
                self._reply(*answer)

            # -- the interesting routes ----------------------------------------
            def _llm_ack(self):
                """Stamp this recipe version, or say it has no loop to stamp."""
                rest = urlsplit(self.path).path[len("/api/workflows/"):-len("/llm-ack")]
                wfid, _, version = rest.partition("/versions/")
                if not outer.scenario.has_llm_loop:
                    self._reply(422, {"code": "LLM_LOOP_NOT_PRESENT",
                                      "error": "this version has no LLM loop"})
                    return
                with outer._lock:
                    outer.llm_acks.append((wfid, version))
                    outer._acked.add((wfid, version))
                self._reply(200, {"version": int(version) if version.isdigit() else version,
                                  "acknowledgedAt": "2026-09-05T00:00:00Z"})

            def _workflow_run(self):
                sc = outer.scenario
                wfid = urlsplit(self.path).path[len("/api/workflows/"):-len("/run")]
                # A workflow the backend no longer holds cannot be run. Only a
                # scenario that declares `workflows` is checked, so the create + run
                # tests -- which run an id the fake invented -- are unaffected.
                if sc.workflows and wfid not in sc.workflows:
                    self._reply(404, {"error": "not_found"})
                    return
                with outer._lock:
                    left = outer._refusals_left.get(wfid, 0)
                    if left or (sc.active_run_never_clears and wfid in sc.workflows):
                        if not sc.active_run_never_clears:
                            outer._refusals_left[wfid] = left - 1
                        if wfid not in outer._leftover_runs:   # the run already in flight
                            outer._run_n += 1
                            leftover = outer._leftover_runs[wfid] = f"run-{outer._run_n}"
                            outer._run_done[leftover] = False
                        refuse = True
                    else:
                        outer._leftover_runs.pop(wfid, None)
                        refuse = False
                if refuse:
                    self._reply(409, {"code": "RUN_ALREADY_ACTIVE", "error": "RUN_ALREADY_ACTIVE"})
                    return
                if sc.run_refusal:
                    code = _REFUSAL_STATUS.get(sc.run_refusal, 422)
                    self._reply(code, {"code": sc.run_refusal, "error": sc.run_refusal})
                    return
                body = self._json_body_recorded()
                with outer._lock:
                    outer.run_bodies.append(body)
                    acked = any(w == wfid for w, _ in outer._acked)
                if sc.has_llm_loop and not acked:
                    self._reply(422, {"code": "LLM_LOOP_UNACKNOWLEDGED",
                                      "error": "acknowledge the LLM loop first"})
                    return
                bad = _input_errors(sc.recipe_inputs, body.get("inputs") or {})
                if bad:
                    self._reply(422, {"code": "INPUT_INVALID", "error": "INPUT_INVALID",
                                      "inputs": bad})
                    return
                with outer._lock:
                    outer._run_n += 1
                    run_id = f"run-{outer._run_n}"
                    outer.run_started_at.append(time.monotonic())
                    outer._run_done[run_id] = False
                episode_id = self.headers.get("x-bench-episode-id") or ""
                threading.Thread(target=outer._fire_engine_calls, args=(run_id, episode_id),
                                 daemon=True).start()
                self._reply(201, {"id": run_id, "engine": {"runId": run_id, "status": "running"}})

            def _hold_open(self):
                """Keep the connection open, saying nothing, until the server stops."""
                outer._stopping.wait(timeout=HOLD_OPEN_S)

            def _authoring_view(self, run_id: str):
                """GET the run view: the last frame emitted, plus the terminal one
                when the scenario said the stream would drop it."""
                sc = outer.scenario
                with outer._lock:
                    sent = outer._frames_sent.get(run_id, 0)
                if not sent:
                    self._reply(200, {"status": "running"})
                    return
                frame = self._decorate(sc.frames[sent - 1], run_id)
                self._reply(200, {"runId": run_id, **frame})

            def _decorate(self, frame: dict, run_id: str) -> dict:
                """The scenario's per-run additions to a frame: unique workflow id,
                declared inputs, the builder's assumptions."""
                sc = outer.scenario
                if sc.unique_workflow_ids and frame.get("workflowId"):
                    frame = {**frame, "workflowId": outer._workflow_of(run_id)}
                if (sc.recipe_inputs or sc.recipe_assumptions) and frame.get("status") == "done":
                    recipe = {**(frame.get("recipe") or {}), "inputs": sc.recipe_inputs}
                    if sc.recipe_assumptions:
                        recipe["assumptions"] = sc.recipe_assumptions
                    frame = {**frame, "recipe": recipe}
                return frame

            def _stream(self):
                sc = outer.scenario
                run_id = urlsplit(self.path).path[
                    len("/api/workflows/recipe/runs/"):-len("/stream")]
                with outer._lock:
                    outer.stream_connections += 1
                    connection = outer._connections[run_id] = (
                        outer._connections.get(run_id, 0) + 1)
                    # Only a scenario that asks to be cut resumes; every other
                    # connection replays the job from the start, which is what
                    # the real backend does when a client re-opens the stream.
                    start = (outer._frames_sent.get(run_id, 0)
                             if sc.stream_cut_after is not None else 0)
                if sc.stream_404_after is not None and connection > sc.stream_404_after:
                    self._reply(404, {"error": "not_found"})   # the job is gone
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self._chunk(b": ping\n\n")
                if sc.stream_silent:
                    # No frames, no close: the reader only wakes on its own beat.
                    self._hold_open()
                    return
                for i, frame in enumerate(sc.frames[start:], start=start):
                    if sc.drop_terminal_frame and frame.get("status") in ("done", "error"):
                        # The job reached its ending; the client never hears it.
                        # The view is the only place that says so.
                        with outer._lock:
                            outer._frames_sent[run_id] = i + 1
                        if sc.hold_open_after_terminal:
                            # ...and the connection stays open too, so not even a
                            # closed stream tells the client to go and look.
                            self._hold_open()
                        break
                    if (sc.stream_cut_after is not None and connection == 1
                            and i - start >= sc.stream_cut_after):
                        break                      # the edge cut the response
                    time.sleep(sc.delay_s.get("frame", 0))
                    frame = self._decorate(frame, run_id)
                    self._chunk(f"data: {json.dumps(frame)}\n\n".encode())
                    with outer._lock:
                        outer._frames_sent[run_id] = i + 1
                    if frame.get("status") == "awaiting_input":
                        rid = (frame.get("awaiting_reply") or {}).get("requestId", "")
                        outer._event(rid).wait(timeout=REPLY_GATE_TIMEOUT_S)
                        with outer._lock:
                            cancelled = run_id in outer._cancelled
                        if cancelled:
                            self._chunk(b'data: {"status": "error", "error": "cancelled"}\n\n')
                            break
                    if frame.get("status") in ("done", "error"):
                        break
                self._chunk(b"")   # terminating chunk closes the stream

            def _chunk(self, payload: bytes):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(payload), payload))
                self.wfile.flush()

        return Handler

    def start(self) -> "FakeMonarch":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stopping.set()
        self.httpd.shutdown()
        # Join before closing: a stream handler still writing frames from the
        # previous scenario would otherwise outlive its test and serve them to
        # the next one, whose fixture is a different FakeMonarch but whose
        # client may still be reading.
        self._thread.join(timeout=10)
        self.httpd.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
