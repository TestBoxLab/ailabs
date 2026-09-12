"""Windows evidence paths must consider their absolute length, preserving source IDs."""
import copy
import json
import os
from pathlib import Path

import pytest

from wb_orchestrator.orchestrator import Orchestrator
from wb_results import evidence
from wb_results.store import Store
from wb_world.episode import load_suite

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows extended-path regression")


def test_short_relative_path_gets_prefix_when_absolute_location_is_long(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = Path("evidence") / ("x" * 145) / "round"
    assert len(str(relative)) < 230 < len(os.path.abspath(relative))
    result = evidence._long(relative)
    assert str(result).startswith("\\\\?\\")
    evidence.write_json(result / "snapshot.json", {"retained": True})
    assert json.loads((result / "snapshot.json").read_text(encoding="utf-8")) == {"retained": True}


def test_orchestrator_preserves_exact_source_ids_under_long_relative_output_root(tmp_path, monkeypatch):
    prototype = load_suite(Path(__file__).resolve().parents[1] / "tasks")[0]
    tasks = []
    ids = ["task_20251217_153037_688_97d7df7d_be0bd794", "task_20251218_063226_501_97d7df7d_8fd400d1"]
    for identity in ids:
        task = copy.deepcopy(prototype)
        task["task"] = identity
        tasks.append(task)
    monkeypatch.chdir(tmp_path)
    root = Path("evidence") / ("x" * 145)
    assert len(str(root)) < 230 < len(os.path.abspath(root / "source-round"))
    store = Store(tmp_path / "results.sqlite3")
    engine = Orchestrator(store, tmp_path, ["null"], 1, root, tasks=tasks, provider_concurrency=1)
    run = engine.run("source-round")
    rows = store.episodes(run=run)["rows"]
    assert sorted(row["task_id"] for row in rows) == sorted(ids)
    for row in rows:
        assert not evidence.verify_manifest(store.artifacts(row["episode_id"])["manifest"])
        assert Path(row["artifacts_uri"]).parent.parent.name == row["task_id"]
