"""M1 tests: prefix stability, cache-field normalization, mock e2e,
resume-after-kill, retry-on-429, timeout termination, cache degradation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner.schema import EpisodeRow
from wb_arms import providers
from wb_arms.api_loop import ApiLoopArm, build_tools_gemini, build_tools_openai, canonical_json
from wb_arms.providers import Provider
from wb_orchestrator.orchestrator import ConfigDrift, Orchestrator, RunKilled
from wb_results.store import Store
from tests.mock_openai import MockOpenAIServer

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"


# -- fixtures -----------------------------------------------------------------

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


def make_orch(tmp_path, arms=("mock",), k=2, **kw) -> tuple[Store, Orchestrator]:
    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator(store, TASKS_DIR, list(arms), k, out_dir=tmp_path / "out",
                        provider_concurrency=kw.pop("concurrency", 1), **kw)
    return store, orch


# -- prefix stability ---------------------------------------------------------

def test_tools_serialize_byte_stable():
    a = canonical_json(build_tools_openai()).encode()
    b = canonical_json(build_tools_openai()).encode()
    assert a == b
    assert canonical_json(build_tools_gemini()).encode() == canonical_json(build_tools_gemini()).encode()
    arm1, arm2 = ApiLoopArm("glm-5.3"), ApiLoopArm("glm-5.3")
    assert canonical_json(arm1._tools_openai) == canonical_json(arm2._tools_openai)
    blob = canonical_json(build_tools_openai())
    for banned in ("run_id", "episode_id", "timestamp", "202"):
        assert banned not in blob


# -- cache-field normalization (the four vendor shapes + absent) --------------

def test_cache_field_normalization():
    glm = {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 42}}
    assert providers.extract_cached_tokens(glm) == (42, "prompt_tokens_details.cached_tokens")

    kimi = {"prompt_tokens": 100, "cached_tokens": 37}
    assert providers.extract_cached_tokens(kimi) == (37, "cached_tokens")

    fw = providers.get("kimi-k3-fireworks")
    headers = {"Fireworks-Cached-Prompt-Tokens": "55"}
    got = providers.extract_cached_tokens({"prompt_tokens": 100}, headers, fw)
    assert got == (55, "header:fireworks-cached-prompt-tokens")

    gem = {"usageMetadata": {"cachedContentTokenCount": 64}}
    assert providers.extract_cached_tokens(gem) == (64, "usageMetadata.cachedContentTokenCount")

    cached, source = providers.extract_cached_tokens({"prompt_tokens": 100})
    assert (cached, source) == (0, None)   # absent -> 0 + None, caller must flag


def test_cost_split_cached_uncached():
    p = providers.get("glm-5.3")
    cost = providers.cost_usd(p, prompt=1_000_000, cached=600_000, output=100_000)
    assert cost == pytest.approx(400_000 * 1.40 / 1e6 + 600_000 * 0.26 / 1e6 + 100_000 * 4.40 / 1e6)


# -- mock end-to-end: 10 tasks x mock arm x k=2 -------------------------------

def test_mock_e2e_full_matrix(tmp_path, mock_server):
    store, orch = make_orch(tmp_path, k=2, concurrency=2)
    run_id = orch.run("run-e2e")
    st = store.status(run_id)
    assert st["episodes_done"] == st["episodes_total"] == 20
    arm = st["arms"]["bare/api/mock"]
    assert arm["episodes"] == 20
    assert arm["tokens_prompt"] > 0 and arm["tokens_cached"] > 0
    assert 0 < arm["cache_hit_rate"] < 1
    assert arm["cost_usd"] > 0
    assert st["terminations"] == {"completed": 20}

    res = store.episodes(run=run_id)
    assert res["source"]["denominator"] == 20
    assert res["source"]["run_id"] == run_id
    for r in res["rows"]:
        assert r["termination"] == "completed"
        assert r["tokens"]["prompt"] > 0

    jsonl = tmp_path / "out" / run_id / "episodes.jsonl"
    lines = jsonl.read_text().strip().split("\n")
    assert len(lines) == 20
    EpisodeRow(**json.loads(lines[0]))

    ep0 = res["rows"][0]
    arts = store.artifacts(ep0["episode_id"])
    assert set(arts) == {"snapshot0", "snapshot1", "turns", "events", "grading", "result", "manifest"}
    assert json.loads(Path(arts["snapshot0"]).read_text())


# -- resume after kill --------------------------------------------------------

def test_resume_after_kill(tmp_path, mock_server):
    store, orch = make_orch(tmp_path, k=2, concurrency=1, stop_after=7)
    with pytest.raises(RunKilled):
        orch.run("run-kill")
    assert len(store.completed_identities("run-kill")) == 7
    calls_phase1 = mock_server.request_count
    assert calls_phase1 == 14   # 7 episodes x 2 calls, none in flight at the kill

    store2, orch2 = make_orch(tmp_path, k=2, concurrency=1)
    orch2.resume("run-kill")
    st = store2.status("run-kill")
    assert st["episodes_done"] == 20
    # completed episodes were not re-run: only the 13 remaining hit the server
    assert mock_server.request_count - calls_phase1 == 13 * 2
    assert st["finished"] is not None


def test_resume_refuses_on_config_drift(tmp_path, mock_server):
    store, orch = make_orch(tmp_path, k=2, concurrency=1, stop_after=3)
    with pytest.raises(RunKilled):
        orch.run("run-drift")
    _, orch_k3 = make_orch(tmp_path, k=3, concurrency=1)
    with pytest.raises(ConfigDrift):
        orch_k3.resume("run-drift")


# -- retry on 429 -------------------------------------------------------------

def test_retry_on_429(tmp_path, mock_server):
    mock_server.fail_requests = {1}          # first request rate-limited, then fine
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-429")
    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 1
    assert rows[0]["termination"] == "completed"
    assert rows[0]["retries"] == 1


def test_429_exhausts_after_max_retries(tmp_path, mock_server):
    mock_server.fail_requests = set(range(1, 20))   # never recovers
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-429x")
    rows = store.episodes(run=run_id)["rows"]
    assert rows[0]["termination"] == "infra:rate_limit"
    assert rows[0]["retries"] == 2               # max 2 retries, then recorded
    assert rows[0]["passed"] is False


# -- timeout ------------------------------------------------------------------

def test_timeout_termination(tmp_path, mock_server):
    mock_server.delay_s = 0.6
    store, orch = make_orch(tmp_path, k=1, concurrency=1, timeout_s=0.3)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-timeout")
    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 1                        # grade+record ran despite timeout
    assert rows[0]["termination"] == "timeout"
    assert rows[0]["passed"] is False


# -- cache regression assertion -----------------------------------------------

def test_cache_degraded_flag(tmp_path, mock_server):
    mock_server.cache_mode = "degraded"
    mock_server.n_tool_turns = 4                 # long enough to reach turn 3
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-degraded")
    rows = store.episodes(run=run_id)["rows"]
    assert any(f.startswith("cache_degraded@msg=") for f in rows[0]["flags"]), rows[0]["flags"]


def test_cache_reporting_absent_flag(tmp_path, mock_server):
    mock_server.cache_mode = "absent"
    store, orch = make_orch(tmp_path, k=1, concurrency=1)
    orch.tasks = orch.tasks[:1]
    run_id = orch.run("run-absent")
    rows = store.episodes(run=run_id)["rows"]
    assert "cache_reporting=absent" in rows[0]["flags"]
    assert rows[0]["tokens"]["cached"] == 0
