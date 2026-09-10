"""OpenAPI docs for the simulated services + the REST front door Monarch calls.
Validity is checked with openapi-spec-validator, the Python twin of the
swagger-parser gate Feature Discovery runs on every spec it ingests."""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest
from openapi_spec_validator import validate

from wb_arms.http_shim import EpisodeHTTPShim
from wb_world.episode import Episode, load_task_file
from wb_world.openapi import build_all, load_schemas

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks" / "simple.email_sf_contact_city_update.json"


def test_every_service_yields_a_valid_openapi_document():
    schemas = load_schemas()
    specs = build_all("http://127.0.0.1:1")
    assert len(specs) == 47
    total = 0
    for svc, spec in specs.items():
        validate(spec)   # raises on an invalid document
        ops = sum(len(v) for v in spec["paths"].values())
        total += ops
        assert spec["servers"][0]["url"].endswith("/" + svc)
    # 758 AB endpoints; 72 share a method+path with a sibling and are merged, not dropped.
    assert total == 686
    qb = specs["quickbooks"]["paths"]["/v3/company/{companyId}/invoice"]["post"]
    assert qb["summary"].startswith("4 variants") and "quickbooks.invoice.void" in qb["description"]


def _http(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_published_gmail_routes_read_and_modify_the_frozen_world():
    task = load_task_file(ROOT / "tasks/check-collateral/simple.email_airtable_lead.json")
    ep = Episode(task, episode_id="gmail-route-regression")
    direct = Episode(task, episode_id="gmail-route-reference")
    original_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    expected = json.loads(direct.api_fetch("GET", original_url))
    assert expected["messages"]
    message_id = expected["messages"][0]["id"]
    shim = EpisodeHTTPShim(ep).start()
    try:
        status, listed = _http("GET", f"{shim.url}/gmail/v1/users/me/messages")
        assert (status, listed) == (200, expected)
        body = {"removeLabelIds": ["UNREAD"]}
        expected = json.loads(direct.api_fetch("POST", f"{original_url}/{message_id}/modify",
                                              body=json.dumps(body)))
        assert "error" not in expected
        status, modified = _http("POST", f"{shim.url}/gmail/v1/users/me/messages/{message_id}/modify", body)
        assert (status, modified) == (200, expected)
        assert ep.snapshot() == direct.snapshot()
    finally:
        shim.stop()


@pytest.fixture
def shim():
    ep = Episode(load_task_file(TASK), episode_id="shim-test")
    s = EpisodeHTTPShim(ep).start()
    yield s, ep
    s.stop()


def test_rest_round_trip_mutates_the_episode_world(shim):
    s, ep = shim
    status, idx = _http("GET", f"{s.url}/openapi/index.json")
    assert status == 200 and "salesforce" in idx
    status, spec = _http("GET", f"{s.url}/openapi/salesforce.json")
    assert status == 200 and spec["servers"][0]["url"] == f"{s.url}/salesforce"

    status, got = _http("GET", f"{s.url}/salesforce/services/data/v61.0/sobjects/Contact/003004")
    assert status == 200 and got.get("FirstName") == "Lisa"

    status, _ = _http("PATCH", f"{s.url}/salesforce/services/data/v61.0/sobjects/Contact/003004",
                      {"MailingCity": "Denver"})
    assert status in (200, 204)
    contact = next(c for c in ep.world.salesforce.contacts if c.id == "003004")
    assert contact.mailing_city == "Denver"

    status, err = _http("GET", f"{s.url}/salesforce/services/data/v61.0/sobjects/Contact/nope")
    assert status == 404 and "error" in err
    status, err = _http("GET", f"{s.url}/not-a-service/x")
    assert status == 404


def test_host_and_public_url_are_configurable():
    ep = Episode(load_task_file(TASK), episode_id="shim-bind")
    s = EpisodeHTTPShim(ep, host="0.0.0.0", port=0,
                        public_url="http://host.docker.internal:9105").start()
    try:
        assert s.url == f"http://0.0.0.0:{s.port}"
        status, idx = _http("GET", f"http://127.0.0.1:{s.port}/openapi/index.json")
        assert status == 200
        assert idx["salesforce"]["url"] == "http://host.docker.internal:9105/openapi/salesforce.json"
    finally:
        s.stop()


def test_default_host_stays_loopback():
    ep = Episode(load_task_file(TASK), episode_id="shim-default")
    s = EpisodeHTTPShim(ep)
    try:
        assert s.url == f"http://127.0.0.1:{s.port}"
    finally:
        s.httpd.server_close()


# -- the front-door access log (one JSON line per request) --------------------

def _log_lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_access_log_records_every_request(tmp_path):
    log = tmp_path / "front-door.jsonl"
    ep = Episode(load_task_file(TASK), episode_id="shim-log")
    s = EpisodeHTTPShim(ep, access_log=log).start()
    try:
        _http("GET", f"{s.url}/salesforce/services/data/v61.0/query?q=SELECT+Id")
        _http("PATCH", f"{s.url}/salesforce/services/data/v61.0/sobjects/Contact/003004",
              {"MailingCity": "Denver"})
        _http("GET", f"{s.url}/not-a-service/x")
    finally:
        s.stop()
    lines = _log_lines(log)
    assert len(lines) == 3
    get, patch, missing = lines
    assert get["method"] == "GET" and get["path"].endswith("query?q=SELECT+Id")
    assert get["ts"].endswith("+00:00") and isinstance(get["elapsed_ms"], (int, float))
    assert get["response_bytes"] > 0 and get["request_bytes"] == 0
    assert patch["method"] == "PATCH" and "Denver" in patch["request_body"]
    assert patch["request_bytes"] > 0
    assert missing["status"] == 404 and "not-a-service" in missing["response_body"]


def test_access_log_truncates_at_500_characters_and_keeps_the_header(tmp_path):
    log = tmp_path / "front-door.jsonl"
    ep = Episode(load_task_file(TASK), episode_id="shim-trunc")
    s = EpisodeHTTPShim(ep, access_log=log).start()
    try:
        big = {"MailingCity": "x" * 2000}
        data = json.dumps(big).encode()
        req = urllib.request.Request(
            f"{s.url}/salesforce/services/data/v61.0/sobjects/Contact/003004",
            data=data, method="PATCH",
            headers={"Content-Type": "application/json", "x-bench-episode-id": "ep-42"})
        try:
            urllib.request.urlopen(req).read()
        except urllib.error.HTTPError as e:
            e.read()
    finally:
        s.stop()
    line = _log_lines(log)[0]
    assert len(line["request_body"]) == 500 and line["request_bytes"] > 500
    assert len(line["response_body"]) <= 500
    assert line["episode_id"] == "ep-42"


def test_no_access_log_by_default(tmp_path):
    ep = Episode(load_task_file(TASK), episode_id="shim-nolog")
    s = EpisodeHTTPShim(ep).start()
    try:
        _http("GET", f"{s.url}/openapi/index.json")
    finally:
        s.stop()
    assert list(tmp_path.iterdir()) == []


def test_fixed_port_can_restart_after_serving_a_request():
    ep = Episode(load_task_file(TASK), episode_id="shim-restart")
    first = EpisodeHTTPShim(ep).start()
    port = first.port
    status, _ = _http("GET", f"{first.url}/openapi/index.json")
    assert status == 200
    first.stop()

    second = EpisodeHTTPShim(ep, port=port).start()
    try:
        status, _ = _http("GET", f"{second.url}/openapi/index.json")
        assert status == 200
    finally:
        second.stop()


def test_fixed_port_refuses_an_active_listener():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    try:
        ep = Episode(load_task_file(TASK), episode_id="shim-busy")
        with pytest.raises(OSError):
            EpisodeHTTPShim(ep, port=listener.getsockname()[1])
    finally:
        listener.close()
