"""Feature 005: classify the corpus by difficulty and draw frozen task sets.

The measure, the cut points and the draw are all defined here, and all of them
are computed from the task files alone: no key, no network, no model call.
See specs/005-task-tiers/data-model.md for the rules this file implements.
"""
from __future__ import annotations

import datetime
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from wb_orchestrator import declare
from wb_world.episode import (WORLD_PACKAGE, contract_hash, load_task_file,
                              recorded_world_version, seeded_services)

SET_NAMES = ("tier-simple", "tier-medium", "tier-complex", "random-10")
TIER_ORDER = ("simple", "medium", "complex")
MEASURE = (
    "services seeded (initial_state services whose starting data is not the "
    'world\'s own empty default; "meta" never counts) + expected changes '
    "(info.expected_changes) + tools needed (info.zapier_tools), computed from "
    "the task file; tiers are the terciles of the whole corpus, ties on a cut "
    "point falling in the lower tier. The random set is drawn from the whole "
    "usable corpus except the tasks already drawn into the three tiers, so it "
    "is an independent check of the blended average."
)


# --- the measure --------------------------------------------------------------

def score_task(task: dict[str, Any]) -> int:
    """services seeded + expected changes + tools needed (data-model.md §2).

    Seeded means the task's data says something about the service. Under the
    repaired world every scored task lists all 48 apps' empty defaults, so
    counting keys would give every one of them 48 and the measure would say
    nothing (unblock plan M1, 8 Sep 2026); an empty default is not a seed.
    """
    info = task.get("info", {})
    services = seeded_services(info.get("initial_state", {}))
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
    low, high = s[max(n // 3 - 1, 0)], s[max(2 * n // 3 - 1, 0)]
    if low == high:
        # Every task would land in one or two tiers and the draw would then refuse
        # for a reason that hides this one. Say what is actually wrong.
        raise ValueError(f"scores are too concentrated to split into three tiers "
                         f"(both cuts land on {low})")
    return {"low": low, "high": high}


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


@dataclass(frozen=True)
class Folder:
    """One corpus folder, counted by the single scan `load_corpus` performs."""
    path: Path
    domain: str
    tasks: int
    usable: int


@dataclass
class Pool:
    entries: list[Entry] = field(default_factory=list)
    # task id -> (reason code, detail); codes are NO_RULE and DRIFT, so a caller
    # counts by reason without parsing the sentence a reader sees.
    excluded: dict[str, tuple[str, str]] = field(default_factory=dict)
    folders: list[Folder] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(f.tasks for f in self.folders)


NO_RULE, DRIFT = "no_rule", "drift"


def excluded_reason(code: str, detail: str) -> str:
    """The sentence a reader sees for an exclusion code."""
    if code == NO_RULE:
        return f"no approval rule ({detail})"
    return "contract hash does not match content"


def _unmapped_types(task: dict[str, Any]) -> list[str]:
    try:
        return declare.derive(task, declare.default_side_effects())["unmapped"]
    except KeyError:                       # an assertion without the "type" key
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
        if any(f.domain == domain for f in pool.folders):
            raise ValueError(f"two corpus folders reduce to the domain {domain!r}: "
                             f"{[str(f.path) for f in pool.folders if f.domain == domain]} "
                             f"and {d}; one of them would be lost")
        paths = sorted(d.glob("*.json"))
        if not paths:
            raise FileNotFoundError(f"no task files in {d}")
        usable = 0
        for p in paths:
            task = load_task_file(p)
            task_id = task.get("task", p.stem)
            if not task["info"].get("expected_changes"):
                pool.excluded[task_id] = (
                    NO_RULE, f"unmapped assertion types: {_unmapped_types(task)}")
                continue
            if task.get("contract_sha256") != contract_hash(task):
                pool.excluded[task_id] = (DRIFT, "")
                continue
            pool.entries.append(Entry(task_id, domain, score_task(task),
                                      task["contract_sha256"], p))
            usable += 1
        pool.folders.append(Folder(d, domain, len(paths), usable))
    return pool


# --- the draw -----------------------------------------------------------------

@dataclass
class DrawResult:
    cuts: dict[str, int]
    total: int                 # every task read, exclusions included
    usable: int
    excluded: dict[str, str]
    folders: list[Folder]
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
    """An exact copy of the task plus the two labels (§4).

    Re-serialised with sorted keys and a trailing newline rather than copied byte
    for byte, so the same seed writes the same bytes whatever the original's
    formatting was. Every value is carried over untouched, and the hash ignores
    the two labels, so the copy keeps its original's contract_sha256.
    """
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
    return DrawResult(cuts=cuts, total=pool.total, usable=len(entries),
                      excluded=pool.excluded, folders=pool.folders,
                      sets={k: [e.task_id for e in sorted(v, key=lambda e: e.task_id)]
                            for k, v in drawn.items()},
                      by_domain=by_domain, written=written)


DEFAULT_REFREEZE_REASON = (
    "an approval-rule change rewrote every task's hash; the drawn ids are unchanged")


def refreeze(dirs: Iterable[str | Path], out: str | Path = "tasks",
             because: str = DEFAULT_REFREEZE_REASON) -> DrawResult:
    """Rewrite the four sets from the corpus without drawing again.

    An approval-rule change rewrites every corpus task's hash, which leaves the
    frozen copies under `tasks/` stale. Redrawing is the wrong repair: a rule
    fix also changes which tasks are usable, so the same seed over a different
    pool picks a different ten and the round sheets stop describing the sets
    that ran. Refreezing keeps the ids the draw chose and refreshes only their
    content, their hashes and the manifest.
    """
    out = Path(out)
    manifest_path = out / "tiers-manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest at {manifest_path}; there is nothing "
                                f"to refreeze - run `wb corpus tiers --seed N` first")
    old = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    pool = load_corpus(dirs)
    by_id = {e.task_id: e for e in pool.entries}
    cuts = tier_cuts(e.score for e in pool.entries)

    drawn: dict[str, list[Entry]] = {}
    for name in SET_NAMES:
        picked = []
        for row in old["sets"][name]["tasks"]:
            entry = by_id.get(row["task"])
            if entry is None:
                raise ValueError(
                    f"{row['task']} is in the manifest's {name} but no longer "
                    f"usable in the corpus; refusing to refreeze a set whose "
                    f"membership would change")
            picked.append(Entry(entry.task_id, entry.domain, entry.score,
                                entry.contract_sha256, entry.path,
                                tier_of(entry.score, cuts)))
        drawn[name] = picked

    written: list[Path] = []
    by_domain: dict[str, dict[str, int]] = {}
    for set_name, picked in drawn.items():
        label = "random" if set_name == "random-10" else set_name.split("-", 1)[1]
        counts: dict[str, int] = {}
        for e in sorted(picked, key=lambda e: e.task_id):
            written.append(_write_task(e, label, out / set_name))
            counts[e.domain] = counts.get(e.domain, 0) + 1
        by_domain[set_name] = dict(sorted(counts.items()))

    written.append(_write_manifest(out, pool, cuts, old["seed"], old["per_tier"],
                                   drawn, by_domain, refrozen=because))
    return DrawResult(cuts=cuts, total=pool.total, usable=len(pool.entries),
                      excluded=pool.excluded, folders=pool.folders,
                      sets={k: [e.task_id for e in sorted(v, key=lambda e: e.task_id)]
                            for k, v in drawn.items()},
                      by_domain=by_domain, written=written)


def _write_manifest(out: Path, pool: Pool, cuts: dict[str, int], seed: int,
                    per_tier: int, drawn: dict[str, list[Entry]],
                    by_domain: dict[str, dict[str, int]],
                    refrozen: str = "") -> Path:
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # The world the drawn tasks record (unblock plan M1): a set drawn from a
    # corpus imported under a revision names it here, and every row it records
    # carries the matching suite id.
    world_version = recorded_world_version(
        [load_task_file(e.path) for picked in drawn.values() for e in picked])
    manifest = {
        "measure": MEASURE,
        "generated_at": now,
        # A refreeze keeps the draw and refreshes the content, so the reader
        # can tell a re-run of the same seed from a rewrite of the same ids.
        **({"refrozen_at": now, "refrozen_because": refrozen} if refrozen else {}),
        "world": {"package": WORLD_PACKAGE, "version": world_version},
        "seed": seed,
        "per_tier": per_tier,
        "cuts": cuts,
        "corpus": [{"dir": f.path.as_posix(), "domain": f.domain,
                    "tasks": f.tasks, "usable": f.usable} for f in pool.folders],
        "excluded": {t: excluded_reason(*r) for t, r in sorted(pool.excluded.items())},
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
