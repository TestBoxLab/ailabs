"""Unblock plan M2 (8 Sep 2026): freeze a task set listed by id, with its manifest.

A slate is a frozen task set whose members were listed by hand, one id per
line, rather than drawn from a seed the way `wb corpus tiers` draws the four
tier sets. The gauntlet of the unblock plan (the ApplicationBench achievable50
slate) is the first one.

The freeze copies each corpus task file unchanged into the set's folder and
writes `<name>-manifest.yaml` beside it: the selection rule (the comment lines
of the id list), why the set exists, the suite revision, and every task's hash,
difficulty score and tier label, so a round on the slate carries the same
source line a tier round does. Everything is computed from the task files
alone: no key, no network, no model call.

The freeze refuses, naming every offender, when an id is missing from the
corpus, has no derived approval rule, does not match its own hash, or already
sits in another frozen set. Nothing is written before every id has passed.
"""
from __future__ import annotations

import datetime
import importlib.metadata
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from wb_orchestrator import tiers
from wb_world.episode import contract_hash, load_task_file

TIERS_MANIFEST = "tiers-manifest.yaml"
# The sets `wb corpus tiers` freezes; every other frozen set is named by its manifest.
TIER_SET_GLOBS = ("tier-*", "random-10")
CUTS_FROM_CORPUS = "computed from the corpus"
UNCLASSIFIED = "unclassified"     # the tier label when the corpus has no cut points


class Refusal(Exception):
    """Nothing was written; every offender is named with its reason."""

    def __init__(self, message: str, offenders: Iterable[tuple[str, str]] = ()):
        self.offenders = list(offenders)
        super().__init__("\n".join([message] + [f"  {t}: {why}" for t, why in self.offenders]))


# --- the id list ---------------------------------------------------------------

@dataclass(frozen=True)
class IdList:
    ids: list[str]            # in the order listed
    selection_rule: str       # the comment lines, `#` stripped, one per line
    path: Path


