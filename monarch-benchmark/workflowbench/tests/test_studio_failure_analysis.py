"""Evidence-only outcome buckets: no provider, store writes, or inferred causes."""
from copy import deepcopy
from unittest.mock import Mock, call

import pytest

from wb_studio.failure_analysis import analysis


def result(model="bare", *, passed=False, termination="completed", checks=None, **extra):
    return {"task": "sales.contact", "model": model, "passed": passed, "termination": termination,
            "checks": checks if checks is not None else [{"type": "field_equals", "passed": passed}], **extra}


def studio_for(results, events=(), planned=1):
    models = list(dict.fromkeys(r["model"] for r in results))
    models += ["unrecorded-" + str(i) for i in range(max(0, planned - len(models)))]
    job = {"id": "run-1", "results": results, "settings": {"tasks": ["sales.contact"],
           "models": models}}
    studio = Mock(spec=["job", "events", "tasks"])
    studio.job.return_value = job
    studio.events.return_value = list(events)
    studio.tasks = {"sales.contact": {"info": {"assertions": [{"field": "Phone", "value": "123"}]}}}
    return studio


def event(identity, kind, model="bare", **values):
    return {"id": identity, "type": kind, "task": "sales.contact", "model": model, **values}


def test_requirements_and_scope_keep_exact_checks_changes_and_event_citations():
    studio = studio_for([result(checks=[{"type": "field_equals", "passed": False},
                                       {"type": "allowed_changes_only", "passed": False}],
                                unexpected_changes=[{"service": "gmail", "path": "messages[0].label_ids",
                                                     "before": ["INBOX"], "after": ["TRASH"]}])],
                        [event(1, "node_finished", status="error"), event(2, "attempt_finished")])
    attempt = analysis(studio, "run-1")["attempts"][0]
    assert attempt["bucket"] == "unintended_changes"
    assert "INBOX" in attempt["narrative"] and "TRASH" in attempt["narrative"]
    assert "Unmet: Phone should be 123" in attempt["narrative"]
    assert attempt["checks"] == [
        {"name": "field_equals", "title": "Phone should be 123", "passed": False, "check_index": 0},
        {"name": "allowed_changes_only", "title": "allowed_changes_only", "passed": False, "check_index": 1}]
    assert attempt["observed_facts"][1] == {"text": "Failed: Phone should be 123", "event_ids": [2],
        "check_names": ["field_equals"], "check_index": 0, "source": "result.checks"}
    assert attempt["earliest_supported_evidence"]["event_id"] == 1
    assert "unverified" in attempt["earliest_supported_evidence"]["text"]
    assert attempt["causal_hypotheses"] == []


@pytest.mark.parametrize("termination,bucket,infrastructure", [
    ("infra:harness_crash", "infrastructure", True),
    ("infra:rate_limit", "infrastructure", True),
    ("infra:weekly_budget", "budget_limit", True),
    ("infra:attempt_cap", "budget_limit", True),
    ("timeout", "timeout", False),
    ("infra:timeout", "timeout", True),
    ("completed", "requirement_unmet", False),
])
def test_explicit_termination_precedes_checks_without_relabeling_infrastructure(termination, bucket, infrastructure):
    report = analysis(studio_for([result(termination=termination)]), "run-1")
    attempt = report["attempts"][0]
    assert (attempt["bucket"], attempt["infrastructure"]) == (bucket, infrastructure)
    assert report["summary"]["infrastructure_attempts"] == int(infrastructure)
    assert [b["count"] for b in report["buckets"] if b["id"] == bucket] == [1]
    assert attempt["earliest_supported_evidence"] is None


def test_unclassified_failure_does_not_infer_budget_timeout_or_missing_actions_from_prose():
    studio = studio_for([result(termination="agent_error", checks=[],
                                error="Perhaps a timeout or budget issue; no tool actions visible")])
    attempt = analysis(studio, "run-1")["attempts"][0]
    assert attempt["bucket"] == "unclassified"
    assert attempt["event_ids"] == []
    assert attempt["earliest_supported_evidence"] is None
    assert attempt["causal_hypotheses"] == []
    assert "do not prove missing actions" in attempt["limitations"]


