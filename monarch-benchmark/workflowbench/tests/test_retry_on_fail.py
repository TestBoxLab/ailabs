"""One retry per failed prompt (plan key `retry_on_fail`).

A plan may ask for one extra attempt of any prompt a competitor failed on. The
retry runs as the next trial of the same (task, competitor), on a fresh copy of
the data, and its row carries the flag `retry`. A passed attempt schedules
nothing; an `infra:` termination schedules nothing either, because the episode
already retried those inside itself and they are not the task's verdict.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_config import (  # noqa: F401  (site is a fixture)
    PLAN, edit, site, write)
from wb_arms.api_loop import ArmResult, InfraError
from wb_orchestrator import config as config_mod
from wb_orchestrator.cli import _banner
from wb_orchestrator.config import ConfigError
from wb_orchestrator.orchestrator import Orchestrator, RunKilled
from wb_results.store import Store
from wb_world.episode import load_suite

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"


# -- doubles ------------------------------------------------------------------

class _FailArm:
    """Does nothing, so every assertion fails: `passed` is always False."""
    name = "failer"
    provider_key = None

    def run(self, ep, deadline=None) -> ArmResult:
        return ArmResult()


class _PassArm:
    """Writes exactly what the task's assertions ask for: `passed` is always True."""
    name = "passer"
    provider_key = None

    def run(self, ep, deadline=None) -> ArmResult:
        from runner.arms import OracleArm
        OracleArm().run(ep)
        return ArmResult()


class _InfraArm:
    """Fails with a non-retryable infra error, so the row terminates `infra:*`."""
    name = "infra"
    provider_key = None

    def run(self, ep, deadline=None) -> ArmResult:
        raise InfraError("infra:model_unavailable", "provider is down", retryable=False)


_REGISTRY = {"failer": _FailArm(), "passer": _PassArm(), "infra": _InfraArm()}


def _orch(tmp_path, arm, k=1, retry_on_fail=1, store=None) -> tuple[Store, Orchestrator]:
    store = store or Store(tmp_path / "wb.sqlite3")
    tasks = load_suite(TASKS_DIR)[:2]
    orch = Orchestrator(store, TASKS_DIR, [], k, out_dir=tmp_path / "out",
                        provider_concurrency=1, tasks=tasks, retry_on_fail=retry_on_fail)
    orch.arm_keys = [arm.name]
    return store, orch


@pytest.fixture()
def patched(monkeypatch):
    """Let `_execute` build the test double instead of a real arm."""
    import wb_orchestrator.orchestrator as m
    monkeypatch.setattr(m, "build_arm", lambda key: _REGISTRY[key])
    yield


def _rows(store, run_id, arm):
    rows = [r for r in store.episodes(run=run_id)["rows"] if r["arm"] == arm]
    return sorted(rows, key=lambda r: (r["task_id"], r["trial"]))


# -- scheduling ----------------------------------------------------------------

def test_failed_attempt_schedules_exactly_one_retry(tmp_path, patched):
    store, orch = _orch(tmp_path, _REGISTRY["failer"])
    orch.run("run-fail")
    rows = _rows(store, "run-fail", "failer")
    assert len(rows) == 4                              # 2 tasks x (1 attempt + 1 retry)
    assert [r["trial"] for r in rows] == [0, 1, 0, 1]
    assert not any(r["passed"] for r in rows)
    # only the extra attempt is flagged, so a report can count retries
    assert [("retry" in r["flags"]) for r in rows] == [False, True, False, True]


def test_a_retry_never_retries_itself(tmp_path, patched):
    """`retry_on_fail: 1` means one extra attempt, not an unbounded chain."""
    store, orch = _orch(tmp_path, _REGISTRY["failer"])
    orch.run("run-once")
    assert max(r["trial"] for r in _rows(store, "run-once", "failer")) == 1


def test_passed_attempt_schedules_no_retry(tmp_path, patched):
    store, orch = _orch(tmp_path, _REGISTRY["passer"])
    orch.run("run-pass")
    rows = _rows(store, "run-pass", "passer")
    assert len(rows) == 2 and all(r["passed"] for r in rows)
    assert all("retry" not in r["flags"] for r in rows)


def test_infra_termination_does_not_consume_a_retry(tmp_path, patched):
    """Infrastructure failures are retried inside the episode and excluded from
    the pass denominator; they must not spend the prompt's one retry."""
    store, orch = _orch(tmp_path, _REGISTRY["infra"])
    orch.run("run-infra")
    rows = _rows(store, "run-infra", "infra")
    assert len(rows) == 2
    assert all(r["termination"].startswith("infra:") for r in rows)
    assert all("retry" not in r["flags"] for r in rows)


def test_retry_on_fail_zero_behaves_exactly_as_today(tmp_path, patched):
    store, orch = _orch(tmp_path, _REGISTRY["failer"], k=2, retry_on_fail=0)
    orch.run("run-off")
    rows = _rows(store, "run-off", "failer")
    assert len(rows) == 4                              # 2 tasks x 2 repetitions, no extras
    assert all("retry" not in r["flags"] for r in rows)


