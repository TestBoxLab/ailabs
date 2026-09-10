"""HTTP client for the Monarch backend (research R5; specs/002).

Stdlib only. Session auth: either a token handed in (MONARCH_TOKEN) or a login
that reads the `monarch_session` cookie; every later call sends it as
`x-monarch-session`. The authoring stream is server-sent events read on a fixed
beat so a deadline can interrupt it, and `get_authoring_run` is the backstop
that says where a job stands when the stream loses its terminal frame.

Errors follow the arm contract: anything the backend cannot answer for
(connection refused, 5xx, a refused login) is `InfraError("infra:harness_crash")`
and is not the competitor's fault; a workflow run the backend *deliberately*
refuses is `MonarchRefused`, which the attempt flow reads as a gate refusal.
"""
from __future__ import annotations

import json
import select
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from typing import Iterator

from wb_arms.api_loop import EpisodeTimeout, InfraError

DEFAULT_TIMEOUT_S = 30.0
# The SSE reader waits at most this long for the socket to have something, so a
# silent server cannot park it past its deadline (live run-20260908-145828: a
# 1800 s deadline, cut at 2369 s).
SOCKET_TIMEOUT_S = 20.0


class MonarchRefused(Exception):
    """The backend answered 4xx with a refusal code (e.g. RUN_HOST_BLOCKED)."""

    def __init__(self, code: str, status: int, body: dict):
        super().__init__(f"{code} (HTTP {status})")
        self.code, self.status, self.body = code, status, body


