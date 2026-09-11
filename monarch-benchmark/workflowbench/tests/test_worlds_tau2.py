import json

import pytest

from wb_world.adapter import unsatisfied
from wb_worlds.tau2.adapter import Tau2World
from wb_worlds.tau2.server import WorldService


class Engine:
    def create(self, task):
        return {"value": 0, "domain": task["domain"], "messages": []}

    def describe(self, env):
        return {"domain": env["domain"], "tools": [{"name": "set_value", "parameters": {"type": "object"}}], "policy": "policy"}

    def snapshot(self, env):
        return {"tau2-retail": {"records": {"one": {"value": env["value"]}}}}

    def call(self, env, tool, args, requestor="assistant"):
        env["value"] = args["value"]
        env["messages"].append({"role": requestor, "tool": tool, "arguments": args})
        return json.dumps({"value": env["value"]})

    def evidence(self, env):
        return {"messages": env["messages"], "snapshot1": self.snapshot(env)}


def test_tau2_contract_and_private_worlds_even_when_attempt_id_repeats():
    assert unsatisfied(Tau2World) == []
    service = WorldService(Engine())
    first = service.dispatch("/create", {"domain": "retail", "episode_id": "same"})
    second = service.dispatch("/create", {"domain": "retail", "episode_id": "same"})
    assert first["id"] != second["id"]
    service.dispatch("/call", {"id": first["id"], "tool": "set_value", "arguments": {"value": 7}})
    assert service.dispatch("/snapshot", {"id": first["id"]}) == {"tau2-retail": {"records": {"one": {"value": 7}}}}
    assert service.dispatch("/snapshot", {"id": second["id"]}) == {"tau2-retail": {"records": {"one": {"value": 0}}}}
    service.dispatch("/close", {"id": first["id"]})
    service.dispatch("/close", {"id": first["id"]})
    with pytest.raises(KeyError):
        service.dispatch("/snapshot", {"id": first["id"]})


@pytest.fixture
def world(monkeypatch):
    service = WorldService(Engine())
    monkeypatch.setattr(Tau2World, "_request", lambda self, path, body: service.dispatch(path, body))
    return Tau2World({"source_ref": {"domain": "retail", "task": {"id": "1"}}}, "attempt")


def test_adapter_publishes_only_domain_tools_and_retains_actual_evidence(world, tmp_path):
    world.artifacts_dir = tmp_path
    assert world.interfaces().services() == ["tau2-retail"]
    spec = world.interfaces().spec("tau2-retail", "http://public.test")
    assert set(spec["paths"]) == {"/tau2-retail/set_value", "/tau2-retail/send_message"}
    assert json.loads(world.api_fetch("POST", "/admin/snapshot", body="{}"))["error"]["code"] == 403
    assert json.loads(world.api_fetch("POST", "/tau2-retail/set_value", body='{"value": 4}')) == {"value": 4}
    result = world.finish()
    evidence = json.loads((tmp_path / "tau2-trajectory.json").read_text())
    assert evidence["messages"] == [{"role": "assistant", "tool": "set_value", "arguments": {"value": 4}}]
    assert evidence["snapshot1"] == result


def test_customer_calls_are_refused_without_budget_callback(world):
    with pytest.raises(RuntimeError, match="budgeted"):
        world.send_message("Hello")


def test_invalid_competitor_json_returns_a_tool_error(world):
    result = world.api_fetch("POST", "/tau2-retail/set_value", body="{bad")
    assert json.loads(result)["error"]["code"] == 400
    assert world.snapshot()["tau2-retail"]["records"]["one"]["value"] == 0
