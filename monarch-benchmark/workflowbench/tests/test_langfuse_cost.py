"""Cost from Monarch's Langfuse traces (feature 002, T041)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest

from tests.fake_langfuse import FakeLangfuse
from wb_arms.langfuse_cost import (
    LangfuseUnavailable,
    PriceLookupError,
    read_generations,
    summarize,
)
from wb_orchestrator.config import load_price_table

TABLE = Path(__file__).resolve().parents[1] / "config" / "models" / "monarch-team-bedrock.yaml"


@pytest.fixture(scope="module")
def table():
    return load_price_table(TABLE)


def _read(lf, table, episode="ep-1", **kw):
    return read_generations(lf.url, "pk", "sk", episode, table, **kw)


def test_only_tagged_traces_with_phase_from_nearest_ancestor(table):
    with FakeLangfuse() as lf:
        lf.add_trace("ep-1",
                     spans=[("s1", "recipe.plan", None),
                            ("s2", "engine.run", None), ("s3", "engine.step", "s2"),
                            ("s4", "helper", None)],
                     generations=[("g1", "s1", "anthropic.claude-opus-4-8-v1", {"input": 1}),
                                  ("g2", "s3", "anthropic.claude-sonnet-5-v1", {"input": 2}),
                                  ("g3", "s4", "anthropic.claude-haiku-4-5-v1", {"input": 3}),
                                  ("g4", None, "anthropic.claude-haiku-4-5-v1", {"input": 4})])
        lf.add_trace("ep-2", spans=[("o1", "recipe.plan", None)],
                     generations=[("gx", "o1", "anthropic.claude-opus-4-8-v1", {"input": 9})])
        lf.add_trace(None, generations=[("gy", None, "anthropic.claude-opus-4-8-v1", {"input": 9})])

        gens = {g.observation_id: g for g in _read(lf, table)}
        paths = [r["path"] for r in lf.requests]

    # Langfuse Cloud ignores the metadata filter (verified 4 Sep 2026), so the
    # episode's traces are picked out client-side: the other two are not read.
    assert any("/api/public/traces?" in p for p in paths)
    assert any("/api/public/observations?" in p and "traceId=trace-1" in p for p in paths)
    assert not any("traceId=trace-2" in p or "traceId=trace-3" in p for p in paths)
    assert set(gens) == {"g1", "g2", "g3", "g4"}
    assert (gens["g1"].phase, gens["g1"].family) == ("authoring", "claude-opus-4-8")
    assert (gens["g2"].phase, gens["g2"].family) == ("execution", "claude-sonnet-5")
    assert gens["g3"].phase == "other"
    assert gens["g4"].phase == "other"

    summary = summarize(list(gens.values()), table)
    assert sorted(summary.other_spans) == ["<none>", "helper"]


def test_summarize_prices_two_families_in_two_phases(table):
    with FakeLangfuse() as lf:
        lf.add_trace("ep-1",
                     spans=[("s1", "recipe.plan", None), ("s2", "engine.run", None)],
                     generations=[
                         # 5.00 + 25.00 + 0.50 + 6.25 = 36.75
                         ("g1", "s1", "anthropic.claude-opus-4-8-v1",
                          {"input": 1_000_000, "output": 1_000_000,
                           "cache_read_input_tokens": 1_000_000,
                           "cache_creation_input_tokens": 1_000_000}),
                         # 1.00 + 0.50 = 1.50
                         ("g2", "s2", "anthropic.claude-haiku-4-5-v1",
                          {"input": 1_000_000, "output": 100_000}),
                     ])
        summary = summarize(_read(lf, table), table)

    assert summary.missing is False
    assert summary.by_phase["authoring"]["claude-opus-4-8"] == {
        "input": 1_000_000, "output": 1_000_000, "cache_read": 1_000_000,
        "cache_write": 1_000_000, "cost_usd": 36.75}
    assert summary.by_phase["execution"]["claude-haiku-4-5"]["cost_usd"] == 1.50
    assert summary.total_usd == 38.25
    assert summary.tokens == {"input": 2_000_000, "output": 1_100_000,
                              "cache_read": 1_000_000, "cache_write": 1_000_000}


def test_no_generations_is_missing_and_free(table):
    with FakeLangfuse() as lf:
        summary = summarize(_read(lf, table), table)
    assert (summary.total_usd, summary.missing, summary.by_phase) == (0.0, True, {})


def test_parent_cycle_does_not_hang(table):
    with FakeLangfuse() as lf:
        lf.add_trace("ep-1", spans=[("s1", "loop-a", "s2"), ("s2", "loop-b", "s1")],
                     generations=[("g1", "s1", "anthropic.claude-opus-4-8-v1", {"input": 1})])
        gens = _read(lf, table)
    assert [(g.phase, g.ancestor) for g in gens] == [("other", "loop-a")]


def test_unmapped_model_raises_naming_model_and_table(table):
    with FakeLangfuse() as lf:
        lf.add_trace("ep-1", spans=[("s1", "recipe.plan", None)],
                     generations=[("g1", "s1", "anthropic.claude-nova", {"input": 1})])
        with pytest.raises(PriceLookupError) as e:
            _read(lf, table)
    assert "claude-nova" in str(e.value) and "monarch-team-bedrock" in str(e.value)


def test_absent_usage_counts_zero_tokens(table):
    with FakeLangfuse() as lf:
        lf.add_trace("ep-1", spans=[("s1", "recipe.plan", None)],
                     generations=[("g1", "s1", "anthropic.claude-opus-4-8-v1", None)])
        summary = summarize(_read(lf, table), table)
    assert summary.missing is False and summary.total_usd == 0.0
    assert summary.tokens == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def test_pagination_across_two_pages(table):
    with FakeLangfuse() as lf:
        for i in range(3):
            lf.add_trace("ep-1", spans=[(f"s{i}", "recipe.plan", None)],
                         generations=[(f"g{i}", f"s{i}", "anthropic.claude-opus-4-8-v1",
                                       {"input": 1_000_000})])
        gens = _read(lf, table, page_size=2)
    assert sorted(g.observation_id for g in gens) == ["g0", "g1", "g2"]
    assert summarize(gens, table).total_usd == 15.0


def test_from_timestamp_narrows_the_trace_list(table):
    """Only traces at or after the attempt's start are read (Cloud has thousands)."""
    old = datetime(2026, 9, 1, tzinfo=timezone.utc)
    cutoff = datetime(2026, 9, 4, tzinfo=timezone.utc)
    with FakeLangfuse() as lf:
        lf.add_trace("ep-1", spans=[("s0", "recipe.plan", None)], timestamp=old,
                     generations=[("g_old", "s0", "anthropic.claude-opus-4-8-v1",
                                   {"input": 1_000_000})])
        lf.add_trace("ep-1", spans=[("s1", "recipe.plan", None)],
                     timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
                     generations=[("g_new", "s1", "anthropic.claude-opus-4-8-v1",
                                   {"input": 1_000_000})])
        gens = _read(lf, table, from_timestamp=cutoff)
        paths = [r["path"] for r in lf.requests]
    assert [g.observation_id for g in gens] == ["g_new"]
    assert any("fromTimestamp=" + quote(cutoff.isoformat(), safe="") in p for p in paths)


def test_usage_details_is_preferred_and_usage_is_the_inclusive_fallback(table):
    """usageDetails.input is disjoint; usage.input includes cache (verified 4 Sep 2026)."""
    disjoint = {"input": 1_000_000, "output": 1_000_000,
                "cache_read_input_tokens": 1_000_000,
                "cache_creation_input_tokens": 1_000_000}
    for details in (True, False):
        with FakeLangfuse() as lf:
            lf.add_trace("ep-1", spans=[("s1", "recipe.plan", None)],
                         generations=[("g1", "s1", "anthropic.claude-opus-4-8-v1", disjoint)],
                         usage_details=details)
            g = _read(lf, table)[0]
        assert (g.input, g.output, g.cache_read, g.cache_write) == (
            1_000_000, 1_000_000, 1_000_000, 1_000_000), f"usage_details={details}"


def test_bad_credentials_raise_langfuse_unavailable(table):
    with FakeLangfuse() as lf:
        with pytest.raises(LangfuseUnavailable):
            read_generations(lf.url, "pk", "wrong", "ep-1", table)
