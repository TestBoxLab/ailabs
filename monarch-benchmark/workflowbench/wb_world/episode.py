"""Episode lifecycle: seed a fresh AutomationBench WorldState per episode.

Design ref: T0-INGESTION-SPEC.md (Deliverable 1, 4).
- fresh WorldState from the task fixture (same seeding path the AB runner uses)
- frozen clock via WorldMeta.current_time
- service gating via WorldMeta.allowed_services (built into api_fetch upstream)
- snapshot() = canonical model dump, taken at episode start and end
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from automationbench.runner import compute_allowed_services, strip_none_values
from automationbench.schema.world import WorldState
from automationbench.tools.api.fetch import api_fetch
from automationbench.tools.api.search import api_search
from automationbench.tools.api.encode import base64_encode


class EvidenceWriteError(OSError):
    """Durable recording failed, distinct from an application's tool I/O error."""


class Episode:
    """One arm attempt on one task, over its own private world."""

    def __init__(self, task: dict[str, Any], episode_id: str, frozen_time: str | None = None):
        info = task["info"]
        initial = strip_none_values(copy.deepcopy(info.get("initial_state", {})))
        self.task = task
        self.episode_id = episode_id
        self.world = WorldState(**initial)
        self.world.meta.allowed_services = compute_allowed_services(
            info.get("initial_state", {}), info.get("assertions", []), info.get("zapier_tools", [])
        )
        # Frozen clock: explicit arg > latest date in fixture > fixed default.
        self.world.meta.current_time = _resolve_clock(frozen_time, initial)
        self.tool_calls: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self._journal = None
        self.snapshot0 = self.snapshot()

    def attach_journal(self, directory: str | Path) -> None:
        """Begin durable observations before arm.run, in a new attempt directory.

        A recovered snapshot is only the last completed tool observation; a
        crash in a later action may have changed state that was never observed.
        Journal I/O failures propagate so recording cannot silently disappear.
        """
        if self._journal is not None or self.events:
            raise RuntimeError("attach the journal before any tool use and only once")
        from wb_results.evidence import AttemptJournal
        self._journal = AttemptJournal(Path(directory), self.snapshot0)

    def record_agent_event(self, entry: dict) -> None:
        """Persist an observed request/response/error supplied by the harness.

        Unattached episodes keep their existing in-memory behavior. The caller
        remains responsible for excluding credentials and hidden reasoning.
        """
        if self._journal is not None:
            try:
                self._journal.agent(entry)
            except OSError as exc:
                raise EvidenceWriteError(f"agent journal write failed: {exc}") from exc

    def _record_tool_event(self, event: dict, snapshot=None) -> None:
        try:
            self._journal.tool(event, snapshot)
        except OSError as exc:
            raise EvidenceWriteError(f"tool journal write failed: {exc}") from exc

    # -- the three tools, closed over this episode's world -------------------
    def api_search(self, query: str, top_k: int = 5) -> str:
        self.tool_calls.append({"tool": "api_search", "query": query})
        return self._observe("api_search", {"query": query, "top_k": top_k},
                             lambda: api_search(query, top_k))

    def api_fetch(self, method: str, url: str, params: str | None = None, body: str | None = None) -> str:
        self.tool_calls.append({"tool": "api_fetch", "method": method, "url": url})
        return self._observe("api_fetch", {"method": method, "url": url, "params": params, "body": body},
                             lambda: api_fetch(self.world, method, url, params=params, body=body))

    def base64_encode(self, text: str) -> str:
        self.tool_calls.append({"tool": "base64_encode"})
        return self._observe("base64_encode", {"text": text}, lambda: base64_encode(text))

    def _observe(self, tool: str, arguments: dict, call):
        event = {"sequence": len(self.events), "kind": "tool", "tool": tool,
                 "arguments": copy.deepcopy(arguments),
                 "started_at": datetime.now(timezone.utc).isoformat()}
        self.events.append(event)
        if self._journal is not None:
            self._record_tool_event({**event, "status": "running"})
        try:
            value = call()
            event.update(status="completed", result=value)
            return value
        except Exception as exc:
            event.update(status="error", error=str(exc))
            raise
        finally:
            event["finished_at"] = datetime.now(timezone.utc).isoformat()
            if self._journal is not None and event.get("status") in ("completed", "error"):
                self._record_tool_event(event, self.snapshot if event["status"] == "completed" else None)

    # -- snapshots ------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return self.world.model_dump(mode="json")

    def finish(self) -> dict[str, Any]:
        self.snapshot1 = self.snapshot()
        return self.snapshot1


