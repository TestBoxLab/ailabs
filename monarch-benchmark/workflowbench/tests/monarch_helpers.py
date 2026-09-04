"""Shared setup for the Monarch tests: a config site, an arm, ports, a checkout.

`test_run_config.py` and `test_monarch_arm.py` both need these; they live here
so neither test module has to import the other.
"""
from __future__ import annotations

import socket
import subprocess

import pytest

from tests.test_config import ENV, PRICE_TABLE, edit, runnable_monarch, write
from wb_orchestrator import config
from wb_orchestrator.orchestrator import build_arm_for

KB = """\
product: simulated-apps
generated_at: 2026-09-04T12:00:00Z
seeds_format: public-api-seeds@1
shim_public_url: http://host.docker.internal:9105
kb:
  bench-airtable: 6d07bde6f1c2
  bench-asana: 272673e3a9b0
  bench-gmail: 9b1f0c4a5e77
  bench-salesforce: 3c2e8d90aa41
"""

# Everything the Monarch competitor needs before a run may start: the session,
# the addresses written as placeholders, and the Langfuse keys. No MONARCH_TOKEN:
# the fake backend only accepts a session it issued, so the arm has to log in.
MONARCH_ENV = {**{k: v for k, v in ENV.items() if k != "MONARCH_TOKEN"},
               "MONARCH_PASSWORD": "monarch-dev",
               "MONARCH_URL": "http://127.0.0.1:4174",
               "MONARCH_FD_URL": "http://127.0.0.1:3001",
               "LANGFUSE_URL": "http://127.0.0.1:3000",
               "LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}


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


def free_port() -> int:
    """A port nothing listens on right now (the front door binds a fixed one)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def free(port: int) -> None:
    """Assert the front door let go of its fixed port."""
    s = socket.socket()
    s.bind(("0.0.0.0", port))
    s.close()


def monarch_site(site, kb=KB, monarch_repo=None):
    """The `site` fixture with a runnable Monarch competitor, its price table and its kb file."""
    runnable_monarch(site, modes="[create-run]", monarch_repo=monarch_repo)
    write(site / "config/models", PRICE_TABLE)
    if kb is not None:
        (site / "config/products/simulated-apps.monarch-kb.yaml").write_text(kb)
    return site


def resolve_monarch(site, env=MONARCH_ENV):
    return config.resolve(site / "config/products/simulated-apps.yaml",
                          site / "config/plans/smoke-frontier.yaml",
                          env=env, audiences={"internal": ["*"]})


def arm_against(site, fake, port, repo, fd=None, kb=KB, env=None, langfuse=None):
    """A Monarch arm whose harness points at the fakes on their real ports."""
    monarch_site(site, kb=kb, monarch_repo=str(repo))
    text = (site / "config/harnesses/monarch.yaml").read_text()
    text = (edit(text, "base_url", fake.url)
            .replace("shim_port: 9105", f"shim_port: {port}")
            .replace("shim_public_host: host.docker.internal", "shim_public_host: 127.0.0.1"))
    if fd is not None:
        text = edit(text, "fd_url", fd.url)
    if langfuse is not None:
        text = edit(text, "langfuse_url", langfuse.url)
    write(site / "config/harnesses", text)
    env = env or MONARCH_ENV
    rc = resolve_monarch(site, env=env)
    competitor = next(c for c in rc.competitors if c.harness.kind == "monarch")
    arm = build_arm_for(competitor, rc)
    # build_arm_for hands the arm os.environ; the test's env is the one that
    # names the fakes, so the arm must read that instead.
    arm.env = env
    return arm


# -- 004: a run-only site --------------------------------------------------

RECIPES = """\
product: simulated-apps
tasks: {tasks}
generated_at: '2026-09-04T12:00:00Z'
kb_hash_file_sha: 9f2c1d0ea3b47856c9d2e0f1a4b6c8d90e2f4a6b8c0d2e4f6a8b0c2d4e6f8a0b
monarch: monarch@1a2b3c4
recipes:
  simple.email_sf_contact_city_update:
    workflow_id: wf-1
    recipe_version: 3
    authored_at: '2026-09-04T12:03:11Z'
    attempts_used: 1
  simple.sf_opp_closed_won:
    workflow_id: wf-2
    recipe_version: 2
    authored_at: '2026-09-04T12:09:40Z'
    attempts_used: 3
missing: {{}}
"""


def run_only_site(site, recipes=RECIPES, kb=KB, monarch_repo=None):
    """`monarch_site` with the plan in run-only mode and a recipes file beside the product."""
    monarch_site(site, kb=kb, monarch_repo=monarch_repo)
    runnable_monarch(site, modes="[create-run, run-only]", monarch_repo=monarch_repo)
    plan = (site / "config/plans/smoke-frontier.yaml").read_text()
    write(site / "config/plans", plan.replace("mode: create-run", "mode: run-only"))
    if recipes is not None:
        tasks = config.load_plan(site / "config/plans/smoke-frontier.yaml").tasks
        (site / "config/products/simulated-apps.monarch-recipes.yaml").write_text(
            recipes.format(tasks=f'"{tasks}"'))
    return site
