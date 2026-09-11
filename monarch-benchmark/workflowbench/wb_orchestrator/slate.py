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
import hashlib
import importlib.metadata
import json
import random
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


# --- the stratified split (FR-017, FR-018, FR-033) -----------------------------

SPLIT_MEASURE = (
    'services seeded (initial_state keys except "meta") + expected changes '
    "(info.expected_changes) + tools needed (info.zapier_tools), computed from the task "
    "file; tiers are the terciles of the whole corpus, ties on a cut point falling in "
    "the lower tier."
)
MEASURE_KIND = "structural-proxy"
MEASURE_VERSION = "1"


def slate_sha(tasks: Iterable[Row]) -> str:
    pairs = sorted((r.task_id, r.contract_sha256) for r in tasks)
    blob = json.dumps(pairs, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass
class SplitResult:
    dev_out: Path
    heldout_out: Path
    manifest: Path
    development: list[Row]
    held_out: list[Row]
    balance: dict[str, dict[str, dict[str, int]]]
    cuts: dict[str, int]
    seed: int
    per_slate: int
    because: str
    total: int
    usable: int
    folders: list[tiers.Folder]
    dev_sha: str
    heldout_sha: str
    written: list[Path] = field(default_factory=list)


def format_split_summary(res: SplitResult) -> str:
    lines = []
    lines.append(f"drawn from {res.usable} usable tasks across {len(res.folders)} domains")
    for slate_name in ("development", "held-out"):
        slate_rows = res.development if slate_name == "development" else res.held_out
        tiers_dict = res.balance[slate_name]["tiers"]
        simple_n = tiers_dict.get("simple", 0)
        medium_n = tiers_dict.get("medium", 0)
        complex_n = tiers_dict.get("complex", 0)
        lines.append(
            f"{slate_name:<12} {len(slate_rows)} tasks   simple {simple_n}  medium {medium_n}  complex {complex_n}"
        )

    dev_dom = res.balance["development"]["domains"]
    held_dom = res.balance["held-out"]["domains"]
    all_doms = sorted(set(dev_dom.keys()) | set(held_dom.keys()))
    dom_strs = [f"{d} {dev_dom.get(d, 0)}/{held_dom.get(d, 0)}" for d in all_doms]
    lines.append(f"domains balanced: {'  '.join(dom_strs)}")
    lines.append(
        f"frozen: {res.dev_out.as_posix()} (sha {res.dev_sha[:4]}…), {res.heldout_out.as_posix()} (sha {res.heldout_sha[:4]}…)"
    )
    lines.append(f"manifest: {res.manifest.as_posix()}")
    return "\n".join(lines)


def _write_split(dev_path: Path, dev_rows: list[Row], heldout_path: Path, heldout_rows: list[Row],
                 manifest_path: Path, manifest_text: str) -> list[Path]:
    """Write both slates and the manifest, or write nothing at all.

    A half-written held-out slate could never be redrawn: `split` refuses on any
    *.json already in that folder, so a copy that failed partway — a full disk, a
    permission — would retire the name for good with no way back but renaming the
    folder by hand. Everything this call wrote comes off again if any of it fails.
    """
    written: list[Path] = []
    try:
        for folder, rows in ((dev_path, dev_rows), (heldout_path, heldout_rows)):
            folder.mkdir(parents=True, exist_ok=True)
            for r in rows:
                target = folder / r.path.name
                shutil.copyfile(r.path, target)
                written.append(target)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest_text, newline="\n")
        written.append(manifest_path)
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return written


