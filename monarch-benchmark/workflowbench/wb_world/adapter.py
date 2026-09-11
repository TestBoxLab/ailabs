"""The world-adapter contract (feature 026, contracts/world-adapter.md).

A product under test names a world; each attempt gets its own instance of it. The
list below was *read from what the orchestrator and the arms already demand of an
episode*, not designed fresh -- which is why `wb_world.episode.Episode` satisfies it
today with no behavioural change and becomes the AutomationBench implementation by
declaration.

Keep REQUIRED_INSTANCE short. Every name in it is a thing the next world has to
implement, and a contract that grows to fit one source stops being a seam.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# What an attempt uses. Methods, then the four values the orchestrator reads.
REQUIRED_INSTANCE = (
    "api_search", "api_fetch", "base64_encode",
    "snapshot", "finish", "close",
    "attach_journal", "record_agent_event", "interfaces",
    "artifacts_dir", "snapshot0", "tool_calls", "events",
)

# What grading uses, later and out of process. Class methods on purpose: the
# attempt's world is gone by then, and it must be, or something would be grading
# itself.
REQUIRED_CLASS = ("prerequisites", "positive_check", "service_names")


@dataclass
class PositiveResult:
    """One source's own answer to "is the expected result present?".

    `detail` is whatever the source returned, kept whole and not summarized -- a
    report that cannot show why a check failed is a report nobody trusts.
    `side_effects` is the source's own collateral finding where it has one (AppWorld
    does); it is recorded *beside* the lab's approval rule, never merged into it.
    """
    passed: bool
    detail: Any
    source: str
    side_effects: Any | None = None


def unsatisfied(world: type) -> list[str]:
    """Names of the contract this class does not provide, in contract order.

    The four data attributes are checked on the class, so every world declares them
    as class-level defaults and rebinds them in `__init__`. That makes the contract
    checkable without constructing a world, which matters: constructing an
    EnterpriseOps-Gym world starts a container.
    """
    return [name for name in REQUIRED_INSTANCE + REQUIRED_CLASS if not hasattr(world, name)]


# --- what the front door needs from a world's published surface ------------------
#
# Three questions, one object: which services exist, what is the interface document
# for one of them, and what URL does a REST path map to inside this world. The
# AutomationBench implementation wraps its own schemas (`SchemaInterfaces` in
# wb_world/openapi.py); a world whose surface is a list of tools uses ToolInterfaces.


class ToolInterfaces:
    """A world whose surface is tools rather than REST resources.

    EnterpriseOps-Gym has 512 tools over MCP; tau2 has Python functions per domain.
    Each becomes `POST /{service}/{tool_name}` with the tool's own input schema as
    the request body -- its real name, never a guessed resource path. A tool called
    `create_incident` is an operation called `create_incident`, because inventing
    `POST /incidents` would describe an interface the world does not have.
    """

    def __init__(self, tools_by_service: dict[str, list[dict[str, Any]]]):
        self.tools_by_service = tools_by_service

    def services(self) -> list[str]:
        return list(self.tools_by_service)

    def spec(self, service: str, public_url: str) -> dict[str, Any]:
        from wb_world.tools_openapi import build_tool_spec
        return build_tool_spec(service, self.tools_by_service[service], public_url)

    def rest_url(self, service: str, rest: str) -> str:
        return f"/{service}/{rest}"


@dataclass
class Journal:
    """The no-op journal a world uses until one is attached. Saves every adapter
    from writing the same `if self._journal is not None` twice."""
    events: list = field(default_factory=list)

    def agent(self, entry: dict) -> None:
        self.events.append(entry)

    def tool(self, event: dict, snapshot=None) -> None:
        self.events.append(event)


def canonical(state: Any) -> Any:
    """A snapshot that survives a round trip through a file, with stable ordering.

    Two dumps of an untouched world must be identical, or every re-dump would read
    as collateral damage. Adapters that build a snapshot out of database rows sort
    them before calling this.
    """
    return json.loads(json.dumps(state, sort_keys=True, default=str))
