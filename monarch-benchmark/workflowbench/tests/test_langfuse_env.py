"""LANGFUSE_OTLP_AUTH (what a Monarch deployment carries) yields the key pair the cost reader needs."""
import base64

from wb_orchestrator.config import derive_langfuse_keys


def test_derives_the_pair_from_the_basic_header():
    env = {"LANGFUSE_OTLP_AUTH": "Basic " + base64.b64encode(b"pk-lf-1:sk-lf-2").decode()}
    assert derive_langfuse_keys(env) is True
    assert env["LANGFUSE_PUBLIC_KEY"] == "pk-lf-1" and env["LANGFUSE_SECRET_KEY"] == "sk-lf-2"


def test_never_overrides_keys_already_set_and_ignores_garbage():
    env = {"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b", "LANGFUSE_OTLP_AUTH": "Basic zzz"}
    assert derive_langfuse_keys(env) is False and env["LANGFUSE_PUBLIC_KEY"] == "a"
    assert derive_langfuse_keys({"LANGFUSE_OTLP_AUTH": "not base64!"}) is False
    assert derive_langfuse_keys({"LANGFUSE_OTLP_AUTH": base64.b64encode(b"no-colon").decode()}) is False
    assert derive_langfuse_keys({}) is False
