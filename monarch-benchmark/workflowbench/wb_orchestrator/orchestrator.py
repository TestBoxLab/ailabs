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
from wb_orchestrator import config as config_mod
from wb_orchestrator.config import ConfigError
from wb_world.episode import Episode, contract_hash, load_suite  # noqa: F401  (re-exported)

MAX_INFRA_RETRIES = 2
SUITE = "workflowbench-synthetic@0.1"


class RunKilled(Exception):
    pass


class ConfigDrift(Exception):
    pass


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


def build_arm_for(competitor: config_mod.Competitor, run_config: "config_mod.RunConfig | None" = None):
    """Build the arm a plan competitor names; the arm reports under the competitor's name (R1).

    Monarch is the exception: it reports under the version of the checkout it ran
    from, so `run_config` is required to build one (it carries the plan, the price
    table and the knowledge base).
    """
    h = competitor.harness
    if h.kind == "api":
        arm = ApiLoopArm(competitor.model.name)
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
        repo = config_mod.from_workflowbench(h.monarch_repo, config_dir)
        try:
            name = monarch_version(repo)
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
                          recipes_path=products / f"{run_config.product.name}.monarch-recipes.yaml")
    arm.name = competitor.name
    return arm


class Orchestrator:
    @classmethod
    def from_config(cls, store: Store, run_config: config_mod.RunConfig, out_dir: str | Path,
                    provider_concurrency: int | None = None) -> "Orchestrator":
        plan = run_config.plan
        # arms=[] skips the old key validation; competitor names are set below.
        self = cls(store, run_config.tasks_dir, [], plan.repetitions, out_dir,
                   timeout_s=plan.timeout_s,
                   provider_concurrency=provider_concurrency or plan.concurrency,
                   tasks=run_config.tasks, retry_on_fail=plan.retry_on_fail)
        self.arm_keys = [c.name for c in run_config.competitors]
        self.run_config = run_config
        return self

    def __init__(self, store: Store, suite_dir: str | Path, arms: list[str], k: int,
                 out_dir: str | Path, timeout_s: float = 600.0,
                 provider_concurrency: int = 4, stop_after: int | None = None,
                 tasks: list[dict] | None = None, retry_on_fail: int = 0):
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        if retry_on_fail < 0:
            raise ValueError(f"retry_on_fail must be >= 0, got {retry_on_fail}")
        if len(set(arms)) != len(arms):
            raise ValueError(f"duplicate arms would double-run identities: {arms}")
        for a in arms:
            _validate_arm_key(a)
        self.store = store
        self.run_config: config_mod.RunConfig | None = None
        self.suite_dir = str(suite_dir)
        self.tasks = tasks if tasks is not None else load_suite(suite_dir)
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

    def _config(self) -> dict:
        if self.run_config:
            return self.run_config.config_json
        return {"suite_dir": self.suite_dir, "arms": self.arm_keys, "k": self.k,
                "timeout_s": self.timeout_s, "n_tasks": len(self.tasks)}

    def _hash(self) -> str:
        if self.run_config:
            return self.run_config.hash
        return config_hash(self.tasks, self.arm_keys, self.k, self.timeout_s)

    def run(self, run_id: str | None = None) -> str:
        run_id = run_id or f"run-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        self.store.create_run(run_id, self._hash(), SUITE, self._config())
        self._execute(run_id, skip=set())
        return run_id

    def resume(self, run_id: str) -> str:
        run = self.store.run(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id!r}")
        if run["config_hash"] != self._hash():
            raise ConfigDrift(
                f"config drift: run has {run['config_hash']}, current config is {self._hash()}; "
                "refusing to resume")
        # The ceiling counts the run's cumulative spend, whatever stopped it.
        self._spent = self.store.status(run_id)["spend_usd"]
        if self.run_config and self.run_config.plan.cost_ceiling_usd <= self._spent:
            ceiling = self.run_config.plan.cost_ceiling_usd
            raise ConfigError(self.run_config.plan_path, "cost_ceiling_usd",
                              f"run {run_id}: spend US$ {self._spent:.2f} already meets ceiling "
                              f"US$ {ceiling:.2f}; raise cost_ceiling_usd in the plan to continue")
        self.store.set_stop_reason(run_id, None)  # the run is going again
        self._execute(run_id, skip=self.store.completed_identities(run_id))
        return run_id

    def _pending_retries(self, run_id: str, arm_name: str) -> list[tuple[dict, int]]:
        """Retries a resumed run still owes: a recorded attempt that failed on a
        non-infra termination, whose retry trial was never recorded.

        Derived from the store rather than remembered, so an interrupted run
        picks up exactly the retries it had not run yet.
        """
        if not self.retry_on_fail:
            return []
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
                        and self._retry_budget_left(trial) and trial + self.k not in trials):
                    work.append((task, trial + self.k))
        return work

    def _earns_a_retry(self, passed: bool, termination: str) -> bool:
        """A failed attempt is retried unless the infrastructure was what failed:
        those are already retried inside the episode and are not the task's verdict."""
        return bool(self.retry_on_fail) and not passed and not termination.startswith("infra:")

    def _retry_budget_left(self, trial: int) -> bool:
        """Trials 0..k-1 are the planned repetitions; each may spend `retry_on_fail`
        extra attempts, laid out as trial + k, + 2k, ... so no two identities clash."""
        return trial // self.k < self.retry_on_fail

    def _execute(self, run_id: str, skip: set[tuple[str, str, int]]) -> None:
        arms = ([build_arm_for(c, self.run_config) for c in self.run_config.competitors]
                if self.run_config
                else [build_arm(k) for k in self.arm_keys])
        threads = []
        for arm in arms:
            work = [(task, trial) for task in self.tasks for trial in range(self.k)
                    if (task["task"], arm.name, trial) not in skip]
            work += [(t, trial) for t, trial in self._pending_retries(run_id, arm.name)
                     if (t["task"], arm.name, trial) not in skip]
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
        if self._abort.is_set():
            raise RunKilled(f"run {run_id} killed after {self._recorded} episodes")
        self.store.finish_run(run_id)
        self.store.export_jsonl(run_id, self._run_dir(run_id) / "episodes.jsonl")

    def _run_arm_group(self, run_id: str, arm, work: list[tuple[dict, int]]) -> None:
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
            earned = self._run_episode(run_id, arm, task, trial)
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
        ep_dir = self._run_dir(run_id) / "episodes" / task_id / arm.name.replace("/", "_") / f"t{trial}"
        ep_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()

        termination, error, retries = "completed", None, 0
        result = ArmResult()
        acc = ArmResult()   # spend from failed attempts: paid for, so accounted
        ep: Episode | None = None
        attempt = 0
        while True:
            # PROVISION + SNAPSHOT0: fresh world per attempt (a retried episode
            # must not see the aborted attempt's writes).
            ep = Episode(task, episode_id=eid)
            (ep_dir / "snapshot0.json").write_text(json.dumps(ep.snapshot0))
            deadline = time.monotonic() + self.timeout_s
            try:
                result = arm.run(ep, deadline=deadline)
                termination, error = result.termination, result.error
                break
            except EpisodeTimeout as e:
                termination, error = "timeout", str(e)
                # A timed-out attempt still spent money and still reached some
                # phases; the row reports both (rule 9). No retry follows, so
                # the partial result is the result.
                result = getattr(e, "partial", None) or result
                break
            except InfraError as e:
                termination, error = e.kind, str(e)
                partial = getattr(e, "partial", None)
                if partial is not None:
                    for f in ("tokens_prompt", "tokens_cached", "tokens_cache_write", "tokens_output",
                              "cost_usd", "turns", "tool_calls"):
                        setattr(acc, f, getattr(acc, f) + getattr(partial, f))
                    acc.turn_log.extend(partial.turn_log)
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

        if acc.tokens_prompt or acc.cost_usd:
            for f in ("tokens_prompt", "tokens_cached", "tokens_cache_write", "tokens_output",
                      "cost_usd", "turns", "tool_calls"):
                setattr(result, f, getattr(result, f) + getattr(acc, f))
            result.turn_log = acc.turn_log + result.turn_log
            result.flags.append("spend_includes_failed_attempts")

        # SNAPSHOT1 + GRADE + RECORD always run, whatever ARM_RUN did. A crash
        # in this stage records an infra:harness_crash row rather than losing
        # the episode; only a failing record_episode itself still propagates.
        try:
            snap1 = ep.finish()
            (ep_dir / "snapshot1.json").write_text(json.dumps(snap1))
            (ep_dir / "turns.jsonl").write_text(
                "\n".join(json.dumps(t) for t in result.turn_log) + ("\n" if result.turn_log else ""))
            g = grade(task, ep.snapshot0, snap1)
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
        row = EpisodeRow(
            episode_id=eid, run_id=run_id, task_id=task_id, suite=SUITE,
            contract_sha256=contract_hash(task), arm=arm.name, trial=trial,
            model=model, test_mode=test_mode,
            passed=g["passed"] and termination == "completed",
            assertions_passed=g["assertions_passed"],
            invariant_passed=g["invariant"]["passed"],
            invariant_declared=g["invariant_declared"],
            check_results=[{k: r[k] for k in ("type", "passed")} for r in g["assertion_results"]],
            unexpected_changes=g["invariant"]["unexpected_changes"],
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
                                        wall_clock_s=round(time.monotonic() - t0, 4))},
            termination=termination, error=error, artifacts_uri=str(ep_dir),
            started_at=started, finished_at=datetime.now(timezone.utc))
        self.store.record_episode(row)
        for kind, name in (("snapshot0", "snapshot0.json"), ("snapshot1", "snapshot1.json"),
                           ("turns", "turns.jsonl")):
            self.store.add_artifact(eid, kind, str(ep_dir / name))

        with self._count_lock:
            self._recorded += 1
            self._spent += row.cost_usd or 0.0
            if self._stop_after is not None and self._recorded >= self._stop_after:
                self._abort.set()
            # ponytail: at most concurrency x competitors in-flight attempts can finish
            # after the ceiling trips; a per-attempt pre-check before the provider call
            # is the upgrade.
            if (self.run_config and self._spent > self.run_config.plan.cost_ceiling_usd
                    and self._stop_reason is None):
                self._stop_reason = "cost_ceiling"
                self._abort.set()
        return self._earns_a_retry(row.passed, termination)


