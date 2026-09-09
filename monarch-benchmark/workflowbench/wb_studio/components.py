"""Trusted, versioned extension points. HTTP selects installed code; it never loads code."""
from dataclasses import dataclass
import hashlib
import inspect
from pathlib import Path

from grader.grade import grade
from wb_studio.agents import run_loop, episode_executor


@dataclass(frozen=True)
class Component:
    role: str
    id: str
    name: str
    implementation: object
    sha256: str


class Components:
    def __init__(self):
        self._items = {}
        self.defaults = {}
        self.register("brain", "agent-loop-v1", "Agent loop", run_loop, default=True)
        self.register("action_builder", "episode-tools-v1", "Episode tools", episode_executor, default=True)
        self.register("judge", "state-checks-v1", "Deterministic state checks", grade, default=True)

    def register(self, role, identity, name, implementation, *, default=False, sha256=None):
        if role not in ("brain", "action_builder", "judge") or not callable(implementation):
            raise ValueError("Invalid component role or implementation")
        if not isinstance(identity, str) or not identity or identity in self._items:
            raise ValueError("Component identities must be unique and nonempty")
        digest = sha256 or hashlib.sha256(Path(inspect.getsourcefile(implementation)).read_bytes()).hexdigest()
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("A component requires a SHA-256 code identity")
        self._items[identity] = Component(role, identity, name, implementation, digest)
        if default:
            self.defaults[role] = identity

    def pin(self, selection=None):
        if selection is None:
            selection = {}
        if not isinstance(selection, dict) or set(selection) - set(self.defaults):
            raise ValueError("Choose installed brain, action_builder and judge components")
        result = {}
        for role, default in self.defaults.items():
            identity = selection.get(role, default)
            item = self._items.get(identity) if isinstance(identity, str) else None
            if item is None or item.role != role:
                raise ValueError(f"Unknown {role} component")
            result[role] = {"id": item.id, "sha256": item.sha256}
        return result

    def resolve(self, pins, role):
        pin = pins[role]
        item = self._items.get(pin["id"])
        if item is None or item.role != role or item.sha256 != pin["sha256"]:
            raise ValueError(f"Pinned {role} implementation is unavailable or changed")
        return item.implementation

    def catalog(self):
        return {"defaults": dict(self.defaults), "items": [
            {"id": c.id, "role": c.role, "name": c.name, "sha256": c.sha256}
            for c in self._items.values()]}
