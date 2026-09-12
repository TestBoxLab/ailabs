"""The turn stream is events, not a re-read every 650 ms (feature 024, stage S2).

`GET /api/genesis/turns/<id>/events` is the same shape as the run stream the Studio
already serves: `Last-Event-ID` with an `after=` fallback, one `id:` per event, a
keepalive comment, and a `done` frame carrying the settled turn so the client never has
to ask again. Two things the run stream lacks and this one has: a `retry:` at open,
because EventSource has no backoff of its own and would otherwise use whatever the
browser decided; and a keepalive relaxed to 15 s, because a turn is minutes of slow tool
calls rather than a run's steady tick.
"""
from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from wb_studio.app import ROOT, Studio, handler
from wb_world.episode import load_suite


@pytest.fixture
def studio(tmp_path):
    return Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1],
                  gateway_factory=lambda *a, **k: pytest.fail("paid dispatch"))


def write_turn(studio, identity, status, events):
    from wb_results.evidence import write_json
    turn = {"id": identity, "status": status, "model": "m", "message": "hi", "answer": "done",
            "created_at": "2026-09-11T00:00:00+00:00", "events": events, "maximum_usd": "1.00"}
    write_json(studio.genesis.path("turns", identity), turn)
    return turn


@contextmanager
def server_for(studio):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(studio))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def stream(port, path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    body = r.read().decode()
    c.close()
    return r.status, dict(r.getheaders()), body


def frames(body, kind):
    out = []
    for block in body.split("\n\n"):
        if f"event: {kind}" in block:
            for line in block.splitlines():
                if line.startswith("data: "):
                    out.append(json.loads(line[6:]))
    return out


def test_a_settled_turn_streams_its_events_then_the_turn(studio):
    events = [{"id": 1, "type": "tool_started", "action": "read_run"},
              {"id": 2, "type": "tool_completed", "action": "read_run", "detail": "ok"}]
    write_turn(studio, "t1", "completed", events)
    with server_for(studio) as port:
        status, headers, body = stream(port, "/api/genesis/turns/t1/events")
    assert status == 200 and headers["Content-Type"] == "text/event-stream"
    assert [e["id"] for e in frames(body, "step")] == [1, 2]
    done = frames(body, "done")
    assert len(done) == 1 and done[0]["status"] == "completed" and "events" not in done[0]


def test_it_names_its_own_reconnect_delay(studio):
    write_turn(studio, "t1", "completed", [])
    with server_for(studio) as port:
        _, _, body = stream(port, "/api/genesis/turns/t1/events")
    assert body.startswith("retry: 2000")


def test_last_event_id_resumes_without_replaying(studio):
    write_turn(studio, "t1", "completed", [{"id": i, "type": "tool_started", "action": "x"} for i in (1, 2, 3)])
    with server_for(studio) as port:
        _, _, body = stream(port, "/api/genesis/turns/t1/events", {"Last-Event-ID": "2"})
    assert [e["id"] for e in frames(body, "step")] == [3]


def test_the_after_query_is_the_fallback_for_the_first_connection(studio):
    write_turn(studio, "t1", "completed", [{"id": i, "type": "tool_started", "action": "x"} for i in (1, 2, 3)])
    with server_for(studio) as port:
        _, _, body = stream(port, "/api/genesis/turns/t1/events?after=1")
    assert [e["id"] for e in frames(body, "step")] == [2, 3]


def test_each_frame_carries_its_id_so_a_reconnect_knows_where_it_stopped(studio):
    write_turn(studio, "t1", "completed", [{"id": 7, "type": "tool_started", "action": "x"}])
    with server_for(studio) as port:
        _, _, body = stream(port, "/api/genesis/turns/t1/events")
    assert "id: 7" in body


def test_an_unknown_turn_is_refused_before_the_stream_opens(studio):
    with server_for(studio) as port:
        status, headers, _ = stream(port, "/api/genesis/turns/nope/events")
    assert status != 200 and headers.get("Content-Type") != "text/event-stream"


def test_the_proxy_is_told_not_to_buffer(studio):
    write_turn(studio, "t1", "completed", [])
    with server_for(studio) as port:
        _, headers, _ = stream(port, "/api/genesis/turns/t1/events")
    assert headers["Cache-Control"] == "no-cache" and headers["X-Accel-Buffering"] == "no"
