"""Offline regrading must preserve the original and bind the selected verdict."""
import copy
import json
from pathlib import Path

import pytest

from runner.schema import EpisodeRow
from tests.test_evidence import TASKS, _run
from wb_orchestrator.orchestrator import regrade
from wb_report.report import GateError, build_report


def revised_grader(monkeypatch, artifacts, *, passed=False):
    grading = json.loads(Path(artifacts["grading"]).read_text(encoding="utf-8"))
    grading["passed"] = passed
    grading["assertions_passed"] = passed
    for check in grading["assertion_results"]:
        check["passed"] = passed
    monkeypatch.setattr("wb_orchestrator.orchestrator.grade", lambda *args: copy.deepcopy(grading))


def current(store, row):
    latest = store.episodes(run=row["run_id"])["rows"][0]
    flag = next(value for value in latest["flags"] if value.startswith("grading_revision="))
    revision_id = flag.split(":")[1]
    return latest, Path(store.artifacts(row["episode_id"])["regrade:" + revision_id])


def test_regrade_preserves_original_and_report_selects_hash_bound_revision(tmp_path, monkeypatch):
    store, row = _run(tmp_path, monkeypatch)
    artifacts = store.artifacts(row["episode_id"])
    originals = {kind: Path(artifacts[kind]).read_bytes() for kind in ("grading", "result", "manifest")}
    revised_grader(monkeypatch, artifacts)
    summary = regrade(store, row["run_id"], TASKS)
    assert summary["regraded"] == summary["changed"] == 1
    latest, path = current(store, row)
    assert latest["passed"] is False
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["grading"]["assertions_passed"] is False
    assert record["verdict"]["passed"] is False
    assert record["previous"] is None
    assert record["provenance"]["source_sha256"]["grader/grade.py"]
    assert record["inputs"]["snapshot1"]["sha256"]
    assert record["created_at"]
    for kind, original in originals.items():
        assert Path(artifacts[kind]).read_bytes() == original
    report = build_report(store, row["run_id"])
    selected = report["grading_evidence"][row["episode_id"]]
    assert selected["kind"] == "regrade"
    assert selected["uri"] == str(path)
    assert selected["sha256"] == latest["flags"][-1].split(":")[-1]
    assert report["matrix"]["rows"][0]["cells"][row["arm"]]["passed"] == 0


def test_repeated_regrade_retains_and_validates_previous_chain(tmp_path, monkeypatch):
    store, row = _run(tmp_path, monkeypatch)
    revised_grader(monkeypatch, store.artifacts(row["episode_id"]))
    regrade(store, row["run_id"], TASKS)
    first, first_path = current(store, row)
    first_bytes = first_path.read_bytes()
    revised_grader(monkeypatch, store.artifacts(row["episode_id"]), passed=True)
    assert regrade(store, row["run_id"], TASKS)["changed"] == 1
    second, second_path = current(store, row)
    assert second["passed"] is True
    assert first_path != second_path
    assert first_path.read_bytes() == first_bytes
    assert json.loads(second_path.read_text())["previous"] == first["flags"][-1]
    first_path.write_text("{}", encoding="utf-8")
    with pytest.raises(GateError, match="invalid grading evidence"):
        build_report(store, row["run_id"])
    summary = regrade(store, row["run_id"], TASKS)
    assert summary["evidence_invalid"] == 1 and summary["regraded"] == 0
    assert store.episodes(run=row["run_id"])["rows"][0] == second


