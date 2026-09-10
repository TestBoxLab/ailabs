"""The live Product Graph Monarch Enterprise uses, read from its discovery
service over GET only, and the Studio's read-only routes for it. All offline:
the network is a fake that records every request."""
import json

import pytest

from tests.monarch_helpers import free_port, repo  # noqa: F401  (fixture)
from tests.test_config import site  # noqa: F401  (fixture)
from tests.test_studio_app import request, server_for
from tests.test_studio_enterprise import configured, studio_for
from wb_studio import live_graph

ZOHO = {"slug": "bench-zoho-desk", "display_name": "Zoho-Desk (benchmark)", "domain": "shim.test", "business_action_count": 2,
        "replayable_action_count": 1, "is_database": False, "last_run_started_at": "2026-09-03T00:00:00Z"}
GMAIL = {"slug": "bench-gmail", "display_name": "Gmail (benchmark)", "domain": "shim.test", "business_action_count": 1,
         "replayable_action_count": 0, "is_database": False, "last_run_started_at": None}
ACTIONS = [
    {"action_key": "bench-zoho-desk:list:tickets", "area": "tickets", "label": "List tickets", "state": "active", "verb": "list",
     "target_kind": "unknown", "has_implementation": True, "implementation_sources": ["public"], "replay_verified": None, "contract_version": 5},
    {"action_key": "bench-zoho-desk:create:contacts", "area": "contacts", "label": "Create a contact", "state": "active", "verb": "create",
     "target_kind": "unknown", "has_implementation": True, "implementation_sources": ["public"], "replay_verified": True, "contract_version": 5},
]


class FakeDiscovery:
    """Pages keyed by path; every call is recorded so a test can prove what was sent."""

    def __init__(self, pages=None, failing=None):
        self.calls, self.pages, self.failing = [], pages or {}, failing

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        if self.failing:
            raise live_graph.LiveGraphUnavailable(self.failing)
        path, _, query = url.partition("?")
        cursor = dict(p.split("=") for p in query.split("&") if p).get("cursor")
        return self.pages[(path.split("/v1", 1)[1], cursor)]


@pytest.fixture(autouse=True)
def fresh_cache():
    live_graph.forget()
    yield
    live_graph.forget()


@pytest.fixture
def app(tmp_path, site, repo):
    """A Studio whose Monarch harness names a gated discovery service, as the Railway one is."""
    configured(site, repo, free_port(), fd_url="http://127.0.0.1:2")
    harness = site / "config/harnesses/monarch.yaml"
    harness.write_text(harness.read_text() + "fd_api_key_env: FD_API_SHARED_SECRET" + chr(10))
    return studio_for(tmp_path, site, env={"FD_API_SHARED_SECRET": "gate-key"})


def test_products_come_from_the_discovery_service_over_get_with_the_gate_header(app, monkeypatch):
    fake = FakeDiscovery({("/products", None): {"items": [ZOHO, GMAIL], "next_cursor": None}})
    monkeypatch.setattr(live_graph, "fetch", fake)
    data = live_graph.products(app)
    assert data["read_only"] is True and data["source"] == "127.0.0.1:2"
    assert [p["name"] for p in data["products"]] == ["Gmail (benchmark)", "Zoho-Desk (benchmark)"]
    assert data["products"][1] == {"slug": "bench-zoho-desk", "name": "Zoho-Desk (benchmark)", "domain": "shim.test", "actions": 2,
                                   "replayable": 1, "database": False, "last_run_at": "2026-09-03T00:00:00Z"}
    (url, headers), = fake.calls
    assert url.startswith("http://127.0.0.1:2/v1/products?") and headers == {"x-fd-api-key": "gate-key"}


def test_pages_follow_the_cursor_until_the_last_one(app, monkeypatch):
    fake = FakeDiscovery({("/products", None): {"items": [ZOHO], "next_cursor": "c2"},
                          ("/products", "c2"): {"items": [GMAIL], "next_cursor": None}})
    monkeypatch.setattr(live_graph, "fetch", fake)
    assert len(live_graph.products(app)["products"]) == 2
    assert len(fake.calls) == 2 and "cursor=c2" in fake.calls[1][0]


def test_actions_of_a_product_are_listed_by_area_then_label(app, monkeypatch):
    fake = FakeDiscovery({("/products/bench-zoho-desk/business-actions", None): {"items": ACTIONS, "next_cursor": None}})
    monkeypatch.setattr(live_graph, "fetch", fake)
    data = live_graph.actions(app, "bench-zoho-desk")
    assert data["read_only"] is True and data["product"] == "bench-zoho-desk"
    assert [(a["area"], a["label"], a["verb"], a["verified"]) for a in data["actions"]] == \
        [("contacts", "Create a contact", "create", True), ("tickets", "List tickets", "list", None)]
    assert data["actions"][0]["key"] == "bench-zoho-desk:create:contacts" and data["actions"][0]["sources"] == ["public"]


def test_answers_are_cached_for_a_minute(app, monkeypatch):
    fake = FakeDiscovery({("/products", None): {"items": [ZOHO], "next_cursor": None}})
    monkeypatch.setattr(live_graph, "fetch", fake)
    live_graph.products(app)
    live_graph.products(app)
    assert len(fake.calls) == 1
    live_graph.forget()
    live_graph.products(app)
    assert len(fake.calls) == 2


def test_a_harness_without_a_discovery_service_says_so(tmp_path, site, repo):
    app = studio_for(tmp_path, configured(site, repo, free_port(), fd_url="${UNSET_DISCOVERY_URL}"))
    with pytest.raises(live_graph.LiveGraphUnavailable, match="UNSET_DISCOVERY_URL"):
        live_graph.products(app)


def test_routes_are_read_only(app, monkeypatch):
    fake = FakeDiscovery({("/products", None): {"items": [ZOHO], "next_cursor": None},
                          ("/products/bench-zoho-desk/business-actions", None): {"items": ACTIONS, "next_cursor": None}})
    monkeypatch.setattr(live_graph, "fetch", fake)
    with server_for(app) as port:
        status, _, body = request(port, "GET", "/api/live-graph/products")
        assert status == 200 and json.loads(body)["products"][0]["slug"] == "bench-zoho-desk"
        status, _, body = request(port, "GET", "/api/live-graph/products/bench-zoho-desk/actions")
        assert status == 200 and len(json.loads(body)["actions"]) == 2
        for path in ("/api/live-graph/products", "/api/live-graph/products/bench-zoho-desk/actions"):
            status, _, _ = request(port, "POST", path, body="{}", headers={"Content-Type": "application/json", "X-Studio-Token": app.token})
            assert status == 404, path
        assert request(port, "GET", "/api/live-graph/products/../etc/actions")[0] == 404
    assert all(url.startswith("http://127.0.0.1:2/v1/products") for url, _ in fake.calls)


def test_an_unreachable_service_is_a_503_in_plain_words(app, monkeypatch):
    monkeypatch.setattr(live_graph, "fetch", FakeDiscovery(failing="Monarch's discovery service could not be reached: refused"))
    with server_for(app) as port:
        status, _, body = request(port, "GET", "/api/live-graph/products")
        assert status == 503
        assert json.loads(body) == {"error": "Monarch's discovery service could not be reached: refused", "read_only": True}
