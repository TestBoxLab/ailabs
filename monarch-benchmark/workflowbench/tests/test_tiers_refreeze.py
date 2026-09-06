"""`wb corpus tiers --refreeze` rebuilds the four sets without redrawing.

When the approval rules change, every drawn task's hash changes with them and
the frozen copies under `tasks/` go stale. A plain redraw is the wrong repair:
fixing the rules also made 218 previously unusable tasks usable, so the same
seed over a larger pool would pick a different ten. Refreezing keeps the task
ids the draw already chose and only refreshes their content and hashes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from wb_orchestrator import tiers

ROOT = Path(__file__).resolve().parents[1]
CORPUS = sorted((ROOT / "corpus").glob("imported-*"))


def _manifest(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "tasks" / "tiers-manifest.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def frozen(tmp_path):
    """A copy of the frozen sets: refreezing must never rewrite the committed ones."""
    import shutil
    shutil.copytree(ROOT / "tasks", tmp_path / "tasks")
    return tmp_path


def test_refreeze_keeps_every_task_id(frozen):
    before = {name: [t["task"] for t in _manifest(frozen)["sets"][name]["tasks"]]
              for name in tiers.SET_NAMES}
    result = tiers.refreeze(CORPUS, out=frozen / "tasks")
    for name in tiers.SET_NAMES:
        assert result.sets[name] == before[name], name


def test_refreeze_writes_the_corpus_hash_each_task_now_carries(frozen):
    tiers.refreeze(CORPUS, out=frozen / "tasks")
    corpus = {}
    for d in CORPUS:
        for p in d.glob("*.json"):
            task = json.loads(p.read_text(encoding="utf-8"))
            corpus[task["task"]] = task["contract_sha256"]
    for name in tiers.SET_NAMES:
        for p in (frozen / "tasks" / name).glob("*.json"):
            task = json.loads(p.read_text(encoding="utf-8"))
            assert task["contract_sha256"] == corpus[task["task"]], task["task"]


def test_refreeze_manifest_records_the_same_seed_and_the_new_hashes(frozen):
    tiers.refreeze(CORPUS, out=frozen / "tasks")
    manifest = _manifest(frozen)
    assert manifest["seed"] == 20260904
    assert manifest["refrozen_at"], "a refreeze must say when it happened"
    for name in tiers.SET_NAMES:
        for row in manifest["sets"][name]["tasks"]:
            path = frozen / "tasks" / name / f"{row['task']}.json"
            task = json.loads(path.read_text(encoding="utf-8"))
            assert row["contract_sha256"] == task["contract_sha256"], row["task"]


def test_refreeze_refuses_when_a_drawn_task_left_the_corpus(tmp_path):
    """Silently dropping a task would change the set behind the reader's back."""
    manifest = _manifest()
    manifest["sets"]["tier-simple"]["tasks"].append(
        {"task": "finance.not_a_real_task", "domain": "finance", "score": 1,
         "tier": "simple", "contract_sha256": "0" * 16})
    out = tmp_path / "tasks"
    out.mkdir()
    (out / "tiers-manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="not_a_real_task"):
        tiers.refreeze(CORPUS, out=out)


def test_the_frozen_sets_match_the_corpus_right_now():
    """The repository state itself: no drift between tasks/ and corpus/."""
    corpus = {}
    for d in CORPUS:
        for p in d.glob("*.json"):
            task = json.loads(p.read_text(encoding="utf-8"))
            corpus[task["task"]] = task["contract_sha256"]
    for name in tiers.SET_NAMES:
        for p in sorted((ROOT / "tasks" / name).glob("*.json")):
            task = json.loads(p.read_text(encoding="utf-8"))
            assert task["contract_sha256"] == corpus[task["task"]], p.name