def regrade(store: Store, run_id: str, suite_dir: str | Path) -> dict[str, Any]:
    """wb grade: re-grade offline from stored snapshots, update rows in place."""
    tasks = {t["task"]: t for t in load_suite(suite_dir)}
    res = store.episodes(run=run_id)
    changed = regraded = drifted = missing_task = missing_artifacts = 0
    for r in res["rows"]:
        task = tasks.get(r["task_id"])
        if task is None:
            missing_task += 1
            continue
        # Provenance: never grade old snapshots against an edited contract.
        if r.get("contract_sha256") and contract_hash(task) != r["contract_sha256"]:
            drifted += 1
            continue
        arts = store.artifacts(r["episode_id"])
        if "snapshot0" not in arts or "snapshot1" not in arts:
            missing_artifacts += 1
            continue
        s0 = json.loads(Path(arts["snapshot0"]).read_text())
        s1 = json.loads(Path(arts["snapshot1"]).read_text())
        g = grade(task, s0, s1)
        row = EpisodeRow(**r)
        new_passed = g["passed"] and row.termination == "completed"
        if (new_passed, g["assertions_passed"], g["invariant"]["passed"]) != (
                row.passed, row.assertions_passed, row.invariant_passed):
            changed += 1
        row.passed = new_passed
        row.assertions_passed = g["assertions_passed"]
        row.invariant_passed = g["invariant"]["passed"]
        row.invariant_declared = g["invariant_declared"]
        row.check_results = [{k: x[k] for k in ("type", "passed")} for x in g["assertion_results"]]
        row.unexpected_changes = g["invariant"]["unexpected_changes"]
        row.n_changes = g["n_changes"]
        store.record_episode(row)
        regraded += 1
    return {"run_id": run_id, "regraded": regraded, "changed": changed,
            "contract_drift": drifted, "task_missing": missing_task,
            "artifacts_missing": missing_artifacts}
