"""The Monarch competitor is named from its checkout (US1, T023).

The row name is the version read from the Monarch repo -- `monarch@<sha>`, plus
`+<branch>` off main -- so a report always says which build was measured. A
`monarch_repo` that is not a git checkout is a config error, not a crash.
"""
from __future__ import annotations

import subprocess

import pytest

from tests.test_config import site  # noqa: F401  (site is a fixture)
from tests.test_run_config import monarch_site, resolve_monarch
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import build_arm_for


def git(repo, *args) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A one-commit git repo standing in for the Monarch checkout, on `main`."""
    d = tmp_path / "monarch"
    d.mkdir()
    git(d, "init", "-q")
    git(d, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "--allow-empty", "-q", "-m", "x")
    git(d, "checkout", "-q", "-B", "main")
    return d


def monarch_arm(site, repo_path):
    """Build the Monarch competitor of a resolved plan pointed at `repo_path`."""
    monarch_site(site, monarch_repo=str(repo_path))
    rc = resolve_monarch(site)
    competitor = next(c for c in rc.competitors if c.harness.kind == "monarch")
    return build_arm_for(competitor, rc)


def test_arm_is_named_for_the_checked_out_commit(site, repo):
    arm = monarch_arm(site, repo)
    assert arm.name == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}"
    assert arm.model_label == arm.name


def test_a_branch_off_main_is_part_of_the_name(site, repo):
    git(repo, "checkout", "-q", "-b", "lab")
    arm = monarch_arm(site, repo)
    assert arm.name == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}+lab"
    assert arm.model_label == arm.name


def test_a_path_that_is_not_a_checkout_is_a_config_error(site, tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    with pytest.raises(ConfigError) as exc:
        monarch_arm(site, not_a_repo)
    assert exc.value.path == str(site / "config/harnesses/monarch.yaml")
    assert exc.value.field == "monarch_repo"
    assert "version" in str(exc.value)