def test_retries_start_after_the_planned_repetitions(tmp_path, patched):
    """With repetitions 2, the retry of a failed trial 1 is trial 2, not a clash."""
    store, orch = _orch(tmp_path, _REGISTRY["failer"], k=2, retry_on_fail=1)
    orch.run("run-k2")
    per_task: dict[str, list[int]] = {}
    for r in _rows(store, "run-k2", "failer"):
        per_task.setdefault(r["task_id"], []).append(r["trial"])
    assert all(t == [0, 1, 2, 3] for t in per_task.values())


# -- resume --------------------------------------------------------------------

def test_resume_re_derives_a_pending_retry(tmp_path, patched):
    """A recorded failed trial 0 with no trial 1 gets its retry on resume."""
    store, orch = _orch(tmp_path, _REGISTRY["failer"])
    orch._stop_after = 2                     # both first attempts, no retries
    with pytest.raises(RunKilled):
        orch.run("run-resume")
    assert len(_rows(store, "run-resume", "failer")) == 2

    store2, orch2 = _orch(tmp_path, _REGISTRY["failer"])
    orch2.resume("run-resume")
    rows = _rows(store2, "run-resume", "failer")
    assert [r["trial"] for r in rows] == [0, 1, 0, 1]
    assert [("retry" in r["flags"]) for r in rows] == [False, True, False, True]


def test_resume_does_not_re_retry_a_recorded_retry(tmp_path, patched):
    store, orch = _orch(tmp_path, _REGISTRY["failer"])
    orch.run("run-done")
    store2, orch2 = _orch(tmp_path, _REGISTRY["failer"])
    orch2.resume("run-done")
    assert len(_rows(store2, "run-done", "failer")) == 4    # nothing added


# -- the plan key --------------------------------------------------------------

def _oracle_plan(site, extra="", repetitions=2):
    """Resolve the shared fixture plan with one scripted competitor."""
    plan = edit(PLAN, "competitors")
    plan = edit(plan, "baseline", "oracle")
    plan = edit(plan, "repetitions", str(repetitions))
    plan = edit(plan, "tasks", f'"{(ROOT / "tasks").as_posix()}"')
    plan += "competitors:\n  - {harness: oracle}\n" + extra
    write(site / "config/plans", plan)
    return config_mod.resolve(site / "config/products/simulated-apps.yaml",
                              site / "config/plans/smoke-frontier.yaml")


def test_plan_defaults_to_no_retry(tmp_path):
    assert config_mod.load_plan(write(tmp_path, PLAN)).retry_on_fail == 0
    with_retry = write(tmp_path, PLAN + "retry_on_fail: 1\n")
    assert config_mod.load_plan(with_retry).retry_on_fail == 1


def test_retry_on_fail_must_be_a_non_negative_integer(tmp_path):
    with pytest.raises(ConfigError) as exc:
        config_mod.load_plan(write(tmp_path, PLAN + "retry_on_fail: -1\n"))
    assert exc.value.field == "retry_on_fail"


def test_retry_on_fail_moves_the_hash_only_when_it_is_set(site):
    """Hashed like every plan field; a plan that asks for no retry keeps the
    hash it has today, so runs stored before this key stay regradable."""
    h0 = _oracle_plan(site).hash
    assert _oracle_plan(site, "retry_on_fail: 0\n").hash == h0
    # repetitions 1 so the retry stays inside smoke scale: 10 x (1 + 1) = 20
    h1 = _oracle_plan(site, repetitions=1).hash
    assert _oracle_plan(site, "retry_on_fail: 1\n", repetitions=1).hash != h1


def test_the_size_counts_retries_as_attempts(site):
    """The launch gate (an approval record above smoke scale, decision D5) judges
    what the round could cost, not its best case: retries count."""
    assert _oracle_plan(site, repetitions=2).attempts_per_competitor == 20        # at smoke scale
    rc = _oracle_plan(site, "retry_on_fail: 1\n", repetitions=2)                  # 10 x 3 = 30
    assert rc.attempts_per_competitor == 30 > config_mod.SMOKE_SCALE_ATTEMPTS


# -- the size line -------------------------------------------------------------

def test_size_line_says_one_attempt_plus_one_retry(site):
    """`wb run` states the size in the agreed words before anything is spent."""
    rc = _oracle_plan(site, "retry_on_fail: 1\n", repetitions=1)
    assert ("prompts: 10; attempts per prompt: 1 plus 1 retry on failure; "
            "attempts per competitor: 10 to 20") in _banner(rc)
    # the ceiling keeps counting every attempt, so the round total is the upper bound
    assert "competitors: 1; attempts in the round: 20" in _banner(rc)


def test_size_line_is_unchanged_without_retries(site):
    rc = _oracle_plan(site)
    assert ("prompts: 10; attempts per prompt and competitor: 2; "
            "attempts per competitor: 20 = 10 x 2") in _banner(rc)


