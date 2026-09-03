"""HTTP client for the Monarch backend (research R5; specs/002).

Stdlib only. Session auth: either a token handed in (MONARCH_TOKEN) or a login
that reads the `monarch_session` cookie; every later call sends it as
`x-monarch-session`. The authoring stream is server-sent events read line by
line so a deadline can interrupt it.

Errors follow the arm contract: anything the backend cannot answer for
(connection refused, 5xx, a refused login) is `InfraError("infra:harness_crash")`
and is not the competitor's fault; a workflow run the backend *deliberately*
refuses is `MonarchRefused`, which the attempt flow reads as a gate refusal.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from typing import Iterator

DEFAULT_TIMEOUT_S = 30.0


class MonarchRefused(Exception):
    """The backend answered 4xx with a refusal code (e.g. RUN_HOST_BLOCKED)."""

    def __init__(self, code: str, status: int, body: dict):
        super().__init__(f"{code} (HTTP {status})")
        self.code, self.status, self.body = code, status, body


class MonarchClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    # -- plumbing --------------------------------------------------------------

    def _budget(self, deadline: float | None) -> float:
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
        from wb_arms.api_loop import InfraError
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
        from wb_arms.api_loop import InfraError
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
        from wb_arms.api_loop import InfraError
        try:
            with urllib.request.urlopen(self._request("GET", "/api", accept="text/plain"),
                                        timeout=self._budget(deadline)) as r:
                return r.status == 200
        except (urllib.error.HTTPError, OSError):
            return False
        except InfraError:                                  # pragma: no cover - not raised here
            return False

    # -- authoring -------------------------------------------------------------

    def start_authoring(self, goal: str, episode_id: str, deadline: float | None = None) -> str:
        out = self._call("POST", "/api/workflows/recipe/runs", {"goal": goal},
                         headers={"x-bench-episode-id": episode_id}, deadline=deadline)
        return out["runId"]

    def stream(self, run_id: str, deadline: float | None = None) -> Iterator[dict]:
        """Yield the parsed `data:` frames of the authoring stream until it closes.

        Comment lines (`: ping`) and blank separators are dropped. The socket
        timeout is the remaining budget, so a stalled stream raises rather than
        hanging; the deadline is also checked between frames.
        """
        from wb_arms.api_loop import EpisodeTimeout, InfraError
        req = self._request("GET", f"/api/workflows/recipe/runs/{run_id}/stream",
                            accept="text/event-stream")
        try:
            resp = urllib.request.urlopen(req, timeout=self._budget(deadline))
        except urllib.error.HTTPError as e:
            raise InfraError("infra:harness_crash",
                             f"Monarch stream {run_id}: HTTP {e.code}") from e
        except OSError as e:
            raise InfraError("infra:harness_crash", f"Monarch stream {run_id}: {e}") from e
        timeout = EpisodeTimeout(f"deadline hit while streaming authoring run {run_id}")
        with resp:
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    raise timeout
                try:
                    line = resp.readline()
                except TimeoutError as e:
                    # The socket timeout is the remaining budget, so a stalled
                    # read means the deadline passed mid-frame, not a crash.
                    raise timeout from e
                if not line:
                    return
                line = line.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    frame = _json_or_none(line[len("data:"):].strip().encode())
                    if frame is not None:
                        yield frame

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
        return self._call("POST", f"/api/workflows/{workflow_id}/run", {"mode": mode},
                          headers={"x-bench-episode-id": episode_id}, deadline=deadline)

    def get_run(self, run_id: str, deadline: float | None = None) -> dict:
        return self._call("GET", f"/api/workflows/runs/{run_id}", deadline=deadline)

    def delete_workflow(self, workflow_id: str, deadline: float | None = None) -> dict:
        # Already gone is the state we wanted, so 404 is success.
        return self._call("DELETE", f"/api/workflows/{workflow_id}", deadline=deadline,
                          ok_status=(404,))


def _json_or_none(raw: bytes):
    try:
        return json.loads(raw or b"null")
    except json.JSONDecodeError:
        return None
