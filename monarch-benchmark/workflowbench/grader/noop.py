"""No-op validation (AppWorld's rule): every assertion must FAIL on the
untouched initial world. An assertion that passes before any work is done
cannot discriminate and is flagged as vacuous. Run as corpus CI. (P3.)"""
from __future__ import annotations

from typing import Any

import automationbench.rubric.assertions  # noqa: F401
from automationbench.rubric.registry import AssertionRegistry
from wb_world.episode import Episode


def validate_task(task: dict[str, Any]) -> dict[str, Any]:
    ep = Episode(task, episode_id="noop-validation")
    vacuous = []
    for a in task["info"].get("assertions", []):
        try:
            if AssertionRegistry.check(ep.world, a):
                vacuous.append(a)
        except Exception as e:  # a crashing check is its own defect class
            vacuous.append({**a, "_error": str(e)})
    n = len(task["info"].get("assertions", []))
    # Zero assertions is the degenerate vacuous case: nothing to discriminate.
    return {"task": task.get("task"), "n_assertions": n,
            "vacuous": vacuous, "ok": not vacuous and n > 0}
