"""The Monarch competitor: its name, and one attempt end to end (US1, T023-T032).

The row name is the version read from the Monarch repo -- `monarch@<sha>`, plus
`+<branch>` off main -- so a report always says which build was measured. A
`monarch_repo` that is not a git checkout is a config error, not a crash.

The attempt tests drive the real arm against the fake backend: a completed
attempt writes to the `Episode` through the front door, the module lock keeps
two attempts from overlapping, a busy port is infrastructure, and the whole
pilot plan runs offline beside the answer key.
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from runner.arms import _sf_updates_from_assertions
from tests.fake_fd import fd_serving
from tests.fake_langfuse import FakeLangfuse
from tests.fake_monarch import FakeMonarch, Scenario
from tests.monarch_helpers import (  # noqa: F401  (repo is a fixture)
    KB, MONARCH_ENV, arm_against, free, free_port, git, monarch_site, repo, resolve_monarch)
from tests.test_config import (  # noqa: F401  (site is a fixture)
    HARNESS_MONARCH, HARNESS_SCRIPTED, PLAN, PRICE_TABLE, edit, site, write)
from tests.test_monarch_client import header
from wb_arms.api_loop import EpisodeTimeout, InfraError
from wb_arms.monarch import MonarchArm, bench_episode_id
from wb_arms.monarch_client import MonarchClient
from wb_orchestrator import config
from wb_orchestrator.config import ConfigError, load_product
from wb_orchestrator.orchestrator import Orchestrator, build_arm_for
from wb_report.report import build_report, render_md
from wb_results.store import Store
from wb_world.episode import Episode, load_suite, load_task_file
from wb_world.seeds import product_slug

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PATH = ROOT / "config/products/simulated-apps.yaml"


def monarch_arm(site, repo_path):
    """Build the Monarch competitor of a resolved plan pointed at `repo_path`."""
    monarch_site(site, monarch_repo=str(repo_path))
    rc = resolve_monarch(site)
    competitor = next(c for c in rc.competitors if c.harness.kind == "monarch")
    return build_arm_for(competitor, rc)


def test_arm_is_named_for_the_checked_out_commit(site, repo):
    arm = monarch_arm(site, repo)
    assert arm.name == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}"
    assert arm.model_label == arm.name


def test_a_branch_off_main_is_part_of_the_name(site, repo):
    git(repo, "checkout", "-q", "-b", "lab")
    arm = monarch_arm(site, repo)
    assert arm.name == f"monarch@{git(repo, 'rev-parse', '--short', 'HEAD')}+lab"
    assert arm.model_label == arm.name


def test_a_path_that_is_not_a_checkout_is_a_config_error(site, tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    with pytest.raises(ConfigError) as exc:
        monarch_arm(site, not_a_repo)
    assert exc.value.path == str(site / "config/harnesses/monarch.yaml")
    assert exc.value.field == "monarch_repo"
    assert "version" in str(exc.value)


# -- T025/T026: one attempt end to end ----------------------------------------

TASKS_DIR = ROOT / "tasks"
SF = "/salesforce/services/data/v61.0/sobjects"


def task(name: str = "simple.email_sf_contact_city_update") -> dict:
    return load_task_file(TASKS_DIR / f"{name}.json")


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """The fakes answer instantly; a 2 s production poll would only add dead time."""
    monkeypatch.setattr(MonarchArm, "POLL_INTERVAL_S", 0.02)


def city_of(snapshot: dict, contact_id: str = "003004") -> str:
    return next(c["mailing_city"] for c in snapshot["salesforce"]["contacts"]
                if c["id"] == contact_id)


def test_completed_attempt(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        ep = Episode(task(), episode_id="run-x/simple.email_sf_contact_city_update/monarch/t0")
        result = arm.run(ep, deadline=time.monotonic() + 60)
        snap1 = ep.finish()

    assert city_of(snap1) == "Denver"
    assert result.termination == "completed" and result.error is None
    ids = result.turn_log[0]["monarch"]
    assert ids["workflowId"] == "wf-1" and ids["runId"] == "run-1" and ids["recipeVersion"] == 1
    starts = [r for r in fake.requests
              if r["path"] == "/api/workflows/recipe/runs" or r["path"].endswith("/run")]
    assert len(starts) == 2
    # The header carries the id mapped into Monarch's charset, not the raw one.
    assert all(header(r, "x-bench-episode-id") == bench_episode_id(ep.episode_id)
               for r in starts)
    assert fake.deleted_workflows == ["wf-1"]
    assert result.phases["authoring"].wall_clock_s > 0
    assert result.phases["execution"].wall_clock_s > 0
    # The front door let go of its fixed port.
    s = socket.socket()
    s.bind(("0.0.0.0", port))
    s.close()


# -- T027/T028: one Monarch at a time, and a port that is already taken -------

def test_lock_serialises(site, repo):
    """Two attempts overlap in time; Monarch sees them one after the other."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})],
                  delay_s={"frame": 0.05})
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        errors = []

        def attempt(i):
            try:
                arm.run(Episode(task(), episode_id=f"run-x/t/monarch/t{i}"),
                        deadline=time.monotonic() + 60)
            except BaseException as e:            # noqa: BLE001  reported below
                errors.append(e)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
            assert not t.is_alive(), "an attempt never returned; the lock is stuck"

    assert not errors, errors
    assert len(fake.authoring_started_at) == 2 and len(fake.deleted_at) == 2
    # No overlap: the second authoring request only lands after the first
    # attempt finished, which its delete marks.
    assert fake.authoring_started_at[1] >= fake.deleted_at[0]


