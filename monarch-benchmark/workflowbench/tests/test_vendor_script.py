"""scripts/vendor_automation_bench.py: copy a repaired AutomationBench tree into
vendor/automation-bench, refusing the wrong version and leaving caches behind.

Everything here runs on a tiny fake source tree; the real candidate is never
touched by a test.
"""
from __future__ import annotations

import hashlib

import pytest

from scripts import vendor_automation_bench as vab


def _fake_source(root, version="1.0.6+evalrepair.10"):
    """A source tree with the files that must be copied and the ones that must not."""
    src = root / "candidate"
    wanted = {
        "pyproject.toml": f'[project]\nname = "automation-bench"\nversion = "{version}"\n',
        "automationbench/__init__.py": "VERSION = 'x'\n",
        "automationbench/domains/_evalrepair10.py": "# repair\n",
        "tests/test_a.py": "def test_a(): pass\n",
        "adjudication/ledger.json": "{}\n",
        ".gitignore": "*.log\n",
    }
    unwanted = {
        ".git/HEAD": "ref: refs/heads/main\n",
        ".venv/Lib/site-packages/pkg.py": "x\n",
        "automationbench/__pycache__/__init__.cpython-313.pyc": "bytes\n",
        "candidate-pytest.log": "1940 passed\n",
        "candidate-ruff.log": "All checks passed!\n",
        ".pytest_cache/v/cache/nodeids": "[]\n",
        ".ruff_cache/CACHEDIR.TAG": "x\n",
    }
    for rel, text in {**wanted, **unwanted}.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return src, sorted(wanted), sorted(unwanted)


def test_refuses_a_version_other_than_the_expected_one(tmp_path):
    src, _, _ = _fake_source(tmp_path, version="1.0.6")
    dest = tmp_path / "vendor" / "automation-bench"
    with pytest.raises(vab.VendorError) as e:
        vab.vendor(src, dest, expect_version="1.0.6+evalrepair.10")
    msg = str(e.value)
    assert "1.0.6+evalrepair.10" in msg and "1.0.6" in msg    # both versions named
    assert not dest.exists()                                    # nothing copied


def test_copies_the_tree_without_caches_logs_or_git(tmp_path):
    src, wanted, unwanted = _fake_source(tmp_path)
    dest = tmp_path / "vendor" / "automation-bench"
    summary = vab.vendor(src, dest, expect_version="1.0.6+evalrepair.10",
                         tree_id="7ac9559eb65540feac74d5d12c37406b4d69fd56")

    for rel in wanted:
        assert (dest / rel).is_file(), rel
    for rel in unwanted:
        assert not (dest / rel).exists(), rel
    assert not (dest / ".git").exists() and not (dest / ".venv").exists()

    assert summary["files"] == len(wanted)
    assert summary["version"] == "1.0.6+evalrepair.10"
    record = (dest / vab.RECORD_NAME).read_text(encoding="utf-8")
    assert f"source: {src.resolve().as_posix()}" in record
    assert "expected_version: 1.0.6+evalrepair.10" in record
    pyproject_sha = hashlib.sha256((src / "pyproject.toml").read_bytes()).hexdigest()
    assert f"pyproject_sha256: {pyproject_sha}" in record
    assert f"files: {len(wanted)}" in record
    assert "source_tree_id: 7ac9559eb65540feac74d5d12c37406b4d69fd56" in record
    assert "vendored_at: 20" in record                          # an ISO date
    assert f"tree_sha256: {summary['tree_sha256']}" in record
    # the record itself is not one of the counted files, and the hash covers
    # exactly the copied files, so a second copy of the same source agrees
    assert vab.tree_sha256(dest) == summary["tree_sha256"]


def test_tree_hash_changes_when_a_file_changes(tmp_path):
    src, _, _ = _fake_source(tmp_path)
    dest = tmp_path / "vendor" / "automation-bench"
    before = vab.vendor(src, dest, expect_version="1.0.6+evalrepair.10")["tree_sha256"]
    (src / "automationbench" / "__init__.py").write_text("VERSION = 'y'\n", encoding="utf-8")
    after = vab.vendor(src, dest, expect_version="1.0.6+evalrepair.10",
                       replace=True)["tree_sha256"]
    assert before != after


def test_refuses_to_overwrite_an_existing_copy_unless_asked(tmp_path):
    src, wanted, _ = _fake_source(tmp_path)
    dest = tmp_path / "vendor" / "automation-bench"
    dest.mkdir(parents=True)
    (dest / "old-file.txt").write_text("from the previous world\n", encoding="utf-8")

    with pytest.raises(vab.VendorError, match="--replace"):
        vab.vendor(src, dest, expect_version="1.0.6+evalrepair.10")
    assert (dest / "old-file.txt").exists()                     # untouched

    vab.vendor(src, dest, expect_version="1.0.6+evalrepair.10", replace=True)
    assert not (dest / "old-file.txt").exists()                 # the old copy is gone
    for rel in wanted:
        assert (dest / rel).is_file(), rel


def test_refuses_a_source_without_a_pyproject(tmp_path):
    src = tmp_path / "empty"
    src.mkdir()
    with pytest.raises(vab.VendorError, match="pyproject.toml"):
        vab.vendor(src, tmp_path / "dest", expect_version="1.0.6+evalrepair.10")
    assert not (tmp_path / "dest").exists()


def test_cli_prints_a_summary_and_exit_codes(tmp_path, capsys):
    src, wanted, _ = _fake_source(tmp_path)
    dest = tmp_path / "vendor" / "automation-bench"

    assert vab.main(["--source", str(src), "--dest", str(dest),
                     "--expect-version", "1.0.6+evalrepair.10"]) == 0
    out = capsys.readouterr().out
    assert "1.0.6+evalrepair.10" in out and f"files: {len(wanted)}" in out
    assert dest.as_posix() in out

    # the wrong version is refused with exit 2 and nothing more is written
    src2, _, _ = _fake_source(tmp_path / "other", version="2.0.0")
    assert vab.main(["--source", str(src2), "--dest", str(tmp_path / "dest2"),
                     "--expect-version", "1.0.6+evalrepair.10"]) == 2
    assert "2.0.0" in capsys.readouterr().err
    assert not (tmp_path / "dest2").exists()
