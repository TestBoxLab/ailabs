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
import threading
import traceback
from datetime import datetime
from pathlib import Path

from wb_results.evidence import write_json
from wb_studio.library import now_sao_paulo

MODULES = ("wb_studio.code_index", "wb_studio.genesis_sleep",
           "wb_studio.genesis_ranking", "wb_studio.genesis_memory_suite", "wb_studio.genesis_channels")  # feature 022 lanes; missing ones are skipped


class Scheduler:
    def __init__(self, studio, stamps: Path):
        self.studio, self.stamps, self.jobs, self.lock = studio, Path(stamps), [], threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def daily(self, name: str, hour: int, fn) -> None:
        if not 0 <= int(hour) <= 23:
            raise ValueError("hour is 0 to 23")
        self.jobs.append({"name": name, "hour": int(hour), "fn": fn})

    def discover(self) -> None:
        """Register every module that offers a DAILY job; a missing module is not an error."""
        for name in MODULES:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            offer = getattr(module, "DAILY", None)
            if offer and not any(j["name"] == offer[0] for j in self.jobs):
                self.daily(*offer)

    def _read(self) -> dict:
        try:
            return json.loads(self.stamps.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def due(self, now: datetime | None = None) -> list:
        now = now or now_sao_paulo()
        stamps = self._read()
        today = now.date().isoformat()
        return [j for j in self.jobs if now.hour >= j["hour"] and (stamps.get(j["name"]) or {}).get("day") != today]

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
            stamps[name] = entry
            write_json(self.stamps, stamps)
        return entry

    def run_due(self, now: datetime | None = None) -> list:
        return [self.run(j["name"], now) for j in self.due(now)]

    def status(self) -> list:
        stamps = self._read()
        return [{"name": j["name"], "hour": j["hour"], **{k: v for k, v in (stamps.get(j["name"]) or {}).items() if k != "trace"}} for j in self.jobs]

    def start(self, interval_s: float = 300) -> None:
        """One daemon thread that checks the clock; only the owning web process calls this."""
        if self._thread:
            return

        def loop():
            while not self._stop.wait(interval_s):
                try:
                    self.run_due()
                except Exception:
                    pass
        self._thread = threading.Thread(target=loop, daemon=True, name="studio-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
