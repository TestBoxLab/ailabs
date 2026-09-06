"""T015: the seed generator writes a complete, valid public-api-seeds folder set."""
from __future__ import annotations

import json
import re
import shutil
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
        # extract may be {} -- a response with no body has nothing to name, and
        # the builder reads that as known_empty ("run for effect").
        assert all(v.startswith("$") for v in rt["extract"].values()), path
        # `parameters` and `creates_entities` are required on every
        # implementation: the importer's projectSeed maps over both unguarded.
        assert isinstance(impls[0]["parameters"], list), path
        assert isinstance(impls[0]["creates_entities"], list), path
        if ba["verb"] == "create":
            for ce in impls[0]["creates_entities"]:
                # the id the engine binds must be one this step really extracts
                assert ce["identifier_path"] in rt["extract"].values(), path
                # the importer reads `type`, not `entity`
                assert ce["type"] and "entity" not in ce, path
                assert isinstance(ce["display_name_from"], str), path
                assert ce["identifier_keys"] == [], path
        else:
            assert impls[0]["creates_entities"] == [], path


PARAM_REQUIRED = ("name", "classification", "location", "json_path", "type", "required")
# `source_form_field` is gone in v5: it is for captured HTML forms and feeds only
# the entity-type resolver, so the builder never sees it.
PARAM_OPTIONAL = ("entity_type", "example_value", "constraints", "items", "format")


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
        "example_value": "Acme renewal",
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
            assert p["type"] in {"integer", "number", "string", "boolean",
                                 "object", "array"}, (path, p["name"])
            assert p["example_value"] != p["name"], (path, p["name"])
            for o in p["constraints"].get("enum_options", ()):
                # a numeric enum value fails the executor's zod parse and makes
                # the whole action unexecutable
                assert isinstance(o.get("value"), str), (path, p["name"], o)


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
    # an extract that is not an object at all: `{}` is legal (known_empty), a
    # list is not -- the engine maps over the names.
    doc["implementations"][0]["http_template"]["steps"][0]["response_template"]["extract"] = []
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path)
    assert {g.file for g in gaps} == {victim.name}
    assert any("extract" in g.gap for g in gaps), [g.gap for g in gaps]


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


# ---------------------------------------------------------------- v4: responses
# The live gap (4 Sep 2026, run-20260904-192933): every read/list carried
# `schema: {"type": "object"}` and `extract: {"id": "$.id"}`, so Monarch's
# planner could not chain "read the message" -> "its subject/body/sender" and
# fell back to an AI mailbox step that failed. The response must describe the
# record the front door actually returns.

def test_gmail_read_message_exposes_the_fields_the_mock_returns(generated):
    """The exact chain the live round could not plan: message -> subject/body/sender."""
    out, _ = generated
    doc = json.loads((out / "bench-gmail" / "bench-gmail_read_messages.json")
                     .read_text(encoding="utf-8"))
    step = doc["implementations"][0]["http_template"]["steps"][0]
    rt = step["response_template"]
    props = rt["schema"]["properties"]
    for field in ("id", "subject", "from", "to", "body_plain", "date"):
        assert field in props, (field, sorted(props))
        assert rt["extract"][field] == f"$.{field}", field
    assert rt["schema"]["type"] == "object"


def test_gmail_list_messages_extracts_from_the_wrapper_key(generated):
    """The front door answers {"messages": [...]}, not a bare array (verified 4 Sep).

    And Gmail's list handler projects a stub: format="minimal" returns
    {id, threadId} only. Promising `subject` here would tell the planner it can
    skip the read -- the step this whole change exists to make plannable.
    """
    out, _ = generated
    doc = json.loads((out / "bench-gmail" / "bench-gmail_list_messages.json")
                     .read_text(encoding="utf-8"))
    rt = doc["implementations"][0]["http_template"]["steps"][0]["response_template"]
    assert rt["schema"]["type"] == "object"
    coll = rt["schema"]["properties"]["messages"]
    assert coll["type"] == "array"
    assert sorted(coll["items"]["properties"]) == ["id", "threadId"]
    # The ARRAY itself is the output. The engine's path grammar has no `[*]`, so
    # v4.1's `$.messages[*].id` resolved to nothing at run time; the builder
    # iterates the array through the node's own `items.path` instead.
    assert rt["extract"]["messages"] == "$.messages"
    assert rt["extract"]["resultSizeEstimate"] == "$.resultSizeEstimate"
    assert not any("[*]" in v for v in rt["extract"].values())


def test_salesforce_read_contact_carries_the_record_fields(generated):
    out, _ = generated
    doc = json.loads((out / "bench-salesforce" / "bench-salesforce_read_sobjects.json")
                     .read_text(encoding="utf-8"))
    rt = doc["implementations"][0]["http_template"]["steps"][0]["response_template"]
    assert len(rt["extract"]) > 1
    assert rt["extract"]["Id"] == "$.Id"


def test_a_read_names_the_record_fields_it_can_chain_on(generated):
    """The v3 state of the world -- only `$.id` -- must not come back."""
    out, _ = generated
    for path, doc in _actions(out):
        if path.parent.name not in ("bench-gmail", "bench-salesforce"):
            continue
        if doc["business_action"]["verb"] != "read":
            continue
        rt = doc["implementations"][0]["http_template"]["steps"][0]["response_template"]
        assert len(rt["extract"]) > 1, path


