"""The live view of a Monarch attempt (feature 011): the engine run stream and
the observer hook the Studio watches.

The client follows the stock `GET /api/engine/runs/:id/stream` until the engine
is terminal; a backend without the route makes the arm poll instead. Either
way the observer hears every builder frame, the recipe when the run starts,
each node whose state moved, and the end of the run.
"""
from __future__ import annotations

import time

import pytest

from tests.fake_monarch import FakeMonarch, Scenario
from tests.monarch_helpers import arm_against, free_port, repo  # noqa: F401  (repo is a fixture)
from tests.test_config import site  # noqa: F401  (fixture)
from tests.test_monarch_arm import SF, task
from wb_arms.api_loop import InfraError
from wb_arms.monarch import MonarchArm
from wb_arms.monarch_client import MonarchClient
from wb_world.episode import Episode

RECIPE = {"steps": [{"id": "read", "label": "Read the contact", "productSlug": "bench-salesforce", "kind": "action"},
                    {"id": "write", "label": "Update the city", "productSlug": "bench-salesforce", "kind": "action"}]}
FRAMES = [{"status": "running", "phase": "plan", "message": "Reading the request"},
          {"status": "done", "workflowId": "wf-1", "recipeVersion": 1, "recipe": RECIPE}]


def step(identity, status, label=None, **extra):
    return {"stepId": identity, "label": label or identity, "productSlug": "bench-salesforce", "status": status, **extra}


VIEWS = [{"steps": [step("read", "running"), step("write", "pending")]},
         {"steps": [step("read", "succeeded"), step("write", "running", progress={"current": 1, "total": 1})]},
         {"steps": [step("read", "succeeded"), step("write", "succeeded", message="MailingCity set")]}]


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(MonarchArm, "POLL_INTERVAL_S", 0.05)


def logged_in(fake) -> MonarchClient:
    client = MonarchClient(fake.url)
    client.login("bench@testbox.com", "monarch-dev")
    return client


# -- the client --------------------------------------------------------------------

def test_run_stream_yields_every_view_and_closes_when_the_engine_is_terminal():
    with FakeMonarch(Scenario(run_views=VIEWS)) as fake:
        client = logged_in(fake)
        started = client.run_workflow("wf-1", "ep-1")
        assert fake.wait_for_run(started["engine"]["runId"])
        views = list(client.run_stream(started["engine"]["runId"], deadline=time.monotonic() + 30))
    assert [v["engineState"]["status"] for v in views] == ["running", "running", "running", "done"]
    assert views[-1]["status"] == "succeeded"
    assert [s["status"] for s in views[-1]["steps"]] == ["succeeded", "succeeded"]


def test_run_stream_without_the_route_is_infrastructure_not_a_verdict():
    with FakeMonarch(Scenario()) as fake:
        client = logged_in(fake)
        started = client.run_workflow("wf-1", "ep-1")
        with pytest.raises(InfraError, match="HTTP 404"):
            list(client.run_stream(started["engine"]["runId"], deadline=time.monotonic() + 30))


def test_run_recipe_is_none_when_the_backend_has_no_such_run():
    with FakeMonarch(Scenario()) as fake:
        client = logged_in(fake)
        assert client.run_recipe("run-404") is None
        started = client.run_workflow("wf-1", "ep-1")
        assert client.run_recipe(started["id"])["runId"] == started["id"]


# -- the arm's observer -----------------------------------------------------------

def watched_attempt(site, repo, scenario):
    heard = []
    with FakeMonarch(scenario) as fake:
        arm = arm_against(site, fake, scenario.port, repo)
        arm.observer = lambda kind, **data: heard.append((kind, data))
        result = arm.run(Episode(task(), episode_id="run-x/simple.email_sf_contact_city_update/monarch/t0"),
                         deadline=time.monotonic() + 60)
    return heard, result, fake


def scenario(**overrides):
    port = free_port()
    sc = Scenario(shim_url=f"http://127.0.0.1:{port}", frames=[dict(f) for f in FRAMES],
                  engine_calls=[("PATCH", f"{SF}/Contact/003004", {"MailingCity": "Denver"})],
                  run_views=[dict(v) for v in VIEWS], **overrides)
    sc.port = port
    return sc


def test_observer_hears_builder_frames_the_recipe_and_every_node_change(site, repo):
    heard, result, fake = watched_attempt(site, repo, scenario())
    assert result.termination == "completed", result.error
    kinds = [k for k, _ in heard]
    assert kinds[:4] == ["authoring_started", "authoring_frame", "authoring_frame", "authoring_finished"]
    finished = dict(heard[3][1])
    assert finished["workflow_id"] == "wf-1" and finished["recipe"] == RECIPE and finished["questions"] == 0
    assert kinds[4] == "run_started" and heard[4][1]["recipe"] == RECIPE and heard[4][1]["run_id"] == "run-1"
    changes = [(d["step"]["stepId"], d["step"]["status"]) for k, d in heard if k == "run_step"]
    assert changes == [("read", "running"), ("write", "pending"), ("read", "succeeded"), ("write", "running"), ("write", "succeeded")]
    assert kinds[-1] == "run_finished" and heard[-1][1]["status"] == "completed"
    assert heard[-1][1]["view"]["steps"][-1]["message"] == "MailingCity set"
    assert fake.run_stream_connections == 1
    # The stream replaced polling: the log holds every distinct view, not a poll per tick.
    polls = [entry["poll"] for entry in result.turn_log if "poll" in entry]
    assert len(polls) == 4 and polls[-1]["status"] == "succeeded"


def test_without_the_engine_stream_the_same_node_changes_come_from_polling(site, repo):
    heard, result, fake = watched_attempt(site, repo, scenario(run_stream_404=True, delay_s={"run": 0.4}))
    assert result.termination == "completed", result.error
    assert any("run_stream_unavailable" in entry for entry in result.turn_log)
    changes = [(d["step"]["stepId"], d["step"]["status"]) for k, d in heard if k == "run_step"]
    assert changes[0] == ("read", "running") and changes[-1] == ("write", "succeeded")
    assert ("read", "succeeded") in changes and ("write", "running") in changes
    assert [k for k, _ in heard][-1] == "run_finished"


def test_a_failed_run_reports_the_failing_node_and_an_error_status(site, repo):
    failing = scenario(run_outcome={"status": "failed", "errorCode": "ACTION_FAILED", "errorNodeId": "write"})
    failing.run_views[-1] = {"steps": [step("read", "succeeded"), step("write", "failed", message="HTTP 500", errorCode="ACTION_FAILED")]}
    heard, result, fake = watched_attempt(site, repo, failing)
    assert result.termination == "agent_error" and result.error == "run_error:ACTION_FAILED node=write"
    last = heard[-1]
    assert last[0] == "run_finished" and last[1]["status"] == "error"
    assert [(d["step"]["stepId"], d["step"]["status"]) for k, d in heard if k == "run_step"][-1] == ("write", "failed")


def test_a_question_is_reported_with_the_fixed_reply(site, repo):
    asked = scenario()
    asked.frames = [{"status": "awaiting_input",
                     "awaiting_reply": {"requestId": "q1", "questions": [{"id": "a", "text": "Which contact?"}]}},
                    dict(FRAMES[1])]
    heard, result, fake = watched_attempt(site, repo, asked)
    assert result.termination == "completed", result.error
    replies = [d for k, d in heard if k == "authoring_reply"]
    assert len(replies) == 1 and replies[0]["questions"] == 1 and replies[0]["request_id"] == "q1"
    assert "No further information is available" in replies[0]["text"]
