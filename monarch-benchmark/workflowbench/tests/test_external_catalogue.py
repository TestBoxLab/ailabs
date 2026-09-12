"""The external seed path must describe only the adapter's published contract."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from wb_world.episode import contract_hash
from wb_world import seeds
from wb_orchestrator import external_catalogue as catalog

PUBLIC = "https://front.example.test/door"


@pytest.fixture
def source(tmp_path, monkeypatch):
    pin = {"package": "tau2", "version": "1.0.1", "revision": "a" * 40, "split": "retail/base"}
    directory = tmp_path / "tasks"
    directory.mkdir()
    for index in (1, 2):
        task = {"task":f"source.{index}", "prompt": "PRIVATE REQUEST", "source_ref":{"answer":"PRIVATE ANSWER"},
                "info":{"world":pin, "initial_state":{"private":"PRIVATE SNAPSHOT"}}}
        task["contract_sha256"] = contract_hash(task)
        (directory / f"{index}.json").write_text(json.dumps(task))
    product = SimpleNamespace(name="alternative", world="tau2", services=["gmail"],
                              source=SimpleNamespace(benchmark="tau2",version="1.0.1",split="retail/base"))
    doc = {"openapi":"3.1.0", "servers":[{"url": PUBLIC + "/gmail"}],
           "components":{"schemas":{"Body":{"type":"object","properties":{
              "label":{"type":"string","description":"New label"}, "optional":{"type":"integer","default":4}},
              "required":["label"]}, "Reply":{"type":"object","properties":{"label":{"type":"string"},"note":{"type":"string"}},"required":["label"]}}},
           "paths":{"/messages/{message_id}":{"parameters":[{"name":"message_id","in":"path","required":True,"schema":{"type":"string"}}],
             "patch":{"operationId":"edit_message","summary":"Edit message", "requestBody":{"required":True,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Body"}}}},
                      "responses":{"200":{"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Reply"}}}}}}}}}
    closed = []
    class Interfaces:
        def services(self): return ["gmail", "private"]
        def spec(self, service, public_url):
            assert service == "gmail"
            assert public_url == PUBLIC
            return copy.deepcopy(doc)
    class World:
        _private_spec = {"/admin/snapshot": {"get":{}}}
        snapshot0 = {"secret":"PRIVATE SNAPSHOT"}
        def __init__(self, task, episode_id): self.task = task
        @classmethod
        def prerequisites(cls): return []
        def interfaces(self): return Interfaces()
        def close(self): closed.append(self.task["task"])
    monkeypatch.setattr(catalog, "resolve_world", lambda _: World)
    return product, directory, doc, closed


def actions(out):
    return [json.loads(path.read_text()) for path in out.glob("bench-*/*.json") if path.name != "_meta.json"]


def test_generate_keeps_required_optional_refs_and_only_public_contract(source, tmp_path):
    product, tasks, doc, closed = source
    result = catalog.generate(product, tasks, tmp_path / "seeds", PUBLIC)
    out = tmp_path / "seeds"
    assert result.operations_in_spec == result.files_written == 1
    assert result.service_slugs == {"gmail":"bench-alternative-gmail"}
    assert closed == ["source.1", "source.2"]
    action, = actions(out)
    step = action["implementations"][0]["http_template"]["steps"][0]
    assert step["url_template"] == PUBLIC + "/gmail/messages/{{message_id}}"
    assert step["response_template"]["schema"] == doc["components"]["schemas"]["Reply"]
    assert step["response_template"]["extract"] == {"label":"$.label", "note":"$.note"}
    params = {p["name"]:p for p in action["implementations"][0]["parameters"]}
    assert params["label"]["required"] is True
    assert params["optional"]["required"] is False
    assert params["optional"]["example_value"] == 4
    assert "example_value" not in params["label"]
    assert "example_value" not in params["message_id"]
    assert seeds.validate(out) == []
    serialized = "".join(p.read_text() for p in out.rglob("*.json"))
    assert "PRIVATE" not in serialized
    assert "/admin/" not in serialized
    assert "source_ref" not in serialized
    assert catalog.product_slug(SimpleNamespace(name="appworld"), "gmail") != seeds.product_slug("gmail")


def test_tool_interfaces_full_route_is_not_prefixed_twice_and_hashes_repeat(source, tmp_path):
    product, tasks, doc, closed = source
    doc["servers"] = [{"url":PUBLIC}]
    doc["paths"] = {"/gmail/send_message": {"post":{"operationId":"send_message","requestBody":{"content":{"application/json":{"schema":{"type":"object","properties":{"message":{"type":"string"}},"required":["message"]}}}},"responses":{"200":{"content":{"application/json":{"schema":{"type":"object"}}}}}}}}
    first = catalog.generate(product, tasks, tmp_path / "first", PUBLIC)
    second = catalog.generate(product, tasks, tmp_path / "second", PUBLIC)
    action, = actions(tmp_path / "first")
    assert action["implementations"][0]["http_template"]["steps"][0]["url_template"] == PUBLIC + "/gmail/send_message"
    assert first.sha256 == second.sha256 == seeds.folder_sha256(tmp_path / "first")
    assert {p.relative_to(tmp_path/"first").as_posix():p.read_bytes() for p in (tmp_path/"first").rglob("*") if p.is_file()} == {p.relative_to(tmp_path/"second").as_posix():p.read_bytes() for p in (tmp_path/"second").rglob("*") if p.is_file()}


def test_path_query_same_name_keeps_both_values_and_defaults(source, tmp_path):
    product,tasks,doc,_ = source
    path = doc["paths"]["/messages/{message_id}"]
    path["patch"]["parameters"] = [{"name":"message_id","in":"query","required":False,"schema":{"type":"string"}}, {"name":"limit","in":"query","required":False,"schema":{"type":"integer","default":20}}]
    catalog.generate(product,tasks,tmp_path/"out",PUBLIC)
    action, = actions(tmp_path/"out")
    params = action["implementations"][0]["parameters"]
    assert len({p["name"] for p in params}) == len(params) == 5
    assert {p["location"] for p in params if "message_id" in p["name"]} == {"path","query"}
    assert seeds.validate(tmp_path/"out") == []


def test_failed_reference_closes_world_without_publishing_partial_files(source,tmp_path):
    product,tasks,doc,closed = source
    doc["paths"]["/messages/{message_id}"]["patch"]["requestBody"]["content"]["application/json"]["schema"] = {"$ref":"https://private.example/answer.json"}
    with pytest.raises(ValueError,match="reference"):
        catalog.generate(product,tasks,tmp_path/"out",PUBLIC)
    assert closed == ["source.1"]
    assert not (tmp_path/"out").exists()


def test_undeclared_source_response_and_request_fields_are_not_invented(source,tmp_path):
    product,tasks,doc,_ = source
    op = doc["paths"]["/messages/{message_id}"]["patch"]
    op["requestBody"] = {"content":{"application/x-www-form-urlencoded":{"schema":{"type":"object","properties":{"username":{"type":"string"},"password":{"type":"string"}},"required":["username","password"]}}}}
    op["responses"] = {"204":{"description":"No response body"}}
    catalog.generate(product,tasks,tmp_path/"out",PUBLIC)
    action, = actions(tmp_path/"out")
    impl=action["implementations"][0]
    step=impl["http_template"]["steps"][0]
    assert step["body_template"] == {"password":"{{password}}","username":"{{username}}"}
    assert step["response_template"] == {"status":204,"extract":{},"schema":{"description":"No response body"}}
    assert impl["creates_entities"] == []


def test_open_source_body_is_one_typed_payload_without_invented_fields(source,tmp_path):
    product,tasks,doc,_ = source
    op=doc["paths"]["/messages/{message_id}"]["patch"]
    op["requestBody"]={"required":True,"content":{"application/json":{"schema":{"type":"object","additionalProperties":True,"description":"Published extensible body"}}}}
    catalog.generate(product,tasks,tmp_path/"out",PUBLIC)
    action, = actions(tmp_path/"out")
    impl=action["implementations"][0]
    assert impl["http_template"]["steps"][0]["body_template"] == "{{payload}}"
    payload, = [p for p in impl["parameters"] if p["location"] == "body"]
    assert (payload["name"],payload["type"],payload["required"]) == ("payload","object",True)
    assert "example_value" not in payload
    assert "Published extensible body" in payload["constraints"]["helper_text"]

def test_mixed_scalar_union_remains_exact_inside_root_json_payload(source,tmp_path):
    product,tasks,doc,_ = source
    schema={"type":"object","properties":{"answer":{"anyOf":[{"type":"number"},{"type":"integer"},{"type":"string"}]}},"required":["answer"]}
    doc["paths"]["/messages/{message_id}"]["patch"]["requestBody"]={"required":True,"content":{"application/json":{"schema":schema}}}
    catalog.generate(product,tasks,tmp_path/"out",PUBLIC)
    action, = actions(tmp_path/"out")
    impl=action["implementations"][0]
    payload, = [p for p in impl["parameters"] if p["location"] == "body"]
    assert impl["http_template"]["steps"][0]["body_template"] == "{{payload}}"
    assert payload["type"] == "object"
    assert json.loads(payload["constraints"]["helper_text"].split("Source JSON Schema: ",1)[1]) == schema
    assert payload["required"] is True


BULK_DELETE = {"delete": {"operationId": "bulk_delete", "summary": "Delete several messages",
    "requestBody": {"required": True, "content": {"application/json": {
        "schema": {"type": "object", "properties": {"ids": {"type": "string"}}, "required": ["ids"]}}}},
    "responses": {"200": {"content": {"application/json": {
        "schema": {"type": "object", "properties": {"ok": {"type": "string"}}, "required": ["ok"]}}}}}}}


def test_an_operation_monarch_cannot_represent_is_excluded_and_reported(source, tmp_path):
    """One unrepresentable operation used to abort the whole product's catalogue.

    `_action` raised, nothing caught it, `monarch_setup` turned it into
    `Stop(2, "generate", ...)` and no seed file was written -- so a task set naming any
    of the four bodyless-body DELETEs in the real EnterpriseOps-Gym ITSM document could
    not set Monarch up on that product at all. Being unable to express one operation is
    not a reason to teach Monarch nothing.
    """
    product, tasks, doc, closed = source
    doc["paths"]["/messages/bulk"] = copy.deepcopy(BULK_DELETE)
    result = catalog.generate(product, tasks, tmp_path / "seeds", PUBLIC)
    out = tmp_path / "seeds"
    assert result.operations_in_spec == result.files_written == 1, "the representable operation is still taught"
    assert [(e["service"], e["method"], e["path"]) for e in result.excluded] == [("gmail", "delete", "/messages/bulk")]
    assert "bodyless" in result.excluded[0]["reason"]

    # The pack says what Monarch was not taught, and never advertises it either.
    assert json.loads((out / "ok.txt").read_text())["excluded_operations"] == result.excluded
    assert "/messages/bulk" not in (out / "source-contracts.yaml").read_text()


def test_a_catalogue_with_nothing_excluded_is_byte_for_byte_what_it_was(source, tmp_path):
    """The manifest gains the field only when there is something to report, so every
    pack frozen before this change still regenerates identically -- `generate` refuses
    to replace a frozen catalogue file, so a new key on every pack would break setup
    for anyone holding one."""
    product, tasks, doc, closed = source
    catalog.generate(product, tasks, tmp_path / "seeds", PUBLIC)
    manifest = json.loads((tmp_path / "seeds" / "ok.txt").read_text())
    assert "excluded_operations" not in manifest


def test_an_unrepresentable_operation_is_the_only_thing_excluded(source, tmp_path):
    """Excluding on any ValueError would hide real structural faults in a document."""
    product, tasks, doc, closed = source
    doc["paths"]["/messages/{message_id}"]["patch"]["servers"] = [{"url": "https://elsewhere.test"}]
    with pytest.raises(ValueError, match="server overrides"):
        catalog.generate(product, tasks, tmp_path / "seeds", PUBLIC)
