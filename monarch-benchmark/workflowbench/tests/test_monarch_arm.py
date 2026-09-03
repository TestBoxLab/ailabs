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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
from wb_arms.monarch import MonarchArm
from wb_orchestrator import config
from wb_orchestrator.config import ConfigError, load_product
from wb_orchestrator.orchestrator import Orchestrator, build_arm_for
from wb_report.report import build_report, render_md
from wb_results.store import Store
from wb_world.episode import Episode, load_suite, load_task_file

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
    assert all(header(r, "x-bench-episode-id") == ep.episode_id for r in starts)
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
    kb_hashes = {f"bench-{s}": f"{i:012x}" for i, s in enumerate(load_product(PRODUCT_PATH).services)}
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
            f"run-pilot/{t['task']}/{monarch_arm.name}/t{trial}": engine_calls_for(t)
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
    ("the stream closed with nothing terminal", {"frames": [RUNNING]},
     ("row", "agent_error", "stream_closed")),
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
    authored = any(r["path"] == "/api/workflows/recipe/runs" for r in fake.requests)         and any(f.get("status") == "done" for f in sc.frames)
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


def test_timeout_during_run(site, repo):
    """The engine never finishes: the workflow goes, and the spend still lands.

    Rule 9: money spent is money reported, whatever ended the attempt.
    """
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", run_never_finishes=True)
    with FakeMonarch(sc) as fake, FakeLangfuse() as lf:
        arm = arm_against(site, fake, port, repo, langfuse=lf,
                          env={**MONARCH_ENV, **LANGFUSE_ENV(lf)})
        arm.timeout_s = 1.0
        both_phases(lf, EPISODE)
        with pytest.raises(EpisodeTimeout) as exc:
            arm.run(Episode(task(), episode_id=EPISODE), deadline=time.monotonic() + 60)

    assert "execution" in str(exc.value)
    assert fake.deleted_workflows == ["wf-1"]
    assert exc.value.partial.cost_usd > 0
    assert exc.value.partial.phases["authoring"].cost_usd > 0
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
            trace(langfuse, EPISODE)
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
        both_phases(lf, f"run-t/{one_task.stem}/{arm.name}/t0")
        orch.run("run-t")

    row = store.episodes(run="run-t")["rows"][0]
    assert row["termination"] == "timeout"
    assert row["cost_usd"] > 0
    free(port)
