"""A reading that failed can be asked again, and says why it failed.

Before this, `analysis.json` was read back whatever it held, so a stored failure
was permanent, and `analysis.claimed` was never cleared, so a second attempt was
refused. The recorded error was the exception class alone.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from wb_studio.analysis import STALE_CLAIM_SECONDS, review


class _Ledger:
    def __init__(self):
        self.reserved, self.finished = [], []

    def scope_committed(self, scope):
        from decimal import Decimal
        return Decimal("0")

    def reserve_run(self, scope, amount, metadata=None):
        self.reserved.append((scope, amount))

    def finish_run(self, scope):
        self.finished.append(scope)


class _Runtime:
    @contextmanager
    def provider(self, name, **kwargs):
        yield


class _Studio:
    """Enough Studio for the dispatch guard; the gateway always refuses."""

    def __init__(self, directory, refusal):
        self.directory, self.lock, self.ledger, self.runtime = directory, threading.Lock(), _Ledger(), _Runtime()
        self.refusal, self.calls = refusal, 0
        self.tasks = {"sales.contact": {"prompt": [{"content": "system"}, {"content": "Update the contact."}]}}
        (directory / "run-1").mkdir(parents=True, exist_ok=True)

    def gateway_factory(self, ledger, model=None):
        studio = self

        class _Gateway:
            thinking_level = "medium"

            def request(self, *args, **kwargs):
                studio.calls += 1
                raise RuntimeError(studio.refusal)
        return _Gateway()

    def job(self, identity):
        return {"id": identity, "status": "completed",
                "results": [{"task": "sales.contact", "model": "bare", "passed": False,
                             "termination": "completed", "checks": [{"type": "field_equals", "passed": False}]}],
                "settings": {"tasks": ["sales.contact"], "models": ["bare"], "maximum_usd": "1.00"}}

    def events(self, identity):
        return [{"id": 1, "type": "attempt_finished", "task": "sales.contact", "model": "bare"}]


@pytest.fixture
def studio(tmp_path):
    return _Studio(tmp_path, "GEMINI_API_KEY is not set")


def folder(studio):
    return studio.directory / "run-1"


def test_a_failed_reading_records_the_reason_not_only_the_exception_class(studio):
    stored = review(studio, "run-1")
    assert stored["status"] == "failed"
    assert "GEMINI_API_KEY is not set" in stored["error"] and stored["error"].startswith("RuntimeError:")
    assert stored["failed_at"]


def test_without_a_retry_the_stored_failure_is_returned_and_nothing_is_dispatched(studio):
    review(studio, "run-1")
    assert studio.calls == 1
    assert review(studio, "run-1")["status"] == "failed"
    assert studio.calls == 1, "a second read must not reach a provider"


def test_a_retry_dispatches_again_and_clears_the_claim(studio):
    review(studio, "run-1")
    assert (folder(studio) / "analysis.claimed").exists()
    review(studio, "run-1", retry=True)
    assert studio.calls == 2
    assert len(studio.ledger.reserved) == 2 and len(studio.ledger.finished) == 2


def test_a_retry_of_a_completed_reading_returns_it_untouched(studio):
    (folder(studio) / "analysis.json").write_text(json.dumps({"status": "completed", "summary": "done"}), encoding="utf-8")
    assert review(studio, "run-1", retry=True) == {"status": "completed", "summary": "done"}
    assert studio.calls == 0


def test_a_dispatch_still_in_flight_is_never_dispatched_twice(studio):
    (folder(studio) / "analysis.claimed").write_text("hash", encoding="utf-8")
    with pytest.raises(ValueError, match="has not returned yet"):
        review(studio, "run-1", retry=True)
    assert studio.calls == 0


def test_an_interrupted_dispatch_unblocks_once_the_request_could_not_still_be_open(studio):
    claim = folder(studio) / "analysis.claimed"
    claim.write_text("hash", encoding="utf-8")
    stale = time.time() - STALE_CLAIM_SECONDS - 60
    os.utime(claim, (stale, stale))
    assert review(studio, "run-1", retry=True)["status"] == "failed"
    assert studio.calls == 1


def test_the_run_page_reads_the_reason_the_automatic_reading_could_not_run(tmp_path):
    from wb_studio.report_data import narrative_status
    (tmp_path / "analysis.pending.json").write_text(
        json.dumps({"reason": "No analysis credential is configured (GEMINI_API_KEY).", "ceiling_usd": "0.50", "askable": False}),
        encoding="utf-8")
    status = narrative_status(tmp_path)
    assert status["status"] == "pending" and "GEMINI_API_KEY" in status["reason"] and status["askable"] is False


def test_a_reading_that_never_ran_can_still_be_asked_for(tmp_path):
    from wb_studio.report_data import narrative_status
    assert narrative_status(tmp_path)["askable"] is True


def test_turning_the_automatic_reading_off_does_not_take_the_button_away(tmp_path, monkeypatch):
    """STUDIO_ANALYSIS_USD is a choice about automatic spending. `review` pays from
    the run's own ceiling, so a person can still ask; only a wall hides the button."""
    from wb_studio.app import Studio
    from wb_studio.report_data import narrative_status
    monkeypatch.setenv("STUDIO_ANALYSIS_USD", "0")
    studio = Studio(tmp_path / "workspace", tasks={}, gateway_factory=None)
    assert studio.analysis_ceiling == 0
    identity = "run-off"
    folder = studio.directory / identity
    folder.mkdir(parents=True, exist_ok=True)
    studio.job = lambda i: {"id": i, "status": "completed", "results": [],
                            "settings": {"tasks": [], "models": ["claude-opus-5/api"], "maximum_usd": "5.00"}}
    studio.schedule_narrative(identity)
    status = narrative_status(folder)
    assert "STUDIO_ANALYSIS_USD is 0" in status["reason"] and status["askable"] is True


def test_scripted_only_and_a_missing_credential_are_walls(tmp_path, monkeypatch):
    from wb_studio.app import Studio
    from wb_studio.report_data import narrative_status
    monkeypatch.setenv("STUDIO_ANALYSIS_USD", "0.50")
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    studio = Studio(tmp_path / "workspace", tasks={}, gateway_factory=None)
    settings = {"tasks": [], "maximum_usd": "5.00"}

    studio.job = lambda i: {"id": i, "status": "completed", "results": [], "settings": {**settings, "models": ["oracle"]}}
    (studio.directory / "scripted").mkdir(parents=True, exist_ok=True)
    studio.schedule_narrative("scripted")
    assert narrative_status(studio.directory / "scripted")["askable"] is False

    studio.job = lambda i: {"id": i, "status": "completed", "results": [], "settings": {**settings, "models": ["claude-opus-5/api"]}}
    (studio.directory / "nokey").mkdir(parents=True, exist_ok=True)
    studio.schedule_narrative("nokey")
    assert narrative_status(studio.directory / "nokey")["askable"] is False
