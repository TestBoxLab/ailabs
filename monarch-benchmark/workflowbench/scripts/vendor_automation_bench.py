"""Copy a repaired AutomationBench tree into vendor/automation-bench.

The bench installs AutomationBench as an editable path dependency from
`vendor/automation-bench` (gitignored). This script replaces that folder with
a source tree of the version you say you expect, leaving behind what is not
source (its virtual environment, byte-code caches, test caches, logs, the Git
folder), and writes `VENDORED-FROM.txt` beside the copy so anyone can see
where the world came from and check that it is still the same bytes.

    uv run python scripts/vendor_automation_bench.py \
        --source ../../.references/ApplicationBench/vendor/automation-bench \
        --expect-version 1.0.6+evalrepair.10 \
        --tree-id 7ac9559eb65540feac74d5d12c37406b4d69fd56 --replace

After the copy: `uv lock` (the package version changed) and `uv sync`.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

WORKFLOWBENCH_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKFLOWBENCH_DIR.parents[1]
DEFAULT_SOURCE = REPO_ROOT / ".references" / "ApplicationBench" / "vendor" / "automation-bench"
DEFAULT_DEST = WORKFLOWBENCH_DIR / "vendor" / "automation-bench"
RECORD_NAME = "VENDORED-FROM.txt"

# Folders that are never source, and file patterns that are logs.
EXCLUDED_DIRS = (".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache")
EXCLUDED_PATTERNS = ("*.log",)


class VendorError(Exception):
    """A refusal: nothing was copied."""


def _ignore(_directory: str, names: list[str]) -> set[str]:
    out = {n for n in names if n in EXCLUDED_DIRS}
    for pattern in EXCLUDED_PATTERNS:
        out |= set(fnmatch.filter(names, pattern))
    return out


def _excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    return any(fnmatch.fnmatch(path.name, p) for p in EXCLUDED_PATTERNS)


def source_version(source: Path) -> str:
    """`project.version` from the source's pyproject.toml."""
    pyproject = source / "pyproject.toml"
    if not pyproject.is_file():
        raise VendorError(f"no pyproject.toml under {source}; is that an AutomationBench tree?")
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as e:
        raise VendorError(f"{pyproject}: could not read project.version ({e})") from e


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copied_files(root: Path) -> list[Path]:
    """Every file under `root` that counts as vendored source, sorted by path.

    The record file is left out, so the hash below covers exactly the copy.
    """
    return sorted((p for p in root.rglob("*")
                   if p.is_file() and not _excluded(p, root) and p.name != RECORD_NAME),
                  key=lambda p: p.relative_to(root).as_posix())


def tree_sha256(root: Path) -> str:
    """One hash over every copied file: its path and its content, in path order.

    Recompute it later to check that the vendored world is still the bytes the
    record says. It is not a Git tree id; the Git identity is recorded as given.
    """
    root = Path(root)
    h = hashlib.sha256()
    for p in copied_files(root):
        h.update(f"{p.relative_to(root).as_posix()}\t{_sha256(p)}\n".encode())
    return h.hexdigest()


def vendor(source: str | Path, dest: str | Path, expect_version: str,
           replace: bool = False, tree_id: str | None = None) -> dict[str, Any]:
    """Copy `source` to `dest` when its version is `expect_version`.

    Refuses, copying nothing, when the source has no readable version, when the
    version is not the expected one, or when `dest` already exists and
    `replace` is False. With `replace`, the old copy is removed first.
    """
    source, dest = Path(source), Path(dest)
    if not source.is_dir():
        raise VendorError(f"source folder does not exist: {source}")
    version = source_version(source)
    if version != expect_version:
        raise VendorError(f"{source / 'pyproject.toml'} says version {version}, "
                          f"but --expect-version is {expect_version}; nothing copied")
    if dest.exists():
        if not replace:
            raise VendorError(f"{dest} already exists; pass --replace to remove it first "
                              f"(the old copy is not kept)")
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, ignore=_ignore)

    files = copied_files(dest)
    summary = {
        "source": source.resolve().as_posix(),
        "dest": dest.resolve().as_posix(),
        "version": version,
        "pyproject_sha256": _sha256(source / "pyproject.toml"),
        "files": len(files),
        "tree_sha256": tree_sha256(dest),
        "source_tree_id": tree_id,
        "vendored_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (dest / RECORD_NAME).write_text(_record(summary), encoding="utf-8", newline="\n")
    return summary


def _record(s: dict[str, Any]) -> str:
    lines = [
        "AutomationBench vendored copy. Written by scripts/vendor_automation_bench.py; "
        "do not edit by hand.",
        f"source: {s['source']}",
        f"expected_version: {s['version']}",
        f"pyproject_sha256: {s['pyproject_sha256']}",
        f"files: {s['files']}",
        f"tree_sha256: {s['tree_sha256']}",
        f"source_tree_id: {s['source_tree_id'] or 'not given'}"
        + (" (the source's Git tree id as given on the command line; not verified here)"
           if s["source_tree_id"] else ""),
        f"vendored_at: {s['vendored_at']}",
        f"excluded: {', '.join(EXCLUDED_DIRS + EXCLUDED_PATTERNS)}",
        "tree_sha256 is sha256 over '<relative path>\\t<sha256 of content>\\n' for every "
        "copied file in path order; recompute with tree_sha256() in the script.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Replace vendor/automation-bench with a source tree of the expected version.")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE),
                    help=f"the AutomationBench tree to copy (default: {DEFAULT_SOURCE})")
    ap.add_argument("--dest", default=str(DEFAULT_DEST),
                    help=f"where the copy goes (default: {DEFAULT_DEST})")
    ap.add_argument("--expect-version", required=True,
                    help="the version the source's pyproject.toml must declare, "
                         "for example 1.0.6+evalrepair.10")
    ap.add_argument("--tree-id", default=None,
                    help="the source's Git tree id, recorded as given (not verified)")
    ap.add_argument("--replace", action="store_true",
                    help="remove an existing copy first")
    args = ap.parse_args(argv)
    try:
        s = vendor(args.source, args.dest, args.expect_version,
                   replace=args.replace, tree_id=args.tree_id)
    except VendorError as e:
        print(f"vendor_automation_bench: {e}", file=sys.stderr)
        return 2
    print(f"vendored automation-bench {s['version']} from {s['source']}")
    print(f"into {s['dest']}: files: {s['files']}, tree_sha256: {s['tree_sha256']}")
    print(f"pyproject_sha256: {s['pyproject_sha256']}; "
          f"source_tree_id: {s['source_tree_id'] or 'not given'}")
    print(f"record: {Path(s['dest']) / RECORD_NAME}")
    print("next: uv lock && uv sync   (the package version changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
