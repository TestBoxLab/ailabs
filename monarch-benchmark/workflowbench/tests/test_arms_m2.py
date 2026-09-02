"""Tests for the M2-facing arms: claude-code result parsing, monarch gating,
corpus tooling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wb_arms.api_loop import InfraError
from wb_arms.cli_claude_code import invocation, parse_result
from wb_orchestrator.corpus import validate_corpus
from wb_orchestrator.orchestrator import build_arm

ROOT = Path(__file__).resolve().parents[1]


def test_claude_code_result_parsing():
    payload = {"type": "result", "subtype": "success", "is_error": False,
               "result": "done", "num_turns": 7, "total_cost_usd": 0.042,
               "usage": {"input_tokens": 100, "output_tokens": 900,
                         "cache_read_input_tokens": 5000,
                         "cache_creation_input_tokens": 400}}
    r = parse_result(json.dumps(payload), 0)
    assert r.termination == "completed"
    assert r.turns == 7 and r.cost_usd == pytest.approx(0.042)
    assert r.tokens_prompt == 5500 and r.tokens_cached == 5000
    assert r.tokens_output == 900
    assert not r.flags


def test_claude_code_error_and_garbage_output():
    r = parse_result(json.dumps({"is_error": True, "result": "boom"}), 0)
    assert r.termination == "agent_error" and "boom" in r.error
    r2 = parse_result("not json at all", 1, stderr="crash")
    assert r2.termination == "agent_error"
    assert "cli_output_unparseable" in r2.flags


def test_claude_code_stock_invocation_documented():
    inv = invocation()
    assert inv["billing"] == "api-key"
    assert "--permission-mode" in inv["flags"]      # non-default flags are named


def test_monarch_arm_blocked_without_entrypoints(monkeypatch, tmp_path):
    for var in ("MONARCH_AUTHORING_CMD", "MONARCH_ENGINE_CMD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MONARCH_VERSION", "0.9-test")
    arm = build_arm("monarch/stock")
    assert arm.name == "monarch/stock@0.9-test"
    from wb_world.episode import load_task_file, Episode
    task = load_task_file(sorted((ROOT / "tasks").glob("*.json"))[0])
    with pytest.raises(InfraError) as ei:
        arm.run(Episode(task, "m2-block"))
    assert "Deyton" in str(ei.value)                # blocked loudly, names the blocker


def test_monarch_lab_requires_config_and_hashes_it(monkeypatch, tmp_path):
    monkeypatch.delenv("MONARCH_LAB_CONFIG", raising=False)
    with pytest.raises(InfraError):
        build_arm("monarch/lab")
    cfg = tmp_path / "lab.json"
    cfg.write_text('{"experiment": "graph-hints-v2"}')
    monkeypatch.setenv("MONARCH_LAB_CONFIG", str(cfg))
    arm = build_arm("monarch/lab")
    assert arm.name.startswith("monarch/lab@") and len(arm.name.split("@")[1]) == 16


def test_corpus_validate_t0_tasks():
    v = validate_corpus(ROOT / "tasks")
    assert v["n_tasks"] == 10
    assert v["ok"], v
    assert v["oracle_failures"] == 0 and v["noop_failures"] == 0
    assert v["invariant_undeclared"] == 0


def test_corpus_validate_catches_vacuous_task(tmp_path):
    task = json.loads((sorted((ROOT / "tasks").glob("*.json"))[0]).read_text())
    task["info"]["assertions"] = []          # no assertions -> vacuous
    (tmp_path / "bad.json").write_text(json.dumps(task))
    v = validate_corpus(tmp_path)
    assert not v["ok"] and v["noop_failures"] == 1
