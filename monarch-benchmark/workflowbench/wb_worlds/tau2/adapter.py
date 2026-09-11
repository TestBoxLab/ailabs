"""HTTP client for a private Sierra tau2 environment and its budgeted customer."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from wb_world.adapter import PositiveResult, ToolInterfaces, canonical

SEND_MESSAGE = {"name": "send_message", "description": "Speak to the simulated customer and receive their reply. Use this to greet them, obtain the request, ask questions, and communicate the outcome.",
                "parameters": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False}}


class Tau2World:
    artifacts_dir = None
    snapshot0 = None
    tool_calls = ()
    events = ()

    def __init__(self, task, episode_id, frozen_time=None):
        self.task, self.episode_id = task, episode_id
        self.tool_calls, self.events = [], []
        self._journal, self._closed = None, False
        self._customer_callback, self._participant = None, None
        ref = task.get("source_ref") or {}
        self.domain = ref["domain"]
        self.service = "tau2-" + self.domain
        created = self._request("/create", {**ref, "episode_id": episode_id,
                                            "source_world": task.get("info", {}).get("world")})
        self._id = created["id"]
        self._tools = created["tools"]
        self.policy = created["policy"]
        self.snapshot0 = self.snapshot()

    @staticmethod
    def service_names():
        return ["tau2-retail", "tau2-airline", "tau2-telecom", "tau2-telecom-customer"]

    @classmethod
    def prerequisites(cls):
        url = os.environ.get("WB_TAU2_URL", "http://127.0.0.1:18082")
        missing = []
        if not os.environ.get("WB_TAU2_ADMIN_TOKEN"):
            missing.append("tau2 private world server requires WB_TAU2_ADMIN_TOKEN")
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=3) as response:
                if json.load(response).get("benchmark") != "tau2":
                    raise ValueError("not the Sierra tau2 bridge")
        except Exception as exc:
            missing.append(f"tau2 isolated world server unavailable at {url}: {type(exc).__name__}; run wb_worlds/tau2/server.py with the Sierra git environment")
        python = _source_python()
        if not python.is_file():
            missing.append(f"tau2 independent grader Python missing: {python}; set WB_TAU2_PYTHON")
        return missing

    def _request(self, path, body):
        url = os.environ.get("WB_TAU2_URL", "http://127.0.0.1:18082").rstrip("/")
        token = os.environ.get("WB_TAU2_ADMIN_TOKEN")
        if not token:
            raise RuntimeError("tau2 private administration requires WB_TAU2_ADMIN_TOKEN")
        req = urllib.request.Request(url + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "X-WB-Admin-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"tau2 private operation {path}: {exc.read().decode('utf-8', 'replace')}") from exc

    def interfaces(self):
        return ToolInterfaces({self.service: self._tools + [SEND_MESSAGE]})

    def api_search(self, query, top_k=5):
        def search():
            words = re.findall(r"\w+", query.lower())
            tools = self._tools + [SEND_MESSAGE]
            ranked = sorted(tools, key=lambda t: -sum(w in (t["name"] + " " + t.get("description", "")).lower() for w in words))
            return json.dumps([{"service": self.service, "method": "POST", "path": f"/{self.service}/{t['name']}", **t} for t in ranked[:top_k]])
        return self._observe("api_search", {"query": query, "top_k": top_k}, search)

    def api_fetch(self, method, url, params=None, body=None):
        def call():
            path = urllib.parse.urlsplit(url).path
            if "/admin" in path or path in ("/snapshot", "/evidence", "/create", "/close", "/customer-response", "/agent-event"):
                return _error(403, "private tau2 administration is unavailable to competitors")
            prefix = "/" + self.service + "/"
            if method.upper() != "POST" or not path.startswith(prefix):
                return _error(404, "use the published tau2 POST operations")
            name = path[len(prefix):]
            try:
                arguments = json.loads(body or "{}")
            except (json.JSONDecodeError, TypeError):
                return _error(400, "tool arguments must be valid JSON")
            if not isinstance(arguments, dict):
                return _error(400, "tool arguments must be a JSON object")
            if name == "send_message":
                if set(arguments) != {"message"} or not isinstance(arguments["message"], str):
                    return _error(400, "send_message requires one string message")
                return self.send_message(arguments["message"])
            if name not in {t["name"] for t in self._tools}:
                return _error(404, "unknown tau2 tool")
            return self._request("/call", {"id": self._id, "tool": name, "arguments": arguments})
        return self._observe("api_fetch", {"method": method, "url": url, "params": params, "body": body}, call)

    def base64_encode(self, text):
        return self._observe("base64_encode", {"text": text}, lambda: base64.b64encode(text.encode()).decode())

    def attach_customer(self, callback, participant):
        """The orchestrator supplies its existing reserved provider callback.

        callback({messages, tools, model, max_tokens}) returns content and optional
        tool_calls[{id,name,arguments}], usage, cost_usd. No provider runs here.
        """
        if not callable(callback) or not participant.get("model"):
            raise ValueError("tau2 customer requires a budgeted callback and pinned model")
        if self._customer_callback is not None:
            raise RuntimeError("tau2 customer is already attached")
        self._customer_callback, self._participant = callback, dict(participant)

    def send_message(self, message):
        if self._customer_callback is None:
            raise RuntimeError("tau2 requires the orchestrator's budgeted customer callback before speaking to the customer")
        request = self._request("/message", {"id": self._id, "message": message})
        if request.get("stopped"):
            return json.dumps(request)
        for _ in range(20):
            response = self._customer_callback({**request, "model": self._participant["model"],
                                                "max_tokens": self._participant.get("max_tokens", 2048)})
            if not isinstance(response, dict) or (not response.get("content") and not response.get("tool_calls")):
                raise RuntimeError("tau2 customer callback returned no content or tool calls")
            result = self._request("/customer-response", {"id": self._id, "response": response})
            self.record_agent_event({"type": "simulated_customer", "content": result.get("content"),
                                     "model": self._participant["model"], "usage": response.get("usage"),
                                     "cost_usd": response.get("cost_usd"), "stopped": result["stopped"]})
            if not result["needs_generation"]:
                return json.dumps({"message": result.get("content"), "stopped": result["stopped"]})
            request = self._request("/message", {"id": self._id})
        raise RuntimeError("tau2 customer exceeded 20 tool generations in one conversation turn")

    def snapshot(self):
        return canonical(self._request("/snapshot", {"id": self._id}))

    def set_termination(self, termination):
        """Preserve the harness outcome for the source's own termination gate."""
        self._termination = termination

    def finish(self):
        evidence = self._request("/evidence", {"id": self._id})
        termination = getattr(self, "_termination", "completed")
        evidence["workflowbench_termination"] = termination
        if termination != "completed":
            evidence["termination_reason"] = ("infrastructure_error" if termination.startswith("infra:")
                                                else "timeout" if termination == "timeout" else "agent_error")
        self.snapshot1 = canonical(evidence["snapshot1"])
        if self.artifacts_dir:
            dest = Path(self.artifacts_dir)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "tau2-trajectory.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.snapshot1

    def close(self):
        if not self._closed:
            self._request("/close", {"id": self._id})
            self._closed = True

    def attach_journal(self, directory):
        if self._journal is not None or self.events:
            raise RuntimeError("attach tau2 journal before tool use and only once")
        from wb_results.evidence import AttemptJournal
        self._journal = AttemptJournal(Path(directory), self.snapshot0)

    def record_agent_event(self, entry):
        if self._journal is not None:
            self._journal.agent(entry)
        # The actual domain calls are already recorded by the world; adding arm
        # wrapper tool calls would produce an invalid source replay.
        if entry.get("type") == "tau2_customer_message" and entry.get("content"):
            self._request("/agent-event", {"id": self._id, "content": entry["content"]})

    def _observe(self, tool, arguments, call):
        self.tool_calls.append({"tool": tool, **arguments})
        event = {"sequence": len(self.events), "kind": "tool", "tool": tool, "arguments": arguments,
                 "started_at": datetime.now(timezone.utc).isoformat()}
        self.events.append(event)
        if self._journal is not None:
            self._journal.tool({**event, "status": "running"})
        try:
            result = call()
            event.update(status="completed", result=result)
            return result
        except Exception as exc:
            event.update(status="error", error=str(exc))
            raise
        finally:
            event["finished_at"] = datetime.now(timezone.utc).isoformat()
            if self._journal is not None:
                self._journal.tool(event, self.snapshot if event["status"] == "completed" else None)

    @classmethod
    def positive_check(cls, task, snapshot0, snapshot1, artifacts=None):
        path = _evidence_path(artifacts)
        if path is None or not path.is_file():
            raise FileNotFoundError("tau2-trajectory.json is required for independent strict replay; this attempt is ungraded")
        from wb_worlds.tau2.importer import source_pin, source_root
        expected = task["info"]["world"]
        current = source_pin(source_root(), expected["split"])
        if current != expected:
            raise ValueError("tau2 source version/revision changed since task import; refusing to regrade")
        payload = {"source_ref": {**task["source_ref"], "source_world": expected}, "evidence": json.loads(path.read_text(encoding="utf-8")),
                   "snapshot0": snapshot0, "snapshot1": snapshot1}
        with tempfile.TemporaryDirectory(prefix="wb-tau2-grade-") as temp:
            src, dest = Path(temp) / "input.json", Path(temp) / "reward.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
            env.update(PYTHONUTF8="1", PYTHON_DOTENV_DISABLED="1", LITELLM_LOCAL_MODEL_COST_MAP="True")
            proc = subprocess.run([str(_source_python()), str(Path(__file__).with_name("server.py")), "--grade", str(src), str(dest)],
                                  cwd=source_root(), env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            if proc.returncode != 0:
                raise RuntimeError(f"tau2 independent source checker failed: {proc.stderr[-4000:]}")
            reward = json.loads(dest.read_text(encoding="utf-8"))
        return PositiveResult(passed=reward.get("reward") == 1.0, detail=reward,
                              source="tau2 source reward (ALL, unchanged reward_basis, strict replay)")


def _source_python():
    return Path(os.environ.get("WB_TAU2_PYTHON", ".external/tau2-env/Scripts/python.exe" if os.name == "nt" else ".external/tau2-env/bin/python")).resolve()


def _evidence_path(artifacts):
    if isinstance(artifacts, dict):
        value = artifacts.get("tau2-trajectory.json") or artifacts.get("tau2-trajectory")
        return Path(value) if value else None
    return Path(artifacts) / "tau2-trajectory.json" if artifacts else None


def _error(code, message):
    return json.dumps({"error": {"code": code, "message": message}})
