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
from wb_arms.monarch_client import MonarchClient, MonarchRefused
from wb_orchestrator.monarch_setup import expand
from wb_world.episode import Episode

# ponytail: one Monarch at a time, because the front door owns a fixed port and
# the backend runs one workflow per bench user. Per-slot ports and one product
# set per slot are the upgrade if throughput ever matters.
_LOCK = threading.Lock()

TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "stopped"}


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
        never eats another attempt's budget.
        """
        h = self.harness
        with _LOCK:
            deadline = time.monotonic() + self.timeout_s
            port = h.shim_port
            try:
                shim = EpisodeHTTPShim(ep, port=port, host="0.0.0.0",
                                       public_url=f"http://{h.shim_public_host}:{port}").start()
            except OSError as e:
                raise InfraError("infra:harness_crash",
                                 f"front door port {port} busy: {e}", retryable=True) from e
            try:
                return self._attempt(ep, deadline)
            finally:
                shim.stop()

    # -- the attempt, with the front door already up ---------------------------

    def _client(self, deadline: float) -> MonarchClient:
        """The logged-in client for this run; the session is reused across attempts."""
        h = self.harness
        token = self._token or self.env.get(h.credential_env or "")
        client = MonarchClient(expand(h.base_url, self.env, "base_url"), token=token)
        if not token:
            self._token = client.login(h.login_email, self.env.get(h.login_password_env or ""),
                                       deadline=deadline)
        return client

    def _attempt(self, ep: Episode, deadline: float) -> ArmResult:
        res = ArmResult()
        client = self._client(deadline)
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
                try:
                    client.delete_workflow(workflow_id, deadline=time.monotonic() + 30)
                except (InfraError, MonarchRefused) as e:
                    res.turn_log.append({"cleanup_failed": str(e)})
                    res.flags.append("workflow_not_deleted")

    def _author(self, client, ep, goal, deadline, res, ids) -> str | None:
        """Stream the authoring run; return the workflow id, or fill `res` and return None."""
        t0 = time.monotonic()
        recipe_run = client.start_authoring(goal, ep.episode_id, deadline=deadline)
        ids["recipeRunId"] = recipe_run
        workflow_id = None
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
                    res.termination = "agent_error"
                    res.error = f"authoring_error: {frame.get('error')}"
                    break
                if status == "awaiting_input":
                    # T038/T039 answer questions; an account prompt is refused there too.
                    res.termination = "agent_error"
                    res.error = "account_requested"
                    client.cancel(recipe_run, deadline=deadline)
                    break
            else:
                res.termination = "agent_error"
                res.error = "stream_closed"
        finally:
            res.phases["authoring"] = PhaseMetrics(wall_clock_s=round(time.monotonic() - t0, 4))
        return workflow_id

    def _execute(self, client, ep, workflow_id, deadline, res, ids) -> None:
        t0 = time.monotonic()
        try:
            try:
                started = client.run_workflow(workflow_id, ep.episode_id, deadline=deadline)
            except MonarchRefused as e:
                res.termination = "agent_error"
                res.error = f"run_refused:{e.code}"
                return
            run_id = started.get("id") or (started.get("engine") or {}).get("runId")
            ids["runId"] = run_id
            while True:
                out = client.get_run(run_id, deadline=deadline)
                res.turn_log.append({"poll": out})
                status = out.get("status")
                if status in TERMINAL_RUN_STATES:
                    if status != "succeeded":
                        res.termination = "agent_error"
                        res.error = (f"run_error:{out.get('errorCode')} "
                                     f"node={out.get('errorNodeId')}")
                    return
                if time.monotonic() + self.POLL_INTERVAL_S >= deadline:
                    raise EpisodeTimeout(f"deadline hit polling workflow run {run_id}")
                time.sleep(self.POLL_INTERVAL_S)
        finally:
            res.phases["execution"] = PhaseMetrics(wall_clock_s=round(time.monotonic() - t0, 4))
