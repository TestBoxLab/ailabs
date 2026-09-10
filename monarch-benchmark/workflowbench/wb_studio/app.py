"""Private local comparison workspace. Job events are durable, reconnectable SSE."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from runner.arms import OracleArm, SloppyArm
from wb_arms.api_loop import ArmResult
from wb_arms.runtime_manifest import sha256_json
from wb_orchestrator.budget import BudgetLedger, BudgetExceeded
from wb_orchestrator.config import derive_langfuse_keys
from wb_orchestrator.orchestrator import Orchestrator
from wb_results.evidence import write_json
from wb_results.store import Store
from wb_world.episode import load_suite, load_task_file, contract_hash, EvidenceWriteError
from wb_studio.reports import public_task, outcome_report
from wb_studio.difficulty import difficulty
from wb_studio.agents import episode_executor, run_loop
from wb_studio.execution import ArchitectureArm, bound_graphs, execution_manifest, load_version, bind_comparison_model
from wb_studio import enterprise
from wb_studio.components import Components
from wb_studio.runtime import Runtime, AdmittedGateway, positive_int, single_host_owner
from wb_studio.product_graphs import corpus_products
from wb_studio.gateways import GeminiGateway, ProviderGateway
from wb_studio.runtime_registry import (api_controls, capability_matrix, check_launch, credential_present,
                                        resolve_api_control)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STATIC = Path(__file__).parent / "static"


def data_dir() -> Path | None:
    """Where a hosted Studio keeps its state (STUDIO_DATA_DIR, a mounted volume); None = the repo."""
    value = os.environ.get("STUDIO_DATA_DIR")
    return Path(value) if value else None


def public_hosts() -> set[str]:
    """Host names the hosted Studio answers to (STUDIO_PUBLIC_HOSTS, comma separated), besides localhost."""
    return {h.strip().lower() for h in os.environ.get("STUDIO_PUBLIC_HOSTS", "").split(",") if h.strip()}
MODEL_NAMES = {"oracle": "Scripted reference", "sloppy": "Near-miss control", "claude-code": "Claude Code", "codex": "Codex"}
ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def now():
    return datetime.now(timezone.utc).isoformat()


def front_door_target(env, rest: str) -> str:
    """Where the front door relays an application call.

    The shim runs wherever the attempt runs. When the Studio launches it that is
    this container, so the loopback default is right. When the CLI launches it the
    shim is on the operator's machine and reaches the Studio only through a public
    address, which `STUDIO_FRONT_DOOR_TARGET` names. Without it a hosted Studio
    answers 502 to every application call of a CLI round while still serving the
    OpenAPI documents, which reads as "the engine cannot execute" and is really
    "the door leads nowhere".
    """
    target = (env.get("STUDIO_FRONT_DOOR_TARGET") or "").strip()
    if target:
        return target.rstrip("/") + rest
    port = int(env.get("STUDIO_FRONT_DOOR_PORT") or 9105)
    return f"http://127.0.0.1:{port}{rest}"


class Studio:
    def __init__(self, directory=None, tasks=None, gateway_factory=None, adapter_factory=None):
        self.directory = Path(directory or ((data_dir() / "studio") if data_dir() else ROOT / "out" / "studio"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.tasks = {task["task"]: task for task in (tasks if tasks is not None else [load_task_file(p) for p in sorted((ROOT / "corpus").rglob("*.json"))])}
        ledger_path = REPO / "research" / "budget.sqlite3"
        if data_dir():
            ledger_path = data_dir() / "research" / "budget.sqlite3"
        if os.environ.get("STUDIO_LEDGER_PATH"):
            ledger_path = Path(os.environ["STUDIO_LEDGER_PATH"]).expanduser()
        self.ledger = BudgetLedger(self.directory / "budget.sqlite3" if gateway_factory is not None else ledger_path)
        self.gateway_factory = gateway_factory      # test hook for the Gemini control
        self.adapter_factory = adapter_factory      # test hook for every other provider
        # Every finished run gets its interpretation automatically, under this per-run ceiling (US$).
        self.analysis_ceiling = Decimal(os.environ.get("STUDIO_ANALYSIS_USD", "0.50" if gateway_factory is None else "0"))
        self.lock = threading.RLock()
        self.cancelled = {}
        self.token = secrets.token_urlsafe(32)
        from wb_studio.genesis import Genesis
        self.genesis = Genesis(self)
        from wb_studio.scheduler import Scheduler
        self.scheduler = Scheduler(self, self.directory / "genesis" / "schedule.json")
        self.scheduler.discover()
        self.components = Components()
        self.runtime = Runtime()
        self.execution_mode = os.environ.get("STUDIO_EXECUTION_MODE", "local")
        if self.execution_mode not in ("local", "workers"):
            raise ValueError("STUDIO_EXECUTION_MODE must be local or workers")
        self.coordinator = None
        if self.execution_mode == "workers":
            if not os.environ.get("STUDIO_WORKER_TOKEN"):
                raise ValueError("Worker mode requires STUDIO_WORKER_TOKEN")
            from wb_studio.coordinator import Coordinator
            self.coordinator = Coordinator(self, lease_seconds=float(os.environ.get("STUDIO_WORKER_LEASE_SECONDS", "60")))
        # A restart never replays potentially paid work.
        for path in self.directory.glob("*/job.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in ("queued", "running", "cancelling"):
                if self.coordinator is not None and job.get("worker"):
                    continue  # Durable remote claims survive coordinator restarts.
                if job["status"] == "queued" and not (path.parent / "execution.claimed").exists():
                    continue
                job.update(status="interrupted", finished_at=now(), error="Server restarted. Prior requests are not replayed; unknown charges stay reserved.")
                write_json(path, job)
                if self.ledger.run_reservation(job["id"]) is not None:
                    self.ledger.finish_run(job["id"])
        if self.coordinator is not None:
            self.coordinator.reap()

    def _load_env(self):
        if self.gateway_factory is None:
            load_dotenv(REPO / ".env", override=True)
            load_dotenv(ROOT / ".env", override=True)
            derive_langfuse_keys(os.environ)

    def models(self):
        self._load_env()
        entries = []
        for key, control in api_controls().items():
            available = credential_present(control)
            entries.append({"id": key, "name": control["name"], "kind": "API control", "provider": control["provider"],
                            "available": available, "reason": None if available else f"Add {control['key_env']} to .env",
                            "efforts": control["efforts"], "default_effort": control["default_effort"], "rate_card": control["rate_card"],
                            "request_ceiling_usd": control["request_ceiling_usd"]})
        from wb_studio import native
        native_state = native.status(self)
        for key, model in (("claude-code", "claude-opus-5"), ("codex", "gpt-5.6-sol")):
            control = api_controls()[model]
            ready = native_state["launchable"] and credential_present(control)
            entries.append({"id": key, "name": control["name"] + " \u00b7 " + MODEL_NAMES[key], "kind": "Native harness", "available": ready,
                            "efforts": control["efforts"], "default_effort": control["default_effort"],
                            "native_runner": {"harness": key, "model": model, "effort": "default"},
                            "request_ceiling_usd": control["request_ceiling_usd"],
                            "reason": None if ready else native_state["reason"] if not native_state["launchable"] else f"Add {control['key_env']} to .env"})
        for config in [json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.directory / "runner-configs").glob("*.json"))]:
            resolved = resolve_api_control(config)
            if resolved is None and config["provider"] in ("claude-code", "codex"):
                family = "anthropic" if config["provider"] == "claude-code" else "openai"
                mapped = resolve_api_control({**config, "provider": family})
                control = mapped["control"] if mapped else None
                effort_ok = control and (config["effort"] == "default" or config["effort"] in control["efforts"])
                ready = bool(native_state["launchable"] and control and effort_ok and credential_present(control))
                entries.append({"id": "config-" + config["id"], "name": config["name"], "kind": "Native harness", "available": ready,
                                "efforts": [], "native_runner": {"harness": config["provider"], "model": mapped["key"] if mapped else config["model"], "effort": config["effort"]},
                                "request_ceiling_usd": control["request_ceiling_usd"] if control else None,
                                "reason": None if ready else native_state["reason"] if not native_state["launchable"] else "Native model, effort or credential is unavailable"})
                continue
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
            gateway = GeminiGateway(paid, resolved["effort"], with_tools=with_tools)
        else:
            gateway = ProviderGateway(self.ledger, resolved["key"], resolved["effort"], with_tools=with_tools, adapter_factory=self.adapter_factory)
        return AdmittedGateway(gateway, self.runtime, resolved["control"]["provider"], self.cancelled.get)

    def component(self, identity, role):
        pins = self.job(identity).get("component_manifest") or self.components.pin()
        return self.components.resolve(pins, role)

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
        with self.lock:
            path = self.directory / job["id"] / "job.json"
            if path.exists():
                current = json.loads(path.read_text(encoding="utf-8"))
                for key in ("pause_requested", "active_attempts"):
                    if key in current:
                        job[key] = current[key]
            write_json(path, job)

    def _save_control(self, job):
        write_json(self.directory / job["id"] / "job.json", job)
        self.emit(job["id"], "run_control", status=job["status"],
                  pause_requested=job.get("pause_requested", False),
                  active_attempts=job.get("active_attempts", 0))

    def pause(self, identity):
        with self.lock:
            job = self.job(identity)
            if job["status"] not in ("queued", "running"):
                raise ValueError("Only queued or running runs can be paused")
            if not job.get("pause_requested"):
                job["pause_requested"] = True
                self._save_control(job)
            return job

    def resume(self, identity):
        with self.lock:
            job = self.job(identity)
            if job["status"] not in ("queued", "running"):
                raise ValueError("This run has ended and cannot be resumed")
            if not job.get("pause_requested"):
                return job
            job["pause_requested"] = False
            self._save_control(job)
            if self.coordinator is None and not (self.directory / identity / "execution.claimed").exists():
                threading.Thread(target=self.execute, args=(identity,), daemon=True).start()
            return job

    def begin_attempt(self, identity):
        with self.lock:
            job = self.job(identity)
            if job["status"] not in ("queued", "running"):
                return {"admitted": False, "cancelled": True}
            if job.get("pause_requested"):
                return {"admitted": False, "cancelled": False}
            job["active_attempts"] = job.get("active_attempts", 0) + 1
            self._save_control(job)
            return {"admitted": True, "cancelled": False}

    def end_attempt(self, identity):
        with self.lock:
            job = self.job(identity)
            job["active_attempts"] = max(0, job.get("active_attempts", 0) - 1)
            self._save_control(job)

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
            arms.append({"id": selection, "kind": "scripted" if base in ("oracle", "sloppy") else "native" if entry.get("native_runner") else "runner",
                         "name": entry["name"] + (" · " + effort + " reasoning" if effort else ""), "version": "without-monarch",
                         "request_ceiling_usd": entry.get("request_ceiling_usd") or (entry.get("configuration") and api_controls().get(entry.get("control", ""), {}).get("request_ceiling_usd"))})
            if arms[-1]["kind"] == "native":
                arms[-1]["runner"] = {**entry["native_runner"], "effort": effort or entry["native_runner"].get("effort", "default")}
            if arms[-1]["kind"] == "runner":
                control = api_controls()[entry.get("control", base)]
                requested_effort = entry.get("configuration", {}).get("effort", effort or "default")
                arms[-1]["runner"] = {"provider": control["provider"], "model": control["model"],
                                      "effort": control["default_effort"] if requested_effort == "default" else requested_effort}
        return arms

    def create(self, payload, start=True):
        if payload.get("bare_models") and isinstance(payload.get("configuration"), dict) and payload["configuration"].get("prompt"):
            raise ValueError("Bare must use the original task instructions. Remove additional instructions or turn off Bare.")
        identity = payload.get("request_id") or uuid.uuid4().hex
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            raise ValueError("Invalid request ID")
        selected = payload.get("models")
        if selected is None:
            selected = []
        # Every version × runner cell is checked against the capability registry before
        # a job, a reservation or a provider request exists.
        track = payload.get("track", "agentic-request")
        if track not in ("agentic-request", "create-and-run"):
            raise ValueError("Choose agentic requests or workflow building")
        versions = check_launch(self, payload.get("architectures"), selected if isinstance(selected, list) else [], track=track)
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
                arms.append({"id": version["id"], "kind": "version", "name": version["name"], "architecture_name": version["name"], "version": version["id"],
                             "blueprint": version["blueprint"], "number": version["version"], "sha256": version["sha256"],
                             "knowledge_sha256": version.get("knowledge_sha256"), "steps": version.get("steps", []),
                             "request_ceiling_usd": version.get("request_ceiling_usd")})
        if payload.get('comparison_models'):
            if not selected:
                raise ValueError('Choose the models to run through this architecture')
            if any(a['kind'] == 'enterprise' for a in arms):
                raise ValueError('Monarch uses its own configuration; model substitution is available for experimental architectures')
            candidates = self._runner_arms(selected)
            if any(a['kind'] != 'runner' for a in candidates):
                raise ValueError('Experimental nodes currently require API models; native harnesses are separate Bare comparisons')
            expanded = [a for a in arms if a['kind'] != 'version']
            for architecture in (a for a in arms if a['kind'] == 'version'):
                for candidate in candidates:
                    expanded.append({**architecture, 'id': architecture['id'] + '--' + candidate['id'],
                                     'name': architecture['name'] + ' / ' + candidate['name'],
                                     'model_selection': candidate['id'], 'runner_override': candidate['runner'],
                                     'request_ceiling_usd': candidate.get('request_ceiling_usd')})
            arms = expanded
        if payload.get('bare_models'):
            bare = self._runner_arms(payload['bare_models'])
            if any(a['kind'] != 'native' for a in bare):
                raise ValueError('Bare comparisons require a verified native harness, not an API control')
            check_launch(self, ['without-monarch'], payload['bare_models'], track=track)
            requested = {(resolve_api_control(a['runner'])['key'], a['runner']['effort']) for a in self._runner_arms(selected) if a['kind']=='runner'}
            for baseline in bare:
                if (baseline['runner']['model'], baseline['runner']['effort']) not in requested:
                    raise ValueError('Bare must use the same model and thinking setting as an architecture competitor')
            arms += bare
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
        settings = {"models": [a["id"] for a in arms], "arms": arms, "tasks": tasks, "maximum_usd": str(maximum), "track": track,
                    "architectures": [v["id"] for v in versions]}
        concurrency = positive_int(payload.get("concurrency", 1), "Concurrent agents", self.runtime.max_agents)
        pins = self.components.pin(payload.get("components"))
        if any(a["kind"] == "enterprise" for a in arms) and any(pins[r]["id"] != self.components.defaults[r] for r in ("brain", "action_builder")):
            raise ValueError("Monarch Enterprise owns its brain and action builder; use an experimental architecture to swap those components")
        if any(a["kind"] == "native" for a in arms) and any(pins[r]["id"] != self.components.defaults[r] for r in ("brain", "action_builder")):
            raise ValueError("Native harnesses own their brain and task-tool interface; component substitutions require an experimental architecture")
        settings.update(concurrency=concurrency, components={r: p["id"] for r, p in pins.items()})
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
            from wb_studio import native
            native_manifests = {arm["id"]: native.freeze(self, arm["runner"]) for arm in arms if arm["kind"] == "native"}
            if any(a["kind"] != "scripted" for a in arms) and maximum > self.ledger.status().available_usd:
                raise ValueError("Run budget exceeds this week's available capacity")
            if sum(j["status"] in ("queued", "running", "cancelling") for j in self.jobs()) >= 100:
                raise ValueError("The run queue is full. Wait for a run to finish before trying again.")
            if any(a["kind"] != "scripted" for a in arms):
                self.ledger.reserve_run(identity, maximum, metadata={"source": "studio", "track": track})
            try:
                path.mkdir()
                job = {"id": identity, "title": title,
                       "created_at": now(), "status": "queued", "settings": settings, "results": [], "completed": 0,
                       "total": len(tasks) * len(arms), "task_hashes": {t: contract_hash(self.tasks[t]) for t in tasks}}
                from wb_studio.task_sets import task_sets
                reference = next((item for item in task_sets(self, ROOT)['items'] if item['id']=='catalog-50'), None)
                if reference and set(tasks)==set(reference['tasks']) and len(tasks)==50:
                    job['benchmark'] = {'id':'catalog-50', 'task_hashes':dict(job['task_hashes'])}
                from wb_world.episode import installed_world_version, world_of
                job["world_manifest"] = {"package": "automation-bench", "installed_version": installed_world_version(),
                                         "task_worlds": {task: world_of(self.tasks[task]) or {"version": "1.0.6"} for task in tasks}}
                if track == "create-and-run":
                    import hashlib
                    from wb_studio import workflows
                    job["workflow_contract"] = {"formats": {"experimental": "studio-workflow-v1", "monarch": "native-recipe"}, "runtime_sha256": hashlib.sha256(Path(workflows.__file__).read_bytes()).hexdigest(),
                                                "requirement": "saved workflow artifact plus execution"}
                job["component_manifest"] = pins
                job["runtime_manifest"] = self.runtime.snapshot()
                for arm in arms:
                    if arm["kind"] == "native":
                        job.setdefault("runner_manifests", {})[arm["id"]] = {**native_manifests[arm["id"]],
                            "world_sha256": sha256_json(job["world_manifest"]), "selection": arm["id"]}
                    if arm["kind"] == "runner":
                        control = resolve_api_control(arm["runner"])["control"]
                        comparison = {"runner": arm["runner"], "configuration": settings.get("configuration", {"prompt": "", "max_turns": 20}),
                                      "components": pins}
                        job.setdefault("runner_manifests", {})[arm["id"]] = {
                            "schema_version": "ailabs-api-control-v1", "kind": "api-control", "native_harness": False,
                            "harness": "studio-api-loop", "comparison_class": "raw-api-control",
                            "runner": dict(arm["runner"]), "control": control["id"], "adapter": control["adapter"],
                            "rate_card": control["rate_card"], "prices_per_million": control["prices_per_million"],
                            "configuration_sha256": sha256_json(comparison),
                            "qualification": "Rate-carded API control; not a native-harness Bare baseline."}
                    if arm["kind"] == "version":
                        version = load_version(self, arm["blueprint"], arm["number"])
                        if arm.get("runner_override"):
                            version = bind_comparison_model(version, arm["runner_override"])
                        job.setdefault("execution_manifests", {})[arm["id"]] = execution_manifest(version, bound_graphs(self, version))
                    if arm["kind"] == "enterprise":
                        record = next(v for v in versions if v["id"] == arm["id"])
                        job.setdefault("execution_manifests", {})[arm["id"]] = record.get("manifest")
                self.save(job)
                self.cancelled[identity] = threading.Event()
                self.emit(identity, "queued", job=job)
            except BaseException:
                # No durable job means nothing can have been scheduled yet.
                # Keep any request liabilities; release only the unused envelope.
                if not (path / "job.json").exists():
                    if self.ledger.run_reservation(identity) is not None:
                        self.ledger.finish_run(identity)
                    if path.is_dir() and not any(path.iterdir()):
                        path.rmdir()
                raise

        if start and self.coordinator is None:
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
                if not job.get("worker") and not (self.directory / identity / "execution.claimed").exists():
                    job.update(status="cancelled", finished_at=now())
                    if self.ledger.run_reservation(identity) is not None:
                        self.ledger.finish_run(identity)
                    self.save(job)
                    self.emit(identity, "finished", job=job, budget=self.budget())
            self.schedule_narrative(identity)
            return job

    def _arm(self, job, arm, task_id, cancel):
        if job["settings"].get("track") == "create-and-run":
            import hashlib
            from wb_studio import workflows
            if job.get("workflow_contract", {}).get("runtime_sha256") != hashlib.sha256(Path(workflows.__file__).read_bytes()).hexdigest():
                raise ValueError("The workflow artifact contract changed; create a new run with the current contract")
        maximum = Decimal(job["settings"]["maximum_usd"])
        config = job["settings"].get("configuration", {})
        if arm["kind"] == "version":
            version = load_version(self, arm["blueprint"], arm["number"])
            if arm.get("runner_override"):
                version = bind_comparison_model(version, arm["runner_override"])
            graphs = bound_graphs(self, version)
            expected = job.get("execution_manifests", {}).get(arm["id"], {})
            if execution_manifest(version, graphs)["identity_sha256"] != expected.get("identity_sha256"):
                raise ValueError("The published version or its product graph changed since this run was created")
            return ArchitectureArm(self, job["id"], arm["id"], task_id, cancel, maximum, version, graphs, config)
        if arm["kind"] == "native":
            from wb_studio.native import NativeArm
            native_arm = NativeArm(self, job["id"], job["runner_manifests"][arm["id"]], task_id, cancel, maximum)
            native_arm.name = arm["id"]
            return native_arm
        if arm["kind"] == "enterprise":
            return enterprise.build_arm(self, job["id"], arm["id"], task_id, cancel, maximum,
                                        job.get("execution_manifests", {}).get(arm["id"]))
        return LiveArm(self, job["id"], arm["id"], task_id, cancel, maximum)

    def schedule_narrative(self, identity):
        """Every finished run gets its interpretation without a manual step, paid
        from the weekly ledger under the per-run ceiling. When it cannot run, the
        reason is recorded so the report says "Analysis pending" and why."""
        from wb_studio.paid import credential_status
        folder = self.directory / identity
        pending = folder / "analysis.pending.json"
        if (folder / "analysis.json").exists():
            return
        job = self.job(identity)
        arms = job["settings"].get("arms") or [{"id": m, "kind": "runner"} for m in job["settings"]["models"]]
        ceiling = self.analysis_ceiling
        if all(a.get("kind") == "scripted" or a["id"] in ("oracle", "sloppy", "null") for a in arms):
            return write_json(pending, {"reason": "Scripted checks only; there is nothing to interpret.", "ceiling_usd": str(ceiling)})
        if ceiling <= 0:
            return write_json(pending, {"reason": "Automatic analysis is off for this workspace (STUDIO_ANALYSIS_USD is 0).", "ceiling_usd": str(ceiling)})
        if self.gateway_factory is None and not credential_status()["configured"]:
            return write_json(pending, {"reason": "No analysis credential is configured (GEMINI_API_KEY).", "ceiling_usd": str(ceiling)})
        available = Decimal(str(self.budget().get("available", "0")))
        if available < ceiling:
            short = ceiling - available
            return write_json(pending, {"reason": f"The weekly ledger cannot cover the ${ceiling:.2f} analysis ceiling; ${short:.2f} short.",
                                        "shortfall_usd": str(short), "ceiling_usd": str(ceiling)})
        write_json(pending, {"reason": "The analysis was dispatched and has not returned yet.", "ceiling_usd": str(ceiling)})
        threading.Thread(target=self._narrative, args=(identity, ceiling), daemon=True).start()

    def _narrative(self, identity, ceiling):
        from wb_studio.analysis import review
        folder = self.directory / identity
        try:
            review(self, identity, maximum_usd=ceiling)
            (folder / "analysis.pending.json").unlink(missing_ok=True)
        except ValueError as exc:
            write_json(folder / "analysis.pending.json", {"reason": str(exc), "ceiling_usd": str(ceiling)})

    def execute(self, identity):
        if self.coordinator is not None:
            raise RuntimeError("Worker mode dispatches only through authenticated worker claims")
        with self.runtime.runs:
            self._execute(identity)

    def _execute(self, identity):
        job = self.job(identity)
        if job["status"] not in ("queued", "cancelling") or (job.get("pause_requested") and job["status"] == "queued"):
            return
        try:
            with (self.directory / identity / "execution.claimed").open("x") as claim:
                claim.write(now())
                claim.flush()
                os.fsync(claim.fileno())
        except FileExistsError:
            return
        cancel = self.cancelled.setdefault(identity, threading.Event())
        store = None
        try:
            store = Store(self.directory / identity / "results.sqlite3")
            orch = Orchestrator(store, ROOT / "tasks", [], 1, self.directory / identity / "evidence",
                                tasks=[self.tasks[t] for t in job["settings"]["tasks"]], provider_concurrency=1,
                                grader=self.component(identity, "judge"))
            store.create_run(identity, orch._hash(), orch.suite, orch._config())
            arms = job["settings"].get("arms") or [{"id": m, "kind": "runner"} for m in job["settings"]["models"]]
            job["status"] = "running"
            self.save(job)
            self.emit(identity, "running")
            def run_attempt(task_id, arm):
                while not cancel.is_set():
                    with self.runtime.agent(cancel) as admitted:
                        if not admitted:
                            return
                        control = self.begin_attempt(identity)
                        if control.get("cancelled"):
                            cancel.set()
                            return
                        if control["admitted"]:
                            try:
                                live = self._arm(job, arm, task_id, cancel)
                                self.emit(identity, "attempt_started", task=task_id, model=arm["id"])
                                orch._run_episode(identity, live, self.tasks[task_id], 0)
                                row = next(r for r in store.episodes(run=identity)["rows"] if r["task_id"] == task_id and r["arm"] == arm["id"])
                                result = {"task": task_id, "model": arm["id"], "passed": row["passed"], "termination": row["termination"],
                                          "error": row["error"], "cost_usd": row["cost_usd"], "tokens": row["tokens"],
                                          "seconds": row["phases"]["run"]["wall_clock_s"], "tool_calls": row["tool_calls"],
                                          "checks": row["check_results"] + [{"type": "allowed_changes_only", "passed": row["invariant_passed"]}],
                                          "unexpected_changes": row["unexpected_changes"], "flags": row["flags"], "output": live.output}
                                with self.lock:
                                    job["results"].append(result)
                                    job["completed"] += 1
                                    if cancel.is_set():
                                        job["status"] = "cancelling"
                                    self.emit(identity, "attempt_finished", **result)
                                    self.save(job)
                            finally:
                                self.end_attempt(identity)
                            return
                    cancel.wait(.1)

            def attempt(task_id, arm):
                try:
                    return run_attempt(task_id, arm)
                except Exception:
                    # Stop sibling admission immediately, even if an earlier task is slow.
                    cancel.set()
                    raise

            with ThreadPoolExecutor(max_workers=job["settings"].get("concurrency", 1)) as pool:
                futures = [pool.submit(attempt, task_id, arm) for task_id in job["settings"]["tasks"] for arm in arms]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        cancel.set()
                        raise
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
            if self.ledger.run_reservation(identity) is not None:
                self.ledger.finish_run(identity)
            job["finished_at"] = now()
            self.save(job)
            self.emit(identity, "finished", job=job, budget=self.budget())
            self.schedule_narrative(identity)
            if store is not None:
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
        job = studio.job(identity)
        self.config = job["settings"].get("configuration", {})
        self.frozen_runner = next((arm["runner"] for arm in job["settings"].get("arms", [])
                                   if arm["id"] == model and "runner" in arm), None)

    def emit(self, kind, **data):
        try:
            return self.studio.emit(self.identity, kind, model=self.name, task=self.task_id, **data)
        except OSError as exc:
            raise EvidenceWriteError("Live evidence could not be persisted") from exc

    def runner(self):
        if self.frozen_runner is not None:
            return dict(self.frozen_runner)
        # Historical jobs have no runner snapshot; preserve their original resolution.
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
        workflow_track = self.studio.job(self.identity)["settings"].get("track") == "create-and-run"
        execute = self.studio.component(self.identity, "action_builder")(ep)
        if workflow_track:
            from wb_studio.workflows import WORKFLOW_GUIDE, discovery_executor
            system += "\n\nWorkflow artifact requirement:\n" + WORKFLOW_GUIDE
            authoring_execute = discovery_executor(execute)
        else:
            authoring_execute = execute
        result = self.studio.component(self.identity, "brain")(gateway, system=system, brief=ep.task["prompt"][1]["content"], execute_tool=authoring_execute, emit=self.emit,
                          scope_id=self.identity, scope_limit_usd=self.maximum, request_prefix=f"{self.identity}-{self.task_id}-{self.name}",
                          max_turns=self.config.get("max_turns", 20), cancel=self.cancel, deadline=deadline,
                          record=ep.record_agent_event, budget=self.studio.budget)
        if workflow_track and result.termination == "completed":
            from wb_studio.workflows import execute_workflow
            execution = execute_workflow(result.final_text or "", execute=execute, emit=self.emit,
                                         record=ep.record_agent_event, cancel=self.cancel, deadline=deadline)
            result.tool_calls += execution.tool_calls
            result.termination, result.error = execution.termination, execution.error
            result.final_text = execution.final_text or execution.error
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
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"} | public_hosts()
            host = self.headers.get("Host", "").lower()
            origin = self.headers.get("Origin")
            return host in allowed and (not origin or origin in ("http://" + host, "https://" + host)) and (
                not write or self.headers.get("X-Studio-Token") == studio.token)

        def authorised(self) -> bool:
            """HTTP Basic Auth, on when STUDIO_AUTH_USER and STUDIO_AUTH_PASSWORD are both set (the hosted Studio)."""
            user, password = os.environ.get("STUDIO_AUTH_USER"), os.environ.get("STUDIO_AUTH_PASSWORD")
            if not user or not password:
                return True
            header = self.headers.get("Authorization", "")
            if not header.startswith("Basic "):
                return False
            try:
                given = base64.b64decode(header[6:].strip(), validate=True)
            except (ValueError, TypeError):
                return False
            return secrets.compare_digest(given, f"{user}:{password}".encode("utf-8"))

        FRONT_DOOR = "/front-door"

        def is_front_door(self) -> bool:
            return self.path == self.FRONT_DOOR or self.path.startswith(self.FRONT_DOOR + "/")

        def front_door(self):
            """Forward one request to the attempt's front door: wherever its shim runs.

            A hosted Studio is the only address Monarch can reach, so the seeds name
            `https://<studio>/front-door` and this handler relays to the shim the
            Monarch attempt started — on this host by default (STUDIO_FRONT_DOOR_PORT,
            9105), or at STUDIO_FRONT_DOOR_TARGET when the attempt runs elsewhere, as
            a CLI round does. Like the tunnel it replaces there is no login and no
            origin check on this path; the shim itself accepts only its episode's
            world calls.
            """
            rest = self.path[len(self.FRONT_DOOR):] or "/"
            length = int(self.headers.get("Content-Length") or 0)
            if length > 8 * 1024 * 1024:
                return self.send_json({"error": "Request too large"}, 413)
            body = self.rfile.read(length) if length else None
            request = urllib.request.Request(front_door_target(os.environ, rest), data=body, method=self.command)
            for name in ("Content-Type", "Accept", "X-Bench-Episode-Id", "Authorization", "If-Match"):
                value = self.headers.get(name)
                if value:
                    request.add_header(name, value)
            try:
                with urllib.request.urlopen(request, timeout=120) as resp:
                    status, data = resp.status, resp.read()
                    content_type = resp.headers.get("Content-Type") or "application/json"
            except urllib.error.HTTPError as exc:
                status, data = exc.code, exc.read()
                content_type = exc.headers.get("Content-Type") or "application/json"
            except (urllib.error.URLError, OSError, ValueError) as exc:
                return self.send_json({"error": f"front door is not running on this host: {exc}"}, 502)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_PUT(self):
            return self.front_door() if self.is_front_door() else self.send_json({"error": "Not found"}, 404)

        def do_PATCH(self):
            return self.front_door() if self.is_front_door() else self.send_json({"error": "Not found"}, 404)

        def do_DELETE(self):
            return self.front_door() if self.is_front_door() else self.send_json({"error": "Not found"}, 404)

        def challenge(self):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="AI Labs Studio", charset="UTF-8"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self):
            from urllib.parse import urlsplit, parse_qs
            if self.is_front_door():
                return self.front_door()
            if not self.authorised():
                return self.challenge()
            if not self.trusted():
                return self.send_json({"error": "Origin refused"}, 403)
            url = urlsplit(self.path)
            try:
                diagnostics_match = re.fullmatch(r"/api/jobs/([a-zA-Z0-9_-]+)/diagnostics", url.path)
                if diagnostics_match:
                    from wb_studio.failure_analysis import analysis
                    return self.send_json(analysis(studio, diagnostics_match[1]))
                if url.path == "/api/leaderboard":
                    from wb_studio.leaderboard import leaderboard
                    return self.send_json(leaderboard(studio))
                if url.path == "/api/task-sets":
                    from wb_studio.task_sets import task_sets
                    return self.send_json(task_sets(studio, ROOT))
                if url.path == "/api/budget":
                    return self.send_json(studio.budget())
                if url.path == "/api/runtime":
                    state = studio.runtime.snapshot()
                    if studio.coordinator is not None:
                        state.update(studio.coordinator.snapshot())
                    return self.send_json(state)
                if url.path == "/api/components":
                    return self.send_json(studio.components.catalog())
                if url.path == "/api/jobs":
                    if studio.coordinator is not None:
                        studio.coordinator.reap()
                    return self.send_json({"items": studio.jobs()})
                if url.path == "/api/jobs/counts":
                    from wb_studio.measures import run_counts
                    # ponytail: reads every run's events on each call; cache per job if the listing grows slow
                    return self.send_json({"items": {j["id"]: run_counts(j, studio.events(j["id"])) for j in studio.jobs()}})
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
                graph_match = re.fullmatch(r"/api/product-graphs/([a-zA-Z0-9_-]+)/(plan|versions/([0-9]{1,6})/(events|products))", url.path)
                if graph_match:
                    from wb_studio.product_graphs import drilldown as graph_drilldown, folder as graph_folder, load_version as load_graph_version, plan as graph_plan
                    if graph_match[2] == "plan":
                        return self.send_json(graph_plan(studio, graph_match[1]))
                    number = int(graph_match[3])
                    if graph_match[4] == "products":
                        return self.send_json(graph_drilldown(studio, graph_match[1], number))
                    load_graph_version(studio, graph_match[1], number)
                    path = graph_folder(studio, graph_match[1]) / f"v{number:04d}.events.jsonl"
                    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
                    return self.send_json({"events": [json.loads(line) for line in lines if line.strip()]})
                live_match = re.fullmatch(r"/api/live-graph/products(?:/([a-zA-Z0-9_.-]+)/actions)?", url.path)
                if live_match:
                    # Read only: the live graph Monarch Enterprise uses, over GET, never written.
                    from wb_studio import live_graph
                    try:
                        return self.send_json(live_graph.actions(studio, live_match[1]) if live_match[1] else live_graph.products(studio))
                    except live_graph.LiveGraphUnavailable as exc:
                        return self.send_json({"error": str(exc), "read_only": True}, 503)
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
                if url.path == "/api/usage":
                    from wb_studio.usage import usage_report
                    return self.send_json(usage_report(studio))
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
                if url.path == '/api/reports':
                    from wb_studio.report_data import index as report_index
                    return self.send_json(report_index(studio, self.audience(url)))
                report_match = re.fullmatch(r'/api/reports/(run|round)/([a-zA-Z0-9_-]+)', url.path)
                if report_match:
                    from wb_studio.report_data import round_report, run_report
                    build = run_report if report_match[1] == 'run' else round_report
                    return self.send_json(build(studio, report_match[2], self.audience(url)))
                if url.path == '/api/genesis': return self.send_json(studio.genesis.state())
                if url.path == '/api/genesis/schedule': return self.send_json({'jobs': studio.scheduler.status()})
                genesis_match=re.fullmatch(r'/api/genesis/turns/([a-zA-Z0-9_-]+)',url.path)
                if genesis_match: return self.send_json(studio.genesis.read('turns',genesis_match[1]))
                if url.path == '/api/genesis/library':
                    filters={k:v[0] for k,v in parse_qs(url.query).items() if k in ('published_from','published_to','discovered_from','discovered_to','topic','status')}
                    return self.send_json({'items':studio.genesis.library.listing(**filters),'topics':list(__import__('wb_studio.library',fromlist=['TOPICS']).TOPICS)})
                library_match=re.fullmatch(r'/api/genesis/library/([a-zA-Z0-9_-]+)',url.path)
                if library_match: return self.send_json(studio.genesis.library.read(library_match[1]))
                if url.path == '/api/genesis/memory':
                    card=parse_qs(url.query).get('card',[None])[0]
                    return self.send_json({**studio.genesis.memory.read(card),'history':studio.genesis.memory.history_tail(50),'access':studio.genesis.memory.access_stats()})
                if url.path == '/api/genesis/record':
                    query=parse_qs(url.query)
                    return self.send_json({'hits':studio.genesis.memory.search(query.get('q',[''])[0],query.get('limit',['10'])[0])})
                if url.path == '/api/genesis/watcher': return self.send_json(studio.genesis.watcher.status())
                if url.path == '/api/genesis/code-index':
                    from wb_studio.code_index import code_status
                    return self.send_json(code_status(studio))
                self.send_static(url.path)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except (ValueError, FileNotFoundError) as exc:
                # The message stays generic for the browser; the server log keeps the cause.
                print(f"studio GET {url.path}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                self.send_json({"error": "Unknown comparison or invalid cursor"}, 404)

        STATIC_TYPES = {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css",
                        "svg": "image/svg+xml", "woff2": "font/woff2", "png": "image/png", "json": "application/json",
                        "txt": "text/plain; charset=utf-8", "md": "text/plain; charset=utf-8"}

        def send_static(self, path):
            """Serve one file from wb_studio/static; never a path outside it."""
            name = "index.html" if path == "/" else path.lstrip("/")
            file = (STATIC / name).resolve()
            suffix = file.suffix.lstrip(".")
            if not file.is_relative_to(STATIC.resolve()) or suffix not in self.STATIC_TYPES or not file.is_file():
                return self.send_json({"error": "Not found"}, 404)
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", self.STATIC_TYPES[suffix])
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "public, max-age=86400" if name.startswith("vendor/") else "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def audience(self, url):
            """Reports are public unless the reader asks for the internal view."""
            from urllib.parse import parse_qs
            return "internal" if parse_qs(url.query).get("audience", [""])[0] == "internal" else "public"

        def worker_request(self):
            token = os.environ.get("STUDIO_WORKER_TOKEN", "")
            header = self.headers.get("Authorization", "")
            if studio.coordinator is None or not token or not secrets.compare_digest(header, "Bearer " + token):
                return self.send_json({"error": "Worker authorization required"}, 401)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1048576:
                    raise ValueError("Worker request too large")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a worker request object")
                return self.send_json(studio.coordinator.dispatch(payload))
            except (ValueError, TypeError, KeyError, FileNotFoundError, RuntimeError) as exc:
                return self.send_json({"error": str(exc), "error_type": type(exc).__name__, **({"kind": exc.kind} if hasattr(exc, "kind") else {})}, 400)

        def do_POST(self):
            if self.path == "/api/worker":
                return self.worker_request()
            if self.is_front_door():
                return self.front_door()
            if not self.authorised():
                return self.challenge()
            if not self.trusted(write=True):
                return self.send_json({"error": "Origin or session refused"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072:
                    raise ValueError("Request too large")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if self.path == '/api/genesis/chat': return self.send_json(studio.genesis.chat(payload),201)
                schedule_run=re.fullmatch(r'/api/genesis/schedule/([a-z0-9-]+)/run',self.path)
                if schedule_run: return self.send_json(studio.scheduler.run(schedule_run[1]))
                if self.path == '/api/genesis/cards': return self.send_json(studio.genesis.card(payload),201)
                genesis_approval=re.fullmatch(r'/api/genesis/cards/([a-zA-Z0-9_-]+)/approve',self.path)
                if genesis_approval: return self.send_json(studio.genesis.approve(genesis_approval[1],payload))
                if self.path == '/api/genesis/library': return self.send_json(studio.genesis.library.add(payload),201)
                if self.path == '/api/genesis/library/import': return self.send_json(studio.genesis.library.import_ledger(REPO/'research'/'search-log.jsonl'),201)
                library_action=re.fullmatch(r'/api/genesis/library/([a-zA-Z0-9_-]+)/(analyze|use|reclassify)',self.path)
                if library_action: return self.send_json(getattr(studio.genesis.library,library_action[2])(library_action[1],payload))
                if self.path == '/api/genesis/memory': return self.send_json(studio.genesis.memory.edit(payload))
                if self.path == '/api/genesis/drop': return self.send_json(studio.genesis.drop(payload),201)
                if self.path == '/api/genesis/watcher': studio.genesis.watcher.pause(payload.get('paused'));return self.send_json(studio.genesis.watcher.status())
                genesis_stop=re.fullmatch(r'/api/genesis/cards/([a-zA-Z0-9_-]+)/stop',self.path)
                if genesis_stop: return self.send_json(studio.genesis.stop_work(genesis_stop[1]))
                if self.path == '/api/genesis/code-index/refresh': return self.send_json(studio.scheduler.run('code-index'))

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
                    from wb_studio.product_graphs import load_version as load_graph_version, prepare as prepare_graph, summary
                    identity = payload.get("id")
                    if not isinstance(identity, str):
                        raise ValueError("Choose a product graph to prepare")
                    version = prepare_graph(studio, identity, maximum_usd=payload.get("maximum_usd", "1"), revision=payload.get("revision"))
                    parent = load_graph_version(studio, identity, version["parent_version"]) if version.get("parent_version") else None
                    return self.send_json(summary(version, parent), 201)
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
                if self.path == "/api/architectures/sync":
                    from wb_studio.architectures import sync_default
                    return self.send_json(sync_default(studio))
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
                if self.path == "/api/bare-coverage":
                    from wb_studio.bare_coverage import coverage
                    return self.send_json(coverage(studio, payload))
                if self.path == "/api/jobs":
                    return self.send_json(studio.create(payload), 201)
                match = re.fullmatch(r"/api/jobs/([a-zA-Z0-9_-]+)/(pause|resume|cancel)", self.path)
                if match:
                    return self.send_json(getattr(studio, match[2])(match[1]))
                return self.send_json({"error": "Not found"}, 404)
            except BudgetExceeded as exc:
                self.send_json({"error": str(exc)}, 409)
            except (ValueError, TypeError, KeyError, FileNotFoundError) as exc:
                self.send_json({"error": str(exc)}, 400)
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8765))
    parser.add_argument("--host", default=os.environ.get("STUDIO_HOST") or "127.0.0.1",
                        help="bind address; 0.0.0.0 when hosted (then set STUDIO_PUBLIC_HOSTS and the STUDIO_AUTH_* pair)")
    args = parser.parse_args(argv)
    load_dotenv(REPO / ".env", override=False)
    load_dotenv(ROOT / ".env", override=False)
    derive_langfuse_keys(os.environ)
    if args.host != "127.0.0.1" and not (os.environ.get("STUDIO_AUTH_USER") and os.environ.get("STUDIO_AUTH_PASSWORD")):
        parser.error("binding to a non-local address needs STUDIO_AUTH_USER and STUDIO_AUTH_PASSWORD")
    directory = (data_dir() / "studio") if data_dir() else ROOT / "out" / "studio"
    with single_host_owner(directory):
        app = Studio()
        app.genesis.recover_interrupted()
        app.scheduler.start()
        app.genesis.watcher.start()
        server = ThreadingHTTPServer((args.host, args.port), handler(app))
        if app.coordinator is None:
            for job in app.jobs():
                if job["status"] == "queued":
                    threading.Thread(target=app.execute, args=(job["id"],), daemon=True).start()
        else:
            def reap_workers():
                while True:
                    time.sleep(min(5, app.coordinator.lease_seconds / 3))
                    app.coordinator.reap()
            threading.Thread(target=reap_workers, daemon=True).start()
        print(f"AI Labs Studio: http://{args.host}:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
