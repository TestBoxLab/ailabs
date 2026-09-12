"""The Studio's front door must be able to relay to a shim that is not on its host.

The relay assumed the attempt ran in the same container, which is true when the
Studio launches it and false when the CLI does. With the address fixed at
127.0.0.1 a hosted Studio answers 502 to every application call from a laptop
round, so the seeds could name the hosted door but no attempt could serve it.
`STUDIO_FRONT_DOOR_TARGET` names where the shim actually listens.

The second half of this file is feature 024 FR-001. The relay was reachable with
no credentials: `do_GET` and `do_POST` tested `is_front_door()` before
`authorised()`, and `do_PUT`, `do_PATCH` and `do_DELETE` never called
`authorised()` at all. Anyone holding the hosted address could write into a
running attempt's world, and the approval rule reads such a write as the
competitor failing. Basic Auth cannot be the gate here because the competitor
under test calls this path and has no credentials, so the door is gated by a
secret segment that travels in the seed URL instead.
"""
from __future__ import annotations

import http.client
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest
import yaml

from wb_orchestrator.monarch_setup import _write_kb, front_door_path
from wb_studio.app import ROOT, Studio, front_door_target, handler
from wb_world.episode import load_suite


def test_the_default_is_the_studio_s_own_loopback():
    assert front_door_target({}, "/openapi/index.json") == "http://127.0.0.1:9105/openapi/index.json"


def test_a_port_moves_the_loopback_target():
    assert front_door_target({"STUDIO_FRONT_DOOR_PORT": "9200"}, "/x") == "http://127.0.0.1:9200/x"


def test_an_explicit_target_sends_the_call_off_host():
    env = {"STUDIO_FRONT_DOOR_TARGET": "https://tunnel.example.dev"}
    assert front_door_target(env, "/airtable/meta/bases") == "https://tunnel.example.dev/airtable/meta/bases"


def test_a_trailing_slash_on_the_target_does_not_double():
    env = {"STUDIO_FRONT_DOOR_TARGET": "https://tunnel.example.dev/"}
    assert front_door_target(env, "/x") == "https://tunnel.example.dev/x"


def test_the_explicit_target_wins_over_the_port():
    env = {"STUDIO_FRONT_DOOR_TARGET": "https://tunnel.example.dev", "STUDIO_FRONT_DOOR_PORT": "9200"}
    assert front_door_target(env, "/x") == "https://tunnel.example.dev/x"


# --- FR-001: the door is gated by a secret segment -----------------------------------

SECRET = "s3cr3t-front-door-token"
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
# 502 is the tell that the relay was attempted: there is no shim behind the door in a
# test, so only a call that got past the gate can produce one. Which refusal code the
# caller sees does not matter; reaching the world does.
REFUSED = (401, 403, 404)


@pytest.fixture
def gated(tmp_path, monkeypatch):
    """A Studio whose front door demands the secret, as a hosted one must."""
    monkeypatch.setenv("STUDIO_FRONT_DOOR_SECRET", SECRET)
    def forbidden_gateway(*args, **kwargs):
        pytest.fail("An offline Studio test attempted paid dispatch")
    return Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1],
                  gateway_factory=forbidden_gateway)


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


def call(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read().decode()
    finally:
        connection.close()


def test_a_write_without_the_secret_never_reaches_the_world(gated):
    """The reported defect: an anonymous DELETE landed in the running attempt's world."""
    with server_for(gated) as port:
        for method in WRITE_METHODS:
            status, _ = call(port, method, "/front-door/airtable/v0/app1/Tasks/rec1", "{}")
            assert status in REFUSED, f"{method} without the secret was not refused"


def test_a_read_without_the_secret_is_refused(gated):
    with server_for(gated) as port:
        status, _ = call(port, "GET", "/front-door/openapi/index.json")
        assert status in REFUSED


def test_a_wrong_secret_is_refused_on_every_method(gated):
    with server_for(gated) as port:
        for method in ("GET", *WRITE_METHODS):
            status, _ = call(port, method, "/front-door/not-the-secret/airtable/v0/app1/Tasks", "{}")
            assert status in REFUSED, f"{method} with a wrong secret was not refused"


def test_the_right_secret_is_relayed_and_the_segment_is_stripped(gated):
    """502 proves the relay was attempted: there is no shim behind it in a test."""
    with server_for(gated) as port:
        status, body = call(port, "GET", f"/front-door/{SECRET}/openapi/index.json")
        assert status == 502 and "front door is not running on this host" in body


def test_an_unconfigured_door_refuses_rather_than_opening(tmp_path, monkeypatch):
    """Fail closed. An absent secret must not mean 'no gate' on a public address."""
    monkeypatch.delenv("STUDIO_FRONT_DOOR_SECRET", raising=False)
    studio = Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1],
                    gateway_factory=lambda *a, **k: pytest.fail("paid dispatch"))
    with server_for(studio) as port:
        for method in ("GET", *WRITE_METHODS):
            status, _ = call(port, method, "/front-door/anything/airtable/v0/app1/Tasks", "{}")
            assert status in REFUSED, f"{method} was served by an unconfigured front door"


def test_the_secret_segment_is_built_into_the_seed_url():
    """Monarch sends nothing new: the secret rides in the address the seeds name."""
    base = front_door_path("https://studio.example.dev/front-door", {"STUDIO_FRONT_DOOR_SECRET": SECRET})
    assert base == f"https://studio.example.dev/front-door/{SECRET}"


def test_a_seed_url_without_a_secret_is_unchanged():
    assert front_door_path("https://studio.example.dev/front-door", {}) == "https://studio.example.dev/front-door"


def test_the_tracked_knowledge_base_records_the_secret_by_name(tmp_path):
    """`config/products/<product>.monarch-kb.yaml` is git-tracked and this repo is
    public, so a secret written into it once is in history, not just in a file.
    Only the config hash reads this field, and never as an address, so the name
    carries everything the record needs."""
    env = {"STUDIO_FRONT_DOOR_SECRET": SECRET}
    live = front_door_path("https://studio.example.dev/front-door", env)
    assert SECRET in live, "the address Monarch is handed must carry the secret"
    path, _ = _write_kb(tmp_path / "tau2-retail.yaml", "tau2-retail", live,
                        {"bench-gym-itsm-mcp": "sha"}, env=env)
    text = path.read_text(encoding="utf-8")
    assert SECRET not in text, "the secret reached a tracked file"
    assert "${STUDIO_FRONT_DOOR_SECRET}" in text


def test_rotating_the_secret_leaves_the_configuration_unchanged(tmp_path):
    """Rotating per round is what the docstring tells an operator to do. Recording
    the value made that read as a different configuration and moved the hash."""
    written = []
    for secret in ("round-47", "round-48"):
        env = {"STUDIO_FRONT_DOOR_SECRET": secret}
        live = front_door_path("https://studio.example.dev/front-door", env)
        path, _ = _write_kb(tmp_path / "tau2-retail.yaml", "tau2-retail", live,
                            {"bench-gym-itsm-mcp": "sha"}, env=env)
        written.append(yaml.safe_load(path.read_text(encoding="utf-8"))["shim_public_url"])
    assert written[0] == written[1]