def test_port_busy_is_infra(site, repo):
    port = free_port()
    # A real server, like a second front door would be: SO_REUSEADDR (which
    # HTTPServer sets) lets a bare socket steal a bound port on Windows.
    busy = ThreadingHTTPServer(("0.0.0.0", port), BaseHTTPRequestHandler)
    try:
        with FakeMonarch(Scenario()) as fake:
            arm = arm_against(site, fake, port, repo)
            with pytest.raises(InfraError) as exc:
                arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                        deadline=time.monotonic() + 60)
    finally:
        busy.server_close()
    assert exc.value.kind == "infra:harness_crash" and exc.value.retryable
    assert str(port) in str(exc.value)


# -- T031/T032: the pilot plan end to end, offline ----------------------------

def engine_calls_for(t: dict) -> list[tuple]:
    """The answer key as REST calls on the front door: what a correct workflow does."""
    return [("PATCH", f"{SF}/{obj}/{rid}", {field: value})
            for obj, rid, field, value in _sf_updates_from_assertions(t)]


def pilot_site(tmp_path, monarch_url, fd_url, port, repo) -> Path:
    """A config tree on the 10 pilot tasks with two competitors: answer key and Monarch."""
    site = tmp_path / "site"
    for sub in ("products", "models", "harnesses", "plans"):
        (site / "config" / sub).mkdir(parents=True)
    # The shipped product: the pilot tasks and the 47-app knowledge base are its.
    (site / "config/products" / PRODUCT_PATH.name).write_text(
        PRODUCT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    write(site / "config/models", PRICE_TABLE)
    write(site / "config/harnesses", HARNESS_SCRIPTED)
    harness = (edit(HARNESS_MONARCH, "runnable", "true")
               .replace("modes: [full-flow, create-run, run-only]", "modes: [create-run]"))
    harness = (edit(edit(edit(harness, "base_url", monarch_url), "fd_url", fd_url),
                    "monarch_repo", str(repo))
               .replace("shim_port: 9105", f"shim_port: {port}")
               .replace("shim_public_host: host.docker.internal", "shim_public_host: 127.0.0.1"))
    write(site / "config/harnesses", harness)
    plan = edit(PLAN, "tasks", f'"{TASKS_DIR.as_posix()}"')
    plan = edit(edit(plan, "competitors"), "baseline", "oracle")
    plan += "competitors:\n  - {harness: oracle}\n  - {harness: monarch}\n"
    write(site / "config/plans", plan)
    return site


def test_pilot_plan_offline(tmp_path, repo, monkeypatch):
    """Answer key and Monarch on the 10 pilot tasks x 2, against fakes on free ports."""
    port = free_port()
    # The orchestrator builds its arms from os.environ, exactly as `wb run` does.
    for k, v in MONARCH_ENV.items():
        monkeypatch.setenv(k, v)
    tasks = load_suite(TASKS_DIR)
    kb_hashes = {product_slug(s): f"{i:012x}"
                 for i, s in enumerate(load_product(PRODUCT_PATH).services)}
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}")

    with FakeMonarch(sc) as monarch, fd_serving(kb_hashes) as fd:
        site = pilot_site(tmp_path, monarch.url, fd.url, port, repo)
        (site / "config/products/simulated-apps.monarch-kb.yaml").write_text(yaml.safe_dump(
            {"product": "simulated-apps", "generated_at": "2026-09-04T12:00:00Z",
             "seeds_format": "public-api-seeds@1",
             "shim_public_url": f"http://127.0.0.1:{port}", "kb": kb_hashes}))
        rc = config.resolve(site / "config/products/simulated-apps.yaml",
                            site / "config/plans/smoke-frontier.yaml",
                            env={**MONARCH_ENV}, audiences={"internal": ["*"]})
        store = Store(tmp_path / "wb.sqlite3")
        orch = Orchestrator.from_config(store, rc, tmp_path / "out")
        # One story per attempt: the workflow Monarch is pretended to have
        # authored performs that task's answer-key calls. The row is named for
        # the checkout, so the episode ids come from the built arm.
        monarch_arm = build_arm_for(
            next(c for c in rc.competitors if c.harness.kind == "monarch"), rc)
        sc.engine_calls_by_episode = {
            bench_episode_id(f"run-pilot/{t['task']}/{monarch_arm.name}/t{trial}"):
                engine_calls_for(t)
            for t in tasks for trial in range(2)}
        run_id = orch.run("run-pilot")

    rows = store.episodes(run=run_id)["rows"]
    assert len(rows) == 40
    oracle = [r for r in rows if r["arm"] == "oracle"]
    mon = [r for r in rows if r["arm"] != "oracle"]
    assert len(oracle) == 20 and all(r["passed"] for r in oracle)
    assert len(mon) == 20
    assert all(r["termination"] == "completed" for r in mon), \
        {r["episode_id"]: r["error"] for r in mon if r["termination"] != "completed"}
    assert all(r["test_mode"] == "create-run" for r in mon)
    assert all("snapshot1" in store.artifacts(r["episode_id"]) for r in mon)
    assert sum(r["passed"] for r in mon) == 20

    md = render_md(build_report(store, run_id, audience="internal"))
    assert "oracle" in md and mon[0]["arm"] in md
    cfg = json.loads(store.run(run_id)["config_json"])
    assert len(cfg["monarch_kb"]["kb"]) == 47
    assert "monarch-team-bedrock" in cfg["price_tables"]


