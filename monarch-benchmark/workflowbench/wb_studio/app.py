"""Private local comparison workspace. Job events are durable, reconnectable SSE."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
import uuid

from dotenv import load_dotenv
from runner.arms import OracleArm, SloppyArm
from wb_arms.api_loop import ArmResult
from wb_orchestrator.budget import BudgetLedger
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.evidence import write_json
from wb_results.store import Store
from wb_world.episode import load_suite, load_task_file, contract_hash, EvidenceWriteError
from wb_studio.reports import public_task, outcome_report
from wb_studio.difficulty import difficulty
from wb_studio.agents import episode_executor, run_loop
from wb_studio.execution import ArchitectureArm, bound_graphs, execution_manifest, load_version
from wb_studio import enterprise
from wb_studio.product_graphs import corpus_products
from wb_studio.gateways import GeminiGateway, ProviderGateway
from wb_studio.runtime_registry import (api_controls, capability_matrix, check_launch, credential_present,
                                        resolve_api_control)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STATIC = Path(__file__).parent / "static"
MODEL_NAMES = {"oracle": "Scripted reference", "sloppy": "Near-miss control", "claude-code": "Claude Code", "codex": "Codex"}
ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def now():
    return datetime.now(timezone.utc).isoformat()


class Studio:
    def __init__(self, directory=None, tasks=None, gateway_factory=None, adapter_factory=None):
        self.directory = Path(directory or ROOT / "out" / "studio")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.tasks = {task["task"]: task for task in (tasks if tasks is not None else [load_task_file(p) for p in sorted((ROOT / "corpus").rglob("*.json"))])}
        self.ledger = BudgetLedger(self.directory / "budget.sqlite3" if gateway_factory is not None else REPO / "research" / "budget.sqlite3")
        self.gateway_factory = gateway_factory      # test hook for the Gemini control
        self.adapter_factory = adapter_factory      # test hook for every other provider
        self.lock = threading.RLock()
        self.cancelled = {}
        self.token = secrets.token_urlsafe(32)
        # A restart never replays potentially paid work.
        for path in self.directory.glob("*/job.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in ("queued", "running", "cancelling"):
                job.update(status="interrupted", finished_at=now(), error="Server restarted. Prior requests are not replayed; unknown charges stay reserved.")
                write_json(path, job)

    def _load_env(self):
        if self.gateway_factory is None:
            load_dotenv(REPO / ".env", override=True)
            load_dotenv(ROOT / ".env", override=True)

    def models(self):
        self._load_env()
        entries = []
        for key, control in api_controls().items():
            available = credential_present(control)
            entries.append({"id": key, "name": control["name"], "kind": "API control", "provider": control["provider"],
                            "available": available, "reason": None if available else f"Add {control['key_env']} to .env",
                            "efforts": control["efforts"], "default_effort": control["default_effort"], "rate_card": control["rate_card"],
                            "request_ceiling_usd": control["request_ceiling_usd"]})
        for key in ("claude-code", "codex"):
            entries.append({"id": key, "name": MODEL_NAMES[key], "kind": "Native harness", "available": False, "efforts": [],
                            "reason": "Isolated native runtime is not available"})
        for config in [json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.directory / "runner-configs").glob("*.json"))]:
            resolved = resolve_api_control(config)
            if resolved is None:
                reason = ("Native runtime is not available" if config["provider"] in ("claude-code", "codex")
                          else "No verified rate card for this model; add config/models/<name>.yaml before it can spend")
                entries.append({"id": "config-" + config["id"], "name": config["name"], "kind": config["provider"] + " / " + config["effort"],
                                "available": False, "reason": reason, "efforts": [], "configuration": config})
                continue
            control = resolved["control"]
            effort_ok = config["effort"] == "default" or config["effort"] in control["efforts"]
            available = credential_present(control) and effort_ok
            entries.append({"id": "config-" + config["id"], "name": config["name"], "kind": control["name"] + " / " + config["effort"],
                            "available": available, "efforts": [], "configuration": config, "control": control["id"],
                            "reason": None if available else (f"Add {control['key_env']} to .env" if effort_ok else f"{control['name']} does not accept {config['effort']} reasoning")})
        entries += [{"id": key, "name": MODEL_NAMES[key], "kind": "Scripted control", "available": True, "reason": None, "efforts": []} for key in ("oracle", "sloppy")]
        return entries

    def gateway_for(self, runner: dict, with_tools: bool = True):
        """One budget-admitted gateway for a runner config; Gemini keeps its verified preflight."""
        resolved = resolve_api_control(runner)
        if resolved is None:
            raise ValueError("This runner has no rate-carded API control")
        if resolved["key"] == "gemini-3.7-flash":
            from wb_studio.paid import PaidGateway
            paid = (self.gateway_factory or PaidGateway)(self.ledger, model="gemini-3.7-flash")
            return GeminiGateway(paid, resolved["effort"], with_tools=with_tools)
        return ProviderGateway(self.ledger, resolved["key"], resolved["effort"], with_tools=with_tools, adapter_factory=self.adapter_factory)

    def budget(self):
        value = self.ledger.status()
        return {name: str(getattr(value, name + "_usd")) for name in ("weekly_limit", "actual", "held", "available")} | {
            "week_start": value.week_start, "timezone": "America/Sao_Paulo", "blocked": value.blocked}

    def jobs(self):
        return sorted([json.loads(p.read_text(encoding="utf-8")) for p in self.directory.glob("*/job.json")],
                      key=lambda j: j["created_at"], reverse=True)

    def job(self, identity):
        if not ID.fullmatch(identity):
            raise ValueError("Invalid comparison ID")
        return json.loads((self.directory / identity / "job.json").read_text(encoding="utf-8"))

    def save(self, job):
        write_json(self.directory / job["id"] / "job.json", job)

    def emit(self, identity, kind, **data):
        with self.lock:
            file = self.directory / identity / "events.jsonl"
            count = sum(1 for _ in file.open(encoding="utf-8")) if file.exists() else 0
            event = {"id": count + 1, "type": kind, "at": now(), **data}
            with file.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return event

    def events(self, identity, after=0):
        self.job(identity)
        file = self.directory / identity / "events.jsonl"
        result = []
        if file.exists():
            for line in file.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                    if entry["id"] > after:
                        result.append(entry)
                except ValueError:
                    pass  # A crash may leave a partial final line.
        return result

    def _runner_arms(self, selected):
        """Validate runner selections for Without Monarch and describe each as an arm."""
        if not isinstance(selected, list) or any(not isinstance(m, str) for m in selected) or len(set(selected)) != len(selected):
            raise ValueError("Choose one to twelve different configurations")
        catalog = {m["id"]: m for m in self.models()}
        arms = []
        for selection in selected:
            base, _, effort = selection.partition("@")
            entry = catalog.get(base)
            if entry is None or not entry["available"]:
                raise ValueError("A selected runner is unavailable")
            if effort and effort not in entry["efforts"]:
                raise ValueError(f"{entry['name']} does not accept {effort} reasoning")
            if "@" in selection and not effort:
                raise ValueError("A selected runner is unavailable")
            arms.append({"id": selection, "kind": "scripted" if base in ("oracle", "sloppy") else "runner",
                         "name": entry["name"] + (" · " + effort + " reasoning" if effort else ""), "version": "without-monarch",
                         "request_ceiling_usd": entry.get("request_ceiling_usd") or (entry.get("configuration") and api_controls().get(entry.get("control", ""), {}).get("request_ceiling_usd"))})
        return arms

    def create(self, payload, start=True):
        identity = payload.get("request_id") or uuid.uuid4().hex
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            raise ValueError("Invalid request ID")
        selected = payload.get("models")
        if selected is None:
            selected = []
        # Every version × runner cell is checked against the capability registry before
        # a job, a reservation or a provider request exists.
        versions = check_launch(self, payload.get("architectures"), selected if isinstance(selected, list) else [])
        if self.gateway_factory is None and isinstance(selected, list) and any(m in ("oracle", "sloppy") for m in selected):
            raise ValueError("Scripted fixtures are for internal tests, not benchmark runs")
        arms = []
        if any(v["id"] == "without-monarch" for v in versions):
            if not selected:
                raise ValueError("Choose at least one runner for Without Monarch")
            arms += self._runner_arms(selected)
        for version in versions:
            if version["id"] == "default-monarch-enterprise":
                arms.append({"id": version["id"], "kind": "enterprise", "name": version["name"], "version": version["id"],
                             "served": version.get("served"), "request_ceiling_usd": version.get("request_ceiling_usd")})
            if version["id"].startswith("blueprint."):
                arms.append({"id": version["id"], "kind": "version", "name": version["name"], "version": version["id"],
                             "blueprint": version["blueprint"], "number": version["version"], "sha256": version["sha256"],
                             "knowledge_sha256": version.get("knowledge_sha256"), "steps": version.get("steps", []),
                             "request_ceiling_usd": version.get("request_ceiling_usd")})
        if not 1 <= len(arms) <= 12:
            raise ValueError("Choose one to twelve different configurations")
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 800 or any(not isinstance(t, str) for t in tasks) or len(set(tasks)) != len(tasks) or any(t not in self.tasks for t in tasks):
            raise ValueError("Choose one to 800 tasks from this corpus")
        try:
            maximum = Decimal(str(payload.get("maximum_usd", "1")))
            if not maximum.is_finite() or maximum <= 0 or maximum > 300 or maximum.as_tuple().exponent < -2:
                raise ValueError()
        except Exception:
            raise ValueError("Run budget must be between $0.01 and $300, with at most two decimals")
        floor = max((Decimal(a["request_ceiling_usd"]) for a in arms if a.get("request_ceiling_usd")), default=None)
        if floor is not None and maximum < floor:
            worst = max((a for a in arms if a.get("request_ceiling_usd")), key=lambda a: Decimal(a["request_ceiling_usd"]))
            raise ValueError(f"Run budget too low: {worst['name']} reserves up to ${floor:.2f} for a single request before it is admitted. Set at least ${floor:.2f}.")
        title = payload.get("title", "Model comparison")
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            raise ValueError("Use a comparison name between 1 and 100 characters")
        settings = {"models": [a["id"] for a in arms], "arms": arms, "tasks": tasks, "maximum_usd": str(maximum), "track": "agentic-request",
                    "architectures": [v["id"] for v in versions]}
        if "configuration" in payload:
            config = payload["configuration"]
            if not isinstance(config, dict) or set(config) - {"prompt", "max_turns"}:
                raise ValueError("Unsupported execution configuration")
            prompt = config.get("prompt", "")
            turns = config.get("max_turns", 20)
            if not isinstance(prompt, str) or len(prompt) > 12000 or type(turns) is not int or not 1 <= turns <= 50:
                raise ValueError("Prompt must be under 12,000 characters; turn limit must be 1 to 50")
            if prompt and any(a["kind"] == "scripted" for a in arms):
                raise ValueError("Scripted controls cannot follow a custom prompt. Select an API control to test prompt changes.")
            settings["configuration"] = {"prompt": prompt, "max_turns": turns}
        with self.lock:
            path = self.directory / identity
            if path.exists():
                previous = self.job(identity)
                if previous["settings"] != settings:
                    raise ValueError("This request ID already belongs to a different comparison")
                return previous
            if any(a["kind"] != "scripted" for a in arms) and maximum > self.ledger.status().available_usd:
                raise ValueError("Run budget exceeds this week's available capacity")
            path.mkdir()
            job = {"id": identity, "title": title,
                   "created_at": now(), "status": "queued", "settings": settings, "results": [], "completed": 0,
                   "total": len(tasks) * len(arms), "task_hashes": {t: contract_hash(self.tasks[t]) for t in tasks}}
            for arm in arms:
                if arm["kind"] == "version":
                    version = load_version(self, arm["blueprint"], arm["number"])
                    job.setdefault("execution_manifests", {})[arm["id"]] = execution_manifest(version, bound_graphs(self, version))
                if arm["kind"] == "enterprise":
                    record = next(v for v in versions if v["id"] == arm["id"])
                    job.setdefault("execution_manifests", {})[arm["id"]] = record.get("manifest")
            self.save(job)
            self.cancelled[identity] = threading.Event()
            self.emit(identity, "queued", job=job)
        if start:
            threading.Thread(target=self.execute, args=(identity,), daemon=True).start()
        return job

    def cancel(self, identity):
        with self.lock:
            job = self.job(identity)
            if job["status"] in ("queued", "running"):
                self.cancelled.setdefault(identity, threading.Event()).set()
                job["status"] = "cancelling"
                self.save(job)
                self.emit(identity, "cancelling")
            return job

    def _arm(self, job, arm, task_id, cancel):
        maximum = Decimal(job["settings"]["maximum_usd"])
        config = job["settings"].get("configuration", {})
        if arm["kind"] == "version":
            version = load_version(self, arm["blueprint"], arm["number"])
            graphs = bound_graphs(self, version)
            expected = job.get("execution_manifests", {}).get(arm["id"], {})
            if execution_manifest(version, graphs)["identity_sha256"] != expected.get("identity_sha256"):
                raise ValueError("The published version or its product graph changed since this run was created")
            return ArchitectureArm(self, job["id"], arm["id"], task_id, cancel, maximum, version, graphs, config)
        if arm["kind"] == "enterprise":
            return enterprise.build_arm(self, job["id"], arm["id"], task_id, cancel, maximum,
                                        job.get("execution_manifests", {}).get(arm["id"]))
        return LiveArm(self, job["id"], arm["id"], task_id, cancel, maximum)

    def execute(self, identity):
        job = self.job(identity)
        try:
            with (self.directory / identity / "execution.claimed").open("x") as claim:
                claim.write(now())
                claim.flush()
                os.fsync(claim.fileno())
        except FileExistsError:
            return
        cancel = self.cancelled.setdefault(identity, threading.Event())
        store = Store(self.directory / identity / "results.sqlite3")
        orch = Orchestrator(store, ROOT / "tasks", [], 1, self.directory / identity / "evidence",
                            tasks=[self.tasks[t] for t in job["settings"]["tasks"]], provider_concurrency=1)
        store.create_run(identity, orch._hash(), "workflowbench-synthetic@0.1", orch._config())
        arms = job["settings"].get("arms") or [{"id": m, "kind": "runner"} for m in job["settings"]["models"]]
        try:
            job["status"] = "running"
            self.save(job)
            self.emit(identity, "running")
            for task_id in job["settings"]["tasks"]:
                for arm in arms:
                    if cancel.is_set():
                        break
                    live = self._arm(job, arm, task_id, cancel)
                    self.emit(identity, "attempt_started", task=task_id, model=arm["id"])
                    orch._run_episode(identity, live, self.tasks[task_id], 0)
                    row = next(r for r in store.episodes(run=identity)["rows"] if r["task_id"] == task_id and r["arm"] == arm["id"])
                    result = {"task": task_id, "model": arm["id"], "passed": row["passed"], "termination": row["termination"],
                              "error": row["error"], "cost_usd": row["cost_usd"], "tokens": row["tokens"],
                              "seconds": row["phases"]["run"]["wall_clock_s"], "tool_calls": row["tool_calls"],
                              "checks": row["check_results"] + [{"type": "allowed_changes_only", "passed": row["invariant_passed"]}],
                              "unexpected_changes": row["unexpected_changes"], "flags": row["flags"], "output": live.output}
                    job["results"].append(result)
                    job["completed"] += 1
                    self.emit(identity, "attempt_finished", **result)
                    self.save(job)
                if cancel.is_set():
                    break
            job["status"] = "cancelled" if cancel.is_set() else "completed"
            infrastructure = sum(r["termination"].startswith("infra:") for r in job["results"])
            if infrastructure:
                job["error"] = f"{infrastructure} attempt(s) stopped with an execution issue. These are not valid model-quality measurements."
                if infrastructure == len(job["results"]):
                    job["status"] = "failed"
        except Exception as exc:
            job["status"] = "failed"
            # No raw provider errors in the API: they can include URLs/credentials.
            # The traceback stays in the job directory for local diagnosis.
            import traceback
            (self.directory / identity / "execution.error.log").write_text(traceback.format_exc(), encoding="utf-8")
            job["error"] = f"Execution stopped ({type(exc).__name__}). Evidence and reservations were retained."
        finally:
            job["finished_at"] = now()
            self.emit(identity, "finished", job=job, budget=self.budget())
            self.save(job)
            store.close()


class LiveArm:
    """A plain runner on the task: scripted control or one rate-carded API control."""
    provider_key = None
    message_evidence = "normalized"

    def __init__(self, studio, identity, model, task, cancel, maximum):
        self.studio, self.identity, self.name, self.task_id = studio, identity, model, task
        self.cancel, self.maximum, self.output = cancel, maximum, ""
        self.sequence = 0
        self.base_model, _, self.effort = model.partition("@")
        self.config = studio.job(identity)["settings"].get("configuration", {})

    def emit(self, kind, **data):
        try:
            return self.studio.emit(self.identity, kind, model=self.name, task=self.task_id, **data)
        except OSError as exc:
            raise EvidenceWriteError("Live evidence could not be persisted") from exc

    def runner(self):
        if self.base_model.startswith("config-"):
            saved = json.loads((self.studio.directory / "runner-configs" / (self.base_model[len("config-"):] + ".json")).read_text(encoding="utf-8"))
            return {"provider": saved["provider"], "model": saved["model"], "effort": saved["effort"]}
        control = api_controls()[self.base_model]
        return {"provider": control["provider"], "model": control["model"], "effort": self.effort or "default"}

    def run(self, ep, deadline=None):
        original = ep._observe
        def observe(tool, arguments, call):
            node = f"tool-{self.sequence}"
            self.sequence += 1
            self.emit("node_started", node=node, label=tool, arguments=arguments)
            try:
                value = original(tool, arguments, call)
                self.emit("node_finished", node=node, label=tool, output=value, status="completed")
                return value
            except Exception:
                self.emit("node_finished", node=node, label=tool, output="Tool failed; inspect the retained trace.", status="error")
                raise
        ep._observe = observe
        if self.name in ("oracle", "sloppy"):
            (OracleArm if self.name == "oracle" else SloppyArm)().run(ep)
            self.output = "Scripted control completed. See the task checks and individual tool outputs."
            return ArmResult(tool_calls=len(ep.tool_calls), final_text=self.output)
        gateway = self.studio.gateway_for(self.runner())
        self.emit("step_runner", runner=gateway.describe())
        system = ep.task["prompt"][0]["content"]
        if self.config.get("prompt"):
            system += "\n\nExperiment instructions:\n" + self.config["prompt"]
        result = run_loop(gateway, system=system, brief=ep.task["prompt"][1]["content"], execute_tool=episode_executor(ep), emit=self.emit,
                          scope_id=self.identity, scope_limit_usd=self.maximum, request_prefix=f"{self.identity}-{self.task_id}-{self.name}",
                          max_turns=self.config.get("max_turns", 20), cancel=self.cancel, deadline=deadline,
                          record=ep.record_agent_event, budget=self.studio.budget)
        self.output = result.final_text or ""
        return result


def handler(studio):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def trusted(self, write=False):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return host in allowed and (not origin or origin == "http://" + host) and (
                not write or self.headers.get("X-Studio-Token") == studio.token)

        def do_GET(self):
            from urllib.parse import urlsplit, parse_qs
            if not self.trusted():
                return self.send_json({"error": "Origin refused"}, 403)
            url = urlsplit(self.path)
            try:
                if url.path == "/api/blueprints":
                    from wb_studio.blueprints import listing
                    from wb_studio.runtime_registry import annotate_listing
                    return self.send_json({"items": annotate_listing(studio, listing(studio))})
                version_match = re.fullmatch(r"/api/blueprints/([a-zA-Z0-9_-]+)/versions/([0-9]{1,6})/diff", url.path)
                if version_match:
                    from wb_studio.blueprints import diff_versions
                    identity, number = version_match[1], int(version_match[2])
                    query = parse_qs(url.query)
                    other = int(query.get("from", [str(number - 1)])[0])
                    return self.send_json(diff_versions(load_version(studio, identity, other), load_version(studio, identity, number)))
                if url.path == "/api/product-graphs":
                    from wb_studio.product_graphs import listing as graph_listing
                    return self.send_json({"items": graph_listing(studio), "products": corpus_products(studio.tasks)})
                graph_match = re.fullmatch(r"/api/product-graphs/([a-zA-Z0-9_-]+)/(plan|versions/([0-9]{1,6})/events)", url.path)
                if graph_match:
                    from wb_studio.product_graphs import folder as graph_folder, load_version as load_graph_version, plan as graph_plan
                    if graph_match[2] == "plan":
                        return self.send_json(graph_plan(studio, graph_match[1]))
                    number = int(graph_match[3])
                    load_graph_version(studio, graph_match[1], number)
                    path = graph_folder(studio, graph_match[1]) / f"v{number:04d}.events.jsonl"
                    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
                    return self.send_json({"events": [json.loads(line) for line in lines if line.strip()]})
                if url.path == "/api/runners/fireworks":
                    from wb_studio.runners import fireworks_catalog
                    studio.models()
                    return self.send_json(fireworks_catalog(studio))
                if url.path == "/api/architectures/default":
                    from wb_studio.architectures import default_status
                    return self.send_json(default_status(studio))
                if url.path == "/api/architectures/enterprise":
                    return self.send_json(enterprise.version_record(studio))
                if url.path == "/api/architectures/bridge-v2-v9.12":
                    from wb_studio.runtime_registry import bridge_status, BRIDGE_SETTINGS
                    return self.send_json({"settings": BRIDGE_SETTINGS, **bridge_status(studio)})
                if url.path == "/api/capabilities":
                    return self.send_json(capability_matrix(studio))
                if url.path == "/api/state":
                    jobs = studio.jobs()
                    ratings = difficulty(studio.tasks, jobs)
                    return self.send_json({"token": studio.token, "models": [m for m in studio.models() if m["id"] not in ("oracle", "sloppy")], "budget": studio.budget(),
                                           "capabilities": capability_matrix(studio),
                                           "tasks": [public_task(t) | {"difficulty": ratings[t["task"]]} for t in studio.tasks.values()],
                                           "jobs": studio.jobs(), "setups": [json.loads(p.read_text(encoding="utf-8")) for p in (studio.directory / "setups").glob("*.json")] })
                match = re.fullmatch(r"/api/jobs/([a-zA-Z0-9_-]+)(/events|/report)?", url.path)
                if match:
                    identity = match[1]
                    if not match[2]:
                        return self.send_json(studio.job(identity))
                    if match[2] == "/report":
                        report_job = studio.job(identity)
                        report = outcome_report(report_job, studio.events(identity), studio.tasks, studio.directory / identity / "results.sqlite3")
                        analysis = studio.directory / identity / "analysis.json"
                        report["analysis"] = json.loads(analysis.read_text(encoding="utf-8")) if analysis.exists() else None
                        return self.send_json(report)
                    cursor = int(self.headers.get("Last-Event-ID") or parse_qs(url.query).get("after", ["0"])[0])
                    studio.job(identity)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    while True:
                        for event in studio.events(identity, cursor):
                            self.wfile.write(f"id: {event['id']}\ndata: {json.dumps(event)}\n\n".encode())
                            cursor = event["id"]
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        if studio.job(identity)["status"] not in ("queued", "running", "cancelling"):
                            break
                        time.sleep(.4)
                    return
                filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/graph.js": "graph.js", "/graph.css": "graph.css", "/pg.js": "pg.js"}.get(url.path)
                if filename is None:
                    return self.send_json({"error": "Not found"}, 404)
                file = STATIC / filename
                data = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css"}[filename.split(".")[-1]])
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (ValueError, FileNotFoundError):
                self.send_json({"error": "Unknown comparison or invalid cursor"}, 404)

        def do_POST(self):
            if not self.trusted(write=True):
                return self.send_json({"error": "Origin or session refused"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072:
                    raise ValueError("Request too large")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/blueprints/draft":
                    from wb_studio.blueprints import save_draft
                    return self.send_json(save_draft(studio, payload), 201)
                if self.path == "/api/blueprints/validate":
                    from wb_studio.blueprints import problems
                    from wb_studio.runtime_registry import node_support
                    graph = payload.get("graph")
                    structural = problems(graph, strict=False)
                    rows = [] if structural else [r for r in (node_support(studio, n) for n in graph["nodes"]) if r]
                    return self.send_json({"problems": problems(graph), "capabilities": rows})
                if self.path == "/api/blueprints/publish":
                    from wb_studio.blueprints import publish
                    return self.send_json(publish(studio, payload), 201)
                if self.path == "/api/product-graphs/draft":
                    from wb_studio.product_graphs import save_draft as save_graph_draft
                    return self.send_json(save_graph_draft(studio, payload), 201)
                if self.path == "/api/product-graphs/prepare":
                    from wb_studio.product_graphs import prepare as prepare_graph, summary
                    identity = payload.get("id")
                    if not isinstance(identity, str):
                        raise ValueError("Choose a product graph to prepare")
                    return self.send_json(summary(prepare_graph(studio, identity, maximum_usd=payload.get("maximum_usd", "1"), revision=payload.get("revision"))), 201)
                if self.path == "/api/runners/fireworks/refresh":
                    from wb_studio.runners import fireworks_catalog
                    studio.models()
                    return self.send_json(fireworks_catalog(studio, refresh=True))
                if self.path == "/api/runners/config":
                    from wb_studio.runners import runner_config
                    value = runner_config(payload)
                    value["id"] = uuid.uuid4().hex
                    value["name"] = (str(payload.get("name", "")).strip() or value["provider"] + " / " + value["model"])[:100]
                    folder = studio.directory / "runner-configs"
                    folder.mkdir(exist_ok=True)
                    write_json(folder / (value["id"] + ".json"), value)
                    return self.send_json(value, 201)
                if self.path == "/api/architectures/enterprise/verify":
                    verified = enterprise.verify(studio)
                    return self.send_json({"probe": verified, **enterprise.version_record(studio)})
                if self.path == "/api/architectures/refresh":
                    from wb_studio.architectures import default_status
                    return self.send_json(default_status(studio, refresh=True))
                if self.path == "/api/setups":
                    from wb_studio.setups import save_setup
                    return self.send_json(save_setup(studio, payload), 201)
                analyze = re.fullmatch(r"/api/jobs/([a-zA-Z0-9_-]+)/analyze", self.path)
                if analyze:
                    from wb_studio.analysis import review
                    return self.send_json(review(studio, analyze[1]))
                if self.path == "/api/jobs":
                    return self.send_json(studio.create(payload), 201)
                match = re.fullmatch(r"/api/jobs/([a-zA-Z0-9_-]+)/cancel", self.path)
                if match:
                    return self.send_json(studio.cancel(match[1]))
                return self.send_json({"error": "Not found"}, 404)
            except (ValueError, TypeError, KeyError, FileNotFoundError) as exc:
                self.send_json({"error": str(exc)}, 400)
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    load_dotenv(REPO / ".env", override=False)
    load_dotenv(ROOT / ".env", override=False)
    app = Studio()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app))
    print(f"AI Labs Studio: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
