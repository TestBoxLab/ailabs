"""The Monarch competitor: create + run mode, driven through Monarch's own HTTP API.

Monarch authors a workflow from the task's request text and then runs it against
the benchmark front door, so what is measured is the product a customer gets
rather than a model in a loop. The competitor is named for the checkout it ran
from (`monarch@<sha>`, plus `+<branch>` off main) so every row says which build
produced it. See specs/002 for the attempt flow.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from runner.schema import PhaseMetrics
from wb_arms.api_loop import ArmResult, EpisodeTimeout, InfraError
from wb_arms.http_shim import EpisodeHTTPShim
from wb_arms.langfuse_cost import (
    LangfuseUnavailable, PriceLookupError, read_generations, summarize)
from wb_arms.monarch_client import MonarchClient, MonarchRefused
from wb_orchestrator.monarch_setup import Stop, expand
from wb_world.episode import Episode

# ponytail: one Monarch at a time, because the front door owns a fixed port and
# the backend runs one workflow per bench user. Per-slot ports and one product
# set per slot are the upgrade if throughput ever matters.
_LOCK = threading.Lock()

TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "stopped"}

# A refusal the bench's own setup caused, not the workflow's: retried, and out of
# the pass-rate denominator (FR-010, FR-011). Anything else is the workflow's fault.
SETUP_REFUSALS = {"RUN_HOST_BLOCKED", "ENGINE_UNAVAILABLE", "RUN_ALREADY_ACTIVE"}

# ponytail: keyword match on the message, because the backend sends prose, not a
# code, for an authoring failure. Ceiling: a provider message that says none of
# these reads as the planner's own fault. Upgrade: a real error code from Monarch.
LLM_ERROR_KEYWORDS = ("bedrock", "aws", "credential", "not configured", "accessdenied")

# The same sentence for every question, so no attempt is helped more than another
# (rule 1: same request text for every competitor). It is code, never config.
FIXED_REPLY = "No further information is available. Proceed with your best judgment."


def _classify_authoring_error(message: str) -> InfraError | None:
    """The provider's fault -> infrastructure; anything else is the competitor's."""
    if any(k in (message or "").lower() for k in LLM_ERROR_KEYWORDS):
        return InfraError("infra:monarch_llm", f"Monarch's model provider: {message}",
                          retryable=True)
    return None


def _classify_refusal(code: str) -> InfraError | None:
    """A refused run: the bench's setup -> infrastructure; the workflow's -> the row."""
    if code in SETUP_REFUSALS:
        return InfraError("infra:monarch_setup", f"Monarch refused the run: {code}",
                          retryable=True)
    return None


def monarch_version(repo_path: str | Path) -> str:
    """Name the Monarch build in `repo_path`: `monarch@<sha>`, `+<branch>` off main."""
    def git(*args: str) -> str:
        out = subprocess.run(["git", "-C", str(repo_path), *args],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise ValueError(f"git {' '.join(args)} in {repo_path}: "
                             f"{(out.stderr or out.stdout).strip()}")
        return out.stdout.strip()

    sha = git("rev-parse", "--short", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    return f"monarch@{sha}" if branch == "main" else f"monarch@{sha}+{branch}"


class MonarchArm:
    provider_key = "monarch"
    POLL_INTERVAL_S = 2.0

    def __init__(self, harness, timeout_s: float, price_table, kb, env, name: str):
        self.harness = harness
        self.timeout_s = timeout_s
        self.price_table = price_table
        self.kb = kb
        self.env = env
        self.name = name
        self.model_label = name          # recorded as EpisodeRow.model (R6)
        self._token: str | None = None   # one login per run, cached here
        self._infra: InfraError | None = None   # raised after cleanup, see run()
        self._leftover: list[str] = []   # workflows a failed delete left behind

    def prepare(self) -> None:
        """Refuse the run if Monarch's knowledge base is not the one that was frozen.

        A different knowledge base is a different run (FR-019/020), so this is
        checked once, before the first attempt, and is never worth retrying.
        """
        url = expand(self.harness.fd_url, self.env, "fd_url") + "/v1/seeds"
        try:
            with urllib.request.urlopen(url, timeout=10.0) as r:
                items = json.loads(r.read() or b"{}").get("items") or []
        except (OSError, json.JSONDecodeError) as e:
            raise InfraError("infra:harness_crash",
                             f"knowledge base check failed: {url}: {e}", retryable=False) from e
        live = {i.get("slug"): i.get("kb_hash") for i in items}
        for slug, want in self.kb.kb.items():
            got = live.get(slug)
            if got != want:
                raise InfraError(
                    "infra:harness_crash",
                    f"knowledge base drift for {slug}: the run was frozen with {want}, "
                    f"the discovery service reports {got or 'nothing imported'}; "
                    "rerun `wb monarch setup` or use the matching build",
                    retryable=False)

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        """One attempt: author a workflow from the request text, run it, clean up.

        The deadline the orchestrator passes was taken before the queue; the
        attempt's own clock starts when it owns Monarch, so waiting for the lock
        never eats another attempt's budget. `deadline` is therefore ignored.
        """
        h = self.harness
        with _LOCK:
            attempt_deadline = time.monotonic() + self.timeout_s
            port = h.shim_port
            try:
                shim = EpisodeHTTPShim(ep, port=port, host="0.0.0.0",
                                       public_url=f"http://{h.shim_public_host}:{port}").start()
            except OSError as e:
                raise InfraError("infra:harness_crash",
                                 f"front door port {port} busy: {e}", retryable=True) from e
            try:
                res = self._attempt(ep, attempt_deadline)
            finally:
                shim.stop()
        # Cost is read after the front door is down and the lock is free: it is
        # bookkeeping, and a slow Langfuse must not hold the next attempt.
        self._add_cost(res, ep.episode_id)
        # After the cleanup and outside the lock, so the orchestrator's retry
        # starts against a free port and an idle Monarch (FR-011).
        if self._infra is not None:
            infra, self._infra = self._infra, None
            raise infra
        return res

    def _add_cost(self, res: ArmResult, episode_id: str) -> None:
        """Price the attempt's traces. Never changes the verdict (contract §4 rule 5).

        The one exception is a model with no price: the run stops rather than
        report a cost that silently omits it.
        """
        h = self.harness
        try:
            gens = read_generations(
                expand(h.langfuse_url, self.env, "langfuse_url"),
                self.env.get(h.langfuse_public_key_env or "") or "",
                self.env.get(h.langfuse_secret_key_env or "") or "",
                episode_id, self.price_table)
        except (LangfuseUnavailable, Stop):
            # Unreachable, or no address configured: the attempt's verdict stands
            # and the report shows the cost as missing.
            res.flags.append("cost_missing")
            return
        except PriceLookupError as e:
            self._infra = InfraError("infra:harness_crash", str(e), retryable=False)
            return
        cost = summarize(gens, self.price_table)
        if cost.missing:
            res.flags.append("cost_missing")
            return
        res.turn_log.append({"cost": cost.by_phase})
        res.cost_usd = cost.total_usd
        # EpisodeRow.tokens.prompt is the TOTAL input, cache included
        # (runner/schema.py::TokenUsage), while Langfuse reports the three
        # disjointly -- so the cache counts are added in, not left beside.
        t = cost.tokens
        res.tokens_prompt = t["input"] + t["cache_read"] + t["cache_write"]
        res.tokens_cached = t["cache_read"]
        res.tokens_cache_write = t["cache_write"]
        res.tokens_output = t["output"]
        for phase, families in cost.by_phase.items():
            metrics = res.phases.get(phase)
            if metrics is None:
                continue
            metrics.tokens_input = sum(r["input"] + r["cache_read"] + r["cache_write"]
                                       for r in families.values())
            metrics.tokens_output = sum(r["output"] for r in families.values())
            metrics.cost_usd = round(sum(r["cost_usd"] for r in families.values()), 6)
        res.flags += [f"phase_other:{name}" for name in cost.other_spans]

    # -- the attempt, with the front door already up ---------------------------

    def _client(self, deadline: float) -> MonarchClient:
        """The logged-in client for this run; the session is reused across attempts.

        Only ever called under `_LOCK`: caching the token is a read-modify-write
        on the arm, and two attempts logging in at once would race on it.
        """
        assert _LOCK.locked(), "_client caches the session token; call it under _LOCK"
        h = self.harness
        token = self._token or self.env.get(h.credential_env or "")
        client = MonarchClient(expand(h.base_url, self.env, "base_url"), token=token)
        if not token:
            self._token = client.login(h.login_email, self.env.get(h.login_password_env or ""),
                                       deadline=deadline)
        return client

    def _attempt(self, ep: Episode, deadline: float) -> ArmResult:
        res = ArmResult()
        self._infra = None
        client = self._client(deadline)
        self._sweep(client)
        goal = ep.task["prompt"][1]["content"]
        ids: dict = {}
        res.turn_log.append({"monarch": ids})
        workflow_id = None
        try:
            workflow_id = self._author(client, ep, goal, deadline, res, ids)
            if workflow_id is None:
                return res
            self._execute(client, ep, workflow_id, deadline, res, ids)
            return res
        finally:
            if workflow_id:
                # Cleanup must not turn a graded attempt into a crash; the row
                # keeps its termination and the leftover shows up in the log.
                if not self._delete(client, workflow_id):
                    res.turn_log.append({"cleanup_failed": workflow_id})
                    res.flags.append("workflow_not_deleted")

    def _reply(self, client, recipe_run: str, frame: dict, deadline: float) -> int | None:
        """Answer every question in the frame with the one sentence; count them.

        None means the prompt cannot be answered that way -- an account prompt,
        or a prompt with no questions in it -- and the attempt ends.
        """
        ask = frame.get("awaiting_reply") or {}
        questions = ask.get("questions") or []
        if ask.get("kind") == "account" or not questions:
            return None
        client.reply(recipe_run, ask.get("requestId", ""),
                     [{"id": q.get("id"), "text": FIXED_REPLY} for q in questions],
                     deadline=deadline)
        return len(questions)

    def _cancel(self, client, recipe_run: str) -> None:
        """Best effort: a cancel that fails must not hide why the attempt ended."""
        try:
            client.cancel(recipe_run, deadline=time.monotonic() + 30)
        except (InfraError, MonarchRefused):
            pass

    def _delete(self, client, workflow_id: str) -> bool:
        """Delete one workflow; remember it for the next attempt if it will not go."""
        try:
            client.delete_workflow(workflow_id, deadline=time.monotonic() + 30)
        except (InfraError, MonarchRefused):
            if workflow_id not in self._leftover:
                self._leftover.append(workflow_id)
            return False
        return True

    def _sweep(self, client) -> None:
        """Clear what a previous attempt could not delete, before authoring a new one."""
        for workflow_id in list(self._leftover):
            if self._delete(client, workflow_id):
                self._leftover.remove(workflow_id)

    def _author(self, client, ep, goal, deadline, res, ids) -> str | None:
        """Stream the authoring run; return the workflow id, or fill `res` and return None."""
        t0 = time.monotonic()
        recipe_run = client.start_authoring(goal, ep.episode_id, deadline=deadline)
        ids["recipeRunId"] = recipe_run
        workflow_id, questions = None, 0
        try:
            try:
                for frame in client.stream(recipe_run, deadline=deadline):
                    res.turn_log.append({"frame": frame})
                    status = frame.get("status")
                    if status == "done":
                        workflow_id = frame.get("workflowId")
                        ids["workflowId"] = workflow_id
                        ids["recipeVersion"] = frame.get("recipeVersion")
                        break
                    if status == "error":
                        message = frame.get("error")
                        self._infra = _classify_authoring_error(message)
                        res.termination = "agent_error"
                        res.error = f"authoring_error: {message}"
                        break
                    if status == "awaiting_input":
                        asked = self._reply(client, recipe_run, frame, deadline)
                        if asked is None:      # an account prompt, or nothing to answer
                            res.termination = "agent_error"
                            res.error = "account_requested"
                            self._cancel(client, recipe_run)
                            break
                        questions += asked
                        continue
                else:
                    res.termination = "agent_error"
                    res.error = "stream_closed"
            except EpisodeTimeout as e:
                # FR-012: nothing is left running behind a timed-out attempt.
                self._cancel(client, recipe_run)
                raise EpisodeTimeout(f"deadline passed in the authoring phase: {e}") from e
        finally:
            # Recorded even on a timeout: the phase clock is the FR-010 detail
            # that says where the deadline passed.
            res.phases["authoring"] = PhaseMetrics(turns=questions,
                                                   wall_clock_s=round(time.monotonic() - t0, 4))
            res.flags.append(f"questions_asked={questions}")
        return workflow_id

    def _execute(self, client, ep, workflow_id, deadline, res, ids) -> None:
        t0 = time.monotonic()
        try:
            try:
                started = client.run_workflow(workflow_id, ep.episode_id, deadline=deadline)
            except MonarchRefused as e:
                self._infra = _classify_refusal(e.code)
                res.termination = "agent_error"
                res.error = f"run_refused:{e.code}"
                return
            run_id = started.get("id") or (started.get("engine") or {}).get("runId")
            ids["runId"] = run_id
            while True:
                # Checked before the call, so the attempt overshoots its deadline
                # by at most one poll interval rather than by a whole request.
                if time.monotonic() >= deadline:
                    raise EpisodeTimeout(
                        f"deadline passed in the execution phase, polling run {run_id}")
                out = client.get_run(run_id, deadline=deadline)
                res.turn_log.append({"poll": out})
                status = out.get("status")
                if status in TERMINAL_RUN_STATES:
                    if status != "succeeded":
                        res.termination = "agent_error"
                        res.error = (f"run_error:{out.get('errorCode')} "
                                     f"node={out.get('errorNodeId')}")
                    return
                time.sleep(self.POLL_INTERVAL_S)
        finally:
            res.phases["execution"] = PhaseMetrics(wall_clock_s=round(time.monotonic() - t0, 4))
