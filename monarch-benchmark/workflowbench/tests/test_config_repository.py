"""Repository transactions and immutable snapshots, without GitHub or paid calls."""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from wb_orchestrator import config_repository as cr


ROOT = Path(__file__).resolve().parents[1]


def files():
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
            for p in (ROOT / "config").rglob("*") if p.is_file()}


class GitAPI:
    def __init__(self):
        self.head = "a" * 40
        self.content = files()
        self.commits = {self.head: dict(self.content)}
        self.pending = {}
        self.writes = []
        self.race = False
        self.ambiguous = False

    def __call__(self, method, path, body=None):
        if method == "GET" and path == "git/ref/heads/main":
            return {"object": {"sha": self.head}}
        if method == "GET" and path.startswith("git/commits/"):
            return {"tree": {"sha": path.rsplit("/", 1)[-1]}}
        if method == "GET" and path.startswith("git/trees/"):
            commit = path.split("/")[-1].split("?")[0]
            return {"tree": [{"path": p, "mode": "100644", "type": "blob",
                              "size": len(t.encode()), "sha": self.blob(t)}
                             for p, t in self.commits[commit].items()]}
        if method == "GET" and path.startswith("git/blobs/"):
            sha = path.rsplit("/", 1)[-1]
            text = next(t for data in self.commits.values() for t in data.values() if self.blob(t) == sha)
            return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
        self.writes.append((method, path, body))
        if path == "git/trees":
            self.pending = dict(self.commits[body["base_tree"]])
            for entry in body["tree"]:
                if entry.get("sha", "present") is None:
                    self.pending.pop(entry["path"], None)
                else:
                    self.pending[entry["path"]] = entry["content"]
            return {"sha": "b" * 40}
        if path == "git/commits":
            self.commits["c" * 40] = dict(self.pending)
            return {"sha": "c" * 40}
        if path == "git/refs/heads/main":
            assert body["force"] is False
            if self.race:
                self.head = "d" * 40
                raise cr.Conflict("Main changed")
            self.head = body["sha"]
            if self.ambiguous:
                raise cr.RepositoryError("Response lost")
            return {"object": {"sha": self.head}}
        raise AssertionError((method, path))

    @staticmethod
    def blob(text):
        data = text.encode()
        return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def repo(tmp_path):
    api = GitAPI()
    return cr.Repository("TestBoxLab/ailabls-benchmark-config", "test-token", tmp_path, request=api), api


def test_full_current_tree_validates_without_credentials(tmp_path):
    r, api = repo(tmp_path)
    snapshot = r.snapshot()
    assert snapshot["commit"] == api.head
    problems = cr.validate_files({f["path"]: f["text"] for f in snapshot["files"]})
    assert len(problems) == 4
    assert all("achievable-50-" in p and "missing harness monarch-" in p for p in problems)
    assert r.validate(snapshot["commit"], [])["valid"]
    for f in snapshot["files"]:
        assert (Path(snapshot["directory"]) / f["path"]).read_text(encoding="utf-8") == f["text"]


def test_atomic_save_preserves_old_snapshot_and_noop_has_no_commit(tmp_path):
    r, api = repo(tmp_path)
    old = r.snapshot()
    path = "config/models/gpt-5.6-sol.yaml"
    original = api.content[path]
    changed = original + "\n# Reviewed model configuration.\n"
    result = r.save(old["commit"], [{"path": path, "text": changed}], "Review model", "Carlos")
    assert result["commit"] == "c" * 40
    assert (Path(old["directory"]) / path).read_text(encoding="utf-8") == original
    before = len(api.writes)
    assert r.save(result["commit"], [{"path": path, "text": changed}], "No change", "Carlos")["commit"] == result["commit"]
    assert len(api.writes) == before


def test_conflicting_save_never_forces_remote_ref(tmp_path):
    r, api = repo(tmp_path)
    api.race = True
    with pytest.raises(cr.Conflict):
        r.save(api.head, [{"path": "config/README.md", "text": "Changed\n"}], "Edit docs", "Carlos")
    assert api.head == "d" * 40


def test_ambiguous_ref_write_is_confirmed_by_read_not_repeated(tmp_path):
    r, api = repo(tmp_path)
    api.ambiguous = True
    result = r.save(api.head, [{"path": "config/README.md", "text": "Changed\n"}], "Edit docs", "Carlos")
    assert result["commit"] == "c" * 40
    assert sum(path == "git/refs/heads/main" for _, path, _ in api.writes) == 1


@pytest.mark.parametrize("path", ["../config/a.yaml", "config/../secret.yaml", "config/models/../../a.yaml", "config/models/a.py", "config/models/A:bad.yaml"])
def test_unsafe_paths_rejected(path, tmp_path):
    r, api = repo(tmp_path)
    with pytest.raises(ValueError):
        r.save(api.head, [{"path": path, "text": "bad"}], "Edit", "Carlos")
    assert not api.writes


def test_invalid_yaml_and_missing_reference_do_not_write(tmp_path):
    r, api = repo(tmp_path)
    with pytest.raises(ValueError):
        r.save(api.head, [{"path": "config/models/gpt-5.6-sol.yaml", "text": "name: ["}], "Invalid", "Carlos")
    with pytest.raises(ValueError):
        r.save(api.head, [{"path": "config/harnesses/api.yaml", "text": None}], "Missing dependency", "Carlos")
    assert not api.writes


