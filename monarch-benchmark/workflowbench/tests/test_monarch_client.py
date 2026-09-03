"""The Monarch HTTP client against the fake backend (US1, T021).

Covers the whole surface the attempt flow needs: login and the session header,
the authoring run with its episode header and SSE stream, reply/cancel, the
workflow run and its polling, deletion, and the two error shapes (5xx is
infrastructure, a deadline inside the stream is a timeout).
"""
from __future__ import annotations

import time

import pytest

from tests.fake_monarch import FakeMonarch, Scenario
from wb_arms.api_loop import EpisodeTimeout, InfraError
from wb_arms.monarch_client import MonarchClient, MonarchRefused


@pytest.fixture
def fake():
    with FakeMonarch() as f:
        yield f


def header(request: dict, name: str) -> str | None:
    """Header lookup by lowercase name: urllib capitalizes what it puts on the wire."""
    return next((v for k, v in request["headers"].items() if k.lower() == name), None)


def logged_in(fake) -> MonarchClient:
    c = MonarchClient(fake.url)
    c.login("dev-root@testbox.com", "monarch-dev")
    return c


# -- login and the session header ---------------------------------------------

def test_login_stores_the_session_token(fake):
    c = logged_in(fake)
    assert c.token == fake.token
    body = next(r["body"] for r in fake.requests if r["path"] == "/api/auth/login")
    assert body == {"email": "dev-root@testbox.com", "password": "monarch-dev"}


def test_a_given_token_skips_the_login_request(fake):
    fake.scenario.preset_token = "preset-token"
    c = MonarchClient(fake.url, token="preset-token")
    assert c.health() == {"ok": True}
    assert not [r for r in fake.requests if r["path"] == "/api/auth/login"]


def test_every_call_sends_the_session_header(fake):
    c = logged_in(fake)
    c.health()
    c.liveness()
    authed = [r for r in fake.requests if r["path"] not in ("/api/auth/login", "/api")]
    assert authed and all(header(r, "x-monarch-session") == fake.token for r in authed)


def test_a_refused_login_is_an_infra_error(fake):
    fake.scenario.login_ok = False
    with pytest.raises(InfraError) as exc:
        MonarchClient(fake.url).login("dev-root@testbox.com", "wrong")
    assert exc.value.kind == "infra:harness_crash" and "login" in str(exc.value)


def test_liveness_reports_the_plain_text_root(fake):
    assert MonarchClient(fake.url).liveness() is True


# -- authoring: start, stream, reply, cancel ----------------------------------

def test_start_authoring_sends_the_episode_header_and_returns_the_run_id(fake):
    c = logged_in(fake)
    assert c.start_authoring("close the deal", "ep-7") == "rr-1"
    req = next(r for r in fake.requests if r["path"] == "/api/workflows/recipe/runs")
    assert req["body"] == {"goal": "close the deal"}
    assert header(req, "x-bench-episode-id") == "ep-7"
    assert fake.episode_headers == ["ep-7"]


def test_stream_yields_frames_and_ignores_pings(fake):
    c = logged_in(fake)
    run_id = c.start_authoring("goal", "ep-1")
    frames = list(c.stream(run_id, deadline=time.monotonic() + 30))
    assert frames == [{"status": "running", "phase": "plan"},
                      {"status": "done", "workflowId": "wf-1", "recipeVersion": 1}]


def test_reply_reaches_the_stream_gate(fake):
    fake.scenario.frames = [
        {"status": "awaiting_input",
         "awaiting_reply": {"requestId": "q1", "questions": [{"id": "a", "text": "which?"}]}},
        {"status": "done", "workflowId": "wf-2"}]
    c = logged_in(fake)
    run_id = c.start_authoring("goal", "ep-1")
    stream = c.stream(run_id, deadline=time.monotonic() + 30)
    first = next(stream)
    assert first["status"] == "awaiting_input"
    c.reply(run_id, "q1", [{"id": "a", "text": "the first one"}])
    assert next(stream)["status"] == "done"
    assert fake.replies_received == [
        {"requestId": "q1", "answers": [{"id": "a", "text": "the first one"}]}]


def test_cancel_ends_a_run_waiting_on_a_reply(fake):
    fake.scenario.frames = [
        {"status": "awaiting_input", "awaiting_reply": {"requestId": "q1", "questions": []}},
        {"status": "done", "workflowId": "wf-3"}]
    c = logged_in(fake)
    run_id = c.start_authoring("goal", "ep-1")
    stream = c.stream(run_id, deadline=time.monotonic() + 30)
    assert next(stream)["status"] == "awaiting_input"
    c.cancel(run_id)
    assert next(stream) == {"status": "error", "error": "cancelled"}


def test_a_deadline_inside_the_stream_raises_episode_timeout(fake):
    fake.scenario.delay_s = {"frame": 2.0}
    c = logged_in(fake)
    run_id = c.start_authoring("goal", "ep-1")
    with pytest.raises(EpisodeTimeout):
        list(c.stream(run_id, deadline=time.monotonic() + 1.0))


# -- running the workflow ------------------------------------------------------

def test_run_workflow_sends_the_episode_header_and_returns_the_run(fake):
    c = logged_in(fake)
    out = c.run_workflow("wf-1", "ep-9")
    assert out["engine"]["runId"] == "run-1"
    req = next(r for r in fake.requests if r["path"] == "/api/workflows/wf-1/run")
    assert req["body"] == {"mode": "live"}
    assert header(req, "x-bench-episode-id") == "ep-9"


def test_a_refused_run_carries_the_refusal_code(fake):
    fake.scenario.run_refusal = "RUN_HOST_BLOCKED"
    c = logged_in(fake)
    with pytest.raises(MonarchRefused) as exc:
        c.run_workflow("wf-1", "ep-1")
    assert exc.value.code == "RUN_HOST_BLOCKED" and exc.value.status == 422


def test_get_run_polls_until_the_engine_finishes(fake):
    c = logged_in(fake)
    run_id = c.run_workflow("wf-1", "ep-1")["engine"]["runId"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        out = c.get_run(run_id)
        if out["status"] != "running":
            break
    assert out == {"status": "succeeded"}


# -- deletion and infrastructure errors ----------------------------------------

def test_delete_workflow_tolerates_a_missing_workflow(fake):
    c = logged_in(fake)
    c.delete_workflow("wf-1")
    c.delete_workflow("wf-1")           # second delete answers 404; still fine
    assert fake.deleted_workflows == ["wf-1"]


def test_a_server_error_is_an_infra_error(fake):
    fake.scenario.preset_token = "preset-token"
    fake.scenario.server_error = True
    c = MonarchClient(fake.url, token="preset-token")
    with pytest.raises(InfraError) as exc:
        c.health()
    assert exc.value.kind == "infra:harness_crash"


def test_an_unreachable_backend_is_an_infra_error():
    with FakeMonarch() as f:
        url = f.url
    with pytest.raises(InfraError) as exc:
        MonarchClient(url, token="t").health()
    assert exc.value.kind == "infra:harness_crash"
