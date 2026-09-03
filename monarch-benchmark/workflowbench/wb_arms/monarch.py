"""The Monarch competitor: create + run mode, driven through Monarch's own HTTP API.

Monarch authors a workflow from the task's request text and then runs it against
the benchmark front door, so what is measured is the product a customer gets
rather than a model in a loop. The competitor is named for the checkout it ran
from (`monarch@<sha>`, plus `+<branch>` off main) so every row says which build
produced it. See specs/002 for the attempt flow.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from wb_arms.api_loop import ArmResult
from wb_world.episode import Episode


def monarch_version(repo_path: str | Path) -> str:
    """Name the Monarch build in `repo_path`: `monarch@<sha>`, `+<branch>` off main."""
    def git(*args: str) -> str:
        out = subprocess.run(["git", "-C", str(repo_path), *args],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise ValueError(f"git {' '.join(args)} in {repo_path}: "
                             f"{(out.stderr or out.stdout).strip()}")
        return out.stdout.strip()

    sha = git("rev-parse", "--short", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    return f"monarch@{sha}" if branch == "main" else f"monarch@{sha}+{branch}"


class MonarchArm:
    provider_key = "monarch"

    def __init__(self, harness, timeout_s: float, price_table, kb, env, name: str):
        self.harness = harness
        self.timeout_s = timeout_s
        self.price_table = price_table
        self.kb = kb
        self.env = env
        self.name = name
        self.model_label = name          # recorded as EpisodeRow.model (R6)

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        # ponytail: the attempt flow (login, author, stream, run, poll, clean up)
        # lands in T026; this class exists now so the plan can name and build it.
        raise NotImplementedError("the Monarch attempt flow is rewritten in T026")