def test_editing_a_historical_invalid_plan_requires_fixing_its_references(tmp_path):
    r, api = repo(tmp_path)
    path = "config/plans/achievable-50-request.yaml"
    with pytest.raises(ValueError, match="missing harness"):
        r.save(api.head, [{"path": path, "text": api.content[path] + "\n# edited\n"}], "Edit plan", "Carlos")
    assert not api.writes


def test_restore_rejects_tampered_bytes_and_cache(tmp_path):
    r, _ = repo(tmp_path)
    snapshot = r.snapshot()
    source = {k: v for k, v in snapshot.items() if k != "directory"}
    source["files"][0]["text"] += "tampered"
    with pytest.raises(ValueError):
        cr.restore_snapshot(source, tmp_path / "restore")
    snapshot = r.snapshot()
    (Path(snapshot["directory"]) / snapshot["files"][0]["path"]).write_text("corrupted", encoding="utf-8")
    with pytest.raises(ValueError):
        r.snapshot(snapshot["commit"])


def test_oversized_save_is_rejected_before_git_mutation(tmp_path, monkeypatch):
    r, api = repo(tmp_path)
    r.snapshot()
    monkeypatch.setattr(cr, "MAX_TREE", sum(len(t.encode()) for t in api.content.values()) + 10)
    with pytest.raises(ValueError, match="large"):
        r.save(api.head, [{"path": "config/README.md", "text": api.content["config/README.md"] + "x" * 100}], "Large edit", "Carlos")
    assert not api.writes


def test_empty_tree_cannot_be_published(tmp_path):
    r, api = repo(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        r.save(api.head, [{"path": p, "text": None} for p in api.content], "Delete everything", "Carlos")
    assert not api.writes


def test_migration_preserves_raw_line_endings_and_refuses_overwrite(tmp_path):
    from scripts.migrate_benchmark_config import prepare
    source = tmp_path / "original"
    source.mkdir()
    raw = b"# Original documentation\r\nDo not normalize evidence.\r\n"
    (source / "README.md").write_bytes(raw)
    target = tmp_path / "associated-repo"
    manifest = prepare(source, target)
    assert (target / "config/README.md").read_bytes() == raw
    assert manifest["files"]["config/README.md"] == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="empty"):
        prepare(source, target)


@pytest.fixture
def offline_source(tmp_path, monkeypatch):
    source = {"repository": cr.REPOSITORY, "branch": "main", "commit": "a" * 40,
              "files": cr._records({"config/README.md": "Reviewed configuration.\r\n"})}
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    env = {"WB_CONFIG_SNAPSHOT": str(path), "WB_CONFIG_CACHE": str(tmp_path / "cache"),
           "WB_CONFIG_REPOSITORY": cr.REPOSITORY, "WB_CONFIG_GITHUB_TOKEN": "unused"}
    monkeypatch.setattr(cr.Repository, "_request", lambda *a: pytest.fail("Offline source used GitHub"))
    monkeypatch.setattr(cr.subprocess, "run", lambda *a, **k: pytest.fail("Offline source used gh"))
    return path, source, env


def test_offline_snapshot_reads_exact_bytes_and_refuses_writes(offline_source):
    _, source, env = offline_source
    env.pop("WB_CONFIG_REPOSITORY")
    reader = cr.Repository.from_env(env=env)
    assert reader.repository == cr.REPOSITORY and reader.token is None
    snapshot = reader.snapshot()
    assert snapshot["commit"] == source["commit"]
    assert (Path(snapshot["directory"]) / "config/README.md").read_bytes() == source["files"][0]["text"].encode()
    assert reader.snapshot(source["commit"]) == snapshot
    with pytest.raises(ValueError, match="commit"):
        reader.snapshot("b" * 40)
    with pytest.raises(ValueError, match="read-only"):
        reader.validate(source["commit"], [])
    with pytest.raises(ValueError, match="read-only"):
        reader.save(source["commit"], [], "Edit", "Carlos")
    (Path(snapshot["directory"]) / "config/README.md").write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        reader.snapshot()


@pytest.mark.parametrize("invalid", ["missing", "json", "identity", "branch", "commit", "hash", "path", "empty", "oversized"])
def test_offline_snapshot_fails_closed(offline_source, invalid, monkeypatch):
    path, source, env = offline_source
    if invalid == "missing":
        path.unlink()
    elif invalid == "json":
        path.write_text("{")
    else:
        if invalid == "identity": source["repository"] = "unrelated/repository"
        if invalid == "branch": source["branch"] = "other"
        if invalid == "commit": source["commit"] = "main"
        if invalid == "hash": source["files"][0]["text"] += "changed"
        if invalid == "path": source["files"][0]["path"] = "config/../../outside"
        if invalid == "empty": source["files"] = []
        if invalid == "oversized": monkeypatch.setattr(cr, "MAX_TREE", 1)
        path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(cr.RepositoryError):
        cr.Repository.from_env(env=env)
