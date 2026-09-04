"""T015: the seed generator writes a complete, valid public-api-seeds folder set."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from wb_world import seeds
from wb_world.openapi import build_all

SHIM = "http://host.docker.internal:9105"


def _expected_operations() -> int:
    return sum(len(methods) for doc in build_all(SHIM).values() for methods in doc["paths"].values())


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> tuple[Path, seeds.Summary]:
    out = tmp_path_factory.mktemp("seeds")
    return out, seeds.generate(out, SHIM)


def _actions(out: Path):
    for f in sorted(out.rglob("*.json")):
        if f.name != "_meta.json":
            yield f, json.loads(f.read_text(encoding="utf-8"))


def test_one_folder_per_service_and_one_file_per_operation(generated):
    out, summary = generated
    expected = _expected_operations()
    assert expected > 600
    assert len(summary.folders) == 47
    assert summary.operations_in_spec == expected
    assert summary.files_written == expected
    assert sorted(p.name for p in out.iterdir() if p.is_dir()) == sorted(summary.folders)
    assert all(name.startswith("bench-") for name in summary.folders)
    assert len(list(_actions(out))) == expected


def test_meta_file_per_folder(generated):
    out, summary = generated
    for name in summary.folders:
        meta = json.loads((out / name / "_meta.json").read_text(encoding="utf-8"))
        assert meta["domain"] == "host.docker.internal"
        assert meta["host_pattern"] == "host.docker.internal"
        assert meta["requires_login"] is False
        assert meta["login_url"] is None
        assert meta["display_name"].endswith("(benchmark)")


def test_domain_follows_the_public_front_door_host(tmp_path):
    """Behind a tunnel the seeds must name the tunnel's host, not the Docker one."""
    out = tmp_path / "tunnelled"
    summary = seeds.generate(out, "https://example.ngrok-free.dev/")
    folder = out / summary.folders[0]
    meta = json.loads((folder / "_meta.json").read_text(encoding="utf-8"))
    assert meta["domain"] == meta["host_pattern"] == "example.ngrok-free.dev"
    doc = next(json.loads(f.read_text(encoding="utf-8"))
               for f in sorted(folder.glob("*.json")) if f.name != "_meta.json")
    assert doc["business_action"]["product_domain"] == "example.ngrok-free.dev"


def test_every_action_has_the_shape_the_importer_needs(generated):
    out, _ = generated
    for path, doc in _actions(out):
        ba, impls = doc["business_action"], doc["implementations"]
        assert ba["verb"] in {"create", "read", "list", "update", "delete"}, path
        assert ba["product_id"] == path.parent.name
        step = impls[0]["http_template"]["steps"][0]
        assert impls[0]["http_template"]["auth_scheme"] == "none", path
        assert step["url_template"].startswith(SHIM + "/"), path
        rt = step["response_template"]
        assert isinstance(rt["schema"], dict) and rt["schema"], path
        assert rt["extract"] and all(v.startswith("$.") for v in rt["extract"].values()), path
        # `parameters` and `creates_entities` are required on every
        # implementation: the importer's projectSeed maps over both unguarded.
        assert isinstance(impls[0]["parameters"], list), path
        assert isinstance(impls[0]["creates_entities"], list), path
        if ba["verb"] == "create":
            ce = impls[0]["creates_entities"][0]
            assert ce["identifier_path"] == "$.id", path
            # the importer reads `type`, not `entity`
            assert ce["type"] and "entity" not in ce, path
            assert isinstance(ce["display_name_from"], str), path
        else:
            assert impls[0]["creates_entities"] == [], path


PARAM_REQUIRED = ("name", "classification", "location", "json_path", "type", "required")
PARAM_OPTIONAL = ("entity_type", "example_value", "source_form_field", "constraints")


def test_every_placeholder_and_body_key_has_exactly_one_parameter(generated):
    """The array that binds {{...}} to workflow inputs; a gap breaks execution."""
    out, _ = generated
    for path, doc in _actions(out):
        impl = doc["implementations"][0]
        step = impl["http_template"]["steps"][0]
        want = set(re.findall(r"\{\{(\w+)\}\}", step["url_template"]))
        want |= set(step.get("body_template") or {})
        names = [p["name"] for p in impl["parameters"]]
        assert sorted(names) == sorted(set(names)), path      # exactly one each
        assert set(names) == want, path
        for p in impl["parameters"]:
            assert all(k in p for k in PARAM_REQUIRED), (path, p["name"])
            assert set(p) <= set(PARAM_REQUIRED + PARAM_OPTIONAL), (path, p["name"])
            assert p["classification"] in {
                "auth", "entity_reference", "typed", "selected", "auto_generated"}
            assert p["location"] in {"path", "query", "header", "body"}
            assert isinstance(p["required"], bool)
            assert p["constraints"]["helper_text"], (path, p["name"])
        # auth_scheme is none, so no token parameter is ever emitted
        assert "__auth_token" not in names, path


