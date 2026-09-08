import pytest

from tests.mock_openai import MockOpenAIServer
from wb_arms import providers
from wb_arms.providers import Provider
from wb_world import episode


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