# -- T033/T034: the FR-010 termination table ----------------------------------

@pytest.mark.parametrize("message, is_infra", [
    ("Bedrock AccessDeniedException", True),
    # this deployment authors through the Anthropic API, not Bedrock (4 Sep 2026)
    ("Anthropic API error: invalid x-api-key", True),
    ("rate limit exceeded, retry after 30s", True),
    ("Error code 529: overloaded_error", True),
    ("planner gave up", False),
    ("the workflow has no matching action", False),
])
def test_provider_messages_are_infrastructure_the_planner_s_are_not(message, is_infra):
    from wb_arms.monarch import _classify_authoring_error
    assert (_classify_authoring_error(message) is not None) is is_infra


DONE = {"status": "done", "workflowId": "wf-1", "recipeVersion": 1}
RUNNING = {"status": "running", "phase": "plan"}


def authoring_error(message: str) -> list[dict]:
    return [RUNNING, {"status": "error", "error": message}]


# (id, scenario kwargs, expected outcome). An outcome is either
# ("infra", kind, retryable) or ("row", termination, error prefix).
TERMINATION_ROWS = [
    ("authoring error from the model provider",
     {"frames": authoring_error("Bedrock AccessDeniedException")},
     ("infra", "infra:monarch_llm", True)),
    ("authoring error of the planner's own",
     {"frames": authoring_error("planner gave up")},
     ("row", "agent_error", "authoring_error:")),
    ("run refused: host blocked", {"run_refusal": "RUN_HOST_BLOCKED"},
     ("infra", "infra:monarch_setup", True)),
    ("run refused: engine unavailable", {"run_refusal": "ENGINE_UNAVAILABLE"},
     ("infra", "infra:monarch_setup", True)),
    ("run refused: already active", {"run_refusal": "RUN_ALREADY_ACTIVE"},
     ("infra", "infra:monarch_setup", True)),
    ("run refused: invalid input", {"run_refusal": "INPUT_INVALID"},
     ("row", "agent_error", "run_refused:INPUT_INVALID")),
    ("run refused: product not granted", {"run_refusal": "product_not_granted"},
     ("row", "agent_error", "run_refused:product_not_granted")),
    ("run refused: unacknowledged loop", {"run_refusal": "LLM_LOOP_UNACKNOWLEDGED"},
     ("row", "agent_error", "run_refused:LLM_LOOP_UNACKNOWLEDGED")),
    ("run refused: legacy recipe", {"run_refusal": "RUN_LEGACY_RECIPE"},
     ("row", "agent_error", "run_refused:RUN_LEGACY_RECIPE")),
    ("the run itself failed",
     {"run_outcome": {"status": "failed", "errorCode": "STEP_FAILED", "errorNodeId": "n7"}},
     ("row", "agent_error", "run_error:STEP_FAILED node=n7")),
    ("login refused", {"login_ok": False}, ("infra", "infra:harness_crash", True)),
    # A stream that just ends is a cut connection, not a verdict: only a job
    # Monarch no longer has (404 on reconnect) is `stream_closed`.
    ("the authoring job is gone", {"frames": [RUNNING], "stream_404_after": 1},
     ("row", "agent_error", "stream_closed")),
    # Monarch can finish authoring by declining: `done`, no workflow, a message
    # saying why. Live 4 Sep 2026; it used to read as success with nothing to run.
    ("Monarch declined to build the workflow",
     {"frames": [RUNNING, {"status": "done", "workflowId": None, "recipeVersion": None,
                           "message": "I can't build this workflow as specified, "
                                      "the opportunity id cannot be verified."}]},
     ("row", "agent_error", "no_workflow: I can't build this workflow as specified")),
    ("Monarch asked for an account",
     {"frames": [RUNNING, {"status": "awaiting_input",
                           "awaiting_reply": {"requestId": "req-1", "kind": "account"}}]},
     ("row", "agent_error", "account_requested")),
]


@pytest.mark.parametrize("kwargs,expected",
                         [r[1:] for r in TERMINATION_ROWS],
                         ids=[r[0] for r in TERMINATION_ROWS])
def test_termination_table(site, repo, kwargs, expected):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", **kwargs)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        ep = Episode(task(), episode_id="run-x/t/monarch/t0")
        kind, *rest = expected
        if kind == "infra":
            with pytest.raises(InfraError) as exc:
                arm.run(ep, deadline=time.monotonic() + 60)
            assert (exc.value.kind, exc.value.retryable) == tuple(rest)
        else:
            result = arm.run(ep, deadline=time.monotonic() + 60)
            assert result.termination == rest[0]
            assert result.error.startswith(rest[1]), result.error

    # Whatever happened, a workflow that was authored is gone and the port is free.
    # Only a `done` frame that actually names a workflow leaves one to delete.
    authored = any(r["path"] == "/api/workflows/recipe/runs" for r in fake.requests)         and any(f.get("status") == "done" and f.get("workflowId") for f in sc.frames)
    assert fake.deleted_workflows == (["wf-1"] if authored else [])
    s = socket.socket()
    s.bind(("0.0.0.0", port))
    s.close()