def test_parameter_shape_per_location(generated):
    """One known action of each kind, field by field."""
    out, _ = generated
    by_name = {p["name"]: p for p in json.loads(
        (out / "bench-airtable" / "bench-airtable_create_root.json")
        .read_text(encoding="utf-8"))["implementations"][0]["parameters"]}
    assert by_name["baseId"] == {
        "name": "baseId", "classification": "entity_reference", "location": "path",
        "json_path": "$.steps[0].url.baseId", "type": "string", "required": True,
        "entity_type": "base", "example_value": "001401",
        "constraints": {"helper_text": "Identifier for the Airtable base."}}

    body = {p["name"]: p for p in json.loads(
        (out / "bench-slack" / "bench-slack_create_conversations-create.json")
        .read_text(encoding="utf-8"))["implementations"][0]["parameters"]}
    assert body["name"] == {
        "name": "name", "classification": "typed", "location": "body",
        "json_path": "$.steps[0].body.name", "type": "string", "required": True,
        "source_form_field": "name", "example_value": "Acme renewal",
        "constraints": {"helper_text": "Desired name for the new channel."}}
    assert body["is_private"]["type"] == "boolean"
    assert body["is_private"]["required"] is False


ID_RE = re.compile(r"^bench-[a-z0-9-]+:(create|read|list|update|delete):[a-z0-9-]+$")


def test_product_slugs_are_hyphenated_lowercase(generated):
    """The discovery service slugifies `[^a-z0-9]+`; an underscore made two products."""
    out, summary = generated
    for name in summary.folders:
        assert re.fullmatch(r"bench-[a-z0-9-]+", name), name
        assert "_" not in name
    assert "bench-google-ads" in summary.folders
    for path, doc in _actions(out):
        assert doc["business_action"]["product_id"] == path.parent.name, path


def test_action_ids_are_three_well_formed_facets(generated):
    """A malformed id is re-minted by the importer and collides (29 actions lost)."""
    out, _ = generated
    seen = {}
    for path, doc in _actions(out):
        aid = doc["business_action"]["id"]
        assert ID_RE.fullmatch(aid), (path, aid)
        product, verb, obj = aid.split(":")
        assert product == path.parent.name, path
        assert verb == doc["business_action"]["verb"], path
        assert seen.setdefault(aid, path) == path, f"duplicate id {aid}"
        assert path.name == aid.replace(":", "_") + ".json", path


def test_salesforce_opportunity_update_matches_the_engine_reference(generated):
    """The shape the Monarch executor reads: PATCH with real, typed body fields."""
    out, _ = generated
    doc = json.loads((out / "bench-salesforce" /
                      "bench-salesforce_update_opportunity.json").read_text(encoding="utf-8"))
    impl = doc["implementations"][0]
    step = impl["http_template"]["steps"][0]
    assert step["method"] == "PATCH"
    body = {p["name"]: p for p in impl["parameters"] if p["location"] == "body"}
    for field in ("Amount", "StageName", "CloseDate"):
        assert field in body, sorted(body)
        assert step["body_template"][field] == "{{%s}}" % field
        assert body[field]["json_path"] == f"$.steps[0].body.{field}"
        assert body[field]["classification"] == "typed"
        # an update prunes a missing field; required would make the engine invent one
        assert body[field]["required"] is False
    assert body["Amount"]["type"] == "number"
    assert body["Amount"]["example_value"] != "Amount"
    assert "Id" not in body                       # read-only identifier
    ident = next(p for p in impl["parameters"] if p["location"] == "path")
    assert ident["classification"] == "entity_reference"
    assert ident["json_path"] == f"$.steps[0].url.{ident['name']}"
    assert "{{" not in str(ident["example_value"])


def test_body_parameters_are_typed_and_exampled(generated):
    out, _ = generated
    for path, doc in _actions(out):
        impl = doc["implementations"][0]
        for p in impl["parameters"]:
            if p["location"] != "body":
                continue
            assert p["type"] in {"number", "string", "boolean", "object"}, (path, p["name"])
            assert p["example_value"] != p["name"], (path, p["name"])
            if "enum_options" in p["constraints"]:
                assert all("value" in o for o in p["constraints"]["enum_options"])


