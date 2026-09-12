"""Run page (feature 015): counts for the Runs table, check labels that name
their record, and change summaries without the snapshot placeholder."""
import json
import re

import pytest

from tests.test_studio_app import request, server_for
from wb_studio.app import ROOT, Studio
from wb_studio.measures import run_counts
from wb_studio.reports import change_summary, outcome_report, requirement, requirement_facts
from wb_world.episode import load_suite

STATIC = ROOT / "wb_studio" / "static"


def result(model, **extra):
    return {"task": "t1", "model": model, "passed": True, "termination": "completed", "checks": [], "unexpected_changes": [], **extra}


def test_run_counts_turns_unknown_when_no_model_turns_recorded():
    job = {"results": [result("a"), result("b", passed=False, unexpected_changes=[{"path": "x", "before": 1, "after": 2}])]}
    counts = run_counts(job, [])
    assert counts == {"turns": None, "violations": 1, "attempts": 2}


def test_run_counts_turns_are_the_mean_over_evaluated_attempts():
    job = {"results": [result("a"), result("b"), result("c", termination="infra:timeout")]}
    events = [{"id": 1, "type": "model_finished", "task": "t1", "model": "a"},
              {"id": 2, "type": "model_finished", "task": "t1", "model": "a"},
              {"id": 3, "type": "model_finished", "task": "t1", "model": "c"}]
    assert run_counts(job, events) == {"turns": 1.0, "violations": 0, "attempts": 2}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected provider use")
    return Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1], gateway_factory=forbidden)


def test_jobs_counts_route_serves_turns_and_violations_per_run(studio):
    job = studio.create({"request_id": "counts", "title": "Counts", "models": ["oracle", "sloppy"],
                         "tasks": list(studio.tasks), "maximum_usd": "1.00"}, start=False)
    studio.execute(job["id"])
    with server_for(studio) as port:
        status, _, body = request(port, "GET", "/api/jobs/counts")
    assert status == 200
    assert json.loads(body)["items"][job["id"]] == {"turns": None, "violations": 1, "attempts": 2}


def test_requirement_label_names_the_recipient_and_the_content():
    assert requirement({"type": "gmail_message_sent_to", "to": "controller@company.example.com"}, 0) == "Gmail message sent to controller@company.example.com"
    label = requirement({"type": "gmail_message_sent_to_with_body_contains", "to": "alice@company.example.com", "body_contains": ["Approved", "350"]}, 0)
    assert label == "Gmail message sent to alice@company.example.com with body containing Approved, 350"
    assert requirement({"type": "slack_message_exists", "channel_name": "benefits", "text_contains": "Alex Rivera"}, 0) == "Slack message exists; channel name benefits; text contains Alex Rivera"
    assert requirement({"type": "salesforce_field_equals", "collection": "contacts", "record_id": "003001", "field": "phone", "value": "+1-555-0101"}, 0) == "Phone should be +1-555-0101"


def test_requirement_facts_name_record_field_and_expected_value():
    facts = requirement_facts({"type": "salesforce_field_equals", "collection": "contacts", "record_id": "003001", "field": "phone", "value": "+1-555-0101"})
    assert facts == {"record": "contacts 003001", "field": "phone", "expected": "+1-555-0101"}
    facts = requirement_facts({"type": "gmail_message_sent_to_with_body_contains", "to": "alice@x.example", "body_contains": ["Approved", "350"]})
    assert facts == {"record": "to alice@x.example", "field": None, "expected": "body contains Approved, 350"}
    assert requirement_facts({"type": "freshdesk_ticket_not_exists", "subject_contains": "Return label"}) == {"record": None, "field": None, "expected": "subject contains Return label"}


def test_outcome_report_requirements_carry_their_facts(studio):
    job = studio.create({"request_id": "facts", "title": "Facts", "models": ["oracle"], "tasks": list(studio.tasks), "maximum_usd": "1.00"}, start=False)
    studio.execute(job["id"])
    report = outcome_report(studio.job(job["id"]), studio.events(job["id"]), studio.tasks)
    check = report["attempts"][0]["requirements"][0]
    assert check["record"] == "contact 003004" and check["field"] == "mailing city" and check["expected"] == "Denver"
    assert check["passed"] is True


def test_change_summary_names_the_record_instead_of_the_placeholder():
    added = change_summary({"service": "gmail", "op": "added", "path": "gmail.messages[id=msg_9]", "before": None, "after": "<object>"})
    assert added == "Gmail message msg_9 added."
    removed = change_summary({"service": "salesforce", "op": "removed", "path": "salesforce.contacts[id=003001]", "before": "<object>", "after": None})
    assert removed == "Salesforce contact 003001 removed."
    changed = change_summary({"service": "gmail", "op": "changed", "path": "gmail.messages[id=msg_9].payload", "before": "<object>", "after": "<object>"})
    assert changed == "Gmail message msg_9 payload changed."
    scalar = change_summary({"service": "gmail", "op": "changed", "path": "gmail.messages[id=msg_3004].label_ids[0]", "before": "INBOX", "after": "TRASH"})
    assert scalar == "Gmail message msg_3004 labels changed from INBOX to TRASH."
    for text in (added, removed, changed, scalar):
        assert "<object>" not in text


def test_index_has_evidence_tabs_and_runs_table_counts():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    tabs = re.search(r'<div class="inspector-tabs"[^>]*role="tablist"[^>]*>(.*?)</div>', html).group(1)
    names = re.findall(r'<button[^>]*role="tab"[^>]*>([^<]+)</button>', tabs)
    assert names == ["What happened", "Output", "Checks", "Trace", "Timeline"]
    header = re.search(r'<thead><tr><th scope="col">Run</th>(.*?)</tr></thead>', html).group(1)
    assert "Turns" in header and "Violations" in header
    # The column counts tool calls; it was headed "Actions", which named nothing a reader could find.
    assert 'data-results-sort="tools">Tool calls</button>' in html and '>Actions<' not in html
    # The model is its own column, so an attempt can be filtered and sorted by it.
    assert 'data-results-sort="model">Model</button>' in html and 'id="results-model"' in html


def test_static_scripts_name_events_by_what_they_show():
    workspace = (STATIC / "workspace.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "'Event '+id" not in workspace and "Evidence #" not in app
    assert "function eventLabel" in app
    assert "No runs yet" in workspace and "empty-state" in workspace