# -- T035/T036: the deadline, in either phase ---------------------------------

def test_timeout_during_authoring(site, repo):
    """The stream stalls past the deadline: cancel, then clean up, then give up."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", delay_s={"frame": 5.0})
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        arm.timeout_s = 0.5
        with pytest.raises(EpisodeTimeout) as exc:
            arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                    deadline=time.monotonic() + 60)

    assert "authoring" in str(exc.value)
    assert [r for r in fake.requests if r["path"].endswith("/cancel")]
    # Nothing was authored, so there is nothing to delete.
    assert fake.deleted_workflows == []
    free(port)


def test_timeout_during_run(site, repo, monkeypatch):
    """The engine never finishes: the workflow goes, and the spend still lands.

    Rule 9: money spent is money reported, whatever ended the attempt.
    """
    # The attempt budget includes shim initialization and login. Freeze only
    # the arm/client clock until a real execution poll has returned, so slow
    # setup cannot turn this into an authoring timeout. Leave server clocks
    # and socket timeouts real; the arm itself must detect the expired budget.
    now = 0.0
    clock = SimpleNamespace(monotonic=lambda: now, sleep=time.sleep)
    monkeypatch.setattr("wb_arms.monarch.time", clock)
    monkeypatch.setattr("wb_arms.monarch_client.time", clock)
    get_run = MonarchClient.get_run
    polls = []

    def expire_after_poll(client, run_id, deadline=None):
        nonlocal now
        assert not polls, "the arm polled again after its deadline"
        out = get_run(client, run_id, deadline=deadline)
        polls.append(out)
        now = deadline
        return out

    monkeypatch.setattr(MonarchClient, "get_run", expire_after_poll)
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", run_never_finishes=True)
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf:
        arm = arm_against(site, fake, port, repo, langfuse=lf,
                          env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})
        arm.timeout_s = 1.0
        both_phases(lf, BENCH_EPISODE)
        with pytest.raises(EpisodeTimeout) as exc:
            arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)

    assert "execution phase, polling run run-1" in str(exc.value)
    assert len(polls) == 1 and polls[0]["status"] == "running"
    assert len(fake.run_started_at) == 1
    assert fake.deleted_workflows == ["wf-1"]
    partial = exc.value.partial
    opus = (1000 * 5.00 + 500 * 0.50 + 100 * 6.25 + 200 * 25.00) / 1e6
    sonnet = (1000 * 2.00 + 500 * 0.20 + 100 * 2.50 + 200 * 10.00) / 1e6
    assert partial.cost_usd == pytest.approx(opus + sonnet)
    assert partial.phases["authoring"].cost_usd == pytest.approx(opus)
    assert partial.phases["execution"].cost_usd == pytest.approx(sonnet)
    assert partial.phases["execution"].wall_clock_s == arm.timeout_s
    free(port)


# -- T037: a workflow the last attempt could not delete -----------------------

def test_leftover_workflow_deleted_next_attempt(site, repo):
    """A delete that failed is remembered and retried at the start of the next attempt."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", delete_fails_once=True,
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        first = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                        deadline=time.monotonic() + 60)
        assert "workflow_not_deleted" in first.flags
        assert arm._leftover == ["wf-1"]

        arm.run(Episode(task(), episode_id="run-x/t/monarch/t1"),
                deadline=time.monotonic() + 60)

    assert arm._leftover == []
    assert fake.deleted_workflows == ["wf-1"]     # the retry is what finally landed it


# -- T038/T039: every question gets the same sentence -------------------------

def asking(request_id: str, *questions: str) -> dict:
    return {"status": "awaiting_input",
            "awaiting_reply": {"requestId": request_id,
                               "questions": [{"id": q, "text": f"{q}?"} for q in questions]}}


def test_questions_get_fixed_reply(site, repo):
    """Three questions over two prompts, all answered with the one sentence."""
    from wb_arms.monarch import FIXED_REPLY
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[RUNNING, asking("req-1", "q1", "q2"), RUNNING, asking("req-2", "q3"),
                          DONE],
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert [r["requestId"] for r in fake.replies_received] == ["req-1", "req-2"]
    answered = [a for r in fake.replies_received for a in r["answers"]]
    assert [a["id"] for a in answered] == ["q1", "q2", "q3"]
    assert {a["text"] for a in answered} == {FIXED_REPLY}
    assert result.phases["authoring"].turns == 3
    assert "questions_asked=3" in result.flags


