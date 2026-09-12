"""Run matrix orchestration per BUILD-SPEC §2.1.

Episode state machine: PROVISION -> SNAPSHOT0 -> ARM_RUN(timeout) -> SNAPSHOT1
-> GRADE -> RECORD. Grade and record always run, whatever ARM_RUN did.
Checkpoint identity (run_id, task_id, arm, trial); resume skips completed
identities and refuses on config-hash drift. Only infra:* terminations
auto-retry inside the episode (max 2, exponential backoff honoring Retry-After).

A plan may also ask for `retry_on_fail` extra attempts of any prompt a
competitor failed on a non-infra termination: each lands as trial + k, its row
carries the flag `retry`, and resume re-derives the ones it still owes.

Scheduling: the matrix is grouped by arm and each arm's episodes run
back-to-back (cache TTLs are minutes-scale); arms run concurrently with each
other under per-provider semaphores (default 4).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grader.grade import grade
from runner.arms import NullArm, OracleArm, SloppyArm
from runner.schema import EpisodeRow, PhaseMetrics, TokenUsage
from wb_arms.api_loop import ApiLoopArm, ArmResult, EpisodeTimeout, InfraError
from wb_arms import providers
from wb_results.store import Store
from wb_results import evidence
from wb_orchestrator import config as config_mod
from wb_orchestrator.config import ConfigError
from wb_world.episode import (  # noqa: F401  (Episode, contract_hash, load_suite re-exported)
    LEGACY_SUITE, Episode, contract_hash, load_suite, suite_id)

MAX_INFRA_RETRIES = 2
# The label of every set that records no world. A round's real suite id comes
# from its tasks (wb_world.episode.suite_id): the world's version is in it.
SUITE = LEGACY_SUITE


class RunKilled(Exception):
    pass


class ConfigDrift(Exception):
    pass


class RoundAdmissionError(Exception):
    """The week's ledger cannot cover the round's maximum liability; nothing was reserved."""


# legacy: runs recorded before product/plan files
def config_hash(tasks: list[dict], arms: list[str], k: int, timeout_s: float) -> str:
    blob = json.dumps({"tasks": sorted(contract_hash(t) for t in tasks),
                       "arms": sorted(arms), "k": k, "timeout_s": timeout_s},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class _ScriptedAdapter:
    """Wrap the T0 scripted arms into the ArmResult contract."""

    _CLASSES = {"oracle": OracleArm, "sloppy": SloppyArm, "null": NullArm}

    def __init__(self, key: str):
        self._inner = self._CLASSES[key]()
        self.name = self._inner.name
        self.provider_key = None

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        self._inner.run(ep)
        return ArmResult(tool_calls=len(ep.tool_calls))


# legacy: runs recorded before product/plan files
def _validate_arm_key(key: str) -> None:
    known = (key in _ScriptedAdapter._CLASSES or key == "claude-code"
             or key in providers.REGISTRY)
    if not known:
        raise ValueError(
            f"unknown arm {key!r}; known: {sorted(_ScriptedAdapter._CLASSES)} + "
            f"'claude-code' + providers {sorted(providers.REGISTRY)}")


# legacy: runs recorded before product/plan files
def build_arm(key: str):
    if key in _ScriptedAdapter._CLASSES:
        return _ScriptedAdapter(key)
    if key == "claude-code":
        from wb_arms.cli_claude_code import ClaudeCodeArm
        return ClaudeCodeArm()
    arm = ApiLoopArm(key)
    arm.provider_key = key
    return arm


def build_arm_for(competitor: config_mod.Competitor, run_config: "config_mod.RunConfig | None" = None,
                  ledger=None, operator: str | None = None):
    """Build the arm a plan competitor names; the arm reports under the competitor's name (R1).

    Monarch is the exception: it reports under the version of the checkout it ran
    from, so `run_config` is required to build one (it carries the plan, the price
    table and the knowledge base). With a `ledger`, paid arms reserve through it:
    the API loop per request, Monarch per attempt (milestone M3).
    """
    if run_config and run_config.plan.mode == "feature-discovery":
        raise ConfigError(run_config.plan_path, "mode",
                          "feature-discovery execution and evaluation are not implemented")
    h = competitor.harness
    if h.kind == "monarch":
        config_mod.require_model_routing(h, Path(run_config.config_dir if run_config else "config") / "harnesses" / f"{h.name}.yaml")
    if h.kind == "api":
        arm = ApiLoopArm(competitor.model.name, ledger=ledger, operator=operator,
                         provider=providers.from_model(competitor.model),
                         attempt_cap_usd=run_config.plan.attempt_cap_usd if run_config else None)
        arm.provider_key = competitor.model.name
    elif h.kind == "scripted":
        arm = _ScriptedAdapter(h.script)
    elif h.kind == "cli":
        if h.launcher != "claude-code":
            raise ValueError(f"launcher {h.launcher!r} is not runnable yet")
        from wb_arms.cli_claude_code import ClaudeCodeArm
        m = competitor.model
        fields = dict(model=m.name, provider=m.provider, key_env=m.key_env) if m else {}
        rendered = {}
        for k, v in h.env.items():
            try:
                rendered[k] = v.format_map(fields)
            except (KeyError, ValueError, IndexError) as e:
                raise ValueError(f"harness {h.name!r}: env {k!r}: bad placeholder {e}") from e
        arm = ClaudeCodeArm(env=rendered)
    else:
        from wb_arms.monarch import MonarchArm, monarch_version
        if run_config is None:
            raise ValueError("a Monarch competitor needs the run config to build its arm")
        config_dir = Path(run_config.config_dir)
        repo = config_mod.from_workflowbench(h.monarch_repo, config_dir, run_config.runtime_root)
        try:
            name = monarch_version(repo, os.environ.get("MONARCH_BUILD"))
        except ValueError as e:
            raise ConfigError(config_dir / "harnesses" / f"{h.name}.yaml", "monarch_repo",
                              f"cannot read the Monarch version: {e}") from e
        mode = run_config.plan.mode
        if mode == "run-only" and run_config.monarch_recipes is None:
            raise ConfigError(config_dir / "products"
                              / f"{run_config.product.name}.monarch-recipes.yaml", "recipes",
                              "a run-only Monarch competitor needs the recipes file; "
                              "run `wb monarch recipes` first")
        products = config_dir / "products"
        return MonarchArm(harness=h, timeout_s=run_config.plan.timeout_s,
                          price_table=run_config.price_tables.get(h.price_table),
                          kb=run_config.monarch_kb, env=os.environ, name=name, mode=mode,
                          recipes=run_config.monarch_recipes,
                          kb_path=products / f"{run_config.product.name}.monarch-kb.yaml",
                          recipes_path=products / f"{run_config.product.name}.monarch-recipes.yaml",
                          ledger=ledger)
    arm.name = competitor.name
    return arm


class Orchestrator:
    @classmethod
    def from_config(cls, store: Store, run_config: config_mod.RunConfig, out_dir: str | Path,
                    provider_concurrency: int | None = None, ledger=None,
                    operator: str | None = None, attempt_admission=None,
                    attempt_release=None) -> "Orchestrator":
        plan = run_config.plan
        # arms=[] skips the old key validation; competitor names are set below.
        self = cls(store, run_config.tasks_dir, [], plan.repetitions, out_dir,
                   timeout_s=plan.timeout_s,
                   provider_concurrency=provider_concurrency or plan.concurrency,
                   tasks=run_config.tasks, retry_on_fail=plan.retry_on_fail,
                   ledger=ledger, operator=operator, attempt_admission=attempt_admission,
                   attempt_release=attempt_release)
        self.arm_keys = [c.name for c in run_config.competitors]
        self.run_config = run_config
        return self

    def __init__(self, store: Store, suite_dir: str | Path, arms: list[str], k: int,
                 out_dir: str | Path, timeout_s: float = 600.0,
                 provider_concurrency: int = 4, stop_after: int | None = None,
                 tasks: list[dict] | None = None, retry_on_fail: int = 0,
                 ledger=None, operator: str | None = None, grader=None,
                 attempt_admission=None, attempt_release=None):
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        if retry_on_fail < 0:
            raise ValueError(f"retry_on_fail must be >= 0, got {retry_on_fail}")
        if len(set(arms)) != len(arms):
            raise ValueError(f"duplicate arms would double-run identities: {arms}")
        for a in arms:
            _validate_arm_key(a)
        self.store = store
        self.grader = grader or grade
        self.run_config: config_mod.RunConfig | None = None
        self.suite_dir = str(suite_dir)
        self.tasks = tasks if tasks is not None else load_suite(suite_dir)
        self.suite = suite_id(self.tasks)   # refuses a set that mixes worlds
        self.arm_keys = arms
        self.k = k
        self.retry_on_fail = retry_on_fail
        self.out_dir = Path(out_dir)
        self.timeout_s = timeout_s
        self.provider_concurrency = provider_concurrency
        self._sems: dict[str, threading.Semaphore] = {}
        self._stop_after = stop_after
        self._recorded = 0
        self._abort = threading.Event()
        self._count_lock = threading.Lock()
        self._thread_errors: list[BaseException] = []
        self._spent = 0.0            # cumulative cost_usd, carried over on resume
        self._stop_reason: str | None = None
        self.attempt_admission = attempt_admission
        self.attempt_release = attempt_release
        self._paused = threading.Event()
        # The shared weekly ledger paid arms reserve through, who launched the
        # run, and the approval record it runs under (milestone M3).
        self.ledger = ledger
        self.operator = operator
        self.approval_request_id: str | None = None

    def _config(self) -> dict:
        if self.run_config:
            return {**self.run_config.config_json, "launched_by": self.operator,
                    "approval_request": self.approval_request_id}
        return {"suite_dir": self.suite_dir, "arms": self.arm_keys, "k": self.k,
                "timeout_s": self.timeout_s, "n_tasks": len(self.tasks)}

    def _hash(self) -> str:
        if self.run_config:
            return self.run_config.hash
        return config_hash(self.tasks, self.arm_keys, self.k, self.timeout_s)

    def run(self, run_id: str | None = None) -> str:
        run_id = run_id or f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        arms = self._arms()
        self._admit(run_id, arms, skip=set())   # a refused round leaves no run row
        self.store.create_run(run_id, self._hash(), self.suite, self._config())
        if self.run_config and self.run_config.config_source:
            evidence.write_json(self._run_dir(run_id) / "config-source.json", self.run_config.config_source)
        self._execute(run_id, skip=set(), arms=arms)
        return run_id

    def cancel(self) -> None:
        """Stop scheduling and drain in-flight attempts, preserving their evidence and spend."""
        self._stop_reason = "cancelled"
        self._abort.set()

    def resume(self, run_id: str) -> str:
        run = self.store.run(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id!r}")
        if run["stop_reason"] == "cancelled":
            raise RunKilled(f"run {run_id} was explicitly cancelled and cannot resume")
        recorded_config = json.loads(run["config_json"])
        source = recorded_config.get("config_source")
        if source and (self.run_config is None or source != self.run_config.config_source):
            raise ConfigDrift("configuration source drift: resume requires the original repository revision and bytes")
        if source and recorded_config["cost_ceiling_usd"] != self.run_config.plan.cost_ceiling_usd:
            raise ConfigDrift("configuration ceiling drift: a higher ceiling requires a new committed plan and run")
        if run["config_hash"] != self._hash():
            raise ConfigDrift(
                f"config drift: run has {run['config_hash']}, current config is {self._hash()}; "
                "refusing to resume")
        if run["suite"] != self.suite:
            raise ConfigDrift(
                f"suite drift: run {run_id} was recorded under {run['suite']}, the task set "
                f"now gives {self.suite}; refusing to resume on another world")
        # The ceiling counts the run's cumulative spend, whatever stopped it.
        self._spent = self.store.status(run_id)["spend_usd"]
        if self.run_config and self.run_config.plan.cost_ceiling_usd <= self._spent:
            ceiling = self.run_config.plan.cost_ceiling_usd
            raise ConfigError(self.run_config.plan_path, "cost_ceiling_usd",
                              f"run {run_id}: spend US$ {self._spent:.2f} already meets ceiling "
                              f"US$ {ceiling:.2f}; raise cost_ceiling_usd in the plan to continue")
        skip = self.store.completed_identities(run_id)
        arms = self._arms()
        self._admit(run_id, arms, skip)     # only what is left to run is counted
        self.store.set_stop_reason(run_id, None)  # the run is going again
        self._execute(run_id, skip=skip, arms=arms)
        return run_id

    def _arms(self) -> list:
        return ([build_arm_for(c, self.run_config, ledger=self.ledger, operator=self.operator)
                 for c in self.run_config.competitors]
                if self.run_config
                else [build_arm(k) for k in self.arm_keys])

    def _pending_retries(self, run_id: str, arm_name: str) -> list[tuple[dict, int]]:
        """Retries a resumed run still owes: a recorded attempt that failed on a
        non-infra termination, whose retry trial has no final outcome.

        Derived from the store rather than remembered, so an interrupted run
        picks up exactly the retries it had not run yet.
        """
        if not self.retry_on_fail:
            return []
        completed = self.store.completed_identities(run_id)
        by_task: dict[str, dict[int, dict]] = {}
        for r in self.store.episodes(run=run_id)["rows"]:
            if r["arm"] == arm_name:
                by_task.setdefault(r["task_id"], {})[r["trial"]] = r
        work = []
        for task in self.tasks:
            trials = by_task.get(task["task"], {})
            for trial in sorted(trials):
                row = trials[trial]
                if (self._earns_a_retry(row["passed"], row["termination"])
                        and self._retry_budget_left(trial)
                        and (task["task"], arm_name, trial + self.k) not in completed):
                    work.append((task, trial + self.k))
        return work

    def _pending_work(self, run_id: str, arm_name: str,
                      completed: set[tuple[str, str, int]]) -> list[tuple[dict, int]]:
        work = [(task, trial) for task in self.tasks for trial in range(self.k)
                if (task["task"], arm_name, trial) not in completed]
        return work + self._pending_retries(run_id, arm_name)

    def pending_work(self, run_id: str, *, competitor_names: list[str]) -> dict[str, int]:
        """Preview recorded identities without constructing or preparing provider adapters.

        Callers supply the frozen result identities, including Monarch's version.
        Conditional retries count only future failures reachable from pending work.
        """
        completed = self.store.completed_identities(run_id)
        initial = retries = conditional = 0
        for name in competitor_names:
            for _, trial in self._pending_work(run_id, name, completed):
                initial += trial < self.k
                retries += trial >= self.k
                conditional += max(0, self.retry_on_fail - trial // self.k)
        return dict(required_initial=initial, earned_retries=retries,
                    required_attempts=initial + retries, conditional_retries=conditional,
                    maximum_attempts=initial + retries + conditional)

    def _earns_a_retry(self, passed: bool, termination: str) -> bool:
        """A failed attempt is retried unless the infrastructure was what failed:
        those are already retried inside the episode and are not the task's verdict."""
        return bool(self.retry_on_fail) and not passed and not termination.startswith("infra:")

    def _retry_budget_left(self, trial: int) -> bool:
        """Trials 0..k-1 are the planned repetitions; each may spend `retry_on_fail`
        extra attempts, laid out as trial + k, + 2k, ... so no two identities clash."""
        return trial // self.k < self.retry_on_fail

    def _admit(self, run_id: str, arms: list, skip: set[tuple[str, str, int]]) -> None:
        """Refuse a round the week cannot cover, before its first attempt (milestone M3).

        The maximum liability is what every attempt still to run could reserve:
        API attempts at the plan's attempt cap, Monarch attempts at the Monarch
        ceiling, the sum capped by what the cost ceiling still allows this run.
        Nothing is held for the round itself: the per-request reservations are
        the enforcement while it runs, so a resume only counts what is left.
        """
        if self.ledger is None or self.run_config is None:
            return
        from decimal import Decimal
        plan = self.run_config.plan
        per_competitor = self.run_config.attempts_per_competitor
        api_attempts = monarch_attempts = 0
        monarch_ceiling = None
        for arm in arms:
            if isinstance(arm, _ScriptedAdapter):
                continue
            done = sum(1 for _, name, _ in skip if name == arm.name)
            remaining = max(0, per_competitor - done)
            if getattr(arm, "provider_key", None) == "monarch":
                from wb_arms.monarch import attempt_ceiling_usd
                monarch_attempts += remaining
                monarch_ceiling = attempt_ceiling_usd(arm.env)
            else:
                api_attempts += remaining
        parts, asked = [], Decimal("0")
        if api_attempts:
            cap = Decimal(str(plan.attempt_cap_usd))
            parts.append(f"{api_attempts} API attempt{'s' if api_attempts != 1 else ''} x attempt cap US$ {cap:.2f}")
            asked += api_attempts * cap
        if monarch_attempts:
            parts.append(f"{monarch_attempts} Monarch attempt{'s' if monarch_attempts != 1 else ''} "
                         f"x ceiling US$ {monarch_ceiling:.2f}")
            asked += monarch_attempts * monarch_ceiling
        if asked <= 0:
            return
        allowance = max(Decimal("0"), Decimal(str(plan.cost_ceiling_usd)) - Decimal(str(self._spent)))
        liability = min(asked, allowance)
        detail = " + ".join(parts)
        if liability < asked:
            detail += f" = US$ {asked:.2f}, capped by cost_ceiling_usd US$ {plan.cost_ceiling_usd:.2f}"
            if self._spent:
                detail += f" less US$ {self._spent:.2f} already spent"
        status = self.ledger.status()
        available = status.available_usd
        if liability > available:
            raise RoundAdmissionError(
                f"run {run_id}: the week cannot cover this round: maximum liability US$ {liability:.2f} "
                f"({detail}); available US$ {available:.2f} of US$ {status.weekly_limit_usd:.2f} this week "
                f"(US$ {status.actual_usd:.2f} spent, US$ {status.held_usd:.2f} held); "
                f"short by US$ {liability - available:.2f}. Reduce the plan or wait for the next week "
                "(Monday 00:00 America/Sao_Paulo); nothing was reserved")

    def _execute(self, run_id: str, skip: set[tuple[str, str, int]], arms: list | None = None) -> None:
        arms = arms if arms is not None else self._arms()
        if self.run_config:
            from wb_studio.monarch_provenance import capture
            facts = capture(self.run_config, os.environ)
            if facts:
                segment_id = uuid.uuid4().hex
                evidence.write_json(self._run_dir(run_id) / "monarch-provenance" / f"{segment_id}.json",
                    {"id": segment_id, "started_at": datetime.now(timezone.utc).isoformat(), "monarch_provenance": facts})
        threads = []
        for arm in arms:
            work = self._pending_work(run_id, arm.name, skip)
            if not work:
                continue
            t = threading.Thread(target=self._run_arm_group, args=(run_id, arm, work),
                                 name=f"arm-{arm.name}")
            t.start()
            threads.append(t)
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            # Clean interrupt: stop scheduling, let in-flight episodes drain,
            # leave a resumable checkpoint state.
            self._abort.set()
            for t in threads:
                t.join()
            self.store.set_stop_reason(run_id, "interrupted")
            raise RunKilled(
                f"run {run_id} interrupted after {self._recorded} episodes; "
                f"resume with: wb resume {run_id}") from None
        if self._thread_errors:
            # A crashed episode worker must never let the run be marked
            # finished with rows silently missing — fail the run loudly.
            self.store.set_stop_reason(run_id, "worker_error")
            raise self._thread_errors[0]
        if self._stop_reason == "cost_ceiling":
            self.store.set_stop_reason(run_id, "cost_ceiling")
            raise RunKilled(
                f"run {run_id} stopped: spend US$ {self._spent:.2f} exceeds ceiling "
                f"US$ {self.run_config.plan.cost_ceiling_usd:.2f} after {self._recorded} attempts; "
                f"raise cost_ceiling_usd in the plan and run: wb resume {run_id}")
        if self._stop_reason == "weekly_budget":
            self.store.set_stop_reason(run_id, "weekly_budget")
            raise RunKilled(
                f"run {run_id} stopped: the shared weekly budget is exhausted after {self._recorded} "
                f"attempts (US$ {self._spent:.2f} spent on this run); the attempts it cut are recorded "
                "as infra:weekly_budget and run again on resume. When the week has room (Monday 00:00 "
                f"America/Sao_Paulo, or an earlier hold settles), run: wb resume {run_id}")
        if self._abort.is_set():
            if self._stop_reason == "cancelled":
                self.store.set_stop_reason(run_id, "cancelled")
            raise RunKilled(f"run {run_id} killed after {self._recorded} episodes")
        if self._paused.is_set() and self.pending_work(
                run_id, competitor_names=[arm.name for arm in arms])["required_attempts"]:
            self.store.set_stop_reason(run_id, "paused")
            raise RunKilled(f"run {run_id} paused after {self._recorded} attempts; active attempts drained")
        self.store.finish_run(run_id)
        self.store.export_jsonl(run_id, self._run_dir(run_id) / "episodes.jsonl")

    def _run_arm_group(self, run_id: str, arm, work: list[tuple[dict, int]]) -> None:
        if self._abort.is_set():
            return
        if hasattr(arm, "prepare"):   # ponytail: hasattr check; only Monarch has one
            # A refused competitor stops the whole run before any attempt: the
            # thread body's exception is invisible to the joiner otherwise.
            try:
                arm.prepare()
            except BaseException as e:      # noqa: BLE001  re-raised by _execute
                self._thread_errors.append(e)
                self._abort.set()
                return
        sem_key = arm.provider_key or "local"
        sem = self._sems.setdefault(sem_key, threading.Semaphore(self.provider_concurrency))
        with ThreadPoolExecutor(max_workers=self.provider_concurrency,
                                thread_name_prefix=f"ep-{sem_key}") as pool:
            # A failed attempt can add work, so the list is drained rather than
            # zipped: `_episode_guarded` appends the retry it earned.
            queue, done = list(work), 0
            futures = []
            while True:
                while done < len(queue):
                    task, trial = queue[done]
                    done += 1
                    if self._abort.is_set():
                        continue
                    futures.append(pool.submit(self._episode_guarded, run_id, arm, task, trial,
                                               sem, queue))
                if not futures:
                    break
                f = futures.pop(0)
                exc = f.exception()
                if exc is not None:
                    self._thread_errors.append(exc)
                    self._abort.set()

    def _episode_guarded(self, run_id: str, arm, task: dict, trial: int,
                         sem: threading.Semaphore, queue: list | None = None) -> None:
        if self._abort.is_set():
            return
        with sem:
            if self._abort.is_set():
                return
            identity = (task["task"], arm.name, trial)
            if self.attempt_admission is not None:
                reason = self.attempt_admission(*identity)
                if reason == "paused":
                    self._paused.set()
                    return
                if reason == "cancelled":
                    self.cancel()
                    return
                if reason is not None:
                    raise ValueError(f"invalid attempt admission decision: {reason!r}")
            try:
                earned = self._run_episode(run_id, arm, task, trial)
            finally:
                if self.attempt_release is not None:
                    self.attempt_release(*identity)
        if earned and queue is not None and self._retry_budget_left(trial):
            with self._count_lock:
                queue.append((task, trial + self.k))

    def _run_dir(self, run_id: str) -> Path:
        d = self.out_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_episode(self, run_id: str, arm, task: dict, trial: int) -> bool:
        """Run one attempt and record its row. Returns whether it earned a retry."""
        task_id = task["task"]
        eid = f"{run_id}/{task_id}/{arm.name.replace('/', '_')}/t{trial}"
        ep_dir = evidence._long(self._run_dir(run_id) / "episodes" / task_id / arm.name.replace("/", "_") / f"t{trial}")
        ep_dir.mkdir(parents=True, exist_ok=True)
        prior = next((r for r in self.store.episodes(run=run_id, arm=arm.name)["rows"]
                      if r["episode_id"] == eid), None)
        if prior and "evidence_incomplete" in prior.get("flags", []):
            raise evidence.EvidenceIntegrityError(f"incomplete prior evidence requires reconciliation for {eid}")
        if prior and any(flag.startswith("grading_revision=") for flag in prior.get("flags", [])):
            raise evidence.EvidenceIntegrityError(f"regraded episode requires preserved generation recovery for {eid}")
        previous_manifest = ep_dir / "manifest.json"
        old_attempts = list(ep_dir.glob("attempt-*"))
        # A crash can precede the row/manifest commit. Keep those observations
        # untouched until their evidence and billing have been reconciled.
        if old_attempts and (prior is None or not previous_manifest.is_file()):
            raise evidence.EvidenceIntegrityError(f"unreconciled prior attempts for {eid}")
        if prior and "evidence_manifest=v1" in prior.get("flags", []) and not previous_manifest.is_file():
            raise evidence.EvidenceIntegrityError(f"prior evidence manifest is missing for {eid}")
        for directory in old_attempts:
            try:
                metadata = json.loads((directory / "attempt.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
            if (not isinstance(metadata, dict) or metadata.get("status") != "finalized"
                    or metadata.get("completion") != "complete"):
                raise evidence.EvidenceIntegrityError(f"incomplete prior attempt for {eid}: {directory.name}")
        if previous_manifest.exists():
            problems = evidence.verify_manifest(previous_manifest, episode_id=eid,
                                                 contract_sha256=contract_hash(task))
            if problems:
                raise evidence.EvidenceIntegrityError(f"prior evidence is invalid for {eid}: {problems}")
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()

        termination, error, retries = "completed", None, 0
        result = ArmResult()
        acc = ArmResult()   # spend from failed attempts: paid for, so accounted
        prior_spend = (prior.get("cost_usd") or 0.0) if prior else 0.0
        if prior:
            tokens = prior.get("tokens") or {}
            acc.cost_usd = prior_spend
            acc.tokens_prompt = tokens.get("prompt", 0)
            acc.tokens_cached = tokens.get("cached", 0)
            acc.tokens_cache_write = tokens.get("cache_write", 0)
            acc.tokens_output = tokens.get("output", 0)
            acc.turns = prior.get("phases", {}).get("run", {}).get("turns", 0)
            acc.tool_calls = prior.get("tool_calls", 0)
            old_turns = ep_dir / "turns.jsonl"
            if old_turns.is_file():
                acc.turn_log = [json.loads(line) for line in old_turns.read_text(encoding="utf-8").splitlines()
                                if line.strip()]
        ep: Episode | None = None
        attempt = 0
        # Resume appends evidence; it must not erase the failed invocation.
        evidence_index = max((int(p.name.split("-")[1]) for p in ep_dir.glob("attempt-*")
                              if p.is_dir() and p.name.split("-")[1].isdigit()), default=-1) + 1
        while True:
            # PROVISION + SNAPSHOT0: fresh world per attempt (a retried episode
            # must not see the aborted attempt's writes).
            ep = Episode(task, episode_id=eid)
            ep.attach_journal(ep_dir / f"attempt-{evidence_index:03d}")
            # Where an arm may drop its own artifacts (the front door's access log).
            ep.artifacts_dir = ep_dir
            (ep_dir / "snapshot0.json").write_text(json.dumps(ep.snapshot0))
            deadline = time.monotonic() + self.timeout_s
            attempt_result = ArmResult()
            try:
                result = arm.run(ep, deadline=deadline)
                attempt_result = result
                termination, error = result.termination, result.error
                break
            except EpisodeTimeout as e:
                termination, error = "timeout", str(e)
                # A timed-out attempt still spent money and still reached some
                # phases; the row reports both (rule 9). No retry follows, so
                # the partial result is the result.
                result = getattr(e, "partial", None) or result
                attempt_result = result
                break
            except InfraError as e:
                termination, error = e.kind, str(e)
                partial = getattr(e, "partial", None)
                attempt_result = partial or ArmResult()
                if partial is not None:
                    for f in ("tokens_prompt", "tokens_cached", "tokens_cache_write", "tokens_output",
                              "cost_usd", "turns", "tool_calls"):
                        setattr(acc, f, getattr(acc, f) + getattr(partial, f))
                    acc.turn_log.extend(partial.turn_log)
                    acc.flags.extend(flag for flag in partial.flags if flag not in acc.flags)
                if not e.retryable or attempt >= MAX_INFRA_RETRIES:
                    break
                attempt += 1
                retries = attempt
                delay = min(e.retry_after if e.retry_after is not None else 2.0 ** attempt, 60.0)
                end = time.monotonic() + delay
                while time.monotonic() < end and not self._abort.is_set():
                    time.sleep(0.05)
                if self._abort.is_set():
                    break   # record the infra row; resume re-attempts it
            except Exception as e:
                termination, error = "agent_error", str(e)
                break
            finally:
                evidence.write_attempt(ep_dir, evidence_index, ep, attempt_result, termination, error)
                evidence_index += 1

        if any((acc.tokens_prompt, acc.tokens_cached, acc.tokens_cache_write, acc.tokens_output,
                acc.cost_usd, acc.turns, acc.tool_calls, acc.turn_log, acc.flags)):
            for f in ("tokens_prompt", "tokens_cached", "tokens_cache_write", "tokens_output",
                      "cost_usd", "turns", "tool_calls"):
                setattr(result, f, getattr(result, f) + getattr(acc, f))
            result.turn_log = acc.turn_log + result.turn_log
            result.flags.extend(flag for flag in acc.flags if flag not in result.flags)
            result.flags.append("spend_includes_failed_attempts")

        if prior:
            result.flags.append("spend_includes_resumed_attempts")
            result.flags.extend(flag for flag in prior.get("flags", [])
                                if flag in ("cost_missing", "billing=unknown") and flag not in result.flags)
            # The run aggregate includes prior invocations; detailed native
            # phases describe the latest invocation and retain attempt evidence.
            result.flags.append("detailed_phases=latest_invocation")

        # SNAPSHOT1 + GRADE + RECORD always run, whatever ARM_RUN did. A crash
        # in this stage records an infra:harness_crash row rather than losing
        # the episode; only a failing record_episode itself still propagates.
        try:
            snap1 = ep.finish()
            (ep_dir / "snapshot1.json").write_text(json.dumps(snap1))
            (ep_dir / "turns.jsonl").write_text(
                "\n".join(json.dumps(t) for t in result.turn_log) + ("\n" if result.turn_log else ""))
            g = self.grader(task, ep.snapshot0, snap1)
        except Exception as e:
            termination = "infra:harness_crash"
            crash = f"grade/record failed: {e}"
            error = f"{error}; {crash}" if error else crash
            g = {"passed": False, "assertions_passed": False,
                 "invariant": {"passed": False, "unexpected_changes": []},
                 "invariant_declared": False, "assertion_results": [], "n_changes": 0}

        if termination != "completed" and g["n_changes"] > 0:
            # The failed episode mutated the world before dying — visible, so a
            # REAL-mode reset (or an auditor) knows this wasn't a clean no-op.
            result.flags.append("partial_writes_before_failure")

        if trial >= self.k:
            # An extra attempt this prompt earned by failing, not a planned
            # repetition; flagged so a report can count and separate retries.
            result.flags.append("retry")

        model = (getattr(arm, "model_label", None)
                 or getattr(getattr(arm, "provider", None), "model_id", None))
        test_mode = self.run_config.plan.mode if self.run_config else None
        result.flags.append("evidence_manifest=v1")
        row = EpisodeRow(
            episode_id=eid, run_id=run_id, task_id=task_id, suite=self.suite,
            contract_sha256=contract_hash(task), arm=arm.name, trial=trial,
            model=model, test_mode=test_mode,
            passed=g["passed"] and termination == "completed",
            assertions_passed=g["assertions_passed"],
            invariant_passed=g["invariant"]["passed"],
            invariant_declared=g["invariant_declared"],
            check_results=[{k: r[k] for k in ("type", "passed")} for r in g["assertion_results"]],
            unexpected_changes=g["invariant"]["unexpected_changes"],
            count_violations=g["invariant"].get("count_violations", []),
            n_changes=g["n_changes"], tool_calls=result.tool_calls,
            tokens=TokenUsage(prompt=result.tokens_prompt, cached=result.tokens_cached,
                              cache_write=result.tokens_cache_write,
                              output=result.tokens_output),
            cost_usd=result.cost_usd, flags=result.flags, retries=retries,
            gate_refusals=result.gate_refusals,
            phases={**result.phases,
                    "run": PhaseMetrics(turns=result.turns, tool_calls=result.tool_calls,
                                        tokens_input=result.tokens_prompt,
                                        tokens_output=result.tokens_output,
                                        cost_usd=result.cost_usd,
                                        wall_clock_s=round(time.monotonic() - t0 + (
                                            prior.get("phases", {}).get("run", {}).get("wall_clock_s", 0)
                                            if prior else 0), 4))},
            termination=termination, error=error, artifacts_uri=str(ep_dir),
            started_at=started, finished_at=datetime.now(timezone.utc))
        evidence.write_events(ep_dir / "events.jsonl", ep.events)
        evidence.write_json(ep_dir / "grading.json", g)
        evidence.write_json(ep_dir / "result.json", {
            "termination": termination, "error": error, "final_text": result.final_text,
            "cost_usd": result.cost_usd, "flags": result.flags,
            "row": row.model_dump(mode="json")})
        evidence.write_manifest(
            ep_dir, episode_id=eid, contract_sha256=contract_hash(task),
            agent_messages="not_applicable" if isinstance(arm, _ScriptedAdapter) else
                           getattr(arm, "message_evidence", "unavailable"),
            private_reasoning="summaries" if any(isinstance(t, dict) and (t.get("response") or {}).get("reasoning")
                                                 for t in result.turn_log) else "unavailable")

        self.store.record_episode(row)
        for kind, name in (("snapshot0", "snapshot0.json"), ("snapshot1", "snapshot1.json"),
                           ("turns", "turns.jsonl"), ("events", "events.jsonl"),
                           ("grading", "grading.json"), ("result", "result.json"),
                           ("manifest", "manifest.json")):
            self.store.add_artifact(eid, kind, str(ep_dir / name))

        with self._count_lock:
            self._recorded += 1
            self._spent += (row.cost_usd or 0.0) - prior_spend
            if self._stop_after is not None and self._recorded >= self._stop_after:
                self._abort.set()
            # ponytail: at most concurrency x competitors in-flight attempts can finish
            # after the ceiling trips; a per-attempt pre-check before the provider call
            # is the upgrade.
            if (self.run_config and self._spent > self.run_config.plan.cost_ceiling_usd
                    and self._stop_reason is None):
                self._stop_reason = "cost_ceiling"
                self._abort.set()
            if termination == "infra:weekly_budget" and self._stop_reason is None:
                # The ledger refused a request: nothing else can be paid for this
                # week. Stop scheduling; the cut attempts run again on resume.
                self._stop_reason = "weekly_budget"
                self._abort.set()
        return self._earns_a_retry(row.passed, termination)


def regrade(store: Store, run_id: str, suite_dir: str | Path) -> dict[str, Any]:
    """Re-grade offline; append grading evidence before selecting the new verdict."""
    from wb_results import regrade_evidence
    tasks = {t["task"]: t for t in load_suite(suite_dir)}
    res = store.episodes(run=run_id)
    changed = regraded = drifted = missing_task = missing_artifacts = evidence_invalid = 0
    for r in res["rows"]:
        task = tasks.get(r["task_id"])
        if task is None:
            missing_task += 1
            continue
        # Provenance: never grade old snapshots against an edited contract.
        if r.get("contract_sha256") and contract_hash(task) != r["contract_sha256"]:
            drifted += 1
            continue
        if "evidence_incomplete" in r.get("flags", []):
            evidence_invalid += 1
            continue
        arts = store.artifacts(r["episode_id"])
        if (("evidence_manifest=v1" in r.get("flags", []) and "manifest" not in arts)
                or ("manifest" in arts and evidence.verify_manifest(
                    arts["manifest"], episode_id=r["episode_id"], contract_sha256=r.get("contract_sha256")))):
            evidence_invalid += 1
            continue
        if "snapshot0" not in arts or "snapshot1" not in arts:
            missing_artifacts += 1
            continue
        try:
            regrade_evidence.validate_current(r, arts)
            input_bindings = regrade_evidence.inputs(arts)
        except (evidence.EvidenceIntegrityError, OSError, ValueError):
            evidence_invalid += 1
            continue
        grader_provenance = evidence.provenance()
        s0 = json.loads(Path(arts["snapshot0"]).read_text())
        s1 = json.loads(Path(arts["snapshot1"]).read_text())
        g = grade(task, s0, s1)
        row = EpisodeRow(**r)
        new_passed = g["passed"] and row.termination == "completed"
        verdict_changed = (new_passed, g["assertions_passed"], g["invariant"]["passed"]) != (
            row.passed, row.assertions_passed, row.invariant_passed)
        row.passed = new_passed
        row.assertions_passed = g["assertions_passed"]
        row.invariant_passed = g["invariant"]["passed"]
        row.invariant_declared = g["invariant_declared"]
        row.check_results = [{k: x[k] for k in ("type", "passed")} for x in g["assertion_results"]]
        row.unexpected_changes = g["invariant"]["unexpected_changes"]
        row.count_violations = g["invariant"].get("count_violations", [])
        row.n_changes = g["n_changes"]
        try:
            regrade_evidence.publish(store, r, row, g, arts, input_bindings, grader_provenance)
        except evidence.EvidenceIntegrityError:
            evidence_invalid += 1
            continue
        changed += int(verdict_changed)
        regraded += 1
    return {"run_id": run_id, "regraded": regraded, "changed": changed,
            "contract_drift": drifted, "task_missing": missing_task, "evidence_invalid": evidence_invalid,
            "artifacts_missing": missing_artifacts}