class MonarchClient:
    def __init__(self, base_url: str, token: str | None = None,
                 socket_timeout_s: float = SOCKET_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.token = token
        # The authoring stream's beat: how long the reader waits for the socket
        # to have something before reporting back. It bounds how late the
        # deadline can be noticed when the server goes silent, so it is a
        # constructor argument the tests turn down.
        self.socket_timeout_s = socket_timeout_s

    # -- plumbing --------------------------------------------------------------

    def _budget(self, deadline: float | None) -> float:
        # ponytail: 1 s floor, never 0: urlopen reads a non-positive timeout as
        # "no timeout". A call past the deadline still gets that second; the
        # caller (stream, the arm's poll loop) enforces the ceiling.
        return DEFAULT_TIMEOUT_S if deadline is None else max(1.0, deadline - time.monotonic())

    def _request(self, method: str, path: str, body: dict | None = None,
                 headers: dict | None = None, accept: str = "application/json"):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json", "Accept": accept, **(headers or {})}
        if self.token:
            h["x-monarch-session"] = self.token
        return urllib.request.Request(self.base_url + path, data=data, method=method, headers=h)

    def _call(self, method: str, path: str, body: dict | None = None,
              headers: dict | None = None, deadline: float | None = None,
              ok_status: tuple[int, ...] = ()) -> dict:
        """One JSON call. 4xx with a `code` -> MonarchRefused; 5xx and transport -> InfraError."""
        req = self._request(method, path, body, headers)
        try:
            with urllib.request.urlopen(req, timeout=self._budget(deadline)) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            payload = _json_or_none(raw)
            if e.code in ok_status:
                return payload or {}
            if 400 <= e.code < 500 and isinstance(payload, dict) and payload.get("code"):
                raise MonarchRefused(payload["code"], e.code, payload) from e
            raise InfraError("infra:harness_crash",
                             f"Monarch {method} {path}: HTTP {e.code}: "
                             f"{raw[:200].decode('utf-8', 'replace')}") from e
        except OSError as e:
            raise InfraError("infra:harness_crash", f"Monarch {method} {path}: {e}") from e
        return _json_or_none(raw) or {}

    # -- session ---------------------------------------------------------------

    def login(self, email: str, password: str, deadline: float | None = None) -> str:
        req = self._request("POST", "/api/auth/login", {"email": email, "password": password})
        try:
            with urllib.request.urlopen(req, timeout=self._budget(deadline)) as r:
                cookie = SimpleCookie(r.headers.get("Set-Cookie", ""))
                r.read()
        except urllib.error.HTTPError as e:
            raise InfraError("infra:harness_crash",
                             f"Monarch login refused for {email}: HTTP {e.code}") from e
        except OSError as e:
            raise InfraError("infra:harness_crash", f"Monarch login failed: {e}") from e
        if "monarch_session" not in cookie:
            raise InfraError("infra:harness_crash",
                             "Monarch login answered without a monarch_session cookie")
        self.token = cookie["monarch_session"].value
        return self.token

    def health(self, deadline: float | None = None) -> dict:
        return self._call("GET", "/api/health", deadline=deadline)

    def liveness(self, deadline: float | None = None) -> bool:
        try:
            with urllib.request.urlopen(self._request("GET", "/api", accept="text/plain"),
                                        timeout=self._budget(deadline)) as r:
                return r.status == 200
        except (urllib.error.HTTPError, OSError):
            return False

    # -- authoring -------------------------------------------------------------

    def start_authoring(self, goal: str, episode_id: str, deadline: float | None = None,
                        authoring_mode: str | None = None) -> str:
        """Start an authoring job. `authoring_mode="unattended"` asks the builder not
        to stop for questions; anything else sends today's body, with no such field."""
        body = {"goal": goal}
        if authoring_mode == "unattended":
            body["authoring"] = "unattended"
        out = self._call("POST", "/api/workflows/recipe/runs", body,
                         headers={"x-bench-episode-id": episode_id}, deadline=deadline)
        return out["runId"]

    def stream(self, run_id: str, deadline: float | None = None) -> Iterator[dict | None]:
        """Yield the parsed `data:` frames of the authoring stream until it closes.

        Comment lines (`: ping`) and blank separators are dropped. The reader
        waits at most `socket_timeout_s` for the socket to have something, and a
        wait that finds nothing yields `None` -- "still open, nothing said" -- so
        the caller wakes on a fixed beat: that is what lets it observe its
        deadline and poll the run view even when the server has gone quiet.
        """
        yield from self._sse(f"/api/workflows/recipe/runs/{run_id}/stream",
                             f"authoring run {run_id}", deadline)

    def run_stream(self, engine_run_id: str, deadline: float | None = None) -> Iterator[dict]:
        """Yield the run views the engine streams while a workflow executes.

        The stock backend (`engine.controller.ts`, `GET /api/engine/runs/:id/stream`)
        writes one frame per change of the persisted run view -- the same shape as
        `GET /api/workflows/runs/:id`, with `steps` carrying every recipe node's
        status -- and closes the stream once the engine state is terminal. The
        viewer guard accepts the owner's session, so the login token suffices.
        A backend without the route answers 404, which the arm reads as "poll".
        """
        yield from self._sse(f"/api/engine/runs/{engine_run_id}/stream",
                             f"engine run {engine_run_id}", deadline)

    def _sse(self, path: str, label: str, deadline: float | None) -> Iterator[dict]:
        req = self._request("GET", path, accept="text/event-stream")
        try:
            resp = urllib.request.urlopen(req, timeout=self._budget(deadline))
            # The timeout above bounds the connect and the response headers only.
            # Reads are paced by `select` below, so the socket goes back to
            # blocking: a socket timeout on top of the beat would read "timed
            # out" as a crash when the stream is merely quiet.
            sock = _socket_of(resp)
            if sock is not None:
                sock.settimeout(None)
        except urllib.error.HTTPError as e:
            raise InfraError("infra:harness_crash",
                             f"Monarch stream {label}: HTTP {e.code}") from e
        except OSError as e:
            raise InfraError("infra:harness_crash", f"Monarch stream {label}: {e}") from e
        timeout = EpisodeTimeout(f"deadline hit while streaming {label}")
        # Read the socket directly, paced by `select`, rather than through the
        # response object. Two reasons, both learned the hard way: a socket
        # timeout poisons the socket on Windows ("cannot read from timed out
        # object"), and `http.client`'s chunked decoder blocks on a chunk header
        # whatever `select` says -- so neither gives a reliable beat. Raw bytes
        # cost only that chunk-size lines arrive between the SSE lines, and those
        # are dropped by the same rule that drops `: ping`: they are not `data:`.
        sock = _socket_of(resp)
        if sock is None:                # no way in: fall back to blocking reads
            raise InfraError("infra:harness_crash",
                             f"Monarch stream {label}: no socket to read")
        # Whatever `urlopen` already buffered while reading the headers: the
        # socket no longer holds it, so it is taken first.
        pending = _buffered(resp)
        try:
            while True:
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("data:"):
                        frame = _json_or_none(line[len("data:"):].strip())
                        if frame is not None:
                            yield frame
                if deadline is not None and time.monotonic() >= deadline:
                    raise timeout
                if not select.select([sock], [], [], self.socket_timeout_s)[0]:
                    yield None          # the beat: the caller decides what to do
                    continue
                try:
                    chunk = sock.recv(65536)
                except OSError as e:
                    raise InfraError("infra:harness_crash",
                                     f"Monarch stream {label}: {e}") from e
                if not chunk:
                    return              # the server closed, or cut, the stream
                pending += chunk
        finally:
            # The socket has no timeout, so closing a chunked response the caller
            # walked away from would block until the server finished the body.
            # Drop the connection instead: nothing here is reused.
            sock = _socket_of(resp)
            if sock is not None:
                sock.close()
            resp.close()

    def get_authoring_run(self, run_id: str, deadline: float | None = None) -> dict:
        """The authoring run's view: the same fields as an SSE frame.

        The backstop for a terminal frame the stream never delivered (live
        session 25ade669, 8 Sep 2026): `status` is `running`, `awaiting_input`,
        `done` or `error`, and a `done` view carries `workflowId`/`recipeVersion`.
        """
        return self._call("GET", f"/api/workflows/recipe/runs/{run_id}", deadline=deadline)

    def reply(self, run_id: str, request_id: str, answers: list[dict],
              deadline: float | None = None) -> dict:
        return self._call("POST", f"/api/workflows/recipe/runs/{run_id}/reply",
                          {"requestId": request_id, "answers": answers}, deadline=deadline)

    def cancel(self, run_id: str, deadline: float | None = None) -> dict:
        return self._call("POST", f"/api/workflows/recipe/runs/{run_id}/cancel", {},
                          deadline=deadline)

    # -- running and cleanup ---------------------------------------------------

    def run_workflow(self, workflow_id: str, episode_id: str, mode: str = "live",
                     deadline: float | None = None) -> dict:
        body = {"mode": mode}
        return self._call("POST", f"/api/workflows/{workflow_id}/run", body,
                          headers={"x-bench-episode-id": episode_id}, deadline=deadline)

    def llm_ack(self, workflow_id: str, version, deadline: float | None = None) -> dict:
        """Stamp a recipe version's LLM loop; a version with no loop answers 422.

        The stamp is per version, not per run, so it is sent once before the run.
        MonarchRefused("LLM_LOOP_NOT_PRESENT") is the "nothing to stamp" answer.
        """
        return self._call("POST", f"/api/workflows/{workflow_id}/versions/{version}/llm-ack",
                          {}, deadline=deadline)

    def get_workflow(self, workflow_id: str, deadline: float | None = None) -> dict | None:
        """The workflow detail, with its `recipeVersion`; None when Monarch no longer has it."""
        out = self._call("GET", f"/api/workflows/{workflow_id}", deadline=deadline,
                         ok_status=(404,))
        return None if out.get("error") == "not_found" else out

    def workflow_runs(self, workflow_id: str, deadline: float | None = None) -> list[dict]:
        """The workflow's runs, newest first; `[]` when it has never run."""
        out = self._call("GET", f"/api/workflows/{workflow_id}/runs", deadline=deadline)
        return out.get("items") or []

    def get_run(self, run_id: str, deadline: float | None = None) -> dict:
        return self._call("GET", f"/api/workflows/runs/{run_id}", deadline=deadline)

    def run_recipe(self, run_id: str, deadline: float | None = None) -> dict | None:
        """The recipe THIS run executed (`GET /api/workflows/runs/:id/recipe`);
        None when the backend has no such route or no longer holds the run."""
        out = self._call("GET", f"/api/workflows/runs/{run_id}/recipe", deadline=deadline,
                         ok_status=(404,))
        return None if not out or out.get("error") else out

    def delete_workflow(self, workflow_id: str, deadline: float | None = None) -> dict:
        # Already gone is the state we wanted, so 404 is success.
        return self._call("DELETE", f"/api/workflows/{workflow_id}", deadline=deadline,
                          ok_status=(404,))


def _buffered(resp) -> bytes:
    """Body bytes `urlopen` already pulled off the socket while reading headers.

    The reader takes the socket over, so anything the response buffer holds would
    otherwise be lost. `read1` on a `BufferedReader` hands back what the buffer
    has and only goes to the socket when the buffer is empty -- so it is called
    only while the socket is readable, which makes even that case return at once.
    Nothing readable and nothing buffered is the same answer either way: nothing.
    """
    fp, sock = getattr(resp, "fp", None), _socket_of(resp)
    if fp is None or sock is None:
        return b""
    try:
        # What the buffer already holds, first and without touching the socket:
        # `urlopen` can pull the first SSE frame in while reading the headers, and
        # then the socket has nothing pending -- waiting on `select` would time out
        # and drop that frame. Only an empty buffer is a question for the socket.
        if not fp.peek(0):
            if not select.select([sock], [], [], 0.2)[0]:
                return b""
        return fp.read1(65536)
    except (OSError, ValueError):
        return b""


def _socket_of(resp):
    """The response's underlying socket, or None. Best effort: the only way in is
    a private attribute, and a build that hides it simply keeps today's behaviour."""
    return getattr(getattr(getattr(resp, "fp", None), "raw", None), "_sock", None)


def _json_or_none(raw: str | bytes):
    try:
        return json.loads(raw or "null")
    except json.JSONDecodeError:
        return None