def test_a_replayed_prompt_is_answered_and_counted_once(site, repo):
    """Monarch re-sends the awaiting_input frame after a reconnect (4 Sep: 327 copies)."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[RUNNING, asking("req-1", "q1", "q2"), asking("req-1", "q1", "q2"), DONE],
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert [r["requestId"] for r in fake.replies_received] == ["req-1"]
    assert result.phases["authoring"].turns == 2
    assert "questions_asked=2" in result.flags
    free(port)


def test_a_retry_answers_questions_with_the_request_and_guidance(site, repo):
    """Carlos, 4 Sep: on the retry the builder is told the request again plus
    the same guidance the models get; still no data beyond the request."""
    from wb_arms.monarch import RETRY_REPLY
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[RUNNING, asking("req-1", "q1"), DONE],
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t1"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    text = fake.replies_received[0]["answers"][0]["text"]
    assert text == RETRY_REPLY.format(goal=task()["prompt"][1]["content"])
    assert "do not ask further questions" in text
    free(port)


def test_an_attempt_with_no_questions_records_none(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed" and fake.replies_received == []
    assert result.phases["authoring"].turns == 0 and "questions_asked=0" in result.flags


# -- T043/T044: cost of the attempt, read from Langfuse -----------------------

OPUS = "anthropic.claude-opus-4-8-20260101-v1:0"
SONNET = "anthropic.claude-sonnet-5-20260101-v1:0"
EPISODE = "run-x/t/monarch/t0"
# What Monarch actually stamps on the trace: the header-safe form of EPISODE.
BENCH_EPISODE = bench_episode_id(EPISODE)
USAGE = {"input": 1000, "output": 200, "cache_read_input_tokens": 500,
         "cache_creation_input_tokens": 100}


def costed_attempt(site, repo, langfuse, trace=None, env=None):
    """One completed attempt whose traces `trace(langfuse, episode_id)` has laid down."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo, langfuse=langfuse,
                          env=env or {**MONARCH_ENV, **LANGFUSE_ENV(langfuse)})
        if trace is not None:
            trace(langfuse, BENCH_EPISODE)
        result = arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)
    free(port)
    return result


def LANGFUSE_ENV(langfuse) -> dict:
    """The address of a fake Langfuse, with the keys it was built with."""
    return {"LANGFUSE_URL": langfuse.url, "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_SECRET_KEY": "sk"}


def both_phases(lf, episode_id: str) -> None:
    lf.add_trace(episode_id,
                 spans=[("s1", "recipe.plan", None), ("s2", "engine.run", None)],
                 generations=[("g1", "s1", OPUS, USAGE), ("g2", "s2", SONNET, USAGE)])


def test_cost_lands_in_row(site, repo):
    with FakeLangfuse() as lf:
        result = costed_attempt(site, repo, lf, trace=both_phases)

    assert result.termination == "completed" and "cost_missing" not in result.flags
    # The row's prompt count is inclusive of cache (runner/schema.py::TokenUsage),
    # while Langfuse reports the three disjointly: 2 x (1000 + 500 + 100).
    assert result.tokens_prompt == 3200
    assert result.tokens_cached == 1000 and result.tokens_cache_write == 200
    assert result.tokens_output == 400
    # Opus 5.00/0.50/6.25/25.00 and Sonnet 2.00/0.20/2.50/10.00 per million.
    opus = (1000 * 5.00 + 500 * 0.50 + 100 * 6.25 + 200 * 25.00) / 1e6
    sonnet = (1000 * 2.00 + 500 * 0.20 + 100 * 2.50 + 200 * 10.00) / 1e6
    assert result.cost_usd == pytest.approx(opus + sonnet)
    assert result.phases["authoring"].cost_usd == pytest.approx(opus)
    assert result.phases["execution"].cost_usd == pytest.approx(sonnet)
    assert result.phases["authoring"].tokens_input == 1600
    assert result.phases["authoring"].tokens_output == 200
    assert result.phases["execution"].tokens_input == 1600
    breakdown = next(t["cost"] for t in result.turn_log if "cost" in t)
    assert breakdown["authoring"]["claude-opus-4-8"]["cost_usd"] == pytest.approx(opus)
    assert breakdown["execution"]["claude-sonnet-5"]["cost_usd"] == pytest.approx(sonnet)
    # Per-model phases, beside the real ones, for the report's model breakdown.
    # They are a second cut of the same spend, never a phase to sum with the others.
    assert result.phases["model:claude-opus-4-8"].cost_usd == pytest.approx(opus)
    assert result.phases["model:claude-sonnet-5"].cost_usd == pytest.approx(sonnet)
    assert result.phases["model:claude-opus-4-8"].tokens_input == 1600
    assert result.phases["model:claude-opus-4-8"].tokens_output == 200


def test_cost_read_is_bounded_by_the_attempt_start(site, repo):
    """Cloud returns every trace, so the read asks only for this attempt's window."""
    from datetime import datetime, timezone

    def old_and_new(lf, episode_id):
        lf.add_trace(episode_id, spans=[("s0", "recipe.plan", None)],
                     timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
                     generations=[("g0", "s0", OPUS, USAGE)])
        both_phases(lf, episode_id)

    with FakeLangfuse() as lf:
        result = costed_attempt(site, repo, lf, trace=old_and_new)
        paths = [r["path"] for r in lf.requests]

    assert any("fromTimestamp=" in p for p in paths)
    # the 2020 trace is outside the window: two generations priced, not three
    assert result.tokens_output == 400


def test_no_traces_is_cost_missing(site, repo):
    with FakeLangfuse() as lf:
        result = costed_attempt(site, repo, lf)

    assert result.termination == "completed" and result.error is None
    assert result.cost_usd == 0 and "cost_missing" in result.flags


