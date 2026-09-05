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
    assert manifest["version"] == "v5"
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
