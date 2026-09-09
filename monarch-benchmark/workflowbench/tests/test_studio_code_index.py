"""Offline contracts for the daily Monarch code index and Genesis's read-only code tools."""
import json
import shutil
import subprocess

import pytest

from wb_studio import code_index
from wb_studio.app import ROOT, Studio
from wb_studio.scheduler import Scheduler
from wb_world.episode import load_suite


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   text=True, encoding="utf-8", capture_output=True, check=True)


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, encoding="utf-8",
                          capture_output=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A tiny Monarch-shaped checkout: two commits, a route added and a version bumped in the second."""
    repo = tmp_path / "monarch"
    src = repo / "monarch-enterprise" / "apps" / "backend" / "src"
    (src / "graphs").mkdir(parents=True)
    (src / "graphs" / "graphs.service.ts").write_text("export class GraphsService {\n  load() { return 1; }\n}\n", encoding="utf-8")
    (repo / "package.json").write_text(json.dumps({"name": "monarch", "version": "1.0.0"}), encoding="utf-8")
    (repo / "README.md").write_text("Monarch\n", encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "first")
    git(repo, "remote", "add", "origin", str(tmp_path / "no-such-remote"))  # fetch fails; the job carries on
    return repo


def second_commit(repo):
    src = repo / "monarch-enterprise" / "apps" / "backend" / "src"
    (src / "graphs" / "graphs.controller.ts").write_text(
        "export class GraphsController {\n  @Get('graphs/:id')\n  find() {}\n}\n", encoding="utf-8")
    (src / "migrations").mkdir()
    (src / "migrations" / "001-graphs.sql").write_text("create table graphs;\n", encoding="utf-8")
    (repo / "package.json").write_text(json.dumps({"name": "monarch", "version": "1.1.0"}), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "second")


@pytest.fixture
def studio(tmp_path, repo, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)  # Graphify is not installed here
    def forbidden_gateway(*args, **kwargs):
        pytest.fail("An offline code-index test attempted paid dispatch")
    app = Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1], gateway_factory=forbidden_gateway)
    app.enterprise_env = {"MONARCH_REPO": str(repo)}
    return app


def test_settings_follow_the_declared_build(studio):
    assert code_index.settings(studio)["ref"] == "main"
    studio.enterprise_env = {**studio.enterprise_env, "MONARCH_BUILD": "monarch@2ede4b3e+feat/railway-dev-deploy"}
    assert code_index.settings(studio)["ref"] == "feat/railway-dev-deploy"
    studio.enterprise_env = {**studio.enterprise_env, "MONARCH_BUILD_COMMIT": "2ede4b3ee355da81c253087e8c9583ed677c06fa"}
    assert code_index.settings(studio)["ref"] == "2ede4b3ee355da81c253087e8c9583ed677c06fa"
    assert code_index.settings(studio)["out"] == studio.directory / "genesis" / "code-index"


def test_refresh_indexes_records_changes_and_files_one_library_record(studio, repo):
    first = code_index.refresh(studio)
    assert first["status"] == "completed" and first["commit"] == head(repo) and not first["changed"]
    assert first["fetch"].startswith("failed")  # no remote; recorded, not raised
    out = studio.directory / "genesis" / "code-index"
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["files"][".ts"] == 1 and index["tracked_files"] == 3 and index["previous_commit"] is None
    assert index["graphify"] == {"available": False, "report": None, "built_from": None}
    assert not studio.genesis.library.listing(topic="Code understanding")

    second_commit(repo)
    second = code_index.refresh(studio)
    assert second["changed"] and second["previous_commit"] == first["commit"]
    record = json.loads((out / "changes.json").read_text(encoding="utf-8"))
    assert record["from"] == first["commit"] and record["to"] == head(repo) and record["total"] == 3
    assert record["versions"] == [{"package": "package.json", "from": "1.0.0", "to": "1.1.0"}]
    assert record["migrations"] == ["monarch-enterprise/apps/backend/src/migrations/001-graphs.sql"]
    assert record["routes"]["added"] == [{"path": "monarch-enterprise/apps/backend/src/graphs/graphs.controller.ts", "text": "@Get('graphs/:id')"}]
    assert record["backend"] == {"graphs": 1, "migrations": 1}
    md = (out / "MONARCH.md").read_text(encoding="utf-8")
    assert len(md) <= 2500 and head(repo) in md and "3 files changed" in md and "1.0.0 to 1.1.0" in md
    assert "Graphify is not installed" in md
    sources = studio.genesis.library.listing(topic="Code understanding")
    assert len(sources) == 1 and sources[0]["source_type"] == "repo" and sources[0]["url"] == f"{repo}@{head(repo)}"
    assert sources[0]["title"].startswith("Monarch changes ") and "3 files in" in sources[0]["title"]

    third = code_index.refresh(studio)
    assert not third["changed"] and "library_record" not in third
    assert len(studio.genesis.library.listing(topic="Code understanding")) == 1
    assert json.loads((out / "changes.json").read_text(encoding="utf-8")) == record  # the last real change is kept


def test_refresh_never_raises_without_a_checkout(studio, tmp_path):
    studio.enterprise_env = {"MONARCH_REPO": str(tmp_path / "nowhere")}
    assert code_index.refresh(studio)["status"] == "skipped"


def test_code_tools_are_read_only_and_internal(studio, repo):
    genesis = studio.genesis
    before = genesis.tool("code_status", {})
    assert before["indexed"] is False and before["audience"] == "internal"
    code_index.refresh(studio)
    status = genesis.tool("code_status", {})
    assert status["indexed"] and status["commit"] == head(repo) and status["graphify"]["available"] is False
    assert status["monarch_md"].startswith("# Monarch")

    found = genesis.tool("code_search", {"query": "load()", "limit": 5})
    assert found["hits"] == [{"path": "monarch-enterprise/apps/backend/src/graphs/graphs.service.ts", "line": 2, "text": "load() { return 1; }"}]
    assert found["graph"] == [] and found["audience"] == "internal"
    with pytest.raises(ValueError):
        genesis.tool("code_search", {"query": "x"})

    explained = genesis.tool("code_explain", {"symbol": "GraphsService"})
    assert explained["definitions"][0]["path"].endswith("graphs.service.ts") and explained["definitions"][0]["line"] == 1

    page = genesis.tool("code_read", {"path": "package.json"})
    assert page["lines"][0]["line"] == 1 and "monarch" in page["lines"][0]["text"] and page["audience"] == "internal"
    for bad in ("../secret", "/etc/passwd", str(repo / "package.json"), "C:/Windows/win.ini", "missing.ts"):
        with pytest.raises(ValueError):
            genesis.tool("code_read", {"path": bad})

    second_commit(repo)
    fresh = genesis.tool("code_changes", {"since": status["commit"]})
    assert fresh["record"]["total"] == 3 and fresh["record"]["routes"]["added"]
    assert genesis.tool("code_changes", {})["record"] is None  # nothing indexed since the second commit yet


def test_daily_job_is_discovered_and_exposed(studio):
    assert code_index.DAILY == ("code-index", 4, code_index.refresh)
    assert "code-index" in [j["name"] for j in studio.scheduler.jobs]
    scheduler = Scheduler(studio, studio.directory / "genesis" / "schedule-test.json")
    scheduler.discover()
    assert any(j["name"] == "code-index" and j["hour"] == 4 for j in scheduler.jobs)
    entry = studio.scheduler.run("code-index")
    assert entry["status"] == "completed" and entry["summary"]["status"] == "completed"


def test_mcp_allow_list_names_the_code_tools():
    text = (ROOT / "wb_studio" / "genesis_mcp.py").read_text(encoding="utf-8")
    assert all(name in text for name in code_index.TOOLS)
