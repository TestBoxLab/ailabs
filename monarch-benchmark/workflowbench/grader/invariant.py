"""The dual invariant over snapshot diffs.

Strict pass on the state side requires:
  1. every EXPECTED matcher matched at least one observed change, and
  2. every observed change is matched by an EXPECTED or ALLOWED matcher.

A matcher: {"service": str, "op": "added|removed|changed|*", "path": glob,
            "after_contains": optional substring of the post-value,
            "where": optional {dotted field: value} over the changed entry,
            "count": optional exact number of changes this matcher may match}
Kept deliberately small; grows only when a task needs it.

`where` and `count` exist for action-log services (airtable, jira, trello, ...),
where every write lands under one key and its id is minted during the run. A
frozen rule cannot name that id, so it names the write's content instead; `count`
then pins how many such writes were asked for. Doing the requested thing 201
times is not doing the requested thing.
"""
from __future__ import annotations

import re
from typing import Any


def _glob(pattern: str, path: str) -> bool:
    """'*' is the only wildcard; '[', ']' and '.' are literal (paths contain [id=...])."""
    rx = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$"
    return re.match(rx, path) is not None


def _matches(m: dict[str, Any], c: dict[str, Any]) -> bool:
    if m.get("service") not in ("*", None) and m["service"] != c["service"]:
        return False
    if m.get("op", "*") not in ("*", c["op"]):
        return False
    if not _glob(m.get("path", "*"), c["path"]):
        return False
    if "after_contains" in m:
        after = c.get("after")
        if not (isinstance(after, str) and m["after_contains"] in after):
            return False
    for field, want in (m.get("where") or {}).items():
        if _dig(c.get("after"), field) != want:
            return False
    return True


def _dig(value: Any, dotted: str) -> Any:
    """Walk 'params.fields.Status' into the changed entry; missing -> None."""
    for key in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def check_invariant(
    changes: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    allowed: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    allowed = allowed or []
    missing = [m for m in expected if not any(_matches(m, c) for c in changes)]
    unexpected = [
        c for c in changes
        if not any(_matches(m, c) for m in expected) and not any(_matches(m, c) for m in allowed)
    ]
    # A matcher that says how many writes it wants is violated by any other
    # number, so the right write repeated 201 times is not a pass.
    counted = [
        {"matcher": m, "want": m["count"], "got": n}
        for m in expected if "count" in m
        for n in [sum(1 for c in changes if _matches(m, c))] if n != m["count"]
    ]
    return {
        "passed": not missing and not unexpected and not counted,
        "missing_expected": missing,
        "unexpected_changes": unexpected,
        "count_violations": counted,
        "n_changes": len(changes),
    }
