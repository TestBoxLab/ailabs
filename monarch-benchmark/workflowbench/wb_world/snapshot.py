"""Snapshot diffing: turn (snapshot0, snapshot1) into a flat list of changes.

A change record: {"service", "op": added|removed|changed, "path", "before", "after"}
Paths are dotted, list items addressed by a stable identity key (id if present,
else index). meta.* is excluded — it is harness state, not world state.
"""
from __future__ import annotations

from typing import Any

IGNORE_FIELDS = {"created_at", "updated_at", "modified_at", "last_modified_date", "system_modstamp"}  # housekeeping autofields (design: whole-state ignore-list, kept short and explicit)


def diff_snapshots(s0: dict[str, Any], s1: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    services = (set(s0) | set(s1)) - {"meta"}
    for svc in sorted(services):
        _walk(svc, s0.get(svc), s1.get(svc), svc, changes)
    return changes


def _identity(item: Any, idx: int) -> str:
    # A null id is not an identity: the AutomationBench fixtures give every
    # Slack message `id: None`, and keying them all as `[id=None]` collapses the
    # list onto one entry, so an added record reads as edits to the first one.
    if isinstance(item, dict) and item.get("id") is not None:
        return f"[id={item['id']}]"
    return f"[{idx}]"


def _walk(svc: str, a: Any, b: Any, path: str, out: list) -> None:
    if a == b:
        return
    leaf = path.rsplit(".", 1)[-1]
    if leaf in IGNORE_FIELDS:
        return
    # An added or removed subtree is walked against an empty one of its own kind:
    # action-log services keep every write under one key, so collapsing a new key
    # into a single "<object>" change would hide the writes inside it.
    if isinstance(a, (dict, list)) and b in (None, [], {}):
        b = type(a)()
    elif isinstance(b, (dict, list)) and a in (None, [], {}):
        a = type(b)()
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            _walk(svc, a.get(k), b.get(k), f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        amap = {_identity(x, i): x for i, x in enumerate(a)}
        bmap = {_identity(x, i): x for i, x in enumerate(b)}
        for key in sorted(set(amap) | set(bmap)):
            pa, pb = amap.get(key), bmap.get(key)
            p = f"{path}{key}"
            if pa is None:
                out.append({"service": svc, "op": "added", "path": p, "before": None, "after": _brief(pb)})
            elif pb is None:
                out.append({"service": svc, "op": "removed", "path": p, "before": _brief(pa), "after": None})
            else:
                _walk(svc, pa, pb, p, out)
    else:
        op = "added" if a in (None, [], {}) else ("removed" if b in (None, [], {}) else "changed")
        out.append({"service": svc, "op": op, "path": path, "before": _brief(a), "after": _brief(b)})


def _brief(v: Any, limit: int = 400) -> Any:
    # An added/removed entry keeps its own content: the collateral judge matches
    # a write by what it says (`where`), because an action-log id is minted
    # during the run and no frozen rule can name it.
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str) and len(v) > limit:
        return v[:limit] + "…"
    return v