def read_ids(path: str | Path) -> IdList:
    """One task id per line; `#` comments and blank lines allowed."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no id list at {path}")
    ids: list[str] = []
    rule: list[str] = []
    seen: set[str] = set()
    duplicates: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            rule.append(line[1:].strip())
            continue
        if line in seen:
            if line not in {t for t, _ in duplicates}:
                duplicates.append((line, "listed more than once"))
            continue
        seen.add(line)
        ids.append(line)
    if duplicates:
        raise Refusal(f"refusing to read {path.as_posix()}: an id is listed more than once",
                      duplicates)
    if not ids:
        raise Refusal(f"{path.as_posix()} lists no task id")
    return IdList(ids, "\n".join(rule), path)


# --- the frozen sets already there ------------------------------------------------

def frozen_ids(tasks_root: str | Path, except_name: str | None = None) -> dict[str, str]:
    """Task id -> the frozen set it sits in, under `tasks_root`.

    A frozen set is one of the tier draws (`tier-*`, `random-10`) or any folder
    named by a `<name>-manifest.yaml` beside it. A folder with neither is scratch.
    """
    root = Path(tasks_root)
    if not root.is_dir():
        return {}
    folders: list[Path] = []
    for pattern in TIER_SET_GLOBS:
        folders.extend(p for p in root.glob(pattern) if p.is_dir())
    for manifest in root.glob("*-manifest.yaml"):
        folder = root / manifest.name[: -len("-manifest.yaml")]
        if folder.is_dir():
            folders.append(folder)
    found: dict[str, str] = {}
    for folder in sorted(set(folders)):
        if folder.name == except_name:
            continue
        for p in sorted(folder.glob("*.json")):
            found.setdefault(load_task_file(p).get("task", p.stem), folder.name)
    return found


# --- the freeze ----------------------------------------------------------------

@dataclass(frozen=True)
class Row:
    task_id: str
    domain: str
    score: int
    tier: str
    contract_sha256: str
    path: Path                # the corpus original


@dataclass
class SlateResult:
    name: str
    out: Path
    manifest: Path
    tasks: list[Row]
    by_domain: dict[str, int]
    by_tier: dict[str, int]
    cuts: dict[str, int] | None      # None when the corpus has no cut points
    cuts_source: str
    suite_revision: str
    folders: list[tiers.Folder]
    total: int                # every corpus task read
    usable: int
    frozen_overlap: dict[str, str] = field(default_factory=dict)
    refrozen: bool = False
    written: list[Path] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.tasks)


def suite_revision() -> str:
    """The AutomationBench revision installed, the world every task file describes."""
    try:
        return importlib.metadata.version("automation-bench")
    except importlib.metadata.PackageNotFoundError as e:
        raise RuntimeError("automation-bench is not installed; a frozen set must "
                           "record its suite revision") from e


def _rule_gap(task: dict) -> str | None:
    """Why the task has no approval rule, or None when it has one."""
    info = task.get("info") or {}
    for key in ("expected_changes", "allowed_changes"):
        if key not in info:
            return f"no approval rule ({key} is absent)"
    if not info["expected_changes"]:
        return "no approval rule (expected_changes is empty)"
    return None


def _cuts(tasks_root: Path, pool: tiers.Pool) -> tuple[dict[str, int] | None, str, str]:
    """The tier cut points and measure: the tier manifest's when present, else the corpus's own.

    The labels are bookkeeping for the reader, not a condition of the freeze: a
    corpus too small or too concentrated to cut into terciles gives no cuts and
    every task the label "unclassified", with the reason recorded as the source.
    """
    manifest = tasks_root / TIERS_MANIFEST
    if manifest.is_file():
        tm = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if isinstance(tm.get("cuts"), dict) and {"low", "high"} <= set(tm["cuts"]):
            return ({"low": int(tm["cuts"]["low"]), "high": int(tm["cuts"]["high"])},
                    manifest.as_posix(), str(tm.get("measure") or tiers.MEASURE))
    try:
        return tiers.tier_cuts(e.score for e in pool.entries), CUTS_FROM_CORPUS, tiers.MEASURE
    except ValueError as e:
        return None, f"none ({e})", tiers.MEASURE


def freeze(ids_path: str | Path | None, out: str | Path, because: str,
           dirs: Iterable[str | Path], refreeze: bool = False,
           allow_frozen_overlap: bool = False) -> SlateResult:
    """Copy the listed tasks unchanged into `out` and write `<out>-manifest.yaml`.

    `out`'s parent is the tasks root: the manifest goes there and the frozen
    sets there are what an id may not already sit in. With `refreeze` the ids
    come from the existing manifest and only the copies, the hashes and the
    manifest are refreshed; `because` then records why.
    """
    out = Path(out)
    name, tasks_root = out.name, out.parent
    manifest_path = tasks_root / f"{name}-manifest.yaml"
    dirs = [Path(d) for d in dirs]

    if refreeze:
        if not manifest_path.is_file():
            raise FileNotFoundError(f"no manifest at {manifest_path.as_posix()}; there is "
                                    f"nothing to refreeze - freeze the set with --ids first")
        old = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        ids = [row["task"] for row in old.get("tasks", [])]
        selection_rule = str(old.get("selection_rule") or "")
        source_ids = old.get("source_ids")
        first_because = str(old.get("because") or "")
        if ids_path is not None:
            listed = read_ids(ids_path)
            if sorted(listed.ids) != sorted(ids):
                missing = sorted(set(ids) - set(listed.ids))
                extra = sorted(set(listed.ids) - set(ids))
                raise Refusal(
                    f"--ids lists a different set from the one {manifest_path.as_posix()} "
                    f"records; a refreeze keeps the same ids (missing from the file: "
                    f"{', '.join(missing) or 'none'}; not in the manifest: "
                    f"{', '.join(extra) or 'none'})")
            selection_rule, source_ids = listed.selection_rule, listed.path.as_posix()
    else:
        if ids_path is None:
            raise ValueError("a fresh freeze needs the id list (--ids FILE)")
        listed = read_ids(ids_path)
        ids, selection_rule = listed.ids, listed.selection_rule
        source_ids, first_because = listed.path.as_posix(), because
        present = [p for p in out.iterdir()] if out.is_dir() else []
        if present or manifest_path.exists():
            what = (f"already holds {len(present)} files" if present
                    else f"already has a manifest ({manifest_path.as_posix()})")
            raise Refusal(f"{out.as_posix()} {what}; pass --refreeze to rewrite the same "
                          f"ids, or choose another folder")

    pool = tiers.load_corpus(dirs)              # FileNotFoundError when a folder is empty
    cuts, cuts_source, measure = _cuts(tasks_root, pool)
    frozen = frozen_ids(tasks_root, except_name=name)

    rows: list[Row] = []
    offenders: list[tuple[str, str]] = []
    overlap: dict[str, str] = {}
    for task_id in ids:
        path = next((d / f"{task_id}.json" for d in dirs if (d / f"{task_id}.json").is_file()), None)
        task = load_task_file(path) if path is not None else None
        if task is None or task.get("task", path.stem) != task_id:
            offenders.append((task_id, "not in the corpus"))
            continue
        gap = _rule_gap(task)
        if gap:
            offenders.append((task_id, gap))
            continue
        if task.get("contract_sha256") != contract_hash(task):
            offenders.append((task_id, "contract hash does not match content"))
            continue
        if task_id in frozen:
            if not allow_frozen_overlap:
                offenders.append((task_id, f"already frozen in {frozen[task_id]}"))
                continue
            overlap[task_id] = frozen[task_id]
        score = tiers.score_task(task)
        tier = tiers.tier_of(score, cuts) if cuts else UNCLASSIFIED
        rows.append(Row(task_id, path.parent.name.split("imported-", 1)[-1], score,
                        tier, task["contract_sha256"], path))
    if offenders:
        raise Refusal(f"refusing to freeze {name}: {len(offenders)} of {len(ids)} ids "
                      f"cannot be frozen; nothing written", offenders)

    rows.sort(key=lambda r: r.task_id)
    by_domain: dict[str, int] = {}
    for r in rows:
        by_domain[r.domain] = by_domain.get(r.domain, 0) + 1
    by_domain = dict(sorted(by_domain.items()))
    labels = tiers.TIER_ORDER if cuts else (UNCLASSIFIED,)
    by_tier = {t: sum(r.tier == t for r in rows) for t in labels}

    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for r in rows:
        target = out / r.path.name
        shutil.copyfile(r.path, target)         # byte for byte, no label, no re-serialisation
        written.append(target)

    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    revision = suite_revision()
    manifest = {
        "name": name,
        "generated_at": now,
        # A refreeze keeps the ids and refreshes the content, so the reader can
        # tell a rewrite of the same set from a new one (same rule as the tiers).
        **({"refrozen_at": now, "refrozen_because": because} if refreeze else {}),
        "selection_rule": selection_rule,
        "because": first_because,
        "source_ids": source_ids,
        "suite_revision": revision,
        "measure": measure,
        "cuts": cuts,
        "cuts_source": cuts_source,
        "corpus": [{"dir": f.path.as_posix(), "domain": f.domain,
                    "tasks": f.tasks, "usable": f.usable} for f in pool.folders],
        "count": len(rows),
        "count_per_domain": by_domain,
        **({"frozen_overlap": dict(sorted(overlap.items()))} if overlap else {}),
        "tasks": [{"task": r.task_id, "domain": r.domain, "score": r.score,
                   "tier": r.tier, "contract_sha256": r.contract_sha256} for r in rows],
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True,
                                            default_flow_style=False), newline="\n")
    written.append(manifest_path)
    return SlateResult(name=name, out=out, manifest=manifest_path, tasks=rows,
                       by_domain=by_domain, by_tier=by_tier, cuts=cuts,
                       cuts_source=cuts_source, suite_revision=revision,
                       folders=pool.folders, total=pool.total, usable=len(pool.entries),
                       frozen_overlap=dict(sorted(overlap.items())), refrozen=refreeze,
                       written=written)


def summary(r: SlateResult) -> str:
    """One paragraph a reader can paste into a round sheet."""
    domains = ", ".join(f"{d} {n}" for d, n in r.by_domain.items())
    tiers_ = ", ".join(f"{t} {n}" for t, n in r.by_tier.items())
    if r.cuts:
        source = (r.cuts_source if r.cuts_source == CUTS_FROM_CORPUS else f"from {r.cuts_source}")
        cuts = f"cuts {r.cuts['low']}/{r.cuts['high']} {source}: {tiers_}"
    else:
        cuts = f"no cuts, {r.cuts_source}: {tiers_}"
    text = (f"{r.name}: {r.count} tasks {'refrozen' if r.refrozen else 'frozen'} from "
            f"{len(r.folders)} corpus folders ({r.total} tasks, {r.usable} usable) at suite "
            f"revision {r.suite_revision}; per domain: {domains}; {cuts}; every copy is "
            f"byte for byte its corpus original and keeps its hash")
    if r.frozen_overlap:
        text += (f"; {len(r.frozen_overlap)} of them also sit in another frozen set, "
                 f"allowed by --allow-frozen-overlap and recorded in the manifest")
    return text + "."