def test_no_extract_path_uses_a_wildcard(generated):
    """The engine resolves `$.a.b` with numeric `[n]` only. `[*]` silently
    resolved to nothing, which is what made every v4.1 list read empty."""
    out, _ = generated
    for path, doc in _actions(out):
        for step in doc["implementations"][0]["http_template"]["steps"]:
            for name, value in step["response_template"]["extract"].items():
                assert re.fullmatch(r"\$(?:\.[A-Za-z0-9_-]+|\[\d+\])*", value), (path, value)
                assert re.fullmatch(r"\w+", name), (path, name)


def test_every_extract_path_exists_in_the_schema(generated):
    """A path the schema cannot reach is a field the builder wires and the
    response never carries."""
    out, _ = generated
    for path, doc in _actions(out):
        step = doc["implementations"][0]["http_template"]["steps"][0]
        rt = step["response_template"]
        for value in rt["extract"].values():
            assert seeds._schema_at(rt["schema"], value) is not None, (path, value)


def test_a_list_extracts_the_array_itself(generated):
    """The builder iterates through `items.path`, which the lint grounds on the
    extract paths; a per-row path would ground nothing."""
    out, _ = generated
    for path, doc in _actions(out):
        if doc["business_action"]["verb"] != "list":
            continue
        rt = doc["implementations"][0]["http_template"]["steps"][0]["response_template"]
        arrays = [n for n, s in (rt["schema"].get("properties") or {}).items()
                  if isinstance(s, dict) and s.get("type") == "array"]
        for name in arrays:
            assert rt["extract"].get(name) == f"$.{name}", (path, name)


def test_a_write_that_answers_nothing_declares_an_empty_response(generated):
    """The Salesforce PATCH really returns `{}` (probed 4 Sep 2026, and
    impl/salesforce.py:177+ returns it): declaring the record there would wire
    the builder to fields the response never carries."""
    out, _ = generated
    doc = json.loads((out / "bench-salesforce" / "bench-salesforce_update_contact.json")
                     .read_text(encoding="utf-8"))
    rt = doc["implementations"][0]["http_template"]["steps"][0]["response_template"]
    assert rt["extract"] == {}
    assert rt["schema"]["properties"] == {}
    assert rt["schema"]["additionalProperties"] is False


def test_a_salesforce_create_answers_the_id_envelope(generated):
    """`{id, success}`, not the record (impl/salesforce.py:177), and the created
    id must be chainable through exactly that extract path."""
    out, _ = generated
    doc = json.loads((out / "bench-salesforce" / "bench-salesforce_create_contact.json")
                     .read_text(encoding="utf-8"))
    impl = doc["implementations"][0]
    rt = impl["http_template"]["steps"][0]["response_template"]
    assert rt["extract"] == {"id": "$.id", "success": "$.success"}
    assert sorted(rt["schema"]["properties"]) == ["id", "success"]
    ce = impl["creates_entities"][0]
    assert ce["identifier_path"] == "$.id"
    assert ce["type"] == "contact"


def _broken(out, tmp_path, folder_name, victim_rel, mutate):
    """Write one mutated copy of an action and validate just that folder."""
    folder = tmp_path / folder_name / "bench-gmail"
    folder.mkdir(parents=True)
    victim = out / victim_rel
    doc = json.loads(victim.read_text(encoding="utf-8"))
    mutate(doc)
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    return seeds.validate(tmp_path / folder_name)


GMAIL_READ = "bench-gmail/bench-gmail_read_messages.json"


def test_validate_names_a_wildcard_extract(generated, tmp_path):
    """The v4.1 defect: `[*]` resolves to nothing at run time."""
    out, _ = generated

    def mutate(d):
        d["implementations"][0]["http_template"]["steps"][0][
            "response_template"]["extract"] = {"id": "$.messages[*].id"}
    gaps = _broken(out, tmp_path, "wildcard", GMAIL_READ, mutate)
    assert any("extract_path_ungrammatical" in g.gap for g in gaps), [g.gap for g in gaps]


def test_validate_names_an_extract_absent_from_the_schema(generated, tmp_path):
    out, _ = generated

    def mutate(d):
        d["implementations"][0]["http_template"]["steps"][0][
            "response_template"]["extract"]["ghost"] = "$.ghost"
    gaps = _broken(out, tmp_path, "unreachable", GMAIL_READ, mutate)
    assert any("extract_not_in_schema" in g.gap for g in gaps), [g.gap for g in gaps]


def test_validate_names_a_body_on_a_bodyless_method(generated, tmp_path):
    """`{}` is enough: the engine serializes it and fetch refuses the request."""
    out, _ = generated

    def mutate(d):
        d["implementations"][0]["http_template"]["steps"][0]["body_template"] = {}
    gaps = _broken(out, tmp_path, "getbody", GMAIL_READ, mutate)
    assert any("carries a body_template" in g.gap for g in gaps), [g.gap for g in gaps]


