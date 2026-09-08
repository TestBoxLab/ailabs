"""The Monarch competitor: create + run mode, driven through Monarch's own HTTP API.

Monarch authors a workflow from the task's request text and then runs it against
the benchmark front door, so what is measured is the product a customer gets
rather than a model in a loop. The competitor is named for the checkout it ran
from (`monarch@<sha>`, plus `+<branch>` off main) so every row says which build
produced it. See specs/002 for the attempt flow.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runner.schema import PhaseMetrics
from wb_arms.api_loop import ArmResult, EpisodeTimeout, InfraError
from wb_arms.http_shim import EpisodeHTTPShim
from wb_arms.langfuse_cost import (
    LangfuseUnavailable, PriceLookupError, read_generations, summarize)
from wb_arms.monarch_client import MonarchClient, MonarchRefused
from wb_orchestrator.monarch_setup import expand, fd_headers, public_front_door_url
from wb_report.metrics import SYNTHETIC_PHASE_PREFIX
from wb_world.episode import Episode

# ponytail: one Monarch at a time, because the front door owns a fixed port and
# the backend runs one workflow per bench user. Per-slot ports and one product
# set per slot are the upgrade if throughput ever matters.
_LOCK = threading.Lock()

# verified 4 Sep 2026 on Railway: the engine reports a finished run as "success"
SUCCESS_RUN_STATES = {"succeeded", "success"}
TERMINAL_RUN_STATES = SUCCESS_RUN_STATES | {"failed", "failure", "error", "cancelled", "canceled", "stopped"}

# How long one read of `prepare()`'s recipe check may take: the login, and then
# each workflow read.
RECIPE_CHECK_BUDGET_S = 60.0

# ponytail: a fixed 60 s bound on waiting out a run already in flight, not a
# configurable one; the upgrade is a harness field if a real workflow ever
# legitimately runs longer than a bench attempt's deadline (research R4).
# Monarch has no run-cancel route, and run-only must not delete, so waiting is
# the only cure for the leftover of a timed-out attempt.
ACTIVE_RUN_WAIT_S = 60.0

# A workflow the run view revealed at the deadline is only worth running if
# there is time to run it; below this it is deleted and the row says why.
MIN_RUN_TIME_S = 60.0

# How long one read of the run view may take. Short: it is a backstop poll, and
# a slow one must not eat the beat it runs on.
DEFAULT_VIEW_BUDGET_S = 20.0

# The unattended builder runs on a fixed budget (30 turns, 20 minutes of wall
# clock from its first turn; backend 2ede4b3ee). Exhausting it is the
# competitor's own failure: the row records it bare, and the episode's
# infrastructure retry never sees it.
BUDGET_EXHAUSTED = "authoring_budget_exhausted"

# A live run can finish `done` having completed no write node. The engine says
# so in the run's `summary`; the bench reads such a run as a failed attempt,
# because a workflow that changed nothing did not do the task.
NO_WRITES = "no writes performed"

# A refusal the bench's own setup caused, not the workflow's: retried, and out of
# the pass-rate denominator (FR-010, FR-011). Anything else is the workflow's fault.
SETUP_REFUSALS = {"RUN_HOST_BLOCKED", "ENGINE_UNAVAILABLE", "RUN_ALREADY_ACTIVE"}

# ponytail: keyword match on the message, because the backend sends prose, not a
# code, for an authoring failure. Ceiling: a provider message that says none of
# these reads as the planner's own fault. Upgrade: a real error code from Monarch.
# The Anthropic words are there because this deployment authors through the
# Anthropic API directly, not Bedrock (verified 4 Sep 2026).
LLM_ERROR_KEYWORDS = ("bedrock", "aws", "credential", "not configured", "accessdenied",
                      "anthropic", "api key", "api_key", "rate limit", "rate_limit",
                      "overloaded", "529")

# The same sentence for every question, so no attempt is helped more than another
# (rule 1: same request text for every competitor). It is code, never config.
FIXED_REPLY = "No further information is available. Proceed with your best judgment."
# On a retry (trial >= 1) the builder gets the request again plus the same
# guidance the models' system prompt carries; still no data beyond the request.
RETRY_REPLY = ("No further information is available beyond the original request, which was: "
               "\"{goal}\" Make reasonable assumptions for anything it does not state, do not "
               "ask further questions, and build the workflow with your best judgment.")

# Monarch validates `x-bench-episode-id` against this and silently drops a header
# that fails, which loses the trace join and the whole attempt's cost. Our episode
# ids carry `/`, `@` and `+` (run/task/monarch@sha+branch/t0), so they are mapped
# into the charset first. Verified on Railway, 4 Sep 2026.
HEADER_SAFE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]+")


def bench_episode_id(episode_id: str) -> str:
    """The episode id as a header value: unsafe runs become one `-`, capped at 128."""
    return _UNSAFE.sub("-", episode_id)[:128]


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
    # How long the authoring loop waits without a frame before asking the run
    # view where the job stands, and the beat the stream reader wakes on. Both
    # are attributes, not constants, so the tests can turn them down.
    view_poll_interval_s = 20.0
    socket_timeout_s = 20.0

    def __init__(self, harness, timeout_s: float, price_table, kb, env, name: str,
                 mode: str = "create-run", recipes=None, kb_path=None, recipes_path=None):
        self.harness = harness
        self.timeout_s = timeout_s
        self.price_table = price_table
        self.kb = kb
        self.env = env
        self.name = name
        # run-only: the frozen recipes this competitor may run, and the knowledge-base
        # file they were made against. Both are None in create + run.
        self.mode = mode
        self.recipes = recipes
        self.kb_path = kb_path
        self.recipes_path = recipes_path
        # `wb monarch recipes` sets this: the attempt leaves its workflow standing
        # so the command can grade it first and then keep it or delete it.
        self.keep_workflows = False
        self._kept: list[str] = []
        self.model_label = name          # recorded as EpisodeRow.model (R6)
        self._token: str | None = None   # one login per run, cached here
        self._infra: InfraError | None = None   # raised after cleanup, see run()
        self._leftover: list[str] = []   # workflows a failed delete left behind
        # the attempt in flight; a timeout or infra failure reports what it reached
        self._partial = ArmResult()
        # episode id -> generations already priced, because the orchestrator
        # retries an episode under its own id and sums every attempt's spend
        self._billed: dict[str, set[str]] = {}
        self._bench_id = ""              # this attempt's header-safe episode id
        self._trace_ids: list[str] = []  # Langfuse traces this attempt's frames named
        self._started_at: datetime | None = None   # set by run(); bounds the cost read
        self._done_recipe: dict | None = None  # the done frame's recipe, for its `inputs`
        # a workflow the run view revealed once the deadline had passed: nothing
        # will run it, so `_attempt` deletes it rather than leave an orphan
        self._orphan: str | None = None

    def prepare(self) -> None:
        """Refuse the run if Monarch's knowledge base is not the one that was frozen.

        A different knowledge base is a different run (FR-019/020), so this is
        checked once, before the first attempt, and is never worth retrying.
        """
        url = expand(self.harness.fd_url, self.env, "fd_url") + "/v1/seeds"
        req = urllib.request.Request(url, headers=fd_headers(self.harness, self.env))
        try:
            with urllib.request.urlopen(req, timeout=10.0) as r:
                items = json.loads(r.read() or b"{}").get("items") or []
        except (OSError, json.JSONDecodeError) as e:
            raise InfraError("infra:harness_crash",
                             f"knowledge base check failed: {url}: {e}", retryable=False) from e
        # verified 4 Sep against the Railway discovery service: the hash is nested under `kb`
        live = {i.get("slug"): (i.get("kb") or {}).get("kb_hash") for i in items}
        for slug, want in self.kb.kb.items():
            got = live.get(slug)
            if got != want:
                raise InfraError(
                    "infra:harness_crash",
                    f"knowledge base drift for {slug}: the run was frozen with {want}, "
                    f"the discovery service reports {got or 'nothing imported'}; "
                    "rerun `wb monarch setup` or use the matching build",
                    retryable=False)
        if self.mode == "run-only":
            self._check_recipes()

    def _check_recipes(self) -> None:
        """Refuse a run-only run whose frozen recipes are not the ones Monarch holds.

        Two reads, both before any run request: the knowledge-base file must be the
        one the recipes were made against (FR-027), and each recorded workflow must
        still exist at the recorded recipe version (FR-026). Neither is retryable:
        a drifted recipe is a different run, not a flaky one.
        """
        from wb_orchestrator.monarch_recipes import kb_file_sha
        recipes, path = self.recipes, str(self.recipes_path or "the recipes file")
        sha = kb_file_sha(self.kb_path)   # the one definition, shared with the command
        if sha != recipes.kb_hash_file_sha:
            raise InfraError(
                "infra:harness_crash",
                f"the knowledge-base file {self.kb_path} is not the one the recipes in {path} "
                f"were made against (recorded {recipes.kb_hash_file_sha[:12]}, on disk "
                f"{sha[:12]}); the recipes must be remade with `wb monarch recipes`",
                retryable=False)
        # No lock and no front door: these are reads, and no attempt has started.
        client = MonarchClient(expand(self.harness.base_url, self.env, "base_url"),
                               token=self._token or self.env.get(self.harness.credential_env or ""))
        if not client.token:
            # prepare() runs before any attempt, so no lock: nothing else touches
            # _token yet, and caching it here saves the first attempt a login.
            self._token = client.login(
                self.harness.login_email, self.env.get(self.harness.login_password_env or ""),
                deadline=time.monotonic() + RECIPE_CHECK_BUDGET_S)
        for task_id, row in sorted(recipes.recipes.items()):
            # ponytail: a budget per read, not one for the whole check; the ceiling
            # is a set so large the checks alone become slow, which a corpus-sized
            # task set would reach long before Monarch does.
            live = client.get_workflow(row.workflow_id,
                                       deadline=time.monotonic() + RECIPE_CHECK_BUDGET_S)
            if live is None:
                raise InfraError(
                    "infra:harness_crash",
                    f"the recipe for task {task_id} is gone: Monarch does not hold workflow "
                    f"{row.workflow_id}, which {path} records; rerun `wb monarch recipes`",
                    retryable=False)
            if live.get("recipeVersion") != row.recipe_version:
                raise InfraError(
                    "infra:harness_crash",
                    f"recipe drift for task {task_id}: {path} froze workflow {row.workflow_id} "
                    f"at recipe version {row.recipe_version}, Monarch now holds version "
                    f"{live.get('recipeVersion')}; rerun `wb monarch recipes`",
                    retryable=False)

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        """One attempt: author a workflow from the request text, run it, clean up.

        The deadline the orchestrator passes was taken before the queue; the
        attempt's own clock starts when it owns Monarch, so waiting for the lock
        never eats another attempt's budget. `deadline` is therefore ignored.
        """
        h = self.harness
        failed = None
        # The window `_add_cost` asks Langfuse for. A minute of margin covers the
        # clock skew between this machine and the trace timestamps.
        self._started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        trial = ep.episode_id.rsplit("/t", 1)[-1]
        self._reply_text = (RETRY_REPLY.format(goal=ep.task["prompt"][1]["content"])
                            if trial.isdigit() and int(trial) >= 1 else FIXED_REPLY)
        # Inside the lock: `_bench_id` is per-attempt state on a shared arm, and
        # the orchestrator runs attempts of one competitor concurrently.
        with _LOCK:
            self._infra = None          # reset and read in this function only
            self._bench_id = bench_episode_id(ep.episode_id)
            attempt_deadline = time.monotonic() + self.timeout_s
            port = h.shim_port
            try:
                shim = EpisodeHTTPShim(ep, port=port, host="0.0.0.0",
                                       public_url=public_front_door_url(h, self.env)).start()
            except OSError as e:
                raise InfraError("infra:harness_crash",
                                 f"front door port {port} busy: {e}", retryable=True) from e
            try:
                res = self._attempt(ep, attempt_deadline)
            except (EpisodeTimeout, InfraError) as e:
                # Rule 9: the attempt spent money whatever ended it, so the row
                # must carry it. `partial` is what the orchestrator merges; it
                # already does that for an InfraError, and now for a timeout.
                failed, res = e, self._partial
            finally:
                shim.stop()
        # Cost is read after the front door is down and the lock is free: it is
        # bookkeeping, and a slow Langfuse must not hold the next attempt.
        self._add_cost(res, self._bench_id)
        # A refusal classified as infrastructure was stored rather than raised,
        # so cleanup could finish first (FR-011); it is raised here, outside the
        # lock and against a free port. `_add_cost` may have stored one of its
        # own; the `or` guard there keeps whichever came first.
        failed = failed or self._infra
        if failed is not None:
            failed.partial = res
            raise failed
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
                episode_id, self.price_table, from_timestamp=self._started_at,
                # The frames named their traces; the metadata filter is the fallback.
                trace_ids=self._trace_ids or None)
        except LangfuseUnavailable:
            # The attempt's verdict stands; the report shows the cost as missing.
            # An unset address or key never reaches here: resolve() refuses the
            # run before a cent is spent (FR-029).
            res.flags.append("cost_missing")
            return
        except PriceLookupError as e:
            # `or` so a retryable error already stored for this attempt keeps
            # its place: the run stops on it either way, and it came first.
            self._infra = self._infra or InfraError("infra:harness_crash", str(e),
                                                    retryable=False)
            return
        if not gens:
            res.flags.append("cost_missing")
            return
        # Every read returns all generations tagged with the episode id, and an
        # infra retry reuses that id, so anything an earlier attempt of this
        # episode already paid for is dropped before pricing. Nothing new to
        # bill is not the same as nothing found: the spend is already on the
        # earlier attempt, so this one reports zero without the flag.
        billed = self._billed.setdefault(episode_id, set())
        fresh = [g for g in gens if g.observation_id not in billed]
        billed.update(g.observation_id for g in fresh)
        if not fresh:
            return
        cost = summarize(fresh, self.price_table)
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
        # The same spend cut by model instead of by phase, so a report can say what
        # each model cost. These keys sit beside the real phases and must never be
        # summed with them: they are the same money counted another way. Every
        # consumer that has to skip them greps for SYNTHETIC_PHASE_PREFIX.
        per_model: dict[str, list[dict]] = {}
        for families in cost.by_phase.values():
            for family, r in families.items():
                per_model.setdefault(family, []).append(r)
        for family, rows in per_model.items():
            res.phases[f"{SYNTHETIC_PHASE_PREFIX}{family}"] = PhaseMetrics(
                cost_usd=round(sum(r["cost_usd"] for r in rows), 6),
                tokens_input=sum(r["input"] + r["cache_read"] + r["cache_write"] for r in rows),
                tokens_output=sum(r["output"] for r in rows))
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
        client = MonarchClient(expand(h.base_url, self.env, "base_url"), token=token,
                               socket_timeout_s=self.socket_timeout_s)
        if not token:
            self._token = client.login(h.login_email, self.env.get(h.login_password_env or ""),
                                       deadline=deadline)
        return client

    def _attempt(self, ep: Episode, deadline: float) -> ArmResult:
        # Held on the arm so a timeout can still report the phases it reached.
        res = self._partial = ArmResult()
        self._trace_ids = []
        self._done_recipe: dict | None = None
        client = self._client(deadline)
        self._sweep(client)
        goal = ep.task["prompt"][1]["content"]
        # bench_episode_id is recorded so a human can find the attempt's traces.
        ids: dict = {"bench_episode_id": self._bench_id}
        res.turn_log.append({"monarch": ids})
        if self.harness.authoring_mode == "unattended":
            # Only the non-default is flagged, so today's rows keep their flags.
            res.flags.append("authoring=unattended")
        if self.mode == "run-only":
            # The recipe is the bench's frozen artefact, reused by every attempt of
            # this run: nothing is authored, and nothing is deleted on any outcome
            # (FR-012, FR-016), so there is no cleanup `finally` here at all.
            row = self.recipes.recipes[ep.task["task"]]
            ids["workflowId"] = row.workflow_id
            ids["recipeVersion"] = row.recipe_version
            self._execute(client, ep, row.workflow_id, deadline, res, ids)
            return res
        workflow_id = None
        self._orphan = None
        try:
            workflow_id = self._author(client, ep, goal, deadline, res, ids)
            if workflow_id is None:
                return res
            self._execute(client, ep, workflow_id, deadline, res, ids)
            return res
        finally:
            workflow_id = workflow_id or self._orphan
            if workflow_id and self.keep_workflows:
                # `wb monarch recipes` decides keep-or-delete from the checker's
                # verdict, which needs the snapshot this attempt has not taken yet,
                # so the delete is deferred to it (`delete_workflow`).
                self._kept.append(workflow_id)
            elif workflow_id:
                # Cleanup must not turn a graded attempt into a crash; the row
                # keeps its termination and the leftover shows up in the log.
                if not self._delete(client, workflow_id):
                    res.turn_log.append({"cleanup_failed": workflow_id})
                    res.flags.append("workflow_not_deleted")

    def _note_trace(self, frame: dict) -> None:
        """Remember the trace a frame names: the primary join for the cost read."""
        trace_id = frame.get("traceId")
        if trace_id and trace_id not in self._trace_ids:
            self._trace_ids.append(trace_id)

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
                     [{"id": q.get("id"), "text": self._reply_text} for q in questions],
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

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow a `keep_workflows` attempt left standing.

        Only `wb monarch recipes` calls this, once it knows from the checker that
        the attempt did not pass. Takes the lock because it logs in.
        """
        with _LOCK:
            ok = self._delete(self._client(time.monotonic() + 30), workflow_id)
        if ok and workflow_id in self._kept:
            self._kept.remove(workflow_id)
        return ok

    def _sweep(self, client) -> None:
        """Clear what a previous attempt could not delete, before authoring a new one."""
        for workflow_id in list(self._leftover):
            if self._delete(client, workflow_id):
                self._leftover.remove(workflow_id)

    def _terminal(self, view: dict, res, ids) -> tuple[bool, str | None]:
        """Read a `done`/`error` frame or run view. (terminal?, workflow id)."""
        status = view.get("status")
        if status == "done":
            workflow_id = view.get("workflowId")
            ids["workflowId"] = workflow_id
            ids["recipeVersion"] = view.get("recipeVersion")
            # The declaration the run must satisfy; the workflow detail is the
            # fallback (_declared_inputs).
            self._done_recipe = view.get("recipe")
            assumptions = (self._done_recipe or {}).get("assumptions")
            if assumptions:
                # What the unattended builder decided for itself; the report
                # shows it beside the row.
                res.turn_log.append({"assumptions": assumptions})
            if not workflow_id:
                # Monarch finished by declining to build one: either it declined,
                # or triage read the request as not a workflow (unattended, and
                # `assistantText` is where it says why). There is nothing to run,
                # and reading it as success recorded `completed` for an attempt
                # that did nothing (live, 4 Sep 2026).
                message = view.get("message") or view.get("assistantText") or ""
                res.termination = "agent_error"
                res.error = f"no_workflow: {message[:200]}"
            return True, workflow_id
        if status == "error":
            message = view.get("error")
            self._infra = _classify_authoring_error(message)
            res.termination = "agent_error"
            # The unattended builder's fixed budget (30 turns, 20 minutes) is the
            # competitor's own failure, so it is recorded bare and never retried
            # as infra.
            res.error = (BUDGET_EXHAUSTED if message == BUDGET_EXHAUSTED
                         else f"authoring_error: {message}")
            return True, None
        return False, None

    def _view(self, client, recipe_run, res, ids, deadline) -> tuple[bool, str | None]:
        """Ask the run view where the job stands; read a terminal one like a frame.

        The backstop for a terminal frame the stream never delivered (live
        session 25ade669, 8 Sep 2026: the job finished `done` with the recipe
        saved and the bench streamed `running` for another 40 minutes). Recorded
        as `{"view": ...}` so a report can tell it from a frame. A view the
        backend cannot answer for is not a verdict: the stream stays the path.
        """
        try:
            view = client.get_authoring_run(recipe_run, deadline=min(
                deadline, time.monotonic() + DEFAULT_VIEW_BUDGET_S))
        except (InfraError, MonarchRefused):
            return False, None
        res.turn_log.append({"view": view})
        self._note_trace(view)
        return self._terminal(view, res, ids)

    def _author(self, client, ep, goal, deadline, res, ids) -> str | None:
        """Stream the authoring run; return the workflow id, or fill `res` and return None."""
        t0 = time.monotonic()
        recipe_run = client.start_authoring(goal, self._bench_id, deadline=deadline,
                                            authoring_mode=self.harness.authoring_mode)
        ids["recipeRunId"] = recipe_run
        workflow_id, questions = None, 0
        answered: set[str] = set()     # a reconnected stream replays the prompt
        try:
            try:
                # The stream can end without a terminal frame while the job runs
                # on: Railway's edge cuts a long SSE response (seen 4 Sep 2026,
                # frames stopped at ~85 s of a ~120 s authoring), and a terminal
                # frame can be lost outright (8 Sep 2026). So the stream is
                # re-opened, and the run view is polled as a backstop, until a
                # terminal frame or view arrives, the job is gone (404), or the
                # deadline passes.
                done = False
                while not done:
                    last_frame_at = time.monotonic()
                    try:
                        frames = client.stream(recipe_run, deadline=deadline)
                        for frame in frames:
                            if frame is None:
                                # The stream is open and silent. Wake, check the
                                # deadline, and ask the view once the beat is up.
                                if time.monotonic() >= deadline:
                                    raise EpisodeTimeout(
                                        f"deadline hit while streaming authoring "
                                        f"run {recipe_run}")
                                if (time.monotonic() - last_frame_at
                                        >= self.view_poll_interval_s):
                                    last_frame_at = time.monotonic()
                                    done, workflow_id = self._view(
                                        client, recipe_run, res, ids, deadline)
                                    if done:
                                        break
                                continue
                            last_frame_at = time.monotonic()
                            res.turn_log.append({"frame": frame})
                            self._note_trace(frame)
                            status = frame.get("status")
                            if status in ("done", "error"):
                                done, workflow_id = self._terminal(frame, res, ids)
                                break
                            if status == "awaiting_input":
                                rid = (frame.get("awaiting_reply") or {}).get("requestId")
                                if rid and rid in answered:
                                    continue
                                asked = self._reply(client, recipe_run, frame, deadline)
                                if rid:
                                    answered.add(rid)
                                if asked is None:   # an account prompt, or nothing to answer
                                    res.termination = "agent_error"
                                    res.error = "account_requested"
                                    self._cancel(client, recipe_run)
                                    done = True
                                    break
                                questions += asked
                    except InfraError as e:
                        # A 404 means the job no longer exists; reconnecting to a
                        # backend that is merely unwell is the deadline's problem.
                        if "404" not in str(e):
                            raise
                        res.termination = "agent_error"
                        res.error = "stream_closed"
                        done = True
                    if not done:
                        # The stream ended with no terminal frame. It may have
                        # been cut mid-job, or the ending may simply be lost:
                        # the view is what tells the two apart.
                        done, workflow_id = self._view(client, recipe_run, res, ids, deadline)
                    if not done:
                        # Paced, so a backend that closes instantly cannot spin.
                        if time.monotonic() + self.POLL_INTERVAL_S >= deadline:
                            raise EpisodeTimeout(
                                f"deadline passed reconnecting to authoring run {recipe_run}")
                        res.turn_log.append({"stream_reconnect": recipe_run})
                        time.sleep(self.POLL_INTERVAL_S)
            except EpisodeTimeout as e:
                # The deadline landed on a job that may already have finished:
                # one last view says so. A workflow it reveals is run only if
                # there is time to run it, and deleted by the caller otherwise,
                # so a timed-out attempt never leaves an orphan behind.
                done, workflow_id = self._view(client, recipe_run, res, ids,
                                               time.monotonic() + DEFAULT_VIEW_BUDGET_S)
                if done and workflow_id:
                    if deadline - time.monotonic() >= MIN_RUN_TIME_S:
                        return workflow_id
                    res.termination = "agent_error"
                    res.error = "no_time_for_run"
                    self._orphan = workflow_id
                    raise EpisodeTimeout(
                        f"deadline passed in the authoring phase: {e}") from e
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

    def _start_run(self, client, ep, workflow_id, deadline, res) -> dict | None:
        """Start the workflow, waiting out a run already in flight on it (FR-018).

        Create + run authors a fresh workflow every attempt, so it can never meet
        an active run; only run-only can, as the leftover of an attempt that hit
        its deadline with no way to cancel (research R4). None means the wait
        expired: `_infra` carries the retryable failure.
        """
        started_waiting = None
        while True:
            try:
                return client.run_workflow(workflow_id, self._bench_id, deadline=deadline)
            except MonarchRefused as e:
                if e.code != "RUN_ALREADY_ACTIVE" or self.mode != "run-only":
                    raise
            except InfraError as e:
                if "404" not in str(e):
                    raise
                # The recipe was deleted behind the bench's back, between
                # prepare()'s check and this attempt (FR-020).
                raise InfraError(
                    "infra:harness_crash",
                    f"the recipe for task {ep.task['task']} is gone: Monarch does not hold "
                    f"workflow {workflow_id}, which {self.recipes_path} records; "
                    "rerun `wb monarch recipes`", retryable=False) from e
            now = time.monotonic()
            if started_waiting is None:
                started_waiting = now
                res.turn_log.append({"waiting_for_active_run": workflow_id})
            waited = now - started_waiting
            if waited >= ACTIVE_RUN_WAIT_S or now + self.POLL_INTERVAL_S >= deadline:
                self._infra = InfraError(
                    "infra:monarch_setup",
                    f"a run is still active on workflow {workflow_id} after waiting "
                    f"{waited:.1f}s of {ACTIVE_RUN_WAIT_S:.1f}s; Monarch has no route to "
                    "cancel it, so this attempt is retried later", retryable=True)
                res.termination = "agent_error"
                res.error = "run_still_active"
                return None
            # Read the leftover so the log says what is holding the workflow; the
            # run route stays the gate, because only it knows when the lock is free.
            res.turn_log.append({"active_run": client.workflow_runs(workflow_id,
                                                                   deadline=deadline)})
            time.sleep(self.POLL_INTERVAL_S)

    def _llm_ack(self, client, workflow_id, version, deadline) -> bool:
        """Stamp the recipe version's LLM loop; True when a stamp was made.

        A version with no loop answers 422 LLM_LOOP_NOT_PRESENT, which is the
        normal case and not a refusal. Any other refusal is left to the caller,
        so it lands on the row as `run_refused:<code>` like the run's own.
        """
        if version is None:
            return False
        try:
            client.llm_ack(workflow_id, version, deadline=deadline)
        except MonarchRefused as e:
            if e.code == "LLM_LOOP_NOT_PRESENT":
                return False
            raise
        return True

    def _declared_inputs(self, client, workflow_id, deadline) -> list[dict]:
        """The recipe's `inputs`: from the done frame, else from the workflow detail."""
        recipe = self._done_recipe if self.mode != "run-only" else None
        if recipe is None:
            recipe = (client.get_workflow(workflow_id, deadline=deadline) or {}).get("recipe")
        return [d for d in ((recipe or {}).get("inputs") or []) if d.get("name")]

    @staticmethod
    def _needs_input(declared: list[dict]) -> list[str]:
        """The required inputs with no default: what a person would have to type.

        Nothing may be invented for them (rule 1: the same request text for every
        competitor), so an attempt that declares any of these cannot be run
        unattended and ends before the run (Carlos, 6 Sep 2026). An optional input
        and one with a default are simply left out of the run body.
        """
        return [d["name"] for d in declared if d.get("required") and "default" not in d]

    def _execute(self, client, ep, workflow_id, deadline, res, ids) -> None:
        t0 = time.monotonic()
        try:
            # Same discipline as the poll loop: never start work the deadline
            # has already passed, however long authoring took.
            if time.monotonic() >= deadline:
                raise EpisodeTimeout(
                    "deadline passed in the execution phase, before the run started")
            declared = self._declared_inputs(client, workflow_id, deadline)
            needed = self._needs_input(declared)
            if declared:
                res.turn_log.append({"inputs": {"declared": declared, "needed": needed}})
            if needed:
                # A workflow that asks a person for data is not a workflow the
                # bench can run; the row says so instead of guessing values.
                res.flags.append(f"inputs_required={len(needed)}")
                res.termination = "agent_error"
                res.error = "needs_input:" + ",".join(needed)
                return
            try:
                if self._llm_ack(client, workflow_id, ids.get("recipeVersion"), deadline):
                    res.flags.append("llm_loop_acked=1")
                started = self._start_run(client, ep, workflow_id, deadline, res)
            except MonarchRefused as e:
                self._infra = _classify_refusal(e.code)
                res.termination = "agent_error"
                res.error = f"run_refused:{e.code}"
                return
            if started is None:     # the wait expired; `res` and `_infra` are set
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
                    if status not in SUCCESS_RUN_STATES:
                        res.termination = "agent_error"
                        res.error = (f"run_error:{out.get('errorCode')} "
                                     f"node={out.get('errorNodeId')}")
                    elif NO_WRITES in (out.get("summary") or ""):
                        res.termination = "agent_error"
                        res.error = "run_no_writes"
                    return
                time.sleep(self.POLL_INTERVAL_S)
        finally:
            res.phases["execution"] = PhaseMetrics(wall_clock_s=round(time.monotonic() - t0, 4))
