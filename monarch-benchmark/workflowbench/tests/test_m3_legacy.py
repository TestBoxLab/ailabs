"""M3 tests: legacy importer mapping, side-by-side queries, pooling refusal."""
from __future__ import annotations

import json

import pytest

from legacy.importer import LEGACY_SUITE, import_runs, normalize_effort
from runner.schema import EpisodeRow, TokenUsage
from wb_report.report import GateError, build_report
from wb_results.store import Store


def _summary_record(task="finance.airtable_expense_approval", arm="passthrough",
                    model="claude-opus-5", strict=True, status="completed", **over):
    rec = {
        "arm": arm, "model": model, "reasoning_effort": "xhigh", "status": status,
        "task_id": task, "position": 1, "replicate": 0, "wall_seconds": 63.2,
        "enforced_cost_usd": 0.0953, "provider_tokens": 3288, "provider_calls": 5,
        "config_raw_sha256": "0b11d767a972c60a8194216547c392f6",
        "integrity_issues": [],
        "canonical": {"strict_min": strict, "strict_max": strict,
                      "positive_passed": 5 if strict else 3, "positive_total": 5,
                      "guard_violations": 0, "guard_unknown": 0},
    }
    rec.update(over)
    return rec


@pytest.fixture()
def legacy_tree(tmp_path):
    runs = tmp_path / "runs"
    d1 = runs / "run-a"; d1.mkdir(parents=True)
    (d1 / "merged-run-summary.json").write_text(json.dumps(
        [_summary_record(strict=True), _summary_record(task="hr.t2", strict=False)]))
    # shard summaries must NOT be double-counted when a merged file exists
    sh = d1 / "shard-0"; sh.mkdir()
    (sh / "run-summary.json").write_text(json.dumps([_summary_record()]))
    d2 = runs / "run-b"; d2.mkdir()
    (d2 / "run-summary.json").write_text(json.dumps([_summary_record(task="sales.t3")]))
    d3 = runs / "run-empty"; d3.mkdir()      # no summary -> skipped, reported
    return runs


def test_effort_normalization():
    assert normalize_effort("xhigh") == "high"
    assert normalize_effort("max") == "high"
    assert normalize_effort("medium") == "medium"
    assert normalize_effort(None) is None


def test_import_maps_rows_with_flags_not_guesses(tmp_path, legacy_tree):
    store = Store(tmp_path / "wb.sqlite3")
    res = import_runs(store, legacy_tree)
    assert res == {"runs_imported": 2, "rows_imported": 3,
                   "dirs_skipped": ["run-empty"], "suite": LEGACY_SUITE}
    rows = store.episodes(suite=LEGACY_SUITE)["rows"]
    assert len(rows) == 3
    r = next(x for x in rows if x["task_id"] == "finance.airtable_expense_approval")
    assert r["arm"] == "legacy/passthrough@claude-opus-5/high"   # xhigh normalized
    assert r["passed"] is True and r["termination"] == "completed"
    assert r["tokens"] is None                                    # unsplit -> null
    assert "tokens_unsplit" in r["flags"] and "legacy_import" in r["flags"]
    assert r["cost_usd"] == pytest.approx(0.0953)
    failed = next(x for x in rows if x["task_id"] == "hr.t2")
    assert failed["passed"] is False and failed["assertions_passed"] is False


def test_legacy_and_new_rows_side_by_side_never_pooled(tmp_path, legacy_tree):
    store = Store(tmp_path / "wb.sqlite3")
    import_runs(store, legacy_tree)
    store.create_run("run-new", "cfg", "workflowbench-synthetic@0.1",
                     {"suite_dir": "tasks", "arms": ["a"], "k": 1, "n_tasks": 1,
                      "timeout_s": 600})
    store.record_episode(EpisodeRow(
        episode_id="run-new/t1/a/t0", run_id="run-new", task_id="t1", arm="a",
        trial=0, passed=True, assertions_passed=True, invariant_passed=True,
        invariant_declared=True, tokens=TokenUsage(prompt=10, cached=5, output=1)))

    # one query, both suites visible, labels intact
    both = store.episodes()
    suites = {r["suite"] for r in both["rows"]}
    assert suites == {LEGACY_SUITE, "workflowbench-synthetic@0.1"}
    assert both["source"]["denominator"] == 4

    # report builder refuses cross-suite pooling: a legacy-suite row smuggled
    # into a new run's arm must raise, never render
    store.record_episode(EpisodeRow(
        episode_id="run-new/t2/a/t0", run_id="run-new", task_id="t2", arm="a",
        suite=LEGACY_SUITE, trial=0, passed=True, assertions_passed=True,
        invariant_passed=True, invariant_declared=False))
    with pytest.raises(GateError, match="pool"):
        build_report(store, "run-new", audience="internal")


def test_import_is_idempotent(tmp_path, legacy_tree):
    store = Store(tmp_path / "wb.sqlite3")
    import_runs(store, legacy_tree)
    res2 = import_runs(store, legacy_tree)          # INSERT OR REPLACE + same ids
    assert res2["rows_imported"] == 3
    assert len(store.episodes(suite=LEGACY_SUITE)["rows"]) == 3