def test_validate_names_a_numeric_enum_option(generated, tmp_path):
    """A numeric value fails the executor's zod parse: the action is unexecutable."""
    out, _ = generated

    def mutate(d):
        d["implementations"][0]["parameters"][0]["constraints"]["enum_options"] = [
            {"value": 1}]
    gaps = _broken(out, tmp_path, "enum", GMAIL_READ, mutate)
    assert any("enum_options_not_string" in g.gap for g in gaps), [g.gap for g in gaps]


def test_validate_names_a_dangling_identifier_path(generated, tmp_path):
    """A path matching no extract makes the engine bind the wrong field."""
    out, _ = generated
    victim = out / "bench-salesforce" / "bench-salesforce_create_contact.json"
    folder = tmp_path / "ident" / "bench-salesforce"
    folder.mkdir(parents=True)
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["implementations"][0]["creates_entities"][0]["identifier_path"] = "$.nope"
    (folder / victim.name).write_text(json.dumps(doc), encoding="utf-8")
    gaps = seeds.validate(tmp_path / "ident")
    assert any("identifier_path_not_extracted" in g.gap for g in gaps), [g.gap for g in gaps]


def test_validate_names_an_optional_path_parameter(generated, tmp_path):
    """An unfilled path token dispatches literally, so it cannot be optional."""
    out, _ = generated

    def mutate(d):
        for p in d["implementations"][0]["parameters"]:
            if p["location"] == "path":
                p["required"] = False
    gaps = _broken(out, tmp_path, "optpath", GMAIL_READ, mutate)
    assert any("path_parameter_optional" in g.gap for g in gaps), [g.gap for g in gaps]


def test_bodyless_methods_carry_an_explicit_null_body(generated):
    """GET/HEAD/DELETE must send no body: the engine serializes even `{}` and
    fetch rejects those methods with one. v4.1 still sent `{}` plus a
    content-type on 60 DELETE steps."""
    out, _ = generated
    for path, doc in _actions(out):
        step = doc["implementations"][0]["http_template"]["steps"][0]
        headers = step["headers_template"]
        if step["method"] in ("GET", "HEAD", "DELETE"):
            assert step["body_template"] is None, path
            assert headers == {}, path
        else:
            assert isinstance(step["body_template"], dict), path
            assert headers == {"content-type": "application/json"}, path


# ---------------------------------------------------------------- v5: manifest


def test_manifest_records_the_version_and_a_stable_digest(generated, tmp_path):
    out, summary = generated
    manifest = json.loads((out / "ok.txt").read_text(encoding="utf-8"))
    assert manifest["version"] == seeds.VERSION == "v5.2"
    assert manifest["canonical"] is True
    assert manifest["products"] == len(summary.folders)
    assert manifest["actions"] == summary.files_written
    assert manifest["front_door"] == SHIM
    # the canonical rules, each checkable in the bytes that were written
    assert manifest["bodyless_body_null"] is True
    assert manifest["no_wildcard_extracts"] is True
    assert manifest["enum_options_are_strings"] is True
    # the digest is over the seeds, and a regeneration reproduces it
    again = tmp_path / "again-manifest"
    seeds.generate(again, SHIM)
    assert manifest["sha256"] == seeds.folder_sha256(again)
    assert len(manifest["sha256"]) == 64


def test_a_changed_action_changes_the_digest(generated, tmp_path):
    """The digest is what tells two knowledge bases apart."""
    out, _ = generated
    copy = tmp_path / "tampered"
    shutil.copytree(out, copy)
    victim = copy / "bench-gmail" / "bench-gmail_read_messages.json"
    doc = json.loads(victim.read_text(encoding="utf-8"))
    doc["business_action"]["label"] = "Something else"
    victim.write_text(json.dumps(doc), encoding="utf-8")
    assert seeds.folder_sha256(copy) != seeds.folder_sha256(out)


def test_a_create_behind_an_envelope_is_still_chainable(generated):
    """Slack answers `{ok, channel: {...}}` (impl/slack.py:45): the created id is
    one level down, and only the handler code says so. The engine's grammar
    reaches it, so `$.channel.id` is a legal identifier_path."""
    out, _ = generated
    doc = json.loads((out / "bench-slack" /
                      "bench-slack_create_conversations-create.json")
                     .read_text(encoding="utf-8"))
    impl = doc["implementations"][0]
    rt = impl["http_template"]["steps"][0]["response_template"]
    ce = impl["creates_entities"][0]
    assert ce["identifier_path"] == "$.channel.id"
    assert ce["identifier_path"] in rt["extract"].values()   # must be an extract
    assert ce["type"] == "channel"                           # not the RPC segment


# --------------------------------------------------- v5.1: the wire, probed

