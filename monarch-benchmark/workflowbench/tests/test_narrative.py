"""The story of an attempt: timeline, what went right and wrong, the turning
point and one failure mode, all from the record; and what a run's failures
have in common."""
from unittest.mock import Mock

from wb_studio.failure_analysis import analysis
from wb_studio.narrative import MODES, run_story, service_of, story
from wb_studio.reports import outcome_report

TASK = "sales.contact"
ASSERTIONS = [{"type": "salesforce_field_equals", "field": "Phone", "value": "123", "record_id": "003"},
              {"type": "gmail_message_not_sent_to", "to": "dave@company.example.com"}]


def ev(i, kind, model="bare", **v):
    return {"id": i, "type": kind, "task": TASK, "model": model, **v}


def fetch(i, method, url, body=None, model="bare", error=None):
    node = f"tool-{i}"
    yield ev(i, "node_started", model, node=node, label="api_fetch", arguments={"method": method, "url": url, "body": body})
    yield ev(i + 1, "node_finished", model, node=node, status="error" if error else "completed", output=error or "{}")


def trace_for(model, *, writes=True, claim=False, error=False):
    events = [ev(1, "attempt_started", model),
              ev(2, "model_finished", model, output="", reasoning=["Find Lisa's contact, then change the phone."], stop_reason="tool_use"),
              *fetch(3, "GET", "https://x.salesforce.com/contacts", model=model)]
    nxt = 5
    if writes:
        events += [ev(nxt, "model_finished", model, output="", reasoning=["Contact 003 is the one."], stop_reason="tool_use"),
                   *fetch(nxt + 1, "PATCH", "https://x.salesforce.com/contacts/003", body='{"Phone": "999"}', model=model,
                          error="404 not found" if error else None)]
        nxt += 3
    events += [ev(nxt, "model_finished", model, output="All done, the phone is updated." if claim else "I could not find the contact.", stop_reason="end_turn"),
               ev(nxt + 1, "attempt_finished", model)]
    return events


def result_for(model, *, passed=False, phone_ok=False, negative_ok=True, changes=(), termination="completed", error=None):
    return {"task": TASK, "model": model, "passed": passed, "termination": termination, "error": error,
            "checks": [{"type": "salesforce_field_equals", "passed": phone_ok}, {"type": "gmail_message_not_sent_to", "passed": negative_ok},
                       {"type": "allowed_changes_only", "passed": not changes}],
            "unexpected_changes": list(changes)}


def account(results, events):
    job = {"id": "run-1", "results": results, "settings": {"tasks": [TASK], "models": list(dict.fromkeys(r["model"] for r in results))}}
    return outcome_report(job, events, {TASK: {"info": {"assertions": ASSERTIONS}, "prompt": [{"content": "sys"}, {"content": "brief"}]}})


def test_service_of_reads_the_check_type():
    assert service_of({"type": "google_sheets_row_exists"}) == "sheets"
    assert service_of({"type": "gmail_message_sent_to"}) == "gmail"
    assert service_of({}) == ""


def test_wrong_result_names_the_write_that_reached_the_right_place():
    s = account([result_for("bare")], trace_for("bare", claim=True))["attempts"][0]["story"]
    assert s["mode"] == "wrong_result" and s["mode_label"] == MODES["wrong_result"]
    assert s["verdict"].startswith("Failed: 1 of 2 requirements met")
    assert [t["turn"] for t in s["timeline"]] == [1, 2, 3]
    assert s["timeline"][0]["reasoning"] == "Find Lisa's contact, then change the phone."
    assert s["timeline"][1]["actions"][0]["method"] == "PATCH" and s["timeline"][1]["sentence"].startswith("Turn 2 · thought: Contact 003")
    assert s["turning_point"]["event_id"] == 6 and "wrong content" in s["turning_point"]["text"]
    assert any(f["text"].startswith("Not met: Phone should be 123. The closest write") and f["event_ids"] == [6] for f in s["went_wrong"])
    assert s["claimed_done"] and any("reported the work as done" in f["text"] for f in s["went_wrong"])
    assert any(f["text"] == "Read each application before changing it." for f in s["went_right"])
    assert any(f["text"].startswith("Every tool call succeeded (2 in 3 turns)") for f in s["went_right"])


def test_stopped_short_when_nothing_was_written():
    s = account([result_for("bare")], trace_for("bare", writes=False))["attempts"][0]["story"]
    assert s["mode"] == "stopped_short" and not s["claimed_done"]
    assert s["turning_point"]["text"].startswith("The final reply, made without the required change")
    assert any("No write to Salesforce was recorded" in f["text"] for f in s["went_wrong"])