def test_a_span_outside_the_contract_is_flagged(site, repo):
    def trace(lf, episode_id):
        lf.add_trace(episode_id, spans=[("s1", "recipe.rewrite", None)],
                     generations=[("g1", "s1", OPUS, USAGE)])

    with FakeLangfuse() as lf:
        result = costed_attempt(site, repo, lf, trace=trace)

    assert result.termination == "completed"
    assert "phase_other:recipe.rewrite" in result.flags


def test_an_unmapped_model_stops_the_run(site, repo):
    def trace(lf, episode_id):
        lf.add_trace(episode_id, spans=[("s1", "recipe.plan", None)],
                     generations=[("g1", "s1", "meta.llama-4", USAGE)])

    with FakeLangfuse() as lf:
        with pytest.raises(InfraError) as exc:
            costed_attempt(site, repo, lf, trace=trace)

    assert not exc.value.retryable and "llama" in str(exc.value)


def test_langfuse_unreachable_only_flags(site, repo):
    lf = FakeLangfuse().start()
    lf.stop()                       # nothing answers on that address any more
    result = costed_attempt(site, repo, lf, env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})

    assert result.termination == "completed" and result.error is None
    assert result.cost_usd == 0 and "cost_missing" in result.flags


def test_a_timed_out_row_keeps_its_spend(site, repo, tmp_path, monkeypatch):
    """The recorded row, not just the exception: a timeout still shows what it cost."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", run_never_finishes=True)
    kb_hashes = yaml.safe_load(KB)["kb"]     # prepare() must find these unchanged
    env = {**MONARCH_ENV}
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf, fd_serving(kb_hashes) as fd:
        env |= LANGFUSE_ENV(lf)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        arm = arm_against(site, fake, port, repo, fd=fd, langfuse=lf, env=env)
        plan = edit((site / "config/plans/smoke-frontier.yaml").read_text(), "competitors")
        plan = edit(plan, "baseline", "monarch").replace("repetitions: 2", "repetitions: 1")
        plan = plan.replace("timeout_s: 600", "timeout_s: 1")
        plan += "competitors:\n  - {harness: monarch}\n"
        write(site / "config/plans", plan)
        one_task = site / "tasks" / "simple.email_sf_contact_city_update.json"
        rc = config.resolve(site / "config/products/simulated-apps.yaml",
                            site / "config/plans/smoke-frontier.yaml",
                            env=env, audiences={"internal": ["*"]})
        rc.tasks = [t for t in rc.tasks if t["task"] == one_task.stem]
        store = Store(tmp_path / "wb.sqlite3")
        orch = Orchestrator.from_config(store, rc, tmp_path / "out")
        both_phases(lf, bench_episode_id(f"run-t/{one_task.stem}/{arm.name}/t0"))
        orch.run("run-t")

    row = store.episodes(run="run-t")["rows"][0]
    assert row["termination"] == "timeout"
    assert row["cost_usd"] > 0
    free(port)


def test_prepare_sends_the_fd_api_key_when_the_harness_names_one(site, repo):
    """The Railway discovery service gates /v1/seeds (verified 4 Sep 2026)."""
    port = free_port()
    kb_hashes = yaml.safe_load(KB)["kb"]
    with FakeMonarch(Scenario()) as fake, fd_serving(kb_hashes, api_key="s3cret") as fd:
        env = {**MONARCH_ENV, "FD_API_SHARED_SECRET": "s3cret"}
        arm = arm_against(site, fake, port, repo, fd=fd, env=env)
        # unkeyed the gate refuses, and the check must not pass silently
        with pytest.raises(InfraError):
            arm.prepare()
        arm.harness.fd_api_key_env = "FD_API_SHARED_SECRET"
        arm.prepare()
        keyed = [r for r in fd.requests if r["path"].startswith("/v1/")][-1]
    assert keyed["headers"].get("X-Fd-Api-Key") == "s3cret"
    free(port)


def test_an_infra_failure_keeps_its_spend(site, repo):
    """Rule 9 on the infrastructure path too: authoring was paid for before the refusal."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", run_refusal="RUN_HOST_BLOCKED")
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf:
        arm = arm_against(site, fake, port, repo, langfuse=lf,
                          env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})
        both_phases(lf, BENCH_EPISODE)
        with pytest.raises(InfraError) as exc:
            arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)

    assert exc.value.kind == "infra:monarch_setup" and exc.value.retryable
    assert exc.value.partial.cost_usd > 0
    free(port)


def test_each_generation_is_billed_once_across_retries(site, repo):
    """Retries share the episode id, so a second read must not bill it twice.

    The orchestrator sums the `partial` of every failed attempt into the row,
    while Langfuse returns every generation ever tagged with the episode id.
    """
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf:
        arm = arm_against(site, fake, port, repo, langfuse=lf,
                          env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})
        both_phases(lf, BENCH_EPISODE)

        def attempt():
            return arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)

        first = attempt()
        second = attempt()
        # A generation the previous attempts never saw: only that one is new.
        lf.add_trace(BENCH_EPISODE, spans=[("s3", "recipe.plan", None)],
                     generations=[("g3", "s3", OPUS, USAGE)])
        third = attempt()

    assert first.cost_usd > 0 and "cost_missing" not in first.flags
    # Nothing new to bill is not the same as nothing to find: no flag, no spend.
    assert second.cost_usd == 0 and "cost_missing" not in second.flags
    one_opus = (1000 * 5.00 + 500 * 0.50 + 100 * 6.25 + 200 * 25.00) / 1e6
    assert third.cost_usd == pytest.approx(one_opus)
    assert "cost_missing" not in third.flags
    free(port)


