import os
import shutil
import tempfile
from pathlib import Path

import pytest

from tests.mock_openai import MockOpenAIServer
from wb_arms import providers
from wb_arms.providers import Provider
from wb_world import episode


@pytest.fixture(autouse=True)
def no_live_telemetry(monkeypatch):
    """Tests may use local receivers, never the operator's Langfuse project."""
    monkeypatch.setenv("WB_LANGFUSE_ENABLED", "0")


def _clear_provider_keys(names):
    for name in names:
        os.environ.pop(name, None)


@pytest.fixture(autouse=True)
def no_live_providers():
    """No test reaches a real provider.

    `Studio._load_env` and `cli.load_dotenv` read workflowbench/.env with override=True, so one
    test that builds a Studio leaves every real key in os.environ for the rest of the session.
    A later test that runs an API arm then dispatches a billable request -- outside the weekly
    ledger, with no operator and no approval (constitution III) -- and blocks the suite waiting
    on the response. Keys are cleared around every test; a test that wants one sets it itself
    (`mock_server`, or monkeypatch.setenv in the test body).
    """
    names = {p.key_env for p in providers.REGISTRY.values()}
    held = {name: os.environ[name] for name in names if name in os.environ}
    _clear_provider_keys(names)
    yield
    _clear_provider_keys(names)  # whatever load_dotenv injected during the test goes no further
    os.environ.update(held)


@pytest.fixture(autouse=True)
def upstream_world(monkeypatch):
    """The fixture task sets record no world, which means the upstream
    AutomationBench 1.0.6. Pin the "installed world" to it, so the guard in
    config.resolve and corpus.import_ab sees a match whatever package this
    machine has installed. Tests of the guard itself set both sides
    (tests/test_world_revision.py)."""
    monkeypatch.setattr(episode, "installed_world_version",
                        lambda: episode.UPSTREAM_WORLD_VERSION)


@pytest.fixture()
def mock_server(monkeypatch):
    server = MockOpenAIServer()
    monkeypatch.setenv("WB_MOCK_KEY", "mock-key")
    providers.register(Provider(
        key="mock", model_id="mock-1", key_env="WB_MOCK_KEY", adapter="openai",
        base_url=server.base_url, price_in=1.0, price_cached=0.1, price_out=2.0))
    yield server
    server.shutdown()
    providers.REGISTRY.pop("mock", None)


def pytest_configure(config):
    """Windows refuses paths past 260 characters. Evidence folders are deep and pytest's
    default temp root ("pytest-of-<user>/pytest-NNN/<long test name>") pushes them past
    the limit, so a short per-process root is used instead and removed at the end."""
    if os.name == "nt" and not config.option.basetemp:
        root = Path(tempfile.gettempdir()) / "wb" / str(os.getpid())
        shutil.rmtree(root, ignore_errors=True)
        # pytest's getbasetemp() does mkdir() without parents=True, so the shared
        # parent has to exist -- another process's sessionfinish may have taken it.
        root.parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(root)
        config._wb_basetemp = root


def pytest_sessionfinish(session, exitstatus):
    root = getattr(session.config, "_wb_basetemp", None)
    if root:
        shutil.rmtree(root, ignore_errors=True)