# One task per service that seeds it, one read whose real body v5 got wrong, and
# the id to address it with. The expectation is never pasted here: the test
# calls the world in process (the same `api_fetch` the front door serves) and
# compares the keys it really answers with what the seed declares.
#
# Every entry is a shape v5 published wrongly, verified 4 Sep 2026: the record
# instead of the envelope around it (`{Customer: {...}}`), the AutomationBench
# record instead of the wire body (Sheets), or a collection missing the scalars
# beside it (`ok`, `paging`, `total`).
WIRE_PROBES = [
    # (service, task, seed file, method, path, {path var: value})
    ("google_sheets", "tier-simple/finance.annual_budget_prep.json",
     "bench-google-sheets/bench-google-sheets_read_spreadsheets.json",
     "GET", "/v4/spreadsheets/{spreadsheetId}", {"spreadsheetId": "ss_budget_prep"}),
    ("google_sheets", "tier-simple/finance.annual_budget_prep.json",
     "bench-google-sheets/bench-google-sheets_list_values-batchget.json",
     "GET", "/v4/spreadsheets/{spreadsheetId}/values:batchGet",
     {"spreadsheetId": "ss_budget_prep"}),
]


def _wire_keys(service: str, task_rel: str, method: str, path: str,
               values: dict[str, str]) -> set[str]:
    """The top-level keys the front door really answers with, called in process."""
    from wb_world.episode import Episode
    from wb_world.openapi import load_schemas
    task = json.loads((Path("tasks") / task_rel).read_text(encoding="utf-8"))
    episode = Episode(task, "seed-probe")
    base = load_schemas()[service].get("baseUrl", "").rstrip("/")
    for name, value in values.items():
        path = path.replace("{%s}" % name, value)
    body = json.loads(episode.api_fetch(method, base + path))
    assert "error" not in body, f"{service} {path} answered an error: {body}"
    return set(body)


@pytest.mark.parametrize(
    "service,task_rel,seed_file,method,path,values", WIRE_PROBES,
    ids=[f"{p[0]}:{p[4]}" for p in WIRE_PROBES])
