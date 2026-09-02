import pytest

from tests.mock_openai import MockOpenAIServer
from wb_arms import providers
from wb_arms.providers import Provider


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
