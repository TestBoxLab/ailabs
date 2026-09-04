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
    "point falling in the lower tier. The random set is drawn from the whole "
    "usable corpus except the tasks already drawn into the three tiers, so it "
    "is an independent check of the blended average."
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


# --- the draw -----------------------------------------------------------------

@dataclass
class DrawResult:
    cuts: dict[str, int]
    scored: int
    usable: int
    excluded: dict[str, str]
    sets: dict[str, list[str]]
    by_domain: dict[str, dict[str, int]]
    written: list[Path]


def draw_tier(candidates: list[Entry], per_tier: int, rng: random.Random) -> list[Entry]:
    """Round-robin over the tier's domains, alphabetical, one candidate each pass.

    # ponytail: round-robin, not proportional allocation; with ten slots
    # proportional is mostly rounding rules.
    """
    by_domain: dict[str, list[Entry]] = {}
    for e in sorted(candidates, key=lambda e: e.task_id):
        by_domain.setdefault(e.domain, []).append(e)
    for lst in by_domain.values():
        rng.shuffle(lst)                      # sorted first, so input order cannot matter

    picked: list[Entry] = []
    while len(picked) < per_tier:
        took = False
        for domain in sorted(by_domain):
            if len(picked) == per_tier:
                break
            if by_domain[domain]:
                picked.append(by_domain[domain].pop())
                took = True
        if not took:
            break                             # every domain is empty; the caller refuses
    return picked


def _write_task(entry: Entry, tier_label: str, folder: Path) -> Path:
    """A byte copy of the corpus file plus info.tier and info.domain (§4)."""
    task = load_task_file(entry.path)
    task["info"]["tier"] = tier_label
    task["info"]["domain"] = entry.domain
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / entry.path.name
    path.write_text(json.dumps(task, indent=1, sort_keys=True) + "\n", newline="\n")
    return path


def draw(dirs: Iterable[str | Path], seed: int, per_tier: int = 10,
         out: str | Path = "tasks") -> DrawResult:
    """Four frozen task sets and a manifest, byte-reproducible from the seed (§9)."""
    pool = load_corpus(dirs)
    cuts = tier_cuts(e.score for e in pool.entries)
    entries = [Entry(e.task_id, e.domain, e.score, e.contract_sha256, e.path,
                     tier_of(e.score, cuts)) for e in pool.entries]

    # refuse before anything is written
    for tier in TIER_ORDER:
        n = sum(e.tier == tier for e in entries)
        if n < per_tier:
            raise ValueError(f"tier {tier} has {n} usable tasks, fewer than the "
                             f"{per_tier} the draw needs; nothing written")

    rng = random.Random(seed)                 # one generator, fixed consumption order
    drawn: dict[str, list[Entry]] = {}
    for tier in TIER_ORDER:
        drawn[f"tier-{tier}"] = draw_tier([e for e in entries if e.tier == tier],
                                          per_tier, rng)

    # The random set is an independent check of the blended average, so it draws
    # from what the three tiers left behind (decision of 4 Sep 2026, Carlos).
    taken = {e.task_id for picked in drawn.values() for e in picked}
    rest = sorted((e for e in entries if e.task_id not in taken),
                  key=lambda e: e.task_id)
    if len(rest) < per_tier:
        raise ValueError(f"the random set has {len(rest)} usable tasks left after the "
                         f"three tiers, fewer than the {per_tier} the draw needs; "
                         f"nothing written")
    drawn["random-10"] = rng.sample(rest, per_tier)

    out = Path(out)
    written: list[Path] = []
    by_domain: dict[str, dict[str, int]] = {}
    for set_name, picked in drawn.items():
        label = "random" if set_name == "random-10" else set_name.split("-", 1)[1]
        counts: dict[str, int] = {}
        for e in sorted(picked, key=lambda e: e.task_id):
            written.append(_write_task(e, label, out / set_name))
            counts[e.domain] = counts.get(e.domain, 0) + 1
        by_domain[set_name] = dict(sorted(counts.items()))

    written.append(_write_manifest(out, pool, cuts, seed, per_tier, drawn, by_domain))
    return DrawResult(cuts=cuts, scored=len(entries), usable=len(entries),
                      excluded=pool.excluded,
                      sets={k: [e.task_id for e in sorted(v, key=lambda e: e.task_id)]
                            for k, v in drawn.items()},
                      by_domain=by_domain, written=written)


def _write_manifest(out: Path, pool: Pool, cuts: dict[str, int], seed: int,
                    per_tier: int, drawn: dict[str, list[Entry]],
                    by_domain: dict[str, dict[str, int]]) -> Path:
    import datetime

    import yaml
    manifest = {
        "measure": MEASURE,
        "generated_at": datetime.datetime.now(datetime.UTC)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "per_tier": per_tier,
        "cuts": cuts,
        "corpus": [{"dir": d.as_posix(),
                    "domain": d.name.split("imported-", 1)[-1],
                    "tasks": pool.counts[d.name.split("imported-", 1)[-1]][0],
                    "usable": pool.counts[d.name.split("imported-", 1)[-1]][1]}
                   for d in pool.dirs],
        "excluded": dict(sorted(pool.excluded.items())),
        "sets": {name: {
            "by_domain": by_domain[name],
            # the row's tier is always the tier the score falls in, even in
            # random-10 whose files carry the literal label "random".
            "tasks": [{"task": e.task_id, "domain": e.domain, "score": e.score,
                       "tier": e.tier, "contract_sha256": e.contract_sha256}
                      for e in sorted(drawn[name], key=lambda e: e.task_id)],
        } for name in SET_NAMES},
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / "tiers-manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True,
                                   default_flow_style=False), newline="\n")
    return path
