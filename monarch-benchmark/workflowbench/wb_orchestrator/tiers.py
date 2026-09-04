"""Feature 005: classify the corpus by difficulty and draw frozen task sets.

The measure, the cut points and the draw are all defined here, and all of them
are computed from the task files alone: no key, no network, no model call.
See specs/005-task-tiers/data-model.md for the rules this file implements.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from wb_world.episode import contract_hash, load_task_file

SET_NAMES = ("tier-simple", "tier-medium", "tier-complex", "random-10")
TIER_ORDER = ("simple", "medium", "complex")
MEASURE = (
    'services seeded (initial_state keys except "meta") + expected changes '
    "(info.expected_changes) + tools needed (info.zapier_tools), computed from "
    "the task file; tiers are the terciles of the whole corpus, ties on a cut "
    "point falling in the lower tier."
)


# --- the measure --------------------------------------------------------------

def score_task(task: dict[str, Any]) -> int:
    """services seeded + expected changes + tools needed (data-model.md §2)."""
    info = task.get("info", {})
    services = [k for k in info.get("initial_state", {}) if k != "meta"]
    return (len(services)
            + len(info.get("expected_changes", []))
            + len(info.get("zapier_tools", [])))


def tier_cuts(scores: Iterable[int]) -> dict[str, int]:
    """The two values that split the sorted scores into three parts (§3)."""
    s = sorted(scores)
    if not s:
        raise ValueError("no scores to cut")
    # the last value of the first third and of the second third; a tie on a cut
    # point falls in the lower tier by tier_of's comparison, never a coin flip.
    n = len(s)
    return {"low": s[max(n // 3 - 1, 0)], "high": s[max(2 * n // 3 - 1, 0)]}


def tier_of(score: int, cuts: dict[str, int]) -> str:
    """simple at and below low, complex strictly above high, medium between."""
    if score <= cuts["low"]:
        return "simple"
    if score > cuts["high"]:
        return "complex"
    return "medium"


# --- the pool -----------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    task_id: str
    domain: str
    score: int
    contract_sha256: str
    path: Path
    tier: str = ""


@dataclass
class Pool:
    entries: list[Entry] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)
    counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    dirs: list[Path] = field(default_factory=list)


def _unmapped_types(task: dict[str, Any]) -> list[str]:
    from wb_orchestrator import declare
    try:
        return declare.derive(task, declare.default_side_effects())["unmapped"]
    except Exception:                      # a shape the derivation cannot read at all
        return sorted({a.get("type", "?") for a in task["info"].get("assertions", [])})


def load_corpus(dirs: Iterable[str | Path]) -> Pool:
    """Score every corpus task; exclude and name the ones that cannot be drawn.

    The two checks are exactly the two `validate_corpus` already performs: a task
    needs a non-empty approval rule, and its embedded hash must match its content
    (research R9).
    """
    pool = Pool()
    for d in [Path(x) for x in dirs]:
        domain = d.name.split("imported-", 1)[-1]
        paths = sorted(d.glob("*.json"))
        if not paths:
            raise FileNotFoundError(f"no task files in {d}")
        usable = 0
        for p in paths:
            task = load_task_file(p)
            task_id = task.get("task", p.stem)
            if not task["info"].get("expected_changes"):
                pool.excluded[task_id] = (
                    f"no approval rule (unmapped assertion types: {_unmapped_types(task)})")
                continue
            if task.get("contract_sha256") != contract_hash(task):
                pool.excluded[task_id] = "contract hash does not match content"
                continue
            pool.entries.append(Entry(task_id, domain, score_task(task),
                                      task["contract_sha256"], p))
            usable += 1
        pool.counts[domain] = (len(paths), usable)
        pool.dirs.append(d)
    return pool