def split(dirs: Iterable[str | Path], size: int, seed: int,
          dev_out: str | Path, heldout_out: str | Path,
          manifest: str | Path, because: str) -> SplitResult:
    """Draw development and held-out slates stratified by difficulty tier and domain."""
    dev_path = Path(dev_out)
    heldout_path = Path(heldout_out)
    manifest_path = Path(manifest)
    dirs = [Path(d) for d in dirs]

    # Refuse redrawing a frozen held-out slate (FR-018)
    if heldout_path.is_dir() and any(heldout_path.glob("*.json")):
        raise Refusal(
            f"refused: {heldout_path.as_posix()} is a frozen held-out slate. A held-out slate is never redrawn.\n"
            f"Draw a new one under a different name and retire this one with a recorded reason."
        )

    pool = tiers.load_corpus(dirs)
    if len(pool.entries) < 2 * size:
        raise ValueError(f"usable corpus has {len(pool.entries)} tasks, fewer than the {2 * size} "
                         f"needed for two slates of {size}; nothing written")

    cuts = tiers.tier_cuts(e.score for e in pool.entries)
    entries = [tiers.Entry(e.task_id, e.domain, e.score, e.contract_sha256, e.path,
                           tiers.tier_of(e.score, cuts)) for e in pool.entries]

    domains = sorted(set(e.domain for e in entries))
    tier_order = tiers.TIER_ORDER

    # Group entries by cell (tier, domain)
    cells: dict[tuple[str, str], list[tiers.Entry]] = {}
    for e in entries:
        cells.setdefault((e.tier, e.domain), []).append(e)

    # Deterministic shuffling with seed
    rng = random.Random(seed)
    for key in sorted(cells):
        cells[key].sort(key=lambda x: x.task_id)
        rng.shuffle(cells[key])

    # Quotas for total drawn (2 * size)
    tier_quota = {t: 2 * (size // 3 + (1 if i < size % 3 else 0)) for i, t in enumerate(tier_order)}
    domain_quota = {d: 2 * (size // len(domains) + (1 if j < size % len(domains) else 0))
                    for j, d in enumerate(domains)}

    selected_by_cell: dict[tuple[str, str], list[tiers.Entry]] = {k: [] for k in cells}
    tier_counts = {t: 0 for t in tier_order}
    domain_counts = {d: 0 for d in domains}

    # Pass 1: pick tasks satisfying both tier and domain quota
    sorted_domains = list(domains)
    domain_idx = 0
    for t in tier_order:
        needed = tier_quota[t]
        while tier_counts[t] < needed:
            picked = False
            for _ in range(len(sorted_domains)):
                d = sorted_domains[domain_idx % len(sorted_domains)]
                domain_idx += 1
                if cells.get((t, d)) and tier_counts[t] < needed and domain_counts[d] < domain_quota[d]:
                    e = cells[(t, d)].pop(0)
                    selected_by_cell[(t, d)].append(e)
                    tier_counts[t] += 1
                    domain_counts[d] += 1
                    picked = True
                    if tier_counts[t] == needed:
                        break
            if not picked:
                break

    # Pass 2: if any tier quota is not met (e.g. some domains had few tasks), fill tier quota
    for t in tier_order:
        needed = tier_quota[t]
        while tier_counts[t] < needed:
            picked = False
            avail_domains = sorted([d for d in domains if cells.get((t, d))], key=lambda d: domain_counts[d])
            for d in avail_domains:
                if cells.get((t, d)) and tier_counts[t] < needed:
                    e = cells[(t, d)].pop(0)
                    selected_by_cell[(t, d)].append(e)
                    tier_counts[t] += 1
                    domain_counts[d] += 1
                    picked = True
                    if tier_counts[t] == needed:
                        break
            if not picked:
                raise ValueError(f"tier {t} has {tier_counts[t]} usable tasks, fewer than the {needed} needed")

    # Partition selected tasks in each cell between development and held-out:
    dev_entries: list[tiers.Entry] = []
    heldout_entries: list[tiers.Entry] = []
    remainder_slate = "development"

    for t in tier_order:
        for d in sorted_domains:
            cell_tasks = selected_by_cell.get((t, d), [])
            even = 2 * (len(cell_tasks) // 2)
            for i in range(0, even, 2):
                dev_entries.append(cell_tasks[i])
                heldout_entries.append(cell_tasks[i + 1])
            if len(cell_tasks) % 2 == 1:
                rem_task = cell_tasks[-1]
                if remainder_slate == "development":
                    dev_entries.append(rem_task)
                    remainder_slate = "held-out"
                else:
                    heldout_entries.append(rem_task)
                    remainder_slate = "development"

    def make_row(e: tiers.Entry) -> Row:
        return Row(e.task_id, e.domain, e.score, e.tier, e.contract_sha256, e.path)

    dev_rows = sorted([make_row(e) for e in dev_entries], key=lambda r: r.task_id)
    heldout_rows = sorted([make_row(e) for e in heldout_entries], key=lambda r: r.task_id)

    balance = {
        "development": {
            "tiers": {t: sum(r.tier == t for r in dev_rows) for t in tier_order},
            "domains": {d: sum(r.domain == d for r in dev_rows) for d in domains},
        },
        "held-out": {
            "tiers": {t: sum(r.tier == t for r in heldout_rows) for t in tier_order},
            "domains": {d: sum(r.domain == d for r in heldout_rows) for d in domains},
        },
    }

    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    task_manifest_rows = []
    for r in dev_rows:
        task_manifest_rows.append({
            "id": r.task_id,
            "slate": "development",
            "tier": r.tier,
            "domain": r.domain,
            "score": r.score,
            "contract_sha256": r.contract_sha256,
        })
    for r in heldout_rows:
        task_manifest_rows.append({
            "id": r.task_id,
            "slate": "held-out",
            "tier": r.tier,
            "domain": r.domain,
            "score": r.score,
            "contract_sha256": r.contract_sha256,
        })
    task_manifest_rows.sort(key=lambda x: x["id"])

    manifest_dict = {
        "measure": SPLIT_MEASURE,
        "measure_kind": MEASURE_KIND,
        "measure_version": MEASURE_VERSION,
        "generated_at": now,
        "seed": seed,
        "per_slate": size,
        "because": because,
        "cuts": cuts,
        "corpus": [{"dir": f.path.as_posix(), "domain": f.domain,
                    "tasks": f.tasks, "usable": f.usable} for f in pool.folders],
        "balance": balance,
        "tasks": task_manifest_rows,
    }

    written = _write_split(dev_path, dev_rows, heldout_path, heldout_rows, manifest_path,
                           yaml.safe_dump(manifest_dict, sort_keys=False, allow_unicode=True,
                                          default_flow_style=False))

    dev_sha = slate_sha(dev_rows)
    heldout_sha = slate_sha(heldout_rows)

    return SplitResult(
        dev_out=dev_path,
        heldout_out=heldout_path,
        manifest=manifest_path,
        development=dev_rows,
        held_out=heldout_rows,
        balance=balance,
        cuts=cuts,
        seed=seed,
        per_slate=size,
        because=because,
        total=pool.total,
        usable=len(pool.entries),
        folders=pool.folders,
        dev_sha=dev_sha,
        heldout_sha=heldout_sha,
        written=written,
    )

