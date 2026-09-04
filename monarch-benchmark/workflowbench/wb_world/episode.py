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
from pathlib import Path
from typing import Any

from automationbench.runner import compute_allowed_services, strip_none_values
from automationbench.schema.world import WorldState
from automationbench.tools.api.fetch import api_fetch
from automationbench.tools.api.search import api_search
from automationbench.tools.api.encode import base64_encode


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
        self.snapshot0 = self.snapshot()

    # -- the three tools, closed over this episode's world -------------------
    def api_search(self, query: str, top_k: int = 5) -> str:
        self.tool_calls.append({"tool": "api_search", "query": query})
        return api_search(query, top_k)

    def api_fetch(self, method: str, url: str, params: str | None = None, body: str | None = None) -> str:
        self.tool_calls.append({"tool": "api_fetch", "method": method, "url": url})
        return api_fetch(self.world, method, url, params=params, body=body)

    def base64_encode(self, text: str) -> str:
        self.tool_calls.append({"tool": "base64_encode"})
        return base64_encode(text)

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