def test_success_is_preserved_despite_recovered_error_and_failure_buckets_exclude_it():
    report = analysis(studio_for([result(passed=True)], [event(1, "node_finished", status="error"),
                                                     event(2, "attempt_finished")]), "run-1")
    assert report["attempts"][0]["bucket"] == "success"
    assert report["attempts"][0]["narrative"] == "Satisfied: Phone should be 123."
    assert report["attempts"][0]["earliest_supported_evidence"]["event_id"] == 1
    assert report["summary"]["successful_attempts"] == 1
    assert report["summary"]["failed_attempts"] == 0
    assert all(b["count"] == 0 and b["percent_failed"] is None and b["percent_all"] == 0 for b in report["buckets"])


def test_denominators_include_failed_infrastructure_and_successes_without_counting_unrecorded():
    report = analysis(studio_for([
        result("one"), result("two", termination="infra:harness_crash"),
        result("three", checks=[]), result("four", passed=True)], planned=6), "run-1")
    assert report["summary"] == {"recorded_attempts": 4, "successful_attempts": 1, "failed_attempts": 3,
                                "infrastructure_attempts": 1, "planned_attempts": 6, "unrecorded_attempts": 2}
    assert sum(b["count"] for b in report["buckets"]) == 3
    assert sum(b["percent_failed"] for b in report["buckets"]) == 100
    assert sorted(b["percent_failed"] for b in report["buckets"] if b["count"]) == [33.33, 33.33, 33.34]
    assert sum(b["percent_all"] for b in report["buckets"]) == 75
    assert "including infrastructure" in report["denominators"]["percent_failed"]


def test_empty_running_run_has_unavailable_percentages_and_no_invented_failure():
    report = analysis(studio_for([], planned=3), "run-1")
    assert report["summary"]["recorded_attempts"] == report["summary"]["failed_attempts"] == 0
    assert report["summary"]["unrecorded_attempts"] == 3
    assert report["attempts"] == []
    assert all(b["percent_all"] is None and b["percent_failed"] is None for b in report["buckets"])


def test_repeated_and_interleaved_attempts_keep_their_own_events_and_stable_result_ids():
    studio = studio_for([result("one"), result("two"), result("one", passed=True)], [
        event(1, "attempt_started", "one"), event(2, "attempt_started", "two"),
        event(3, "node_finished", "one", status="error"), event(4, "attempt_finished", "one"),
        event(5, "attempt_finished", "two"), event(6, "attempt_started", "one"),
        event(7, "attempt_finished", "one"), event(8, "attempt_started", "one"),
        event(9, "node_finished", "one", status="error")], planned=3)
    report = analysis(studio, "run-1")
    attempts = report["attempts"]
    assert report["summary"]["unrecorded_attempts"] == 1  # A repeat cannot fill another planned model slot.
    assert [a["id"] for a in attempts] == ["attempt-1", "attempt-2", "attempt-3"]
    assert [a["event_ids"] for a in attempts] == [[1, 3, 4], [2, 5], [6, 7]]
    assert attempts[1]["earliest_supported_evidence"] == {"event_id": 5, "type": "attempt_finished", "text": "Recorded failure verdict."}
    assert attempts[2]["earliest_supported_evidence"] is None


def test_read_only_analysis_does_not_mutate_records_or_access_provider_or_store():
    studio = studio_for([result()], [event(4, "attempt_finished")])
    before = deepcopy((studio.job.return_value, studio.events.return_value, studio.tasks))
    first = analysis(studio, "run-1")
    assert analysis(studio, "run-1") == first
    assert (studio.job.return_value, studio.events.return_value, studio.tasks) == before
    assert studio.mock_calls == [call.job("run-1"), call.events("run-1")] * 2


def test_overall_failure_with_all_visible_checks_passed_is_unclassified():
    attempt = analysis(studio_for([result(checks=[{"type": "field_equals", "passed": True},
                                                 {"type": "allowed_changes_only", "passed": True}])]), "run-1")["attempts"][0]
    assert attempt["bucket"] == "unclassified"
    assert attempt["checks"][0]["passed"] is True
    assert "retained checks and termination do not support" in attempt["narrative"]
