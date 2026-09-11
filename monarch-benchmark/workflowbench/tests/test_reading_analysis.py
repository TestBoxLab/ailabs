"""Optional report interpretation stays concise and scoped to supplied evidence."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from tests.test_reasoning_review_retry import _Studio
from wb_studio.analysis import RUBRIC, review


def reading():
    return {
        "summary": "The requested contact update failed its recorded check.",
        "headline": "Contact update remains incomplete",
        "why": "The trace does not establish why the requested value was absent.",
        "opening_event_ids": [2],
        "findings": [{"title": "Missing result", "explanation": "The check failed.",
                      "kind": "fact", "event_ids": [2]}],
        "attempts": [{"task": "sales.contact", "model": "Setup 1",
                      "failure_mode": "wrong_result", "turning_point_event_id": 2,
                      "explanation": "The check failed; the cause remains a hypothesis.",
                      "diagnosis": "The requested contact value was absent.",
                      "responsibility": "undetermined", "event_ids": [1, 2]}],
        "next_actions": [{"text": "Inspect the selected contact.",
                          "acceptance": "Record the selected and requested contact IDs.", "event_ids": [1, 2]}],
        "next_experiment": "Repeat with explicit contact identity.",
        "limitations": "The trace does not establish causation.",
    }


def run_review(tmp_path, data, *, passed=False):
    studio = _Studio(tmp_path, "No provider calls allowed")
    job = studio.job("run-1")
    first = job["results"][0]
    first["passed"] = passed
    first["checks"][0]["passed"] = passed
    job["results"] = [first, dict(first), {**first, "model": "other"}]
    job["settings"]["models"] = ["bare", "other"]
    studio.job = lambda identity: job
    events = [{"id": i, "type": "attempt_finished" if i % 2 == 0 else "model_finished",
               "task": "sales.contact", "model": "bare" if i <= 4 else "other"}
              for i in range(1, 7)]
    studio.events = lambda identity: events
    requests = []

    def request(contents, rubric, tools, **kwargs):
        requests.append(json.loads(contents[0]["parts"][0]["text"]))
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    studio.gateway_factory = lambda *args, **kwargs: SimpleNamespace(request=request)
    return review(studio, "run-1"), requests[0]


def test_optional_reading_preserves_evidence_revision_and_retry_boundaries(tmp_path):
    result, payload = run_review(tmp_path, reading())
    assert result["status"] == "completed"
    assert result["schema_version"] == 2
    assert result["rubric_sha256"] == hashlib.sha256(RUBRIC.encode()).hexdigest()
    assert result["attempts"][0]["responsibility"] == "undetermined"
    assert [a["event_ids"] for a in payload["checked_outcomes"]["attempts"]] == [[1, 2], [3, 4], [5, 6]]
    assert [a["model"] for a in payload["checked_outcomes"]["attempts"]] == ["Setup 1", "Setup 1", "Setup 2"]


@pytest.mark.parametrize("field,value", [
    ("summary", "word " * 101), ("headline", 12), ("why", []),
    ("opening_event_ids", []), ("opening_event_ids", [999]),
    ("opening_event_ids", [True]), ("opening_event_ids", ["2"]),
    ("next_actions", [{"text": "Inspect", "acceptance": "Reproduced", "event_ids": [999]}]),
    ("next_actions", [{"text": "Inspect", "acceptance": 4, "event_ids": [2]}]),
])
def test_invalid_opening_and_next_action_are_rejected(tmp_path, field, value):
    result, _ = run_review(tmp_path, {**reading(), field: value})
    assert result["status"] == "failed"


@pytest.mark.parametrize("field,value", [
    ("task", "invented.task"), ("model", "Setup 9"), ("model", "Setup 2"),
    ("responsibility", "agent"), ("responsibility", []), ("diagnosis", 4),
    ("event_ids", []), ("event_ids", [True]), ("event_ids", ["2"]),
    ("event_ids", [1, 4]), ("event_ids", [1, 6]),
    ("turning_point_event_id", 6),
])
def test_attempt_cannot_invent_ownership_or_borrow_another_attempts_evidence(tmp_path, field, value):
    data = reading()
    data["attempts"][0][field] = value
    result, _ = run_review(tmp_path, data)
    assert result["status"] == "failed"


def test_legacy_response_remains_supported_without_invented_responsibility(tmp_path):
    data = reading()
    for field in ("headline", "why", "opening_event_ids", "next_actions"):
        data.pop(field)
    for field in ("diagnosis", "responsibility", "event_ids"):
        data["attempts"][0].pop(field)
    result, _ = run_review(tmp_path, data)
    assert result["status"] == "completed"
    assert "responsibility" not in result["attempts"][0]


def test_analysis_keeps_checked_business_requirements_in_its_input(tmp_path):
    _, payload = run_review(tmp_path, reading())
    assert payload["checked_outcomes"]["attempts"][0]["requirements"][0]["passed"] is False


def test_analysis_cannot_relabel_a_failed_attempt_as_passed(tmp_path):
    data = reading()
    data["attempts"][0]["failure_mode"] = "passed"
    result, _ = run_review(tmp_path, data)
    assert result["status"] == "failed"


def test_rubric_asks_for_supported_hypotheses_without_automatic_task_blame():
    assert "first suspect" not in RUBRIC
    assert "at most 100 words" in RUBRIC
    assert "shared" in RUBRIC and "undetermined" in RUBRIC
    assert "cannot override" in RUBRIC


def test_rubric_requires_citations_for_successful_attempts_too():
    assert "Every attempt, including passed attempts, requires nonempty event_ids" in RUBRIC
    assert "turning_point_event_id: integer or null, explanation, event_ids: [integers]" in RUBRIC


@pytest.mark.parametrize("cited", [True, False])
def test_repeated_successes_need_their_own_evidence_even_without_a_turning_point(tmp_path, cited):
    data = {"summary": "Both repetitions passed.", "findings": [],
            "next_experiment": "Check independent repetitions.", "limitations": "Small sample.",
            "attempts": [{"task": "sales.contact", "model": "Setup 1", "failure_mode": "passed",
                          "turning_point_event_id": None, "explanation": "The recorded checks passed.",
                          **({"event_ids": ids} if cited else {})} for ids in ([1, 2], [3, 4])]}
    result, _ = run_review(tmp_path, data, passed=True)
    assert result["status"] == ("completed" if cited else "failed")


def test_legacy_unique_success_without_turning_point_or_new_citations_remains_supported(tmp_path):
    data = {"summary": "The recorded attempt passed.", "findings": [], "next_experiment": "Repeat.",
            "limitations": "Small sample.", "attempts": [{"task": "sales.contact", "model": "Setup 2",
            "failure_mode": "passed", "turning_point_event_id": None, "explanation": "The checks passed."}]}
    result, _ = run_review(tmp_path, data, passed=True)
    assert result["status"] == "completed"
