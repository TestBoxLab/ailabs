"""The over-time figure must describe the data it draws.

Feature 024, FR-015. Two things were constant where they should have been derived:

- `reports.js` titled the figure "Monarch pass rate by run" and coloured every series
  with the `monarch` family, whatever the cohort contained.
- `report_data` only put a setup in the trend when its name contained the word
  "monarch", so a round comparing GLM against Bare produced no trend at all — the
  figure was not merely mislabelled, it was unavailable to every round that is not
  about Monarch.

AI-LABS-DIRECTION.md:88 forbids templated celebration. A title that asserts the
programme's headline subject onto whatever happens to be in the cohort is worse than
templated: it is a claim the data does not make.
"""
from __future__ import annotations

from types import SimpleNamespace

from wb_studio import report_data


def run(identity, when, setups):
    """setups: {name: pass_rate} over two fixed tasks."""
    arms = [{"id": name, "kind": "runner", "name": name} for name in setups]
    results = []
    for name, rate in setups.items():
        passes = round(rate * 2)
        for i in range(2):
            results.append({"task": f"t{i}", "model": name, "passed": i < passes,
                            "termination": "stop", "flags": [], "cost_usd": "0.01"})
    return {"id": identity, "status": "completed", "created_at": when, "title": identity,
            "task_hashes": {"t0": "h0", "t1": "h1"},
            "component_manifest": {"judge": "judge-v1"}, "world_manifest": "world-1",
            "settings": {"track": "agentic-request", "tasks": ["t0", "t1"], "arms": arms},
            "results": results, "events": []}


def report_over(*jobs):
    by_id = {j["id"]: j for j in jobs}
    studio = SimpleNamespace(directory=None, jobs=lambda: list(jobs),
                             job=lambda i: by_id[i], events=lambda i: [], tasks={})
    return report_data.round_report(studio, next(iter(report_data.cohorts(studio))))


def test_a_round_without_monarch_still_has_a_trend():
    r = report_over(run("a", "2026-09-01T00:00:00+00:00", {"glm-5.3": 1.0, "Bare glm-5.3": 0.5}),
                    run("b", "2026-09-02T00:00:00+00:00", {"glm-5.3": 0.5, "Bare glm-5.3": 0.5}))
    assert r["trend"], "a round of non-Monarch setups produced no over-time figure at all"
    assert {p["series"] for p in r["trend"]} == {"GLM 5.3 (Z.ai)", "Bare glm-5.3"}


def test_two_builds_of_one_setup_stay_two_lines():
    """Resolved names would collapse them into a line the round never ran."""
    r = report_over(run("a", "2026-09-01T00:00:00+00:00", {"monarch · 0cf63a74e stock": 1.0, "monarch · 9b79557 stock": 0.5}),
                    run("b", "2026-09-02T00:00:00+00:00", {"monarch · 0cf63a74e stock": 0.5, "monarch · 9b79557 stock": 0.5}))
    assert {p["series"] for p in r["trend"]} == {"monarch · 0cf63a74e stock", "monarch · 9b79557 stock"}


def test_the_title_names_what_is_in_the_data():
    r = report_over(run("a", "2026-09-01T00:00:00+00:00", {"glm-5.3": 1.0}),
                    run("b", "2026-09-02T00:00:00+00:00", {"glm-5.3": 0.5}))
    assert "monarch" not in r["trend_title"].lower()
    assert "pass rate" in r["trend_title"].lower()


def test_a_monarch_round_says_so():
    r = report_over(run("a", "2026-09-01T00:00:00+00:00", {"monarch-stock": 1.0}),
                    run("b", "2026-09-02T00:00:00+00:00", {"monarch-stock": 0.5}))
    assert "monarch-stock" in r["trend_title"] or "Monarch" in r["trend_title"]


def test_the_figure_takes_its_colour_from_the_series_not_a_constant():
    """The family is resolved client-side by `Charts.familyOf`, so this checks the one
    thing a Python test can: that the constant is gone and the per-series call is there.
    Duplicating familyOf in Python to assert it properly would be a second
    implementation of a rule that already has one."""
    from wb_studio.app import ROOT
    source = (ROOT / "wb_studio" / "static" / "reports.js").read_text(encoding="utf-8")
    assert "'Monarch pass rate by run'" not in source
    assert "family: 'monarch'" not in source
    assert "family: setupFamily(label)" in source


def test_a_trend_title_is_written_for_any_number_of_setups():
    from wb_studio.report_data import trend_title_for
    assert trend_title_for([]) == "Pass rate by run"
    assert trend_title_for(["glm-5.3"]) == "glm-5.3: pass rate by run"
    assert trend_title_for(["a", "b"]) == "a and b: pass rate by run"
    assert trend_title_for(["a", "b", "c"]) == "Pass rate by run, 3 setups"
