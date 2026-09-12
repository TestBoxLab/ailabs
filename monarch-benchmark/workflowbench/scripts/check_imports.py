"""Every `wb_*` import must resolve to a file git tracks.

The half-commit: you edit a tracked file to use a module you have not added, the
tests pass because the module is sitting in your working tree, and the commit
puts a file into the repository that raises the moment anyone else checks it
out. Four of these shipped on 11 September 2026 within one hour, one of them a
Studio that started and then failed on the Budget page.

The check is cheap because it never needs a clean checkout: it reads the source
on disk but resolves every import against `git ls-files`. A module you have not
`git add`ed is invisible to it, which is exactly the question being asked.

    uv run python scripts/check_imports.py

Three traps, and the reason this lives in CI rather than in anyone's head: three
people wrote this check the same afternoon and each shipped a different
structural blindness. Every version would have passed the bug it was written to
catch.

- **Indented imports count.** This codebase imports lazily inside functions all
  over the Studio; anchoring the pattern at `^` misses about two thirds of them.
- **`from wb_studio import allowances` names a module too.** Matching only the
  part after `from` resolves `wb_studio`, which always exists, and never looks
  at `allowances` - the import that broke the Budget page. Each imported name is
  checked as a possible submodule.
- **`as` hides the name.** `from wb_studio import genesis_engineer as engineer`
  reads as an import of `genesis_engineer as engineer` unless the alias is cut
  first, and that is the exact line behind one of the four half-commits.

A missing dotted module is reported once, not once per imported symbol: the head
is resolved first and the individual names are only examined when it exists.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = re.compile(r"^wb_\w+$")
# `from wb_x.y import a, b` / `import wb_x.y` / `from wb_x import a, b`, at any indent.
IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+(wb_\w+(?:\.\w+)*)[ \t]+import[ \t]+([^\n#]+)"
    r"|import[ \t]+(wb_\w+(?:\.\w+)*))",
    re.M,
)
# A dotted module name inside a string literal: importlib's argument.
STRING_MODULE = re.compile(r"""["'](wb_\w+(?:\.\w+)+)["']""")


def tracked_modules() -> tuple[set[str], set[str]]:
    """Dotted names git tracks, and which of them are packages rather than files.

    The split matters for the string form below: `wb_studio.genesis_engineer` has
    a package for a parent and is a module reference, while
    `wb_studio.report_data.run_report` has a module for a parent and is an
    attribute path that no importlib call will ever be handed.
    """
    modules: set[str] = set()
    packages: set[str] = set()
    for path in source_files():
        parts = Path(path).with_suffix("").parts
        if not parts or not PACKAGE.match(parts[0]):
            continue                     # tests/, scripts/, anything not a wb_ package
        if parts[-1] == "__init__":
            parts = parts[:-1]
            packages.add(".".join(parts))
        modules.add(".".join(parts))
        for i in range(1, len(parts)):
            packages.add(".".join(parts[:i]))
    return modules | packages, packages


def source_files() -> list[str]:
    return subprocess.run(["git", "ls-files", "--", "*.py"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.split()


def unresolved(modules: set[str], files: list[str]) -> list[tuple[str, int, str]]:
    bad = []
    for path in files:
        # Tracked but deleted on disk is a different problem; skip rather than crash.
        file = ROOT / path
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        for match in IMPORT.finditer(text):
            head, names, plain = match.groups()
            line = text.count("\n", 0, match.start()) + 1
            if plain:                                   # import wb_x.y
                if plain.split(" as ")[0].strip() not in modules:
                    bad.append((path, line, plain))
                continue
            if head not in modules:                     # from wb_x.y import ...
                bad.append((path, line, head))
                continue
            if "*" in names or "(" in names:            # star or a wrapped list: head is enough
                continue
            for name in names.split(","):
                name = name.split(" as ")[0].strip()
                if not re.fullmatch(r"[a-z_]\w*", name or ""):
                    continue          # ClassName, CONSTANT: never a module here
                if f"{head}.{name}" in modules:
                    continue          # a submodule git tracks
                if defines(head, name):
                    continue          # an ordinary symbol living in the package
                bad.append((path, line, f"{head}.{name}"))
    return bad


def defines(package: str, name: str) -> bool:
    """Whether `package` supplies `name` itself, rather than as a submodule.

    `from wb_studio import allowances` reads the same as `from x import helper`,
    so a missing submodule is only distinguishable from a plain symbol by looking
    at what the package actually contains.
    """
    init = ROOT / package.replace(".", "/") / "__init__.py"
    module = ROOT / (package.replace(".", "/") + ".py")
    for candidate in (init, module):
        if candidate.is_file():
            body = candidate.read_text(encoding="utf-8", errors="replace")
            # `NAME =`, `NAME: hint =` (annotated), `def NAME`, `class NAME`, or re-exported.
            if re.search(rf"^\s*(def|class)\s+{re.escape(name)}\b|^\s*{re.escape(name)}\s*[:=]|"
                         rf"\bimport\b.*\b{re.escape(name)}\b", body, re.M):
                return True
    return False


def named_in_strings(files: list[str], modules: set[str],
                     packages: set[str]) -> list[tuple[str, int, str]]:
    """Modules named as string literals and imported through importlib.

    `scheduler.MODULES` and `genesis_plugins.MODULES` are tuples of dotted names
    resolved at runtime. A scan for `import` statements cannot see them, and
    `discover()` catches ImportError and moves on - so a checkout missing one of
    those files loses a daily job silently, with nothing anywhere saying so.
    That is failing open, which is worse than the import error it replaces.
    """
    bad = []
    for path in files:
        file = ROOT / path
        # Tests name modules that do not exist on purpose - `wb_studio.not_there`
        # is how the skip path is proved. Only shipped code has to resolve.
        if not file.is_file() or path.startswith("tests/"):
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        for match in STRING_MODULE.finditer(text):
            dotted = match.group(1)
            if dotted in modules:
                continue
            if dotted.rsplit(".", 1)[0] not in packages:
                continue                 # an attribute path, not a module
            bad.append((path, text.count("\n", 0, match.start()) + 1, dotted))
    return bad


def main() -> int:
    modules, packages = tracked_modules()
    files = source_files()
    bad = unresolved(modules, files)
    named = named_in_strings(files, modules, packages)
    if not bad and not named:
        print(f"check_imports: {len(files)} tracked files, every wb_* import resolves.")
        return 0
    if bad:
        print("check_imports: imports that name a module git does not track.\n")
    for path, line, module in sorted(bad):
        print(f"  {path}:{line}: {module}")
    if named:
        print("\ncheck_imports: modules named as strings for importlib, not tracked.")
        print("These fail open - the job is skipped and nothing reports it.\n")
        for path, line, module in sorted(named):
            print(f"  {path}:{line}: {module}")
    # Run locally, these usually are not committed yet - which is the point, and
    # the message has to be true at the moment someone reads it.
    print("\nOnce committed, an import above raises on a clean checkout and a")
    print("string above is skipped in silence. `git add` the missing module in")
    print("the same commit, or take the reference out.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