@pytest.mark.parametrize("corruption", ["record", "missing", "row_verdict", "snapshot_redirect", "flag"])
def test_corrupt_selected_regrade_is_rejected_by_report_and_regrading(tmp_path, monkeypatch, corruption):
    store, row = _run(tmp_path, monkeypatch)
    revised_grader(monkeypatch, store.artifacts(row["episode_id"]))
    regrade(store, row["run_id"], TASKS)
    latest, path = current(store, row)
    if corruption == "record":
        path.write_text("{}", encoding="utf-8")
    elif corruption == "missing":
        path.unlink()
    elif corruption == "row_verdict":
        latest["passed"] = True
        store.record_episode(EpisodeRow(**latest))
    elif corruption == "snapshot_redirect":
        alternate = tmp_path / "snapshot1.json"
        alternate.write_bytes(Path(store.artifacts(row["episode_id"])["snapshot1"]).read_bytes())
        store.add_artifact(row["episode_id"], "snapshot1", str(alternate))
    else:
        latest["flags"][-1] = "grading_revision=broken"
        store.record_episode(EpisodeRow(**latest))
    before = store.episodes(run=row["run_id"])["rows"]
    with pytest.raises(GateError, match="invalid grading evidence"):
        build_report(store, row["run_id"])
    summary = regrade(store, row["run_id"], TASKS)
    assert summary["evidence_invalid"] == 1 and summary["regraded"] == 0
    assert store.episodes(run=row["run_id"])["rows"] == before


def test_unselected_orphan_revision_does_not_change_report_verdict(tmp_path, monkeypatch):
    store, row = _run(tmp_path, monkeypatch)
    revised_grader(monkeypatch, store.artifacts(row["episode_id"]))
    original_record = store.record_episode
    monkeypatch.setattr(store, "record_episode", lambda value: (_ for _ in ()).throw(OSError("write failed")))
    with pytest.raises(OSError, match="write failed"):
        regrade(store, row["run_id"], TASKS)
    monkeypatch.setattr(store, "record_episode", original_record)
    assert store.episodes(run=row["run_id"])["rows"][0] == row
    assert build_report(store, row["run_id"])["grading_evidence"][row["episode_id"]]["kind"] == "original"
    assert regrade(store, row["run_id"], TASKS)["regraded"] == 1


def test_regrade_preserves_noncompleted_termination_even_when_grader_passes(tmp_path, monkeypatch):
    from wb_arms.api_loop import ArmResult
    class ErrorArm:
        name = "error"
        provider_key = None
        def run(self, ep, deadline=None):
            return ArmResult(termination="agent_error", error="failed")
    store, row = _run(tmp_path, monkeypatch, ErrorArm())
    revised_grader(monkeypatch, store.artifacts(row["episode_id"]), passed=True)
    assert regrade(store, row["run_id"], TASKS)["regraded"] == 1
    latest, path = current(store, row)
    assert latest["passed"] is False
    assert latest["termination"] == "agent_error"
    assert json.loads(path.read_text())["verdict"]["passed"] is False
    build_report(store, row["run_id"])


def test_incomplete_episode_evidence_blocks_regrade_and_report(tmp_path, monkeypatch):
    store, row = _run(tmp_path, monkeypatch)
    row["flags"].append("evidence_incomplete")
    store.record_episode(EpisodeRow(**row))
    summary = regrade(store, row["run_id"], TASKS)
    assert summary["evidence_invalid"] == 1 and summary["regraded"] == 0
    with pytest.raises(GateError, match="evidence is incomplete"):
        build_report(store, row["run_id"])
    assert not (Path(row["artifacts_uri"]) / "regrades").exists()


def test_input_change_during_grading_never_publishes_or_counts_a_changed_verdict(tmp_path, monkeypatch):
    store, row = _run(tmp_path, monkeypatch)
    artifacts = store.artifacts(row["episode_id"])
    grading = json.loads(Path(artifacts["grading"]).read_text())
    grading["passed"] = grading["assertions_passed"] = False
    def changed_input(*args):
        Path(artifacts["snapshot1"]).write_text("{}", encoding="utf-8")
        return grading
    monkeypatch.setattr("wb_orchestrator.orchestrator.grade", changed_input)
    summary = regrade(store, row["run_id"], TASKS)
    assert summary["regraded"] == summary["changed"] == 0
    assert summary["evidence_invalid"] == 1
    assert store.episodes(run=row["run_id"])["rows"][0] == row
    assert not (Path(row["artifacts_uri"]) / "regrades").exists()
