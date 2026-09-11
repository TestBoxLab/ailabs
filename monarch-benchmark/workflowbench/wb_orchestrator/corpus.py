"""Corpus tooling per BUILD-SPEC §2.8.

- import-ab: convert AB dataset rows (example_id/prompt/answer/info) into T0
  task files with contract_sha256 embedded. AB rows carry no expected_changes;
  imported tasks therefore run assertion-only until someone declares the dual
  invariant — the grader flags invariant_declared=False, never guesses.
- validate: the two CI jobs. no-op (every assertion fails on the pristine
  world) and oracle (the scripted oracle passes where one exists; tasks whose
  assertion types the oracle can't drive are reported oracle=unsupported, loud).
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

import yaml

from grader.grade import grade
from grader.noop import validate_task
from runner.arms import OracleArm, _sf_updates_from_assertions
from wb_orchestrator.orchestrator import contract_hash
from wb_world import episode as world
from wb_world.episode import (UPSTREAM_WORLD_VERSION, WORLD_PACKAGE, Episode, load_task_file,
                              seeded_services, world_block, world_of)


BASELINE_DOMAIN = "simple"
MANIFEST_NAME = "MANIFEST.yaml"
VENDORED_RECORD = "VENDORED-FROM.txt"      # written by scripts/vendor_automation_bench.py
_REVISION_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def structural_difficulty(task: dict[str, Any]) -> int:
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


score_task = structural_difficulty



def known_domains() -> list[str]:
    """The baseline domain plus the vendor's own public list, in a fixed order.

    # ponytail: the vendor's PUBLIC_DOMAINS is the list; a second copy here would
    # rot the moment they add a domain.
    """
    from automationbench.domains import PUBLIC_DOMAINS
    return [BASELINE_DOMAIN] + sorted(PUBLIC_DOMAINS)


def resolve_domains(domains: list[str]) -> list[str]:
    """`all` means every known domain; an unknown name is refused by name."""
    known = known_domains()
    if domains == ["all"]:
        return known
    unknown = [d for d in domains if d not in known]
    if unknown:
        raise ValueError(f"unknown domain(s) {unknown}; known: {known}")
    return domains


def import_ab(domains: list[str], out_dir: str | Path,
              product_services: list[str] | None = None,
              revision: str | None = None) -> dict[str, Any]:
    """Convert AB rows into task files, one folder per domain when asked.

    `out_dir` may contain `{domain}`, which is replaced per domain. Several
    domains without it is refused rather than mixing them in one folder.

    `revision` labels the world the tasks are imported under: every task then
    carries `info.world` (package, installed version, label), hashed, and the
    folder that holds the domain folders gets a MANIFEST.yaml. Without it the
    import is what it always was, which is only right on the upstream world;
    on any other it is refused, so a repaired world never lands in `corpus/`
    looking like the old one.
    """
    from automationbench.domains import get_domain_dataset
    domains = resolve_domains(domains)
    template = str(out_dir)
    if len(domains) > 1 and "{domain}" not in template:
        raise ValueError(f"several domains ({domains}) need '{{domain}}' in --dest, "
                         f"or they would be mixed in one folder: {template}")
    if revision is not None and not _REVISION_LABEL.fullmatch(revision):
        raise ValueError(f"revision label {revision!r} must be letters, digits, '.', '_' "
                         f"or '-' (it names a folder and a suite)")
    installed = world.installed_world_version()
    if revision is None and installed != UPSTREAM_WORLD_VERSION:
        raise ValueError(f"the installed world is {WORLD_PACKAGE} {installed}, not the upstream "
                         f"{UPSTREAM_WORLD_VERSION}; an import from it must say which revision "
                         f"it is: pass --revision LABEL --out DIR, so it never lands in "
                         f"corpus/ as if it were the {UPSTREAM_WORLD_VERSION} world")

    by_domain: dict[str, dict[str, int]] = {}
    seeded: set[str] = set()
    written, skipped = [], []
    for domain in domains:
        out = Path(template.replace("{domain}", domain))
        out.mkdir(parents=True, exist_ok=True)
        n_written, n_skipped = len(written), len(skipped)
        ds = get_domain_dataset(domain)
        for row in ds:
            info = row["info"] if isinstance(row["info"], dict) else json.loads(row["info"])
            task_name = info.get("task_name") or f"{domain}.{row['example_id']}"
            task = {
                "example_id": row["example_id"],
                "task": task_name,
                "prompt": row["prompt"],
                "answer": row.get("answer"),
                "info": {
                    "zapier_tools": info.get("zapier_tools", []),
                    "initial_state": info.get("initial_state", {}),
                    "assertions": info.get("assertions", []),
                    # AB doesn't declare the dual invariant; leave undeclared.
                    "expected_changes": info.get("expected_changes", []),
                    "allowed_changes": info.get("allowed_changes", []),
                },
            }
            if revision is not None:
                task["info"]["world"] = world_block(revision, installed)
            task["contract_sha256"] = contract_hash(task)
            # What the domain seeds, counted before the skip below: the service
            # check must answer for the whole domain, not only for the tasks this
            # call happened to write, or a re-import would report nothing missing.
            # Seeded means the task's data says something about the service; the
            # repaired world's spelled-out empty defaults do not count.
            seeded |= set(seeded_services(task["info"]["initial_state"]))
            path = out / f"{task_name}.json"
            if path.exists() and json.loads(path.read_text()).get("contract_sha256") == task["contract_sha256"]:
                skipped.append(task_name)
                continue
            path.write_text(json.dumps(task, indent=1, default=str))
            written.append(task_name)
        by_domain[domain] = {"written": len(written) - n_written,
                             "unchanged": len(skipped) - n_skipped}
    missing = sorted(seeded - set(product_services)) if product_services is not None else []
    manifest = None
    if revision is not None and "{domain}" in template:
        # the folder that holds the domain folders describes the whole import
        root = Path(template.replace("{domain}", "x")).parent
        write_manifest(root, imported_at=_now())
        manifest = root / MANIFEST_NAME
    return {"written": len(written), "unchanged": len(skipped),
            "by_domain": by_domain, "missing_services": missing,
            "revision": revision, "world_version": installed,
            "manifest": str(manifest) if manifest else None,
            "tasks": written[:20] + (["..."] if len(written) > 20 else [])}


def _oracle_supported(task: dict[str, Any]) -> bool:
    try:
        handled = list(_sf_updates_from_assertions(task))
    except (KeyError, TypeError):
        return False   # assertion shape/field outside the scripted oracle's map
    return bool(handled) and len(handled) == len(task["info"].get("assertions", []))


def validate_corpus(task_dir: str | Path) -> dict[str, Any]:
    paths = sorted(Path(task_dir).glob("*.json"))
    results = []
    for p in paths:
        task = load_task_file(p)
        r: dict[str, Any] = {"task": task.get("task", p.stem), "file": p.name}
        embedded = task.get("contract_sha256")
        current = contract_hash(task)
        r["contract_hash"] = current
        r["contract_drift"] = bool(embedded) and embedded != current

        noop = validate_task(task)
        r["noop_ok"] = noop["ok"]
        if not noop["ok"]:
            r["noop_detail"] = {k: v for k, v in noop.items() if k != "ok"}

        r["invariant_declared"] = bool(task["info"].get("expected_changes"))

        if _oracle_supported(task):
            ep = Episode(task, episode_id=f"oracle-ci/{r['task']}")
            try:
                OracleArm().run(ep)
                g = grade(task, ep.snapshot0, ep.finish())
                r["oracle"] = "pass" if g["passed"] else "FAIL"
                if not g["passed"]:
                    r["oracle_detail"] = {"assertions": g["assertions_passed"],
                                          "invariant": g["invariant"]["passed"]}
            except Exception as e:
                r["oracle"] = "FAIL"
                r["oracle_detail"] = str(e)
        else:
            r["oracle"] = "unsupported"
        results.append(r)

    n_noop_bad = sum(not r["noop_ok"] for r in results)
    n_oracle_fail = sum(r["oracle"] == "FAIL" for r in results)
    n_unsupported = sum(r["oracle"] == "unsupported" for r in results)
    n_drift = sum(r["contract_drift"] for r in results)
    return {
        "n_tasks": len(results),
        "noop_failures": n_noop_bad,
        "oracle_failures": n_oracle_fail,
        "oracle_unsupported": n_unsupported,
        "invariant_undeclared": sum(not r["invariant_declared"] for r in results),
        "contract_drift": n_drift,
        "ok": n_noop_bad == 0 and n_oracle_fail == 0 and n_drift == 0,
        "results": results,
    }


def format_validation(v: dict[str, Any], verbose: bool = False) -> str:
    lines = [f"corpus: {v['n_tasks']} tasks | noop failures: {v['noop_failures']} | "
             f"oracle failures: {v['oracle_failures']} | oracle unsupported: {v['oracle_unsupported']} | "
             f"invariant undeclared: {v['invariant_undeclared']} | contract drift: {v['contract_drift']}",
             "OK" if v["ok"] else "FAIL"]
    for r in v["results"]:
        bad = (not r["noop_ok"]) or r["oracle"] == "FAIL" or r["contract_drift"]
        if bad or verbose:
            lines.append(f"  {'!' if bad else ' '} {r['task']}: noop={'ok' if r['noop_ok'] else 'FAIL'} "
                         f"oracle={r['oracle']} invariant_declared={r['invariant_declared']}"
                         + (" CONTRACT-DRIFT" if r["contract_drift"] else ""))
            for k in ("noop_detail", "oracle_detail"):
                if k in r:
                    lines.append(f"      {k}: {json.dumps(r[k], default=str)[:200]}")
    return "\n".join(lines)


# --- the corpus manifest (one per world revision) -------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def vendored_record() -> dict[str, str]:
    """What VENDORED-FROM.txt next to the installed package says, as a mapping;
    empty when the copy has no record (a plain clone of upstream, say)."""
    import automationbench
    path = Path(automationbench.__file__).resolve().parents[1] / VENDORED_RECORD
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(":")
        if sep and " " not in key:
            out[key.strip()] = value.strip()
    return out


def _world_of_corpus(folders: list[Path]) -> dict[str, Any]:
    """The one world every task under `folders` records; refuses a mix by name."""
    seen: dict[tuple, list[str]] = {}
    for folder in folders:
        for p in sorted(folder.glob("*.json")):
            task = load_task_file(p)
            w = world_of(task)
            key = (w["package"], str(w["version"]), w.get("revision")) if w else None
            seen.setdefault(key, []).append(task.get("task", p.stem))
    if len(seen) > 1:
        detail = "; ".join(f"{k or 'no world recorded'}: {', '.join(v[:3])}"
                           f"{', ...' if len(v) > 3 else ''}" for k, v in seen.items())
        raise ValueError(f"the folders mix worlds ({detail}); a corpus is one world")
    key = next(iter(seen), None)
    if key is None:
        return {"package": WORLD_PACKAGE, "version": UPSTREAM_WORLD_VERSION, "revision": None}
    return {"package": key[0], "version": key[1], "revision": key[2]}


def write_manifest(root: str | Path, imported_at: str | None = None) -> dict[str, Any]:
    """Write ROOT/MANIFEST.yaml from the imported-* folders under ROOT as they are.

    Usable means what `wb corpus tiers` means: a non-empty approval rule and a
    hash that matches the content. `imported_at` is kept from the previous
    manifest unless given.
    """
    from wb_orchestrator import tiers
    root = Path(root)
    folders = sorted(p for p in root.glob("imported-*") if p.is_dir())
    if not folders:
        raise FileNotFoundError(f"no imported-* folder under {root}")
    path = root / MANIFEST_NAME
    previous = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    world_seen = _world_of_corpus(folders)
    pool = tiers.load_corpus(folders)

    record = vendored_record()
    vendored: dict[str, Any]
    if record.get("expected_version") == world_seen["version"]:
        vendored = {"vendored_from": record.get("source"),
                    "source_tree_id": (record.get("source_tree_id") or "").split(" ")[0] or None,
                    "tree_sha256": record.get("tree_sha256"),
                    "pyproject_sha256": record.get("pyproject_sha256"),
                    "vendored_at": record.get("vendored_at")}
    else:
        vendored = {"vendored_from": f"no {VENDORED_RECORD} for {world_seen['version']} next to "
                                     f"the installed package"}

    rows = []
    for f in pool.folders:
        declared = any(load_task_file(p)["info"].get("expected_changes")
                       for p in sorted(f.path.glob("*.json")))
        rows.append({"dir": f.path.relative_to(root).as_posix(), "domain": f.domain,
                     "tasks": f.tasks, "declared": declared, "usable": f.usable})
    domain_of = {e.task_id: e.domain for e in pool.entries}
    for f in pool.folders:
        for p in f.path.glob("*.json"):
            domain_of.setdefault(load_task_file(p).get("task", p.stem), f.domain)
    without_rule = [{"task": t, "domain": domain_of.get(t), "reason": tiers.excluded_reason(*r)}
                    for t, r in sorted(pool.excluded.items()) if r[0] == tiers.NO_RULE]
    mismatch = [{"task": t, "domain": domain_of.get(t), "reason": tiers.excluded_reason(*r)}
                for t, r in sorted(pool.excluded.items()) if r[0] == tiers.DRIFT]

    manifest: dict[str, Any] = {
        "revision": world_seen["revision"],
        "world": {"package": world_seen["package"], "version": world_seen["version"], **vendored},
        "imported_at": imported_at or previous.get("imported_at") or _now(),
        "manifest_written_at": _now(),
        "usable_means": ("a non-empty approval rule (info.expected_changes) and a "
                         "contract_sha256 that matches the content; the two checks "
                         "wb corpus tiers applies"),
        "folders": rows,
        "tasks_total": pool.total,
        "usable_total": len(pool.entries),
        "without_rule": without_rule,
    }
    if mismatch:
        manifest["hash_mismatch"] = mismatch
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True,
                                   default_flow_style=False), encoding="utf-8", newline="\n")
    return manifest


def format_manifest(root: str | Path, m: dict[str, Any]) -> str:
    root = Path(root)
    w = m["world"]
    lines = [f"{root.as_posix()}: revision {m['revision'] or '(none recorded)'}, "
             f"world {w['package']} {w['version']}"]
    width = max(len(f["domain"]) for f in m["folders"]) + 1
    for f in m["folders"]:
        lines.append(f"  {f['domain']:<{width}} {f['tasks']:>4} tasks, {f['usable']:>4} usable, "
                     f"{'declared' if f['declared'] else 'not declared'}")
    lines.append(f"total: {m['tasks_total']} tasks, {m['usable_total']} usable, "
                 f"{len(m['without_rule'])} without a rule"
                 + (f", {len(m['hash_mismatch'])} whose hash does not match"
                    if m.get("hash_mismatch") else ""))
    lines.append(f"[ok] write {(root / MANIFEST_NAME).as_posix()}")
    return "\n".join(lines)
