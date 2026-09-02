"""M3: subprocess adapter for re-running the pinned legacy fork (BUILD-SPEC §2.9).

The fork runs in ITS OWN venv (quarantined deps) via subprocess; stdout/exports
translate row-for-row into `episodes` under suite=automationbench-legacy@1.0.6.
The pinned clone is Monarch_Main\\AutomationBench-1.0.6-stock (there is no
v9.12 anywhere on disk — the spec string is stale; see importer docstring).

A real legacy re-run is API-billed; this module builds and runs the command
but refuses without keys, same policy as every other arm.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

LEGACY_CLONE = Path(r"C:\Users\Lucas Wakigawa\Monarch_Main\AutomationBench-1.0.6-stock")


def legacy_python(clone: Path = LEGACY_CLONE) -> Path:
    venv = clone / ".venv" / "Scripts" / "python.exe"
    return venv


def ensure_venv(clone: Path = LEGACY_CLONE) -> Path:
    """Create the quarantined venv for the pinned fork if missing."""
    py = legacy_python(clone)
    if py.exists():
        return py
    subprocess.run(["uv", "venv", "-p", "3.13", str(clone / ".venv")], check=True)
    subprocess.run(["uv", "pip", "install", "-q", "-p", str(py), "-e", str(clone)],
                   check=True)
    return py


def run_legacy(model: str, domains: list[str], out_dir: str | Path,
               clone: Path = LEGACY_CLONE, extra_args: list[str] | None = None,
               timeout: float = 7200.0) -> dict[str, Any]:
    if not os.environ.get("ANTHROPIC_API_KEY") and model.startswith("claude"):
        raise RuntimeError("legacy re-run is API-billed; ANTHROPIC_API_KEY not set")
    py = ensure_venv(clone)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(py), "-m", "automationbench.scripts.eval",
           "--model", model, "--domains", *domains,
           "--output-dir", str(out), *(extra_args or [])]
    proc = subprocess.run(cmd, cwd=clone, capture_output=True, text=True,
                          timeout=timeout)
    exports = sorted(out.glob("**/*.json"))
    return {"returncode": proc.returncode, "cmd": cmd,
            "exports": [str(p) for p in exports],
            "stderr_tail": proc.stderr[-2000:] if proc.returncode else ""}
