"""The lab seeds: stock seeds whose descriptions carry reviewed knowledge.

`wb monarch knowledge` (unblock plan M6, T6.3 groundwork) takes the PG-Waki
catalog and the explicit table in `config/products/<product>.knowledge-map.yaml`
and writes a second seed set that differs from the stock one in
`business_action.description` only. Everything the executor and the importer
read -- ids, verbs, url templates, parameters, extracts, schemas, _meta.json --
is byte-identical, so the lab instance runs the same routes with more words
about them. Unmatched entries and actions are listed, never guessed.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.fake_fd import FakeFD
from wb_orchestrator import cli, config, monarch_setup
from wb_world import knowledge, seeds

STAMP = seeds.STAMP
FRONT = "http://front.example"
CONFIG = config.DEFAULT_CONFIG_DIR
PRODUCT = CONFIG / "products" / "simulated-apps.yaml"
HARNESS = CONFIG / "harnesses" / "monarch.yaml"
SHIPPED_MAP = CONFIG / "products" / "simulated-apps.knowledge-map.yaml"
REAL_CATALOG = Path("C:/Users/Lucas Wakigawa/Monarch_Main/ATLAS/backend/config/"
                    "bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json")


# ------------------------------------------------------------ synthetic inputs

def _action(slug: str, verb: str, obj: str, method: str, path: str, params: list[dict],
            extract: dict, schema: dict | None, description: str) -> dict:
    bodyless = method in ("GET", "DELETE")
    body = {p["name"]: "{{%s}}" % p["name"] for p in params if p["location"] == "body"}
    step = {"method": method, "url_template": FRONT + path,
            **({"headers_template": {}, "body_template": None} if bodyless else
               {"headers_template": {"content-type": "application/json"}, "body_template": body}),
            "response_template": {"status": 200, "extract": extract,
                                  **({"schema": schema} if schema is not None else {})}}
    return {
        "business_action": {
            "id": f"{slug}:{verb}:{obj}", "label": f"{verb.title()} {obj}", "product_id": slug,
            "product_domain": "front.example", "area": obj, "state": "active", "verb": verb,
            "description": description, "source_url": f"{FRONT}/openapi/{slug}.json",
            "first_seen_at": STAMP, "last_seen_at": STAMP},
        "implementations": [{
            "id": f"impl_{slug}_{verb}_{obj}_public", "source": "public", "discovered_at": STAMP,
            "idempotent": verb != "create",
            "http_template": {"call_type": "rest", "transport_mode": "header_only",
                              "auth_scheme": "none", "auth_captured": False, "steps": [step]},
            "parameters": params, "creates_entities": []}]}


def _param(name: str, location: str, helper: str, required: bool = True) -> dict:
    where = "url" if location in ("path", "query") else "body"
    return {"name": name, "classification": "typed", "location": location,
            "json_path": f"$.steps[0].{where}.{name}", "type": "string", "required": required,
            "example_value": "x", "constraints": {"helper_text": helper}}


THING = {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
         "required": ["id", "name"]}
THINGS = {"type": "object", "properties": {"things": {"type": "array", "items": THING}},
          "required": ["things"]}

STOCK_ACTIONS = {
    "bench-alpha": {
        "bench-alpha_create_things.json": _action(
            "bench-alpha", "create", "things", "POST", "/alpha/things",
            [_param("name", "body", "The name."), _param("kind", "body", "The kind.", False)],
            {"id": "$.id", "name": "$.name"}, THING, "Creates a thing."),
        "bench-alpha_list_things.json": _action(
            "bench-alpha", "list", "things", "GET", "/alpha/things?q={{q}}",
            [_param("q", "query", "Filter.", False)], {"things": "$.things"}, THINGS, ""),
    },
    "bench-beta": {
        "bench-beta_read_widgets.json": _action(
            "bench-beta", "read", "widgets", "GET", "/beta/widgets/{{id}}",
            [_param("id", "path", "The widget id.")], {"id": "$.id"}, THING, "Reads a widget."),
    },
}


def write_stock(root: Path) -> None:
    """A stock-shaped seed set: two products, three actions, the manifest."""
    for slug, actions in STOCK_ACTIONS.items():
        d = root / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "_meta.json").write_text(seeds._dump(seeds._meta(slug.removeprefix("bench-"), FRONT)),
                                      encoding="utf-8")
        for name, doc in actions.items():
            (d / name).write_text(seeds._dump(doc), encoding="utf-8")
    manifest = {"version": seeds.VERSION, "canonical": True, "products": 2, "actions": 3,
                "front_door": FRONT, "generated_from": "wb monarch setup",
                "sha256": seeds.folder_sha256(root), "conformance": {"ok": 3}}
    (root / "ok.txt").write_text(seeds._dump(manifest), encoding="utf-8")


def _entry(tool: str, app: str, purpose: str, does_not: list[str], mutation: dict,
           response: dict, fields: list[dict]) -> dict:
    return {"source_action_id": f"zapier:{tool}",
            "contract": {"capability_id": tool,
                         "product_origin": f"automationbench:zapier:{app}",
                         "behavior": {"purpose": {"text": purpose},
                                      "does_not": [{"text": t} for t in does_not]},
                         "mutation": mutation, "response": response,
                         "request_fields": fields}}


CATALOG = {
    "schema_version": 1, "generator_version": "synthetic-catalog-v1",
    "entries": [
        _entry("alpha_create_thing", "alpha", "Create a thing in the workspace.",
               ["Does not update an existing thing."],
               {"semantics": "append", "idempotency": "Not idempotent: each call adds a thing."},
               {"produced_fields": ["/results/0"], "record_id_path": "/id"},
               [{"name": "name", "description": "The thing's display name."},
                {"name": "colour", "description": "Not a parameter of the route."},
                {"name": "kind"}]),
        _entry("alpha_find_thing", "alpha", "Find things by name.", [],
               {"semantics": "none"},
               {"produced_fields": [], "collection_path": "/things"},
               [{"name": "q", "description": "A substring of the name."}]),
        _entry("beta_orphan", "beta", "Something the bench has no route for.", [],
               {"semantics": "none"}, {"produced_fields": []}, []),
    ],
    "product_contexts": [
        {"product_origin": "automationbench:zapier:alpha",
         "summary": "Things are keyed by id; names are unique within the workspace."},
    ],
}

MAP = {
    "product": "synthetic",
    "rows": {"zapier:alpha_create_thing": "bench-alpha:create:things",
             "zapier:alpha_find_thing": "bench-alpha:list:things",
             "zapier:alpha_ghost": "bench-alpha:create:things"},
    "notes": {"zapier:alpha_find_thing": "the list route; match by name",
              "zapier:beta_orphan": "no row; the bench has no route for it"},
}


@pytest.fixture()
def inputs(tmp_path):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(CATALOG, indent=1), encoding="utf-8")
    kmap = tmp_path / "synthetic.knowledge-map.yaml"
    kmap.write_text(yaml.safe_dump(MAP, sort_keys=False), encoding="utf-8")
    return catalog, kmap


@pytest.fixture()
def lab(tmp_path, inputs):
    """Stock tree, its enriched copy, and the report."""
    catalog, kmap = inputs
    stock = tmp_path / "stock"
    write_stock(stock)
    out = tmp_path / "lab"
    shutil.copytree(stock, out)
    report = knowledge.enrich(out, knowledge.load_catalog(catalog), knowledge.load_map(kmap))
    return stock, out, report


def _doc(root: Path, slug: str, name: str) -> dict:
    return json.loads((root / slug / name).read_text(encoding="utf-8"))


def _description(root: Path, slug: str, name: str) -> str:
    return _doc(root, slug, name)["business_action"]["description"]


# --------------------------------------------------------------- enrichment

def test_a_matched_action_carries_purpose_non_effects_idempotency_and_record_location(lab):
    _, out, _ = lab
    text = _description(out, "bench-alpha", "bench-alpha_create_things.json")
    assert "Creates a thing." in text                      # the stock sentence stays
    assert "Purpose: Create a thing in the workspace." in text
    assert "Does not: Does not update an existing thing." in text
    assert "Idempotency: Not idempotent: each call adds a thing." in text
    assert "Record id in the response: $.id" in text       # /id is in the seed's schema


def test_a_read_without_an_idempotency_note_is_described_as_read_only(lab):
    _, out, _ = lab
    text = _description(out, "bench-alpha", "bench-alpha_list_things.json")
    assert "Purpose: Find things by name." in text
    assert "Read-only: nothing changes" in text
    assert "Records in the response: the array at $.things" in text


def test_argument_semantics_are_carried_only_for_the_seed_s_own_parameters(lab):
    _, out, _ = lab
    text = _description(out, "bench-alpha", "bench-alpha_create_things.json")
    assert "name: The thing's display name." in text
    assert "colour" not in text                            # not a parameter of the route
    assert "kind" not in text.split("Arguments:")[-1]      # no description in the catalog


def test_a_record_location_the_seed_schema_cannot_reach_is_dropped(tmp_path, inputs):
    catalog, kmap = inputs
    doc = copy.deepcopy(CATALOG)
    doc["entries"][1]["contract"]["response"]["collection_path"] = "/nowhere"
    catalog.write_text(json.dumps(doc), encoding="utf-8")
    out = tmp_path / "lab2"
    write_stock(out)
    knowledge.enrich(out, knowledge.load_catalog(catalog), knowledge.load_map(kmap))
    text = _description(out, "bench-alpha", "bench-alpha_list_things.json")
    assert "nowhere" not in text and "Records in the response" not in text


def test_the_product_context_opens_the_first_action_of_the_product(lab):
    _, out, _ = lab
    first = _description(out, "bench-alpha", "bench-alpha_create_things.json")
    assert first.startswith("Product: Things are keyed by id; names are unique within the workspace.")
    second = _description(out, "bench-alpha", "bench-alpha_list_things.json")
    assert "Product:" not in second
    # _meta.json has exactly the five keys the SPEC allows, so nothing goes there
    meta = _doc(out, "bench-alpha", "_meta.json")
    assert sorted(meta) == ["display_name", "domain", "host_pattern", "login_url", "requires_login"]


def test_a_bench_only_action_and_a_product_without_context_are_left_alone(lab):
    stock, out, _ = lab
    name = "bench-beta_read_widgets.json"
    assert (out / "bench-beta" / name).read_bytes() == (stock / "bench-beta" / name).read_bytes()


def test_everything_but_the_description_is_byte_identical_to_the_stock_seeds(lab):
    stock, out, _ = lab
    for slug, actions in STOCK_ACTIONS.items():
        assert (out / slug / "_meta.json").read_bytes() == (stock / slug / "_meta.json").read_bytes()
        for name in actions:
            before, after = _doc(stock, slug, name), _doc(out, slug, name)
            before["business_action"].pop("description")
            after["business_action"].pop("description")
            assert before == after, f"{slug}/{name} changed outside the description"
    # and no file appeared or vanished inside the product folders
    assert sorted(p.relative_to(out) for p in out.rglob("*.json")) == \
        sorted(p.relative_to(stock) for p in stock.rglob("*.json"))


# ------------------------------------------------------------------ the report

def test_unmatched_entries_and_actions_are_listed_not_guessed(lab):
    _, out, report = lab
    doc = yaml.safe_load((out / "KNOWLEDGE-MAPPING.yaml").read_text(encoding="utf-8"))
    assert doc["counts"] == {
        "catalog_entries": 3, "bench_actions": 3, "matched_entries": 2, "matched_actions": 2,
        "catalog_only": 1, "bench_only": 1, "map_rows_without_catalog_entry": 1,
        "products_with_context": 1, "products_without_context": 1}
    assert doc["catalog_only"] == ["zapier:beta_orphan"]
    assert doc["catalog_only_reasons"] == {"zapier:beta_orphan": "no row; the bench has no route for it"}
    assert doc["bench_only"] == ["bench-beta:read:widgets"]
    assert doc["map_rows_without_catalog_entry"] == ["zapier:alpha_ghost"]
    assert doc["products_without_context"] == ["bench-beta"]
    assert doc["products_with_context"] == ["bench-alpha"]
    assert report.counts == doc["counts"]


def test_the_report_names_the_catalog_the_table_and_every_pair(lab, inputs):
    catalog, kmap = inputs
    _, out, _ = lab
    doc = yaml.safe_load((out / "KNOWLEDGE-MAPPING.yaml").read_text(encoding="utf-8"))
    assert doc["knowledge_source"] == "catalog.json"
    assert doc["knowledge_sha256"] == hashlib.sha256(catalog.read_bytes()).hexdigest()
    assert doc["knowledge_generator"] == "synthetic-catalog-v1"
    assert doc["knowledge_map"] == "synthetic.knowledge-map.yaml"
    assert doc["knowledge_map_sha256"] == hashlib.sha256(kmap.read_bytes()).hexdigest()
    assert "explicit table" in doc["rule"]
    pairs = {(m["catalog"], m["bench"]) for m in doc["matched"]}
    assert pairs == {("zapier:alpha_create_thing", "bench-alpha:create:things"),
                     ("zapier:alpha_find_thing", "bench-alpha:list:things")}
    find = next(m for m in doc["matched"] if m["catalog"] == "zapier:alpha_find_thing")
    assert find["note"] == "the list route; match by name"
    assert find["records"] == "$.things" and find["arguments"] == "1 of 1"
    create = next(m for m in doc["matched"] if m["catalog"] == "zapier:alpha_create_thing")
    assert create["records"] == "$.id" and create["arguments"] == "1 of 3"


def test_the_manifest_carries_the_knowledge_hash_next_to_the_seed_version(lab, inputs):
    catalog, kmap = inputs
    stock, out, _ = lab
    before = json.loads((stock / "ok.txt").read_text(encoding="utf-8"))
    after = json.loads((out / "ok.txt").read_text(encoding="utf-8"))
    assert after["version"] == before["version"] == seeds.VERSION
    assert after["knowledge_sha256"] == hashlib.sha256(catalog.read_bytes()).hexdigest()
    assert after["knowledge_source"] == "catalog.json"
    assert after["knowledge_map"] == "synthetic.knowledge-map.yaml"
    assert after["generated_from"] == "wb monarch knowledge"
    assert after["sha256"] == seeds.folder_sha256(out) != before["sha256"]
    assert after["conformance"] == before["conformance"]   # the executable bytes did not move


def test_same_inputs_same_bytes(tmp_path, inputs):
    catalog, kmap = inputs
    trees = []
    for name in ("one", "two"):
        out = tmp_path / name
        write_stock(out)
        knowledge.enrich(out, knowledge.load_catalog(catalog), knowledge.load_map(kmap))
        trees.append({p.relative_to(out).as_posix(): p.read_bytes()
                      for p in out.rglob("*") if p.is_file()})
    assert trees[0] == trees[1]
    assert "KNOWLEDGE-MAPPING.yaml" in trees[0] and "ok.txt" in trees[0]


def test_enriching_twice_is_a_no_op(lab, inputs):
    catalog, kmap = inputs
    _, out, _ = lab
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    with pytest.raises(knowledge.KnowledgeError, match="already"):
        knowledge.enrich(out, knowledge.load_catalog(catalog), knowledge.load_map(kmap))
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file()} == before


# ------------------------------------------------------------------- refusals

def test_a_map_row_naming_an_action_the_generator_does_not_produce_stops(tmp_path, inputs):
    catalog, kmap = inputs
    doc = dict(MAP, rows={**MAP["rows"], "zapier:beta_orphan": "bench-beta:create:gadgets"})
    kmap.write_text(yaml.safe_dump(doc), encoding="utf-8")
    out = tmp_path / "lab3"
    write_stock(out)
    with pytest.raises(knowledge.KnowledgeError) as e:
        knowledge.enrich(out, knowledge.load_catalog(catalog), knowledge.load_map(kmap))
    assert "bench-beta:create:gadgets" in str(e.value) and "zapier:beta_orphan" in str(e.value)


@pytest.mark.parametrize("doc, why", [
    ({"entries": "no"}, "entries"),
    ({"entries": [{"contract": {}}], "product_contexts": []}, "source_action_id"),
    ({"entries": [{"source_action_id": "zapier:x", "contract": {}}]}, "product_contexts"),
])
def test_a_catalog_with_the_wrong_shape_is_refused(tmp_path, doc, why):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(knowledge.KnowledgeError, match=why):
        knowledge.load_catalog(path)


def test_a_map_with_a_malformed_action_id_is_refused(tmp_path):
    path = tmp_path / "bad.knowledge-map.yaml"
    path.write_text(yaml.safe_dump({"rows": {"zapier:x": "not-an-action-id"}}), encoding="utf-8")
    with pytest.raises(knowledge.KnowledgeError, match="not-an-action-id"):
        knowledge.load_map(path)


# ------------------------------------------------------------------- the CLI

def _fake_generate(calls: list):
    def generate(out_dir, shim_public_url):
        calls.append((Path(out_dir), shim_public_url))
        write_stock(Path(out_dir))
        return seeds.Summary(operations_in_spec=3, files_written=3, folders=sorted(STOCK_ACTIONS))
    return generate


def test_cli_wires_wb_monarch_knowledge(tmp_path, inputs, monkeypatch, capsys):
    catalog, kmap = inputs
    calls: list = []
    monkeypatch.setattr(monarch_setup.seeds, "generate", _fake_generate(calls))
    out = tmp_path / "lab"
    code = cli.main(["monarch", "knowledge", "--knowledge", str(catalog), "--map", str(kmap),
                     "--out", str(out), "--front-door", "http://door.example/"])
    text = capsys.readouterr().out
    assert code == 0, text
    assert calls == [(out.resolve(), "http://door.example")]
    assert "[ok] generate" in text
    assert "[ok] knowledge: matched=2 catalog_only=1 bench_only=1" in text
    assert str(out / "KNOWLEDGE-MAPPING.yaml") in text
    assert (out / "KNOWLEDGE-MAPPING.yaml").is_file()
    assert "Purpose: Find things by name." in _description(out, "bench-alpha", "bench-alpha_list_things.json")


def test_cli_takes_the_front_door_from_the_harness_when_not_given(tmp_path, inputs, monkeypatch):
    catalog, kmap = inputs
    calls: list = []
    monkeypatch.setattr(monarch_setup.seeds, "generate", _fake_generate(calls))
    monkeypatch.setenv("FRONT_DOOR_URL", "https://tunnel.example")
    out = tmp_path / "lab"
    assert cli.main(["monarch", "knowledge", "--knowledge", str(catalog), "--map", str(kmap),
                     "--out", str(out)]) == 0
    assert calls[0][1] == "https://tunnel.example"


def test_cli_finds_the_table_next_to_the_product_file_by_default(tmp_path, inputs, monkeypatch):
    catalog, kmap = inputs
    product = tmp_path / "products" / "synthetic.yaml"
    product.parent.mkdir()
    product.write_text(PRODUCT.read_text(encoding="utf-8").replace("name: simulated-apps", "name: synthetic"),
                       encoding="utf-8")
    shutil.copy(kmap, product.with_name("synthetic.knowledge-map.yaml"))
    monkeypatch.setattr(monarch_setup.seeds, "generate", _fake_generate([]))
    out = tmp_path / "lab"
    assert cli.main(["monarch", "knowledge", "--knowledge", str(catalog), "--product", str(product),
                     "--out", str(out), "--front-door", FRONT]) == 0
    assert (out / "KNOWLEDGE-MAPPING.yaml").is_file()


def test_cli_stops_with_code_2_when_the_table_is_missing(tmp_path, inputs, monkeypatch, capsys):
    catalog, _ = inputs
    monkeypatch.setattr(monarch_setup.seeds, "generate", _fake_generate([]))
    code = cli.main(["monarch", "knowledge", "--knowledge", str(catalog), "--map", str(tmp_path / "no.yaml"),
                     "--out", str(tmp_path / "lab"), "--front-door", FRONT])
    assert code == 2
    assert "[stop] knowledge" in capsys.readouterr().out


def test_setup_with_knowledge_imports_the_lab_seeds_and_records_the_hash(tmp_path, inputs, monkeypatch):
    """`wb monarch setup --knowledge` teaches the instance the enriched set and pins it."""
    catalog, kmap = inputs
    monkeypatch.setattr(monarch_setup.seeds, "generate", _fake_generate([]))
    monkeypatch.setattr(monarch_setup, "_conform_gate", lambda *a, **k: None)
    products = tmp_path / "products"
    products.mkdir()
    product = products / "simulated-apps.yaml"
    # the fake set has two products; the setup wants every service of the product mounted
    product.write_text("name: simulated-apps\nkind: simulated\n"
                       "data: {dataset: synthetic, mutable: true}\nservices: [alpha, beta]\n"
                       "side_effects: config/side-effects.yaml\nmodes: [create-run]\n",
                       encoding="utf-8")
    out = tmp_path / "seeds"
    buf = io.StringIO()
    with FakeFD(fixtures_dir=out) as fd:
        env = {"MONARCH_FD_URL": fd.url, "FRONT_DOOR_URL": FRONT}
        code = monarch_setup.run(product, HARNESS, out, env, buf, conform=False,
                                 knowledge=str(catalog), knowledge_map=str(kmap))
    text = buf.getvalue()
    assert code == 0, text
    assert "[ok] knowledge: matched=2" in text and "[ok] import: 2 apps" in text
    kb = yaml.safe_load(product.with_name("simulated-apps.monarch-kb.yaml").read_text(encoding="utf-8"))
    assert kb["knowledge_sha256"] == hashlib.sha256(catalog.read_bytes()).hexdigest()
    assert kb["knowledge_source"] == "catalog.json"
    assert "Purpose: Find things by name." in _description(out, "bench-alpha", "bench-alpha_list_things.json")


# ------------------------------------------------------- the shipped table

@pytest.fixture(scope="module")
def stock(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("stock")
    seeds.generate(out, FRONT)
    return out


def test_every_row_of_the_shipped_table_names_a_product_of_the_bench():
    kmap = knowledge.load_map(SHIPPED_MAP)
    slugs = {seeds.product_slug(s) for s in config.load_product(PRODUCT).services}
    assert kmap.rows
    for catalog_id, bench_id in kmap.rows.items():
        assert catalog_id.startswith("zapier:"), catalog_id
        assert bench_id.split(":")[0] in slugs, bench_id
    assert set(kmap.notes) - set(kmap.rows), "the notes also explain the entries without a row"


def test_every_row_of_the_shipped_table_names_an_action_the_generator_produces(stock):
    ids = {json.loads(f.read_text(encoding="utf-8"))["business_action"]["id"]
           for f in stock.rglob("*.json") if f.name != "_meta.json"}
    missing = sorted(b for b in knowledge.load_map(SHIPPED_MAP).rows.values() if b not in ids)
    assert missing == []


@pytest.mark.skipif(not REAL_CATALOG.is_file(), reason="the PG-Waki catalog lives outside the repo")
def test_the_real_catalog_enriches_the_real_seeds_and_lists_the_rest(stock, tmp_path):
    out = tmp_path / "lab"
    shutil.copytree(stock, out)
    report = knowledge.enrich(out, knowledge.load_catalog(REAL_CATALOG), knowledge.load_map(SHIPPED_MAP))
    assert report.counts["catalog_entries"] == 273
    assert report.counts["matched_entries"] + report.counts["catalog_only"] == 273
    assert report.counts["map_rows_without_catalog_entry"] == 0
    assert report.counts["products_with_context"] == 43
    assert report.counts["products_without_context"] == 4
    assert not seeds.validate(out)                      # still a valid set
    text = _description(out, "bench-gmail", "bench-gmail_list_messages.json")
    assert "2 uses of this action" in text               # find_email and list_emails
    assert "Records in the response: the array at $.messages" in text
