"""The dual invariant over snapshot diffs.

Strict pass on the state side requires:
  1. every EXPECTED matcher matched at least one observed change, and
  2. every observed change is matched by an EXPECTED or ALLOWED matcher.

A matcher: {"service": str, "op": "added|removed|changed|*", "path": glob,
            "after_contains": optional substring of the post-value}
Kept deliberately small; grows only when a task needs it.
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
    return True


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
    return {
        "passed": not missing and not unexpected,
        "missing_expected": missing,
        "unexpected_changes": unexpected,
        "n_changes": len(changes),
    }
