"""Monarch verification probe record lookup and storage (M5).

Keeps probe loading in wb_orchestrator so the benchmark core does not depend
on the wb_studio UI package (FR-007, T028).
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

PROBE_FILE = "enterprise-probe.json"
PROBE_TTL = timedelta(hours=2)


def probe_path(studio_or_site: Any) -> Path:
    base = getattr(studio_or_site, "directory", studio_or_site)
    return Path(base) / PROBE_FILE


def load_probe(studio_or_site: Any) -> dict | None:
    path = probe_path(studio_or_site)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