def _resolve_clock(frozen_time: str | None, initial: dict[str, Any]) -> datetime:
    if frozen_time:
        return datetime.fromisoformat(frozen_time.replace("Z", "+00:00"))
    latest: datetime | None = None
    def walk(o):
        nonlocal latest
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and len(o) >= 20 and o[4:5] == "-" and o.endswith("Z"):
            try:
                d = datetime.fromisoformat(o.replace("Z", "+00:00"))
                latest = d if latest is None or d > latest else latest
            except ValueError:
                pass
    walk(initial)
    return latest or datetime(2026, 1, 1, tzinfo=timezone.utc)


def load_task_file(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


@lru_cache(maxsize=1)
def _default_world() -> dict[str, Any]:
    """Every service's state in a world nobody seeded, as a task file spells it."""
    return strip_none_values(WorldState().model_dump(mode="json"))


def seeded_services(initial_state: dict[str, Any]) -> list[str]:
    """The services a task's starting data says something about.

    The upstream world left out every service the task did not seed. The
    repaired world (1.0.6+evalrepair.10) writes every service's empty default
    into `initial_state` instead, so "which keys are present" stopped meaning
    "which apps hold data": all 48 are present in every scored task. A service
    counts as seeded when its state differs from the world's own default;
    `meta` is the world's header, never a service.
    """
    defaults = _default_world()
    return [k for k, v in initial_state.items()
            if k != "meta" and strip_none_values(v) != defaults.get(k)]


def load_suite(suite_dir: str | Path) -> list[dict]:
    paths = sorted(Path(suite_dir).glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no task files in {suite_dir}")
    return [load_task_file(p) for p in paths]


# Labels that say which drawn set a copy sits in, not what the work is. They are
# excluded so a drawn copy keeps its corpus original's hash and stays the same
# task under the same approval rule (feature 005, data-model.md section 8).
# ponytail: two ignored keys, not a metadata sidecar; every future label goes
# here deliberately.
_HASH_IGNORED_INFO_KEYS = ("tier", "domain")


def contract_hash(task: dict) -> str:
    info = task.get("info")
    if isinstance(info, dict):
        info = {k: v for k, v in info.items() if k not in _HASH_IGNORED_INFO_KEYS}
    blob = json.dumps({"task": task.get("task"), "prompt": task.get("prompt"),
                       "info": info}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# --- the world a task set was imported under ------------------------------------
#
# The world is the vendored AutomationBench package. When it changes, the tasks
# change with it (the repaired 1.0.6+evalrepair.10 moved every scored task's
# starting data), so a corpus is imported once per world revision and every
# task imported that way carries `info.world`: the package, its version and the
# revision label. The block is hashed, so a task under a new world is a new
# contract; it decides the suite id every row records, so results never pool
# across worlds; and `config.resolve` refuses a set whose world is not the one
# installed. A set that records no world was imported when the only world was
# upstream 1.0.6, and is treated as that world.

WORLD_PACKAGE = "automation-bench"
UPSTREAM_WORLD_VERSION = "1.0.6"          # what every unrecorded set ran on
SUITE_NAME = "workflowbench-synthetic"
LEGACY_SUITE = "workflowbench-synthetic@0.1"   # the label every stored row has today


def installed_world_version() -> str:
    """The version of the vendored AutomationBench package this environment runs."""
    from importlib.metadata import version
    return version(WORLD_PACKAGE)


def world_block(revision: str, version: str | None = None) -> dict[str, str]:
    """What an imported task records about its world."""
    return {"package": WORLD_PACKAGE, "version": version or installed_world_version(),
            "revision": revision}


def world_of(task: dict[str, Any]) -> dict[str, Any] | None:
    info = task.get("info")
    world = info.get("world") if isinstance(info, dict) else None
    return world if isinstance(world, dict) else None


def recorded_world_version(tasks: list[dict[str, Any]]) -> str:
    """The one world version a task set records; UPSTREAM_WORLD_VERSION when it
    records none. A set that mixes worlds is refused, naming the versions and
    the tasks under each."""
    by_version: dict[str, list[str]] = {}
    for t in tasks:
        world = world_of(t)
        version = str(world["version"]) if world and world.get("version") else UPSTREAM_WORLD_VERSION
        by_version.setdefault(version, []).append(str(t.get("task")))
    if len(by_version) > 1:
        detail = "; ".join(
            f"{WORLD_PACKAGE} {v}: {', '.join(ids[:5])}{', ...' if len(ids) > 5 else ''}"
            for v, ids in sorted(by_version.items()))
        raise ValueError(f"the task set mixes worlds ({detail}); a set runs on one world")
    return next(iter(by_version), UPSTREAM_WORLD_VERSION)


def suite_id(tasks: list[dict[str, Any]]) -> str:
    """The suite every row of a round on `tasks` records: the legacy label for a
    set that records no world, `workflowbench-synthetic@<version>` otherwise."""
    version = recorded_world_version(tasks)
    return LEGACY_SUITE if version == UPSTREAM_WORLD_VERSION else f"{SUITE_NAME}@{version}"
