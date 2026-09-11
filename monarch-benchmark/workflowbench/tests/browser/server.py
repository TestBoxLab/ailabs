"""Fixture Studio for browser checks: a temporary workspace with recorded runs
made by the scripted checks (answer key and sloppy), so nothing is paid and
every view has data. Serves on 127.0.0.1 and prints READY when it accepts
requests.

    uv run python tests/browser/server.py --port 8766
"""
import argparse
import os
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb_studio.app import ROOT, Studio, handler  # noqa: E402
from wb_world.episode import load_suite  # noqa: E402


def build(directory: Path, live: bool = False) -> Studio:
    def forbidden_gateway(*args, **kwargs):
        raise RuntimeError("The browser fixture never dispatches paid work")
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)
    tasks = load_suite(ROOT / "tasks")[:3]
    studio = Studio(directory, tasks=tasks, gateway_factory=forbidden_gateway)
    for index, (title, chosen) in enumerate([
        ("Answer key against sloppy, three tasks", [t["task"] for t in tasks]),
        ("Answer key only, one task", [tasks[0]["task"]]),
        ("Sloppy only, two tasks", [t["task"] for t in tasks[:2]]),
    ]):
        models = ["oracle", "sloppy"] if index == 0 else ["oracle"] if index == 1 else ["sloppy"]
        job = studio.create({"request_id": f"fixture-{index + 1}", "title": title, "models": models,
                             "tasks": chosen, "maximum_usd": "1.00"}, start=False)
        studio.execute(job["id"])
    if live:
        streaming(studio, tasks)
    return studio


def streaming(studio, tasks):
    """A run left mid-stream so the live views can be looked at: one attempt finished,
    one still writing, one waiting. The events are the shapes the real execution
    emits; no request is made and the job never finishes."""
    from wb_results.evidence import write_json
    job = studio.create({"request_id": "fixture-live", "title": "Streaming now: answer key and sloppy, three tasks",
                         "models": ["oracle", "sloppy"], "tasks": [t["task"] for t in tasks], "maximum_usd": "1.00",
                         "concurrency": 2}, start=False)
    identity, first, second = job["id"], tasks[0]["task"], tasks[1]["task"]
    job["status"] = "running"
    write_json(studio.directory / identity / "job.json", job)
    emit = lambda kind, **data: studio.emit(identity, kind, **data)
    emit("running")
    # attempt 1: finished
    emit("attempt_started", task=first, model="oracle")
    emit("step_started", task=first, model="oracle", step="agent", label="Agent", step_type="agent")
    emit("model_started", task=first, model="oracle", node="agent:model-1", label="Working", turn=1)
    emit("model_delta", task=first, model="oracle", node="agent:model-1", text="Found the email from Lisa Park. ", turn=1)
    emit("node_started", task=first, model="oracle", node="agent:tool-1", label="salesforce.update_contact", arguments={"id": "003004", "MailingCity": "Denver"}, step="agent")
    emit("node_finished", task=first, model="oracle", node="agent:tool-1", label="salesforce.update_contact", output={"ok": True}, status="completed", step="agent")
    emit("model_finished", task=first, model="oracle", node="agent:model-1", output="Updated the mailing city to Denver.", status="completed")
    emit("step_finished", task=first, model="oracle", step="agent", label="Agent", status="completed", output="Updated the mailing city to Denver.")
    emit("attempt_finished", task=first, model="oracle", passed=True, termination="completed", error=None, cost_usd="0", tokens={}, seconds=1.2,
         tool_calls=1, checks=[{"type": "field", "passed": True}], unexpected_changes=[], flags=[], output="Updated the mailing city to Denver.")
    # attempt 2: still writing
    emit("attempt_started", task=second, model="sloppy")
    emit("step_started", task=second, model="sloppy", step="agent", label="Agent", step_type="agent")
    emit("knowledge_delivered", task=second, model="sloppy", step="agent", source="graph", label="Corpus knowledge v2", products=2)
    emit("model_started", task=second, model="sloppy", node="agent:model-1", label="Working", turn=1)
    emit("node_started", task=second, model="sloppy", node="agent:tool-1", label="gmail.search", arguments={"query": "Amir Hassan"}, step="agent")
    emit("node_finished", task=second, model="sloppy", node="agent:tool-1", label="gmail.search", output={"messages": 1}, status="completed", step="agent")
    for text in ("Reading the message from Amir Hassan. ", "He moved to the Platform team. ", "Looking up his contact in Salesforce"):
        emit("model_delta", task=second, model="sloppy", node="agent:model-1", text=text, turn=1)


def configured_results_handler(studio):
    """Emit actual result SSE messages after subscription, including repeated pairs."""
    source = studio.jobs()[0]["results"][0]
    job = studio.create({"request_id": "fixture-config-results", "title": "Configured result stream fixture",
                         "models": [source["model"]], "tasks": [source["task"]], "maximum_usd": "3.00"}, start=False)
    identity = job["id"]
    first = dict(source, episode_id="fixture-initial", cost_usd=0.25)
    job.update(status="running", config_source={"commit": "fixture"},
               results=[first], completed=1, total=3, cost_usd=0.25)
    job["settings"]["plan_semantics"] = True
    studio.emit(identity, "finished", job={**job, "status": "failed", "finished_at": "2026-09-10T20:00:00+00:00"})
    job["resumed_at"] = "2026-09-10T21:00:00+00:00"
    studio.save(job)
    subscribed = threading.Event()

    def publish():
        retries = [dict(first, episode_id="fixture-retry-1", cost_usd=0.5, flags=["retry"]),
                   dict(first, episode_id="fixture-retry-2", cost_usd=0.75, flags=["retry"])]
        job.update(results=[first, *retries], completed=3, cost_usd=1.5)
        studio.save(job)
        for result in retries:
            studio.emit(identity, "result", **result)

    class ResultHandler(handler(studio)):
        def do_GET(self):
            if self.path == f"/api/jobs/{identity}/events" and not subscribed.is_set():
                subscribed.set()
                timer = threading.Timer(1, publish)
                timer.daemon = True
                timer.start()
            super().do_GET()

    return ResultHandler


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--keep", action="store_true", help="keep the temporary workspace")
    parser.add_argument("--live", action="store_true", help="add a run left mid-stream for the live views")
    parser.add_argument("--configured-results", action="store_true", help="emit configured result events with retries")
    args = parser.parse_args(argv)
    directory = Path(tempfile.mkdtemp(prefix="ailabs-browser-"))
    studio = build(directory / "studio", live=args.live)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), configured_results_handler(studio) if args.configured_results else handler(studio))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"READY http://127.0.0.1:{args.port} workspace={directory}", flush=True)
    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        if not args.keep:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