def test_tool_error_never_recovered_from_is_the_turning_point():
    s = account([result_for("bare")], trace_for("bare", error=True))["attempts"][0]["story"]
    assert s["mode"] == "tool_error" and s["turning_point"]["event_id"] == 6
    assert any(f["text"].startswith("1 tool call failed; the first: update in salesforce — 404 not found") for f in s["went_wrong"])


def test_forbidden_and_scope_come_before_unmet_requirements():
    forbidden = account([result_for("bare", negative_ok=False)], trace_for("bare"))["attempts"][0]["story"]
    assert forbidden["mode"] == "forbidden_action"
    scope = account([result_for("bare", phone_ok=True, changes=[{"service": "salesforce", "path": "contacts[id=004].phone", "op": "changed", "before": "1", "after": "2"}])],
                    trace_for("bare"))["attempts"][0]["story"]
    assert scope["mode"] == "scope_violation" and scope["turning_point"] == {"event_id": 6, "text": "The first write outside the request."}
    assert any("Writes that could have made it: PATCH https://x.salesforce.com/contacts/003" in f["text"] for f in scope["went_wrong"])


def test_passed_ran_out_and_infrastructure():
    passed = account([result_for("bare", passed=True, phone_ok=True)], trace_for("bare"))["attempts"][0]["story"]
    assert passed["mode"] == "passed" and passed["verdict"] == "Passed: 2 of 2 requirements met and nothing else changed, in 2 tool calls."
    assert passed["went_right"][0] == {"text": "Met: Phone should be 123, by update in salesforce.", "event_ids": [6]}
    ran = account([result_for("bare", termination="timeout")], trace_for("bare"))["attempts"][0]["story"]
    assert ran["mode"] == "ran_out" and ran["turning_point"]["text"] == "The last turn before the limit."
    infra = account([result_for("bare", termination="infra:harness_crash")], trace_for("bare"))["attempts"][0]["story"]
    assert infra["mode"] == "infrastructure" and infra["verdict"].startswith("Not measured")


def test_run_story_names_modes_per_setup_and_suspect_tasks():
    results = [result_for("bare"), result_for("monarch")]
    events = trace_for("bare", claim=True) + [{**e, "id": e["id"] + 100} for e in trace_for("monarch", claim=True)]
    attempts = account(results, events)["attempts"]
    s = run_story(attempts, {"bare": "Bare", "monarch": "Monarch"})
    assert s["setups"][0]["modes"][0] == {"mode": "wrong_result", "label": MODES["wrong_result"], "count": 1, "tasks": [TASK]}
    assert s["suspect_tasks"] == [{"task": TASK, "mode_label": MODES["wrong_result"], "setups": ["Bare", "Monarch"]}]
    assert s["paragraphs"][0] == "Bare failed 1 of 1 attempts: 1 time it changed the right place, but not as required."
    assert s["paragraphs"][-1].startswith("1 task failed for every setup in the same way (sales.contact): suspect the task")
    split = run_story(account([result_for("bare"), result_for("monarch", passed=True, phone_ok=True)], events)["attempts"])
    assert split["separating_tasks"] == [{"task": TASK, "passed": ["monarch"], "failed": ["bare"]}]
    assert split["suspect_tasks"] == []


def test_failure_analysis_carries_the_story():
    studio = Mock(spec=["job", "events", "tasks"])
    studio.job.return_value = {"id": "run-1", "results": [result_for("bare")], "settings": {"tasks": [TASK], "models": ["bare"]}}
    studio.events.return_value = trace_for("bare")
    studio.tasks = {TASK: {"info": {"assertions": ASSERTIONS}}}
    fa = analysis(studio, "run-1")
    assert fa["attempts"][0]["story"]["mode"] == "wrong_result"
    assert fa["story"]["setups"][0]["failed"] == 1


def test_application_error_bodies_count_as_tool_errors():
    """The simulator answers a bad call with {"error": {...}} and status completed;
    the story must still see it as a failed call, not a success."""
    events = [ev(1, "attempt_started"), ev(2, "model_finished", output="", reasoning=[], stop_reason="tool_use"),
              ev(3, "node_started", node="tool-0", label="api_fetch", arguments={"method": "GET", "url": "https://x.salesforce.com/nope"}),
              ev(4, "node_finished", node="tool-0", status="completed", output='{"error": {"code": 404, "message": "Unknown API URL"}}'),
              ev(5, "model_finished", output="I could not find it.", stop_reason="end_turn"), ev(6, "attempt_finished")]
    attempt = account([result_for("bare")], events)["attempts"][0]
    assert attempt["actions"][0]["status"] == "error" and attempt["actions"][0]["error"] == "404 Unknown API URL"
    s = attempt["story"]
    assert s["mode"] == "tool_error" and s["turning_point"]["event_id"] == 3
    assert not any(f["text"].startswith("Every tool call succeeded") for f in s["went_right"])
    assert any("404 Unknown API URL" in f["text"] for f in s["went_wrong"])
