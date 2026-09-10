"""A product graph version readable at a glance: the summary sentence built from
the diff counts, the per-product drilldown with the research events behind each
value, and catalog searches recorded in the research log. All offline."""
import json

import pytest

from tests.test_studio_app import request, server_for
from tests.test_studio_execution import CATALOG_FIELDS, save_catalog, studio  # noqa: F401  (fixture)
from wb_studio import product_graphs

FIELDS = [{"path": "product.summary", "type": "string"}, {"path": "product.risk", "type": "number"}]
OWNER = {"path": "product.owner", "type": "string"}


def version(number, records, fields=FIELDS, parent=None, status="complete", removed=()):
    return {"version": number, "parent_version": parent, "status": status, "fields": fields,
            "products": sorted(records), "records": records, "removed": list(removed)}


# ---------------------------------------------------------------- the sentence

def test_first_version_is_described_by_what_it_filled():
    first = version(1, {"gmail": {"product.summary": "Mail service", "product.risk": 2},
                        "slack": {"product.summary": "unknown", "product.risk": 1}})
    assert product_graphs.describe(first, None) == "Filled 3 of 4 fields across 2 products; 1 stayed unknown."


def test_a_version_that_changes_values_counts_the_changes():
    first = version(1, {"gmail": {"product.summary": "Mail service", "product.risk": 2},
                        "slack": {"product.summary": "Chat", "product.risk": 1}})
    second = version(2, {"gmail": {"product.summary": "Mail service", "product.risk": 3, "product.owner": "IT"},
                         "slack": {"product.summary": "Chat", "product.risk": 1}}, FIELDS + [OWNER], parent=1)
    assert product_graphs.describe(second, first) == "Filled 1 of 6 fields across 2 products; changed 1 value; 1 still missing."


def test_a_version_with_nothing_new_says_so():
    records = {"gmail": {"product.summary": "Mail service", "product.risk": 2}, "slack": {"product.summary": "Chat", "product.risk": 1}}
    first = version(1, records)
    same = version(2, json.loads(json.dumps(records)), parent=1, removed=["product.owner"])
    assert product_graphs.describe(same, first) == "Nothing new: all 4 fields match version 1; dropped 1 field."


def test_a_failed_version_filled_nothing():
    assert product_graphs.describe(version(1, {}, status="failed"), None) == "Failed before any field was filled."


def test_listing_and_the_prepare_response_carry_the_sentence(studio):
    save_catalog(studio, CATALOG_FIELDS)
    product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    save_catalog(studio, CATALOG_FIELDS + [dict(OWNER, description="Team that owns it")], revision=1)
    second = product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    listed = product_graphs.listing(studio)[0]["versions"]
    assert listed[0]["summary"] == "Filled 4 of 4 fields across 2 products."
    # The scripted researcher never answers the new field: nothing filled, two slots missing.
    assert listed[1]["summary"] == "Filled 0 of 6 fields across 2 products; 2 still missing."
    with server_for(studio) as port:
        status, _, body = request(port, "GET", "/api/product-graphs")
        assert status == 200 and json.loads(body)["items"][0]["versions"][1]["summary"] == listed[1]["summary"]
        status, _, body = request(port, "POST", "/api/product-graphs/prepare", body=json.dumps({"id": "catalog", "maximum_usd": "2.00"}),
                                  headers={"Content-Type": "application/json", "X-Studio-Token": studio.token})
        assert status == 400 and "Nothing new to research" in json.loads(body)["error"]
    assert product_graphs.summary(second, product_graphs.load_version(studio, "catalog", 1))["summary"] == listed[1]["summary"]


# ---------------------------------------------------------------- the drilldown

def test_drilldown_links_every_value_to_the_events_that_produced_it(studio):
    save_catalog(studio, CATALOG_FIELDS)
    product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    events = [json.loads(line) for line in (studio.directory / "product-graphs" / "catalog" / "v0001.events.jsonl").read_text(encoding="utf-8").splitlines()]
    searches = [e for e in events if e["type"] == "node_started"]
    assert [(e["label"], e["arguments"], e["step"]) for e in searches] == [("api_search", {"query": "salesforce"}, "research")]
    assert [e["type"] for e in events if e.get("node") == searches[0]["node"]] == ["node_started", "node_finished"]
    answer = [e for e in events if e["type"] == "model_finished" and e["status"] == "completed" and e["output"]][-1]

    drill = product_graphs.drilldown(studio, "catalog", 1)
    assert drill["version"] == 1 and [p["product"] for p in drill["products"]] == ["gmail", "salesforce"]
    salesforce = {f["path"]: f for f in drill["products"][1]["fields"]}
    assert salesforce["product.summary"] == {"path": "product.summary", "type": "string", "value": "CRM records", "present": True, "unknown": False,
                                             "since": 1, "events": {"version": 1, "ids": [searches[0]["id"], answer["id"]]}}
    gmail = {f["path"]: f for f in drill["products"][0]["fields"]}
    assert gmail["product.risk"]["value"] == 2 and gmail["product.risk"]["events"] == {"version": 1, "ids": [answer["id"]]}

    save_catalog(studio, CATALOG_FIELDS + [dict(OWNER, description="Team that owns it")], revision=1)
    product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    later = {f["path"]: f for f in product_graphs.drilldown(studio, "catalog", 2)["products"][1]["fields"]}
    assert later["product.summary"]["since"] == 1 and later["product.summary"]["events"]["version"] == 1   # carried: the events live in version 1
    assert later["product.owner"] == {"path": "product.owner", "type": "string", "value": None, "present": False, "unknown": False,
                                      "since": 2, "events": {"version": 2, "ids": []}}
    with pytest.raises(ValueError, match="no version 3"):
        product_graphs.drilldown(studio, "catalog", 3)


def test_drilldown_route(studio):
    save_catalog(studio, CATALOG_FIELDS)
    product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    with server_for(studio) as port:
        status, _, body = request(port, "GET", "/api/product-graphs/catalog/versions/1/products")
        assert status == 200 and json.loads(body) == product_graphs.drilldown(studio, "catalog", 1)
        status, _, body = request(port, "GET", "/api/product-graphs/catalog/versions/1/events")
        assert status == 200 and json.loads(body)["events"][0]["type"] == "step_started"
        assert request(port, "GET", "/api/product-graphs/catalog/versions/2/products")[0] == 404