# -- live fixes from the first Railway attempt --------------------------------

# What the orchestrator really builds: slashes, an @ and a + in the arm name.
LIVE_EPISODE = "run-20260904-133230/simple.sf_opp_amount_update/monarch@e21dc0044+feat_railway-dev-deploy/t0"


def test_bench_episode_id_passes_monarch_header_regex():
    """Monarch drops a header outside `^[A-Za-z0-9._:-]{1,128}$`, losing the trace join."""
    from wb_arms.monarch import HEADER_SAFE, bench_episode_id
    got = bench_episode_id(LIVE_EPISODE)
    assert HEADER_SAFE.fullmatch(got), got
    # Readable, not hashed: the id still says which run, task and attempt.
    assert got.startswith("run-20260904-133230-simple.sf_opp_amount_update-monarch-e21dc0044")
    assert got.endswith("-t0") and "--" not in got
    assert bench_episode_id("a" * 200) == "a" * 128
    assert HEADER_SAFE.fullmatch(bench_episode_id("run/1/monarch@sha+br/t0"))


def test_the_safe_episode_id_is_what_monarch_and_langfuse_see(site, repo):
    """Both start requests carry it, and it is recorded so a human can find the trace."""
    from wb_arms.monarch import bench_episode_id
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id=LIVE_EPISODE),
                         deadline=time.monotonic() + 60)

    safe = bench_episode_id(LIVE_EPISODE)
    starts = [r for r in fake.requests
              if r["path"] == "/api/workflows/recipe/runs" or r["path"].endswith("/run")]
    assert len(starts) == 2
    assert all(header(r, "x-bench-episode-id") == safe for r in starts)
    assert result.turn_log[0]["monarch"]["bench_episode_id"] == safe


def test_a_cut_stream_is_reconnected(site, repo):
    """Railway cuts a long SSE response; the job is still running, so we reconnect."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[RUNNING, RUNNING, RUNNING, DONE],
                  stream_cut_after=2,
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert fake.stream_connections == 2          # cut once, resumed once
    assert result.turn_log[0]["monarch"]["workflowId"] == "wf-1"
    free(port)


def test_a_stream_that_404s_on_reconnect_is_a_lost_job(site, repo):
    """The job is gone: reconnecting forever would only burn the deadline."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[RUNNING, RUNNING, DONE],
                  stream_cut_after=1, stream_404_after=1)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "agent_error" and result.error == "stream_closed"
    free(port)


def test_cost_is_read_by_the_trace_ids_the_frames_named(site, repo):
    """The frames carry `traceId`; that is the join, not a metadata filter Cloud ignores."""
    port = free_port()
    trace_id = "6d84c5162775ed67b5f353fedd3c009f"
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[{**RUNNING, "traceId": trace_id}, {**DONE, "traceId": trace_id}],
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})])
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf:
        # No bench_episode_id on the trace: only the id from the frames can find
        # it, which is the whole point -- Cloud ignores the metadata filter.
        lf.add_trace(None, spans=[("s1", "recipe.plan", None)],
                     generations=[("g1", "s1", OPUS, USAGE)])
        lf.traces[-1]["id"] = trace_id
        for o in lf.observations:
            o["traceId"] = trace_id
        arm = arm_against(site, fake, port, repo, langfuse=lf,
                          env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})
        result = arm.run(Episode(task(), episode_id=LIVE_EPISODE),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert result.cost_usd > 0 and "cost_missing" not in result.flags
    assert trace_id in arm._trace_ids
    # Fetched by id, so the listing endpoint is never asked.
    assert any(f"/api/public/traces/{trace_id}" in r["path"] for r in lf.requests)
    free(port)


def test_a_declined_workflow_still_reports_its_cost(site, repo):
    """Authoring was paid for even though Monarch built nothing (rule 9)."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  frames=[RUNNING, {"status": "done", "workflowId": None,
                                    "message": "I can't build this workflow as specified."}])
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf:
        arm = arm_against(site, fake, port, repo, langfuse=lf,
                          env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})
        both_phases(lf, BENCH_EPISODE)
        result = arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)

    assert result.termination == "agent_error"
    assert result.error.startswith("no_workflow: I can't build this")
    assert result.cost_usd > 0 and "cost_missing" not in result.flags
    assert "execution" not in result.phases      # nothing ran, so no run phase
    assert fake.deleted_workflows == []
    free(port)


def test_run_status_success_is_completed(site, repo):
    """The live engine reports a finished run as "success" (verified 4 Sep 2026);
    both spellings end the poll as a normal finish."""
    from wb_arms.monarch import SUCCESS_RUN_STATES, TERMINAL_RUN_STATES
    assert {"success", "succeeded"} <= SUCCESS_RUN_STATES <= TERMINAL_RUN_STATES
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", run_outcome={"status": "success"})
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        ep = Episode(task(), episode_id="run-x/simple.email_sf_contact_city_update/monarch/t0")
        result = arm.run(ep, deadline=time.monotonic() + 60)
    assert result.termination == "completed" and result.error is None


# -- the run contract: the LLM-loop stamp and the declared inputs --------------
# 7 of 20 live attempts (4 Sep 2026) were refused at start with
# LLM_LOOP_UNACKNOWLEDGED or INPUT_INVALID. The stamp is per recipe version; the
# inputs are filled with no information beyond the request.

DENVER = [("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})]


def run_body(fake) -> dict:
    return fake.run_bodies[-1]


def test_a_recipe_with_an_llm_loop_is_acked_once_and_runs(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", has_llm_loop=True, engine_calls=DENVER)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert fake.llm_acks == [("wf-1", "1")]
    assert "llm_loop_acked=1" in result.flags
    assert run_body(fake) == {"mode": "live"}
    free(port)


def test_a_recipe_without_a_loop_gets_the_422_and_still_runs(site, repo):
    """LLM_LOOP_NOT_PRESENT is the normal answer for a recipe with no loop."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", engine_calls=DENVER)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed" and result.error is None
    assert [r["path"] for r in fake.requests].count(
        "/api/workflows/wf-1/versions/1/llm-ack") == 1
    assert fake.llm_acks == []
    assert "llm_loop_acked=1" not in result.flags
    free(port)


