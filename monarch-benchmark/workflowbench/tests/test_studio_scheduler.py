"""Daily jobs run once a day after their hour, survive restarts through the stamp
file, and never raise into the server."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from wb_studio.scheduler import Scheduler

SP = timezone(timedelta(hours=-3))


def at(day, hour):
    return datetime(2026, 9, day, hour, 5, tzinfo=SP)


@pytest.fixture
def scheduler(tmp_path):
    return Scheduler(SimpleNamespace(directory=tmp_path), tmp_path / "schedule.json")


def test_a_job_runs_once_a_day_after_its_hour_and_again_the_next_day(scheduler):
    runs = []
    scheduler.daily("index", 4, lambda studio: runs.append(1) or {"ok": True})
    assert scheduler.due(at(9, 3)) == []
    assert [e["status"] for e in scheduler.run_due(at(9, 4))] == ["completed"]
    assert scheduler.run_due(at(9, 23)) == []            # same day: done
    assert len(scheduler.run_due(at(10, 4))) == 1        # next day: again
    assert runs == [1, 1]
    assert scheduler.status()[0]["day"] == "2026-09-10" and scheduler.status()[0]["summary"] == {"ok": True}


def test_the_stamp_file_survives_a_restart(tmp_path):
    first = Scheduler(SimpleNamespace(), tmp_path / "schedule.json")
    first.daily("index", 4, lambda studio: {})
    first.run_due(at(9, 5))
    second = Scheduler(SimpleNamespace(), tmp_path / "schedule.json")
    second.daily("index", 4, lambda studio: {})
    assert second.due(at(9, 6)) == []


def test_a_failing_job_is_recorded_not_raised(scheduler):
    def boom(studio):
        raise RuntimeError("git is not installed")
    scheduler.daily("index", 4, boom)
    entry = scheduler.run("index", at(9, 5))
    assert entry["status"] == "failed" and entry["error"] == "RuntimeError: git is not installed"
    assert "trace" not in scheduler.status()[0]


def test_run_now_ignores_the_clock_and_unknown_jobs_are_refused(scheduler):
    scheduler.daily("index", 23, lambda studio: {"n": 1})
    assert scheduler.run("index", at(9, 1))["status"] == "completed"
    with pytest.raises(ValueError):
        scheduler.run("nope")


def test_discover_registers_modules_that_offer_a_daily_job(scheduler, monkeypatch):
    import types, sys
    module = types.ModuleType("wb_studio.fake_daily")
    module.DAILY = ("fake", 2, lambda studio: {"ran": True})
    monkeypatch.setitem(sys.modules, "wb_studio.fake_daily", module)
    monkeypatch.setattr("wb_studio.scheduler.MODULES", ("wb_studio.fake_daily", "wb_studio.not_there"))
    scheduler.discover()
    scheduler.discover()
    assert [j["name"] for j in scheduler.jobs] == ["fake"]
