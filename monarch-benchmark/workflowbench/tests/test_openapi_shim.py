"""OpenAPI docs for the simulated services + the REST front door Monarch calls.
Validity is checked with openapi-spec-validator, the Python twin of the
swagger-parser gate Feature Discovery runs on every spec it ingests."""
from __future__ import annotations

import json
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
