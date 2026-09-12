"""Daily jobs for the owning Studio process: one thread, the São Paulo clock, and a
stamp file so a job runs once a day even across restarts.

A module offers a job by defining `DAILY = (name, hour, function)`; the function
takes the Studio and returns a JSON-able summary. Errors are recorded, never
raised into the server. Nothing here spends money by itself: a job that wants to
must reserve in the weekly ledger like any other paid request.
"""
from __future__ import annotations

import importlib
import json
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from wb_results.evidence import write_json
from wb_studio.library import now_sao_paulo

MODULES = ("wb_studio.code_index", "wb_studio.genesis_sleep", "wb_studio.genesis_initiative",
           "wb_studio.genesis_engineer", "wb_studio.genesis_critic",
           "wb_studio.genesis_ranking", "wb_studio.genesis_memory_suite", "wb_studio.genesis_channels")  # feature 022 lanes; missing ones are skipped
# genesis_initiative comes after genesis_sleep: due jobs run in this order, so the morning reads a
# record the night has already consolidated. genesis_engineer follows both, and the code index at
# 04:00 before them, so a spec is written against an index built the same morning.


class Scheduler:
    def __init__(self, studio, stamps: Path):
        self.studio, self.stamps, self.jobs, self.lock = studio, Path(stamps), [], threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def daily(self, name: str, hour, fn) -> None:
        """`hour` is 0 to 23, or a callable of the Studio that returns it when the job is checked."""
        if not callable(hour) and not 0 <= int(hour) <= 23:
            raise ValueError("hour is 0 to 23")
        self.jobs.append({"name": name, "hour": hour if callable(hour) else int(hour), "fn": fn})

    def _hour(self, job) -> int:
        hour = job["hour"]
        if callable(hour):
            try:
                return int(hour(self.studio))
            except Exception:
                return 23  # a setting that cannot be read runs the job late, never never
        return int(hour)

    def discover(self) -> None:
        """Register every module that offers a DAILY job; a missing module is not an error."""
        for name in MODULES:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            offer = getattr(module, "DAILY", None)
            if not offer:
                continue
            for job in (offer if isinstance(offer[0], (tuple, list)) else [offer]):
                if not any(j["name"] == job[0] for j in self.jobs):
                    self.daily(*job)

    def _read(self) -> dict:
        try:
            return json.loads(self.stamps.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def due(self, now: datetime | None = None) -> list:
        now = now or now_sao_paulo()
        stamps = self._read()
        today = now.date().isoformat()
        return [j for j in self.jobs if now.hour >= self._hour(j) and (stamps.get(j["name"]) or {}).get("day") != today]

    def run(self, name: str, now: datetime | None = None) -> dict:
        """Run one job now, whatever the clock says, and stamp it."""
        now = now or now_sao_paulo()
        job = next((j for j in self.jobs if j["name"] == name), None)
        if job is None:
            raise ValueError(f"Unknown job {name!r}")
        entry = {"day": now.date().isoformat(), "started_at": now.isoformat(timespec="seconds")}
        try:
            entry["summary"] = job["fn"](self.studio)
            entry["status"] = "completed"
        except Exception as exc:  # a job must never take the server down
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["trace"] = traceback.format_exc()[-2000:]
        entry["finished_at"] = now_sao_paulo().isoformat(timespec="seconds")
        with self.lock:
            stamps = self._read()
            previous = stamps.get(name) or {}
            if entry["status"] == "failed" and previous.get("status") == "failed" and previous.get("error") == entry["error"]:
                entry["repeats"] = int(previous.get("repeats") or 0) + 1  # the same failure again: an incident, not news
            stamps[name] = entry
            write_json(self.stamps, stamps)
        if entry.get("repeats"):
            recorder = getattr(getattr(getattr(self.studio, "genesis", None), "autonomy", None), "record", None)
            if callable(recorder):
                recorder("job-incident", job=name, repeats=entry["repeats"], error=entry["error"][:200])
        return entry

    def stopped(self) -> str | None:
        """Why unattended work must not run now, or None.

        Settings that cannot be read stop the jobs. This used to fall through to
        running them: the dials are a spending gate, and a gate that fails open
        because it crashed is worse than no gate, because it reads as one.
        """
        autonomy = getattr(getattr(self.studio, "genesis", None), "autonomy", None)
        if autonomy is None:
            return None   # a Studio without Genesis has nothing to pause
        try:
            from wb_studio.genesis_autonomy import background_wanted
            if autonomy.read()["paused"]:
                return "Genesis is paused; a person has to turn it back on."
            if not background_wanted(autonomy):
                return "The research loop is stopped; an exhausted envelope or all dials off."
        except Exception as exc:
            return (f"Genesis's settings could not be read ({type(exc).__name__}); "
                    "nothing paid runs unattended until they can.")
        return None

    def run_due(self, now: datetime | None = None) -> list:
        """Every due job, unless a person has hit Pause or the dials are off.

        FR-003: six daily jobs reach paid model turns, and none of them read the dial.
        Gating them here rather than in each module means a job added later is paused
        too, without its author having to remember. A skipped job is not stamped, so it
        runs when the pause is lifted rather than being silently lost for the day.
        """
        reason = self.stopped()
        if reason is None:
            return [self.run(j["name"], now) for j in self.due(now)]
        recorder = getattr(getattr(getattr(self.studio, "genesis", None), "autonomy", None), "record", None)
        skipped = []
        for job in self.due(now):
            if callable(recorder):
                recorder("job-skipped", job=job["name"], reason=reason)
            skipped.append({"name": job["name"], "status": "skipped", "reason": reason})
        return skipped

    def status(self) -> list:
        stamps = self._read()
        return [{"name": j["name"], "hour": self._hour(j), **{k: v for k, v in (stamps.get(j["name"]) or {}).items() if k != "trace"}} for j in self.jobs]

    def start(self, interval_s: float = 300) -> None:
        """One daemon thread that checks the clock; only the owning web process calls this."""
        if self._thread:
            return

        def loop():
            while not self._stop.wait(interval_s):
                try:
                    self.run_due()
                except Exception as exc:
                    # The thread must survive; the cause must not vanish.
                    print(f"studio scheduler: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        self._thread = threading.Thread(target=loop, daemon=True, name="studio-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
