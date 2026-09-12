"""The world-adapter seam (feature 026, contracts/world-adapter.md).

A product under test names a world; the orchestrator builds that world for each
attempt. Until this feature the world was always AutomationBench, constructed
directly. These tests pin the contract that makes a second world possible, and the
first thing they check is that the contract is a name for what `Episode` already
does, not a new layer over it.

Everything here runs offline: no containers, no downloads, no network, no keys.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

from wb_world import adapter as adapter_mod
from wb_world import registry
from wb_world.episode import Episode, load_task_file

TASKS = Path(__file__).resolve().parents[1] / "tasks" / "tier-simple"


def a_task() -> dict:
    return load_task_file(sorted(TASKS.glob("*.json"))[0])


# --- the contract itself --------------------------------------------------------

def test_the_contract_names_what_an_attempt_already_needs():
    """The protocol was read from what the orchestrator demands, not invented.

    If this list grows, something asked the worlds for more than the machine
    needs, and the next adapter pays for it.
    """
    assert adapter_mod.REQUIRED_INSTANCE == (
        "api_search", "api_fetch", "base64_encode",
        "snapshot", "finish", "close",
        "attach_journal", "record_agent_event", "interfaces",
        "artifacts_dir", "snapshot0", "tool_calls", "events",
    )
    assert adapter_mod.REQUIRED_CLASS == ("prerequisites", "positive_check", "service_names")


def test_episode_satisfies_the_contract():
    missing = adapter_mod.unsatisfied(Episode)
    assert missing == [], f"Episode does not satisfy the world contract: {missing}"


def test_every_registered_world_satisfies_the_contract():
    for name in registry.known():
        missing = adapter_mod.unsatisfied(registry.resolve(name))
        assert missing == [], f"world {name!r} does not satisfy the contract: {missing}"


# --- the registry ---------------------------------------------------------------

def test_registry_resolves_the_automationbench_world():
    assert registry.resolve("automation-bench") is Episode


def test_registry_refuses_an_unknown_world_by_name():
    with pytest.raises(registry.UnknownWorld) as e:
        registry.resolve("no-such-world")
    assert "no-such-world" in str(e.value)
    assert "automation-bench" in str(e.value), "the refusal must say what is known"


def test_no_source_package_is_imported_at_start_up():
    """A missing source is a named refusal, never an ImportError at start-up.

    This is what keeps the offline suite runnable with none of the three external
    benchmarks installed.
    """
    for module in ("appworld", "tau2"):
        assert module not in sys.modules, f"{module} was imported merely by importing the registry"


def test_an_uninstalled_world_names_its_prerequisite_instead_of_raising():
    for name in registry.known():
        missing = registry.resolve(name).prerequisites()
        assert isinstance(missing, list)
        assert all(isinstance(m, str) and m for m in missing)


# --- the two class methods ------------------------------------------------------

def test_close_is_idempotent():
    ep = Episode(a_task(), episode_id="close-twice")
    ep.close()
    ep.close()


def test_positive_check_runs_after_the_attempt_from_stored_state():
    """It is a class method on purpose: grading happens later, out of process,
    from stored snapshots. Nothing grades itself."""
    task = a_task()
    ep = Episode(task, episode_id="positive")
    s0, s1 = ep.snapshot0, ep.finish()
    result = Episode.positive_check(task, s0, s1, artifacts=None)
    assert result.passed is False, "an untouched world cannot satisfy the task"
    assert result.source
    assert result.detail
    assert result.side_effects is None, "AutomationBench has no side-effect finding of its own"


def test_positive_check_needs_no_live_episode():
    """The attempt's world is gone by grading time; only the snapshots remain."""
    task = a_task()
    ep = Episode(task, episode_id="detached")
    s0, s1 = ep.snapshot0, ep.finish()
    ep.close()
    del ep
    assert Episode.positive_check(task, s0, s1, artifacts=None).source


# --- interfaces and the front door ----------------------------------------------