def test_write_actions_carry_body_fields(generated):
    """No open bag: a field with no token in the template never reaches the wire."""
    out, _ = generated
    empty = [path.name for path, doc in _actions(out)
             if doc["business_action"]["verb"] in ("create", "update")
             and not (doc["implementations"][0]["http_template"]["steps"][0]
                      .get("body_template") or {})]
    # What remains is RPC-shaped (`:mutate`, `search`, `convertLead`, `exports`)
    # or a service whose world schema declares no record for the resource.
    assert len(empty) <= 109, sorted(empty)[:10]
    # every CRUD path of the pilot services carries its fields
    for path, doc in _actions(out):
        if path.parent.name not in ("bench-gmail", "bench-slack", "bench-zendesk",
                                    "bench-google-calendar"):
            continue
        if doc["business_action"]["verb"] in ("create", "update"):
            assert doc["implementations"][0]["http_template"]["steps"][0]["body_template"], path


def test_a_missing_parameter_is_a_gap(generated, tmp_path):
    out, _ = generated
    folder = tmp_path / "bench-airtable"
    folder.mkdir()
    victim = next(f for f, d in _actions(out)
                  if d["implementations"][0]["parameters"])
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["implementations"][0]["parameters"].pop()
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path)
    assert [g.file for g in gaps] == [victim.name]
    assert "parameters_incomplete" in gaps[0].gap


@pytest.mark.parametrize("break_it, gap", [
    (lambda d: d["business_action"].__setitem__("id", "bench_x:create:y"), "id_malformed"),
    (lambda d: d["business_action"].__setitem__("id", "nope"), "id_malformed"),
    (lambda d: d["implementations"][0]["http_template"]["steps"][0]["body_template"]
     .__setitem__("Ghost", "{{Ghost}}"), "body_field_without_parameter"),
    (lambda d: d["implementations"][0]["parameters"].append(
        {"name": "Ghost", "classification": "typed", "location": "body",
         "json_path": "$.steps[0].body.Ghost", "type": "string", "required": False}),
     "parameter_without_token"),
])
def test_validate_names_the_new_gaps(generated, tmp_path, break_it, gap):
    out, _ = generated
    folder = tmp_path / gap
    folder.mkdir()
    victim = out / "bench-salesforce" / "bench-salesforce_update_opportunity.json"
    doc = json.loads(victim.read_text(encoding="utf-8"))
    break_it(doc)
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    assert any(gap in g.gap for g in seeds.validate(folder))


def test_action_ids_unique_within_a_folder(generated):
    out, summary = generated
    for name in summary.folders:
        ids = [json.loads(f.read_text(encoding="utf-8"))["business_action"]["id"]
               for f in (out / name).glob("*.json") if f.name != "_meta.json"]
        assert len(ids) == len(set(ids)), name


def test_validate_finds_no_gap_on_the_generated_set(generated):
    out, _ = generated
    assert seeds.validate(out) == []


def test_validate_names_the_gap_on_a_corrupted_file(generated, tmp_path):
    out, _ = generated
    folder = tmp_path / "bench-slack"
    folder.mkdir()
    victim = next(f for f, _ in _actions(out) if f.parent.name == "bench-slack")
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["implementations"][0]["http_template"]["steps"][0]["response_template"]["extract"] = {}
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path)
    assert [g.file for g in gaps] == [victim.name]
    assert "extract" in gaps[0].gap


def test_two_generations_are_byte_identical(generated, tmp_path):
    out, _ = generated
    again = tmp_path / "again"
    seeds.generate(again, SHIM)
    for f, _ in _actions(out):
        rel = f.relative_to(out)
        assert (again / rel).read_bytes() == f.read_bytes(), rel


def test_validate_names_a_malformed_url_template(generated, tmp_path):
    out, _ = generated
    folder = tmp_path / "bad-url" / "bench-trello"
    folder.mkdir(parents=True)
    victim = next(f for f, _ in _actions(out) if f.parent.name == "bench-trello")
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["implementations"][0]["http_template"]["steps"][0]["url_template"] = SHIM + "/trello/cards/{{}}"
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path / "bad-url")
    assert len(gaps) == 1 and "malformed placeholder" in gaps[0].gap
