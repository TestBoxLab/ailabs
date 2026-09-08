"""BRIDGE v2 + v9.12 inventory: hashes in the original layout, missing components stay missing."""
import hashlib
import json

from wb_arms import runtime_manifest as rm
from wb_studio import provenance


def seed(tmp_path):
    main, codex = tmp_path / "Monarch_Main", tmp_path / "codex"
    files = {
        codex / "vendor-patch-output/scripts/vendor-monarch-graph-inline-v6.ts": "producer",
        codex / "vendor-patch-work/scripts/vendor-monarch-graph-inline-v6.ts": "producer-work-copy",
        main / "AutomationBench-repair/adjudication/microscopic-brittleness-358-v1.json": '{"tasks": []}',
        main / "AB-5a0dea3-clean/adjudication/microscopic-brittleness-358-v1.json": '{"tasks": []}',
        main / "ATLAS/backend/data/bench/bridge-v8/zapier-wired273-4a8e106-manifest-v1/capability-manifest-v1.json": "{}",
        main / "ATLAS/backend/scripts/dev/automationbench-shim.ts": "doctrine",
        main / "AutomationBench-repair/automationbench/tools/zapier/slack/users.py": "current slack",
        main / "Monarch_Report.html": "<html>v9.12</html>",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (main / "AB-5a0dea3-clean").mkdir(exist_ok=True)
    (main / "AutomationBench-repair").mkdir(exist_ok=True)
    return {"monarch_main": str(main), "codex": str(codex)}


def git(repository, revision, path):
    if path == "pyproject.toml":
        return b'version = "1.0.6+evalrepair.10"\n'
    if path.endswith("slack/users.py"):
        return b"current slack" if revision in ("5a0dea3", "f7acf6a") else b"older slack"
    return None


def test_inventory_hashes_found_files_and_keeps_missing_components_missing(tmp_path):
    record = provenance.inventory(seed(tmp_path), git=git)
    by_role = {e["role"]: e for e in record["entries"]}
    assert by_role["graph_producer"]["status"] == "present" and "differ" in by_role["graph_producer"]["note"]
    assert by_role["reviewed_tasks_358"]["status"] == "present" and "note" not in by_role["reviewed_tasks_358"]
    assert by_role["report"]["found"][0]["sha256"] == hashlib.sha256(b"<html>v9.12</html>").hexdigest()
    assert by_role["extension_source_slack"]["status"] == "present_unpinned"
    assert by_role["extension_source_slack"]["matching_revisions"] == ["5a0dea3", "f7acf6a"]
    assert by_role["suite_revision_evalrepair10"]["status"] == "present"
    for role in ("actor_contract", "source_provenance", "generated_graph", "run_manifests_600", "reviewed_catalog"):
        assert by_role[role]["status"] == "missing" and by_role[role]["found"] == []
    assert set(record["missing_required"]) >= {"actor_contract", "source_provenance", "generated_graph", "run_manifests_600"}
    assert record["readiness"]["source"] == record["readiness"]["runtime"] == "source_required"
    assert record["report_claims"]["status"] == "unverified" and record["report_claims"]["treatment"]["completed"] == 361
    manifest = rm.validate(record["runtime_manifest"])
    assert manifest["artifacts"]["generated_graph"]["status"] == "missing"
    assert manifest["artifacts"]["shim_doctrine"]["status"] == "present"
    assert manifest["evaluation"]["model"] == "claude-opus-5" and manifest["evaluation"]["effort"] == "medium"


def test_write_bundle_produces_manifest_and_readable_report(tmp_path):
    folder = tmp_path / "research" / "architectures" / "bridge-v2-v9.12"
    record = provenance.write_bundle(folder, seed(tmp_path))
    stored = json.loads((folder / "source-manifest.json").read_text(encoding="utf-8"))
    assert stored["summary"] == record["summary"] and stored["identity"] == "bridge-v2-v9.12"
    text = (folder / "provenance-report.md").read_text(encoding="utf-8")
    assert "| generated_graph | missing |" in text
    assert "reconstructed candidate, never a reproduction" in text
    assert "5a0dea3" in text


def test_missing_roots_do_not_crash_the_inventory(tmp_path):
    record = provenance.inventory({"monarch_main": str(tmp_path / "nowhere"), "codex": str(tmp_path / "nowhere")}, git=lambda *a: None)
    assert record["summary"]["present"] == 0 and record["summary"]["missing"] == len(record["entries"])