class _ToyWorld:
    """A world with two rows and one tool, used to prove the seam is not shaped
    around AutomationBench. It is the smallest thing that satisfies the contract."""

    services = ("notes",)

    # The contract's four values, declared on the class so it can be checked without
    # building a world. Every adapter does this; constructing an external one starts
    # a container.
    artifacts_dir = None
    snapshot0 = None
    tool_calls = ()
    events = ()

    def __init__(self, task=None, episode_id="toy", frozen_time=None):
        self.state = {"notes": {"rows": [{"id": 1, "text": "one"}]}}
        self.tool_calls: list = []
        self.events: list = []
        self.artifacts_dir = None
        self.snapshot0 = self.snapshot()

    def api_search(self, query, top_k=5):
        return json.dumps({"query": query})

    def api_fetch(self, method, url, params=None, body=None):
        self.tool_calls.append({"method": method, "url": url})
        if method == "POST":
            self.state["notes"]["rows"].append({"id": 2, "text": json.loads(body or "{}").get("text", "")})
        return json.dumps(self.state["notes"])

    def base64_encode(self, text):
        return text[::-1]

    def snapshot(self):
        return json.loads(json.dumps(self.state))

    def finish(self):
        self.snapshot1 = self.snapshot()
        return self.snapshot1

    def close(self):
        pass

    def attach_journal(self, directory):
        pass

    def record_agent_event(self, entry):
        self.events.append(entry)

    def interfaces(self):
        return adapter_mod.ToolInterfaces(
            {"notes": [{"name": "add_note", "description": "add one note",
                        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}}}]})

    @classmethod
    def prerequisites(cls):
        return []

    @classmethod
    def service_names(cls):
        return ["notes"]

    @classmethod
    def positive_check(cls, task, snapshot0, snapshot1, artifacts=None):
        return adapter_mod.PositiveResult(passed=True, detail={}, source="toy", side_effects=None)


def test_a_toy_world_satisfies_the_contract():
    assert adapter_mod.unsatisfied(_ToyWorld) == []


def test_the_front_door_serves_any_world_not_only_an_episode():
    from wb_arms.http_shim import EpisodeHTTPShim

    shim = EpisodeHTTPShim(_ToyWorld()).start()
    try:
        index = json.loads(urllib.request.urlopen(f"{shim.url}/openapi/index.json").read())
        assert "notes" in index
        spec = json.loads(urllib.request.urlopen(f"{shim.url}/openapi/notes.json").read())
        assert spec["openapi"].startswith("3.")
        assert "/notes/add_note" in spec["paths"]
    finally:
        shim.stop()


def test_a_tool_becomes_an_operation_under_its_own_name():
    """A tool that is not a REST resource is published as POST /{service}/{tool},
    with its own input schema as the body. No guessed resource paths: a tool called
    `create_incident` is an operation called `create_incident`, not POST /incidents.
    """
    from wb_world.tools_openapi import build_tool_spec

    spec = build_tool_spec(
        "itsm",
        [{"name": "create_incident", "description": "open an incident",
          "input_schema": {"type": "object", "properties": {"title": {"type": "string"}},
                           "required": ["title"]}}],
        "http://example.test")
    op = spec["paths"]["/itsm/create_incident"]["post"]
    assert op["operationId"] == "create_incident"
    assert op["description"] == "open an incident"
    assert op["requestBody"]["content"]["application/json"]["schema"]["required"] == ["title"]
    assert spec["servers"][0]["url"] == "http://example.test"
    assert "/incidents" not in json.dumps(spec["paths"]), "no resource path may be invented"


def test_the_front_door_dispatches_into_this_attempts_own_world():
    from wb_arms.http_shim import EpisodeHTTPShim

    world = _ToyWorld()
    shim = EpisodeHTTPShim(world).start()
    try:
        req = urllib.request.Request(f"{shim.url}/notes/add_note", method="POST",
                                     data=json.dumps({"text": "two"}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req).read()
    finally:
        shim.stop()
    assert [r["text"] for r in world.state["notes"]["rows"]] == ["one", "two"]
    assert world.tool_calls, "the call must reach the world through its own tools"