def test_schema_and_extract_match_the_real_wire_body(
        generated, service, task_rel, seed_file, method, path, values):
    """Every key the front door answers is declared, and every extract is one of them.

    The shape check that v5's validator could not make: it reads the files, not
    the API. Monarch's planner refused every Google Sheets task because these
    two reads described the AutomationBench `Spreadsheet` record
    (`{id, title, worksheets}`) instead of the wire body.
    """
    out, _ = generated
    real = _wire_keys(service, task_rel, method, path, values)
    step = (json.loads((out / seed_file).read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    declared = set((step["response_template"]["schema"].get("properties") or {}))
    assert not (real - declared), (
        f"{service} {path} answers {sorted(real - declared)}, which the seed never names")
    extract = step["response_template"]["extract"]
    assert set(extract) <= declared
    assert all(v == f"$.{k}" for k, v in extract.items()), extract


def test_sheets_values_read_is_the_value_range_not_the_spreadsheet(generated):
    """GET .../values/{range} answers `{range, majorDimension, values}`.

    v5 reused the spreadsheet record here, so the planner saw no row values at
    all -- the defect that made it say the catalog "doesn't expose the data".
    """
    out, _ = generated
    step = (json.loads((out / "bench-google-sheets" /
                        "bench-google-sheets_read_values.json").read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"]
    assert sorted(props) == ["majorDimension", "range", "values"]
    assert props["values"]["type"] == "array"          # rows, not a record
    assert step["response_template"]["extract"]["values"] == "$.values"


def test_sheets_append_body_is_values_not_spreadsheet_fields(generated):
    """POST .../values/{range}:append takes `{values: [[...]]}`.

    v5 sent `properties`/`sheets`/`spreadsheetUrl` -- spreadsheet fields on a
    row-append -- so nothing the planner wrote could have reached the wire.
    """
    out, _ = generated
    impl = (json.loads((out / "bench-google-sheets" /
                        "bench-google-sheets_create_values.json")
                       .read_text(encoding="utf-8"))["implementations"][0])
    step = impl["http_template"]["steps"][0]
    assert "values" in step["body_template"]
    assert not {"properties", "sheets", "spreadsheetUrl"} & set(step["body_template"])
    values = next(p for p in impl["parameters"] if p["name"] == "values")
    assert values["location"] == "body"
    # and the response is the append receipt, not the spreadsheet
    props = step["response_template"]["schema"]["properties"]
    assert "updates" in props and "tableRange" in props


@pytest.mark.parametrize("seed_file,key", [
    ("bench-quickbooks/bench-quickbooks_read_customer.json", "Customer"),
    ("bench-zendesk/bench-zendesk_read_organizations.json", "organization"),
    ("bench-xero/bench-xero_read_contacts.json", "Contacts"),
    ("bench-google-calendar/bench-google-calendar_read_calendars.json", "calendar"),
    ("bench-linkedin/bench-linkedin_read_organizations.json", "company"),
])
def test_a_record_served_inside_an_envelope_is_declared_as_one(generated, seed_file, key):
    """These reads answer `{<key>: {...}}`, never the bare record.

    v5 declared the record's own fields at the top level, so every field the
    planner wired (`DisplayName`, `id`, `Name`) was `undefined` at run time.
    """
    out, _ = generated
    step = (json.loads((out / seed_file).read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"]
    assert key in props, f"{seed_file} does not declare the envelope key {key!r}"
    assert step["response_template"]["extract"][key] == f"$.{key}"


@pytest.mark.parametrize("seed_file,expected", [
    ("bench-slack/bench-slack_list_users-list.json", {"ok", "members"}),
    ("bench-slack/bench-slack_list_conversations-list.json", {"ok", "channels"}),
    ("bench-hubspot/bench-hubspot_list_contacts.json", {"results", "paging"}),
    ("bench-jira/bench-jira_list_search.json", {"values", "total", "isLast"}),
    ("bench-google-drive/bench-google-drive_list_files.json",
     {"kind", "files", "incompleteSearch"}),
])
def test_a_list_declares_the_scalars_the_handler_serves_beside_it(
        generated, seed_file, expected):
    """A list answers more than its collection: `ok`, `paging`, `total`, `kind`.

    v5 named only the collection (and Slack's under the wrong key, `users` for
    `members`), so the planner could neither page nor tell success from failure.
    """
    out, _ = generated
    step = (json.loads((out / seed_file).read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"]
    assert expected <= set(props), f"{seed_file}: missing {sorted(expected - set(props))}"


def test_an_opaque_body_field_says_how_to_build_one(generated):
    """Gmail's send takes `raw`, a base64url RFC 2822 message.

    `helper_text` is the ONLY prose the builder sees per parameter, so if it does
    not say what bytes go in the blob, nothing does.
    """
    out, _ = generated
    impl = (json.loads((out / "bench-gmail" / "bench-gmail_create_messages-send.json")
                       .read_text(encoding="utf-8"))["implementations"][0])
    raw = next(p for p in impl["parameters"] if p["name"] == "raw")
    helper = raw["constraints"]["helper_text"].lower()
    assert "base64" in helper and "rfc 2822" in helper


# -- v5.2: the rows of a list are the records the world really serves ---------

def test_soql_records_carry_the_wire_field_spelling(generated):
    """`SELECT Id, Name FROM Account` answers `records[].Id`, never `records[].id`.

    Monarch's builder wrote `records[0].id` off v5.1's open-map row schema and the
    step resolved to nothing: the mock's `_salesforce_record_dict` serialises the
    model's `to_display_dict`, whose identifier is `Id`. A row schema with no
    properties could not catch it, so the sObject fields are named here.
    """
    out, _ = generated
    step = (json.loads((out / "bench-salesforce" / "bench-salesforce_list_query.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    row = step["response_template"]["schema"]["properties"]["records"]["items"]
    props = row["properties"]
    assert "Id" in props, "the SOQL row must name the identifier the wire carries"
    assert "id" not in props, "`id` is not a field of a Salesforce record"
    assert "Name" in props and "StageName" in props, "per-object fields must be named"
    assert row.get("additionalProperties") is True, "a SELECT chooses its own columns"
    assert row.get("required") == ["Id"]


def test_an_open_row_is_replaced_by_the_fields_the_model_declares(generated):
    """A list whose rows were an open map now names the service's own fields."""
    out, _ = generated
    for seed_file, key, wanted in [
        ("bench-salesforce/bench-salesforce_list_query.json", "results", "Id"),
        ("bench-xero/bench-xero_list_invoices.json", "Invoices", "InvoiceID"),
    ]:
        path = out / seed_file
        if not path.exists():
            continue
        step = (json.loads(path.read_text(encoding="utf-8"))
                ["implementations"][0]["http_template"]["steps"][0])
        row = step["response_template"]["schema"]["properties"][key]["items"]
        assert wanted in (row.get("properties") or {}), f"{seed_file}: {key} rows are open"


def test_a_base_url_placeholder_becomes_a_path_parameter(generated):
    """BambooHR's {companyDomain} and Recruitee's {company_id} live in the baseUrl.

    v5.1 published the front-door URL without them, so the shim rebuilt a world
    URL that still carried the raw `{companyDomain}` and no router ever matched:
    ~169 actions were unreachable. The placeholder belongs on the front door as a
    path token, declared like any other path parameter.
    """
    out, _ = generated
    for folder, token in [("bench-bamboohr", "companyDomain"),
                          ("bench-recruitee", "company_id")]:
        files = [p for p in sorted((out / folder).glob("*.json"))
                 if p.name != "_meta.json"]
        assert files, f"{folder} has no actions"
        impl = json.loads(files[0].read_text(encoding="utf-8"))["implementations"][0]
        url = impl["http_template"]["steps"][0]["url_template"]
        assert "{{%s}}" % token in url, f"{folder}: {token} is not on the front door"
        assert "{%s}" % token not in url.replace("{{%s}}" % token, ""), \
            f"{folder}: a bare {{{token}}} survives in the URL"
        assert any(p["name"] == token and p["location"] == "path"
                   for p in impl["parameters"]), \
            f"{folder}: {token} is not declared as a path parameter"


@pytest.mark.parametrize("seed_file,key", [
    ("bench-gmail/bench-gmail_list_messages.json", "resultSizeEstimate"),
    ("bench-gmail/bench-gmail_list_threads.json", "resultSizeEstimate"),
    ("bench-jira/bench-jira_list_search.json", "total"),
    ("bench-mailchimp/bench-mailchimp_list_lists.json", "total_items"),
    ("bench-google-calendar/bench-google-calendar_list_calendarlist.json", "resultCount"),
])
def test_a_counted_scalar_is_typed_as_a_number_not_a_record(generated, seed_file, key):
    """`"resultSizeEstimate": len(messages)` is an integer on the wire.

    v5.1 read the handler's literal but did not know what `len(...)` evaluates
    to, so the key stayed untyped, `_action`'s "one open object is the record"
    rule promoted it, and the seed advertised a whole Message record where the
    response carries a count. Sixteen read findings shared this one cause.
    """
    out, _ = generated
    path = out / seed_file
    if not path.exists():
        pytest.skip(f"{seed_file} is not part of this catalogue")
    step = (json.loads(path.read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    prop = step["response_template"]["schema"]["properties"][key]
    assert prop["type"] == "integer", f"{seed_file}: {key} is {prop['type']}, not a count"
    assert "properties" not in prop, f"{seed_file}: {key} still carries record fields"


@pytest.mark.parametrize("seed_file", [
    "bench-zoho-desk/bench-zoho-desk_list_tickets.json",
    "bench-freshdesk/bench-freshdesk_list_v2-tickets.json",
])
def test_a_handler_that_returns_a_bare_array_is_declared_as_one(generated, seed_file):
    """Some lists answer `[{...}]`, with no wrapper key at all.

    `json.dumps([t.to_display_dict() for t in ...])` is the whole body. v5.1
    wrapped every list under a collection key, so the seed promised `$.tickets`
    where the response is the array itself: the extract resolved to nothing and
    the planner could not read a single row.
    """
    out, _ = generated
    path = out / seed_file
    if not path.exists():
        pytest.skip(f"{seed_file} is not part of this catalogue")
    step = (json.loads(path.read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    schema = step["response_template"]["schema"]
    assert schema["type"] == "array", f"{seed_file}: declared {schema['type']}, wire is an array"
    # `$` is the whole body: the only path that reaches a bare array.
    assert list(step["response_template"]["extract"].values()) == ["$"]


@pytest.mark.parametrize("seed_file", [
    "bench-hubspot/bench-hubspot_list_contacts.json",
    "bench-hubspot/bench-hubspot_list_companies.json",
    "bench-hubspot/bench-hubspot_list_deals.json",
    "bench-hubspot/bench-hubspot_list_tickets.json",
])
def test_a_paging_cursor_beside_a_collection_is_not_the_record(generated, seed_file):
    """HubSpot answers `{results: [...], paging: {next: {after}}}`.

    `paging` is a cursor, not a contact. v5.1's "an envelope holding one open
    object is holding the record" rule -- right for Asana's `{data: {...}}` --
    fired here too and published every contact field under `paging`, so the
    builder was told `paging.email` exists.
    """
    out, _ = generated
    path = out / seed_file
    if not path.exists():
        pytest.skip(f"{seed_file} is not part of this catalogue")
    step = (json.loads(path.read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"]
    assert props["results"]["type"] == "array"
    assert not (props["paging"].get("properties") or {}), \
        "paging carries record fields it does not have"


@pytest.mark.parametrize("seed_file,field,type_", [
    ("bench-freshdesk/bench-freshdesk_read_tickets.json", "subject", "string"),
    ("bench-freshdesk/bench-freshdesk_read_tickets.json", "description", "string"),
    ("bench-freshdesk/bench-freshdesk_read_contacts.json", "email", "string"),
])
def test_a_flat_record_built_by_a_helper_keeps_its_field_types(
        generated, seed_file, field, type_):
    """`return json.dumps(_ticket_to_resource(t))` answers the RECORD, flat.

    Its keys were read correctly but every value is `ticket.<attr>` -- an
    attribute the envelope reader cannot type -- so all fourteen were published
    as untyped objects and the builder was told `subject` is a nested object.
    The model behind the attribute says what each one is.
    """
    out, _ = generated
    path = out / seed_file
    if not path.exists():
        pytest.skip(f"{seed_file} is not part of this catalogue")
    step = (json.loads(path.read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    prop = step["response_template"]["schema"]["properties"][field]
    assert prop["type"] == type_, f"{seed_file}: {field} is {prop['type']}, not {type_}"


def test_a_record_promises_no_field_the_wire_can_prune(generated):
    """`to_display_dict` drops empty values, so a record guarantees nothing.

    v5.1 promised the identifier on every record schema. But QuickBooks answers
    `{"CompanyInfo": {"CompanyName": ..., "Country": ...}}` -- a hardcoded literal
    with no `Id` at all -- and Zoom's recordings omit theirs, so `required` was a
    promise the response broke. Only a MODEL that states which keys survive may
    say so; a derived record says nothing.
    """
    out, _ = generated
    for seed_file, key in [
        ("bench-quickbooks/bench-quickbooks_read_companyinfo.json", "CompanyInfo"),
        ("bench-quickbooks/bench-quickbooks_list_preferences.json", "Preferences"),
    ]:
        path = out / seed_file
        if not path.exists():
            continue
        step = (json.loads(path.read_text(encoding="utf-8"))
                ["implementations"][0]["http_template"]["steps"][0])
        inner = step["response_template"]["schema"]["properties"][key]
        assert not inner.get("required"), \
            f"{seed_file}: {key} promises {inner.get('required')}, which the wire prunes"


@pytest.mark.parametrize("seed_file,key,field,type_", [
    ("bench-quickbooks/bench-quickbooks_read_customer.json", "Customer", "Active", "string"),
    ("bench-quickbooks/bench-quickbooks_read_customer.json", "Customer", "Balance", "string"),
])
def test_an_abbreviated_model_name_still_describes_its_resource(
        generated, seed_file, key, field, type_):
    """QuickBooks names its models `QBCustomer`, not `QuickbooksCustomer`.

    `_record_schema` tried the service's own name as the prefix, missed every
    model, and fell through to the jsonc schema -- which describes the REAL Intuit
    API. The mock serialises `"Active": str(self.active).lower()`, a string, so
    the seed promised a boolean the wire never sends.
    """
    out, _ = generated
    path = out / seed_file
    if not path.exists():
        pytest.skip(f"{seed_file} is not part of this catalogue")
    step = (json.loads(path.read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"][key]["properties"]
    assert props[field]["type"] == type_, \
        f"{field} is {props[field]['type']}, the wire sends {type_}"


@pytest.mark.parametrize("seed_file,path_to_array", [
    ("bench-helpcrunch/bench-helpcrunch_list_customers.json", ("data", "events")),
    ("bench-intercom/bench-intercom_list_conversations.json",
     ("conversations", "conversation_parts")),
])
def test_an_array_of_records_does_not_claim_its_rows_are_strings(
        generated, seed_file, path_to_array):
    """`events: list[HelpCrunchCustomerEvent]` holds objects, not strings.

    Every array field was declared `items: {type: string}` regardless of what it
    holds, so the builder was told a list of event RECORDS was a list of words.
    An array whose element type is a model says so instead.
    """
    out, _ = generated
    path = out / seed_file
    if not path.exists():
        pytest.skip(f"{seed_file} is not part of this catalogue")
    step = (json.loads(path.read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    node = step["response_template"]["schema"]["properties"][path_to_array[0]]
    node = (node.get("items") or node)
    field = (node.get("properties") or {})[path_to_array[1]]
    assert field["type"] == "array"
    assert (field.get("items") or {}).get("type") != "string", \
        f"{seed_file}: {path_to_array[1]} rows are records, not strings"


def test_a_status_code_guard_is_not_the_success_body(generated):
    """`return json.dumps({"code": 404, "message": ...})` is the NOT-FOUND guard.

    Zoom writes its refusal without an `error` key, so the reader took those two
    keys for the response and published `{code, message}` as the meeting -- the
    success return is `_meeting_to_resource(m)`, one line above.
    """
    out, _ = generated
    step = (json.loads((out / "bench-zoom" / "bench-zoom_read_meetings.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"].get("properties") or {}
    assert set(props) != {"code", "message"}, "the 404 guard was published as the body"
    assert "topic" in props or "id" in props, "the meeting's own fields are missing"


def test_a_key_type_is_read_from_this_endpoint_not_a_namesake(generated):
    """Zoom's meeting `id` is a string; some other Zoom handler writes an int one.

    `_KEY_TYPES` is keyed by (service, key) and first-writer-wins, so the unrelated
    literal typed the meeting read's `id` as an integer and the seed promised a
    number where the wire sends `"mtg_h1"`.
    """
    out, _ = generated
    for seed_file in ("bench-zoom/bench-zoom_read_meetings.json",
                      "bench-zoom/bench-zoom_list_meeting-summary.json"):
        path = out / seed_file
        if not path.exists():
            continue
        step = (json.loads(path.read_text(encoding="utf-8"))
                ["implementations"][0]["http_template"]["steps"][0])
        prop = (step["response_template"]["schema"].get("properties") or {}).get("id")
        if prop:
            assert prop["type"] == "string", f"{seed_file}: id is {prop['type']}"


def test_a_key_whose_value_may_be_none_is_not_promised(generated):
    """`"createdDateTime": x.isoformat() if x else None` may not be there.

    DocuSign's envelope builder writes three date keys that way and the response
    prunes them when null, yet every key of the literal was declared `required`,
    so the seed promised fields the wire had already dropped.
    """
    out, _ = generated
    step = (json.loads((out / "bench-docusign" / "bench-docusign_read_envelopes.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    required = set(step["response_template"]["schema"].get("required") or [])
    for key in ("createdDateTime", "statusChangedDateTime", "lastModifiedDateTime"):
        assert key not in required, f"{key} is promised but may be pruned"
    # the keys the builder always writes are still promised
    assert "envelopeId" in required and "status" in required


def test_a_collection_row_is_not_filled_with_a_neighbouring_record(generated):
    """DocuSign's `signers` are recipients; nothing models them.

    Asking `_record_schema` for `<path>/signers` found no signer, walked back up
    the path and answered the ENVELOPE -- so the seed said every signer carries
    `emailSubject` and `envelopeId`, and the builder wired fields no row has.
    An unmodelled row is an open row.
    """
    out, _ = generated
    step = (json.loads((out / "bench-docusign" / "bench-docusign_list_recipients.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    row = step["response_template"]["schema"]["properties"]["signers"]["items"]
    props = row.get("properties") or {}
    for alien in ("emailSubject", "envelopeId", "emailBlurb"):
        assert alien not in props, f"a signer does not carry {alien}"


def test_a_literal_annotation_keeps_the_type_of_its_values(generated):
    """`priority: Literal[1, 2, 3, 4]` is an integer on the wire.

    `_annotation_type` fell through every `Literal[...]` to its "string" default,
    so Freshdesk's ticket promised strings where the API serves 1-4.
    """
    out, _ = generated
    step = (json.loads((out / "bench-freshdesk" / "bench-freshdesk_read_tickets.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"]
    assert props["priority"]["type"] == "integer", props["priority"]
    assert props["status"]["type"] == "integer", props["status"]


def test_the_sheets_values_read_declares_rows_of_cells(generated):
    """`values` is an array of ARRAYS -- one inner list per row of cells.

    This is the read the whole conformance check exists for: v5 described the AB
    `Spreadsheet` record here and Monarch's planner refused every Sheets task.
    The rows are lists of scalars, and `majorDimension` is the handler's own
    string parameter, not a nested object.
    """
    out, _ = generated
    step = (json.loads((out / "bench-google-sheets" / "bench-google-sheets_read_values.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    props = step["response_template"]["schema"]["properties"]
    assert props["majorDimension"]["type"] == "string", props["majorDimension"]
    assert props["values"]["type"] == "array"
    assert props["values"]["items"]["type"] == "array", "a row is a list of cells"


def test_a_bare_array_row_is_what_its_own_builder_makes(generated):
    """Freshdesk's list is `[_ticket_to_resource(t) for t in ...]`.

    The row is exactly what that helper writes -- the same fourteen keys the READ
    serves. Falling back to the display-dict record added `priority_code` and
    `status_code`, which this endpoint does not carry, and re-typed `priority`.
    """
    out, _ = generated
    step = (json.loads((out / "bench-freshdesk" / "bench-freshdesk_list_v2-tickets.json")
                       .read_text(encoding="utf-8"))
            ["implementations"][0]["http_template"]["steps"][0])
    row = step["response_template"]["schema"]["items"]
    props = row.get("properties") or {}
    assert "priority_code" not in props and "status_code" not in props
    assert props["priority"]["type"] == "integer", props.get("priority")


def test_the_manifest_carries_the_conformance_totals(generated):
    """v5.2 records what the check made of the seeds it just wrote.

    The digest says WHICH knowledge base this is; the conformance block says how
    true it was against the simulated apps when it was written, so a later round
    can be compared without re-running anything.
    """
    out, _ = generated
    manifest = json.loads((out / "ok.txt").read_text(encoding="utf-8"))
    block = manifest["conformance"]
    assert isinstance(block, dict) and block
    # every action is accounted for: a verdict, or counted as unrunnable here
    assert sum(block.values()) == manifest["actions"]
    assert block["ok"] > 0
    # and the field the commit adds later is NOT written by the generator
    assert "commit" not in manifest


def test_the_digest_ignores_the_conformance_report(generated):
    """`wb monarch conform` writes `conformance.json` INTO the seed folder.

    `folder_sha256` globbed every `*.json`, so running the check changed the
    knowledge base's own fingerprint -- two rounds with identical seeds would
    have compared as different. Only the action files identify the set.
    """
    out, _ = generated
    before = seeds.folder_sha256(out)
    (out / "conformance.json").write_text('{"totals": {"ok": 1}}', encoding="utf-8")
    try:
        assert seeds.folder_sha256(out) == before, \
            "the check's own report changed the knowledge-base digest"
    finally:
        (out / "conformance.json").unlink()


def test_generate_prunes_a_stale_action_file(tmp_path):
    """A file the current run did not write is gone after it.

    Renaming a path leaves the old action behind -- the bamboohr base-URL fix did
    exactly that, and the orphan made the validator count 687 actions for a
    686-action set and stayed in the digest as a seed nothing generates.
    """
    out = tmp_path / "pruned"
    summary = seeds.generate(out, SHIM)
    folder = out / summary.folders[0]
    stale = folder / "bench-stale_read_gone.json"
    stale.write_text('{"business_action": {}}', encoding="utf-8")
    again = seeds.generate(out, SHIM)
    assert not stale.exists(), "a stale action file survived a regeneration"
    assert again.files_written == summary.files_written
    # ...and the digest is the one a clean run produces
    clean = tmp_path / "clean"
    seeds.generate(clean, SHIM)
    assert seeds.folder_sha256(out) == seeds.folder_sha256(clean)


def test_pruning_never_reaches_outside_the_product_folders(tmp_path):
    """Only folders this run writes are pruned, and only their `*.json`.

    Deleting by glob over `out_dir` would take a neighbouring folder's files with
    it -- `wb monarch conform` keeps its report beside the products.
    """
    out = tmp_path / "scoped"
    seeds.generate(out, SHIM)
    (out / "conformance.json").write_text('{"totals": {}}', encoding="utf-8")
    keepsake = out / "notes"
    keepsake.mkdir()
    (keepsake / "mine.json").write_text("{}", encoding="utf-8")

    seeds.generate(out, SHIM)
    assert (out / "conformance.json").exists(), "the check's report was deleted"
    assert (keepsake / "mine.json").exists(), "an unrelated folder was pruned"