REQUIRED_INPUTS = [
    {"name": "spreadsheet_id", "label": "Budget spreadsheet ID", "type": "string",
     "required": True},
    {"name": "row_count", "label": "Rows", "type": "number", "required": True},
    {"name": "notify", "label": "Notify", "type": "boolean", "required": True},
    {"name": "folder", "label": "Folder", "type": "string", "required": False},
    {"name": "region", "label": "Region", "type": "string", "required": True,
     "default": "us-east"},
]


def test_required_inputs_end_the_attempt_before_the_run(site, repo):
    """Nothing may be invented for a required input, so the attempt stops (6 Sep 2026)."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", recipe_inputs=REQUIRED_INPUTS,
                  engine_calls=DENVER)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "agent_error"
    assert result.error == "needs_input:spreadsheet_id,row_count,notify"
    assert "inputs_required=3" in result.flags
    assert fake.run_bodies == [] and fake.llm_acks == []
    # the workflow is still cleaned up, as on any other ending
    assert fake.deleted_workflows == ["wf-1"]
    logged = next(t["inputs"] for t in result.turn_log if "inputs" in t)
    assert logged["declared"] == REQUIRED_INPUTS
    free(port)


def test_optional_inputs_and_defaults_still_run(site, repo):
    """Only a required input with no default stops the attempt; the body stays bare."""
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", engine_calls=DENVER,
                  recipe_inputs=[{"name": "folder", "type": "string", "required": False},
                                 {"name": "region", "type": "string", "required": True,
                                  "default": "us-east"}])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert run_body(fake) == {"mode": "live"}
    assert not [f for f in result.flags if f.startswith("inputs_required")]
    free(port)


def test_no_declared_inputs_sends_mode_only(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", engine_calls=DENVER)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed"
    assert run_body(fake) == {"mode": "live"}
    assert not [t for t in result.turn_log if "inputs" in t]
    free(port)


def test_an_undeclared_key_is_still_a_run_refusal(site, repo):
    """The backend's INPUT_INVALID reaches the row exactly as it does today."""
    from wb_arms.monarch_client import MonarchClient
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}",
                  recipe_inputs=[{"name": "sheet", "type": "string", "required": False}])
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        # a body the arm never builds: the run route must still refuse it
        original = MonarchClient.run_workflow
        MonarchClient.run_workflow = lambda self, wf, ep, mode="live", deadline=None: (
            self._call("POST", f"/api/workflows/{wf}/run", {"mode": mode, "inputs": {"other": "x"}},
                       headers={"x-bench-episode-id": ep}, deadline=deadline))
        try:
            result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                             deadline=time.monotonic() + 60)
        finally:
            MonarchClient.run_workflow = original

    assert result.termination == "agent_error"
    assert result.error == "run_refused:INPUT_INVALID"
    free(port)


# -- the unattended builder (harness key authoring_mode) -----------------------

def test_interactive_sends_no_authoring_field(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", engine_calls=DENVER)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert fake.authoring_bodies == [{"goal": task()["prompt"][1]["content"]}]
    assert "authoring=unattended" not in result.flags
    free(port)


def test_unattended_sends_the_authoring_field(site, repo):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", engine_calls=DENVER)
    with FakeMonarch(sc) as fake:
        arm = arm_against(site, fake, port, repo)
        arm.harness = replace(arm.harness, authoring_mode="unattended")
        result = arm.run(Episode(task(), episode_id="run-x/t/monarch/t0"),
                         deadline=time.monotonic() + 60)

    assert result.termination == "completed", result.error
    assert fake.authoring_bodies == [{"goal": task()["prompt"][1]["content"],
                                      "authoring": "unattended"}]
    assert "authoring=unattended" in result.flags
    free(port)
