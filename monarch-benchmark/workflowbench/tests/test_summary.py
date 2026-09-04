"""Feature 006: the summary page over two to six rounds. Offline throughout."""
from __future__ import annotations

import pytest

from tests.test_html_report import _row
from wb_results.store import Store


@pytest.fixture()
def three_round_store(tmp_path):
    """Three runs of the same three competitors on three different task sets.

    One plan is named `random-10` (the random draw the stratification check
    compares against); the other two are tier rounds carrying `info.tier`.
    Pass rates differ per round so a mean over rounds is not the same number as
    any single round.
    """
    store = Store(tmp_path / "wb.sqlite3")
    arms = ["alpha", "beta", "oracle"]
    rounds = [
        ("run-r1", "random-10", ("r1a", "r1b"),
         {"alpha": [True, False], "beta": [True, True], "oracle": [True, True]}),
        ("run-r2", "tier-1", ("r2a", "r2b"),
         {"alpha": [True, True], "beta": [False, False], "oracle": [True, True]}),
        ("run-r3", "tier-2", ("r3a", "r3b"),
         {"alpha": [False, False], "beta": [True, False], "oracle": [True, True]}),
    ]
    for run_id, plan, tasks, passes in rounds:
        store.create_run(run_id, f"cfg-{plan}", "workflowbench-synthetic@0.1",
                         {"suite_dir": "tasks", "arms": arms, "k": 1,
                          "n_tasks": len(tasks), "plan": plan,
                          "product": "simulated-apps"})
        for arm in arms:
            for task, passed in zip(tasks, passes[arm]):
                store.record_episode(_row(task, arm, 0, passed, run=run_id))
        store.finish_run(run_id)
    return store
