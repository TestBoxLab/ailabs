"""Private tau2 process. Run this file with the Sierra checkout's isolated Python.

No model is called here. Customer generation is returned as an inference request
to the lab's budgeted provider path. Grading is a separate --grade subprocess.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import threading
import subprocess
import tomllib
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def canonical(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


class WorldService:
    def __init__(self, engine):
        self.engine, self.worlds = engine, {}
        self.lock = threading.RLock()

    def dispatch(self, path, body):
        with self.lock:
            if path == "/create":
                env = self.engine.create(body)
                key = uuid.uuid4().hex
                self.worlds[key] = env
                return {"id": key, **self.engine.describe(env)}
            key = body["id"]
            if path == "/close":
                self.worlds.pop(key, None)
                return {"closed": True}
            env = self.worlds[key]
            if path == "/snapshot":
                return self.engine.snapshot(env)
            if path == "/call":
                return self.engine.call(env, body["tool"], body.get("arguments") or {})
            if path == "/evidence":
                return self.engine.evidence(env)
            if path == "/message":
                return self.engine.customer_request(env, body.get("message"))
            if path == "/customer-response":
                return self.engine.customer_response(env, body["response"])
            if path == "/agent-event":
                self.engine.agent_message(env, body["content"])
                return {"recorded": True}
            raise ValueError(f"unknown private operation {path}")


class SourceEngine:
    def __init__(self):
        from tau2.data_model.tasks import Task
        from tau2.data_model.message import AssistantMessage, ToolCall, UserMessage
        self.Task, self.AssistantMessage, self.ToolCall, self.UserMessage = Task, AssistantMessage, ToolCall, UserMessage

    @staticmethod
    def constructor(domain):
        # Narrow domain imports keep voice/provider integrations out of live work.
        import importlib
        module = importlib.import_module(f"tau2.domains.{domain}.environment")
        return module.get_environment

    def create(self, body):
        domain = body["domain"]
        if domain not in ("retail", "airline", "telecom"):
            raise ValueError(f"unsupported tau2 domain {domain}")
        from tau2.utils import DATA_DIR
        pin = body.get("source_world")
        if pin:
            import tau2
            root = Path(tau2.__file__).resolve().parents[2]
            project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                                      capture_output=True, text=True).stdout.strip()
            dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                                   check=True, capture_output=True, text=True).stdout.strip()
            if dirty or pin.get("package") != "tau2" or project["version"] != pin.get("version") or revision != pin.get("revision"):
                raise ValueError("tau2 live source does not match the frozen version/revision")
        data_files = (("db.toml", "user_db.toml", "main_policy.md", "tech_support_manual.md", "tasks.json", "split_tasks.json")
                      if domain == "telecom" else ("db.json", "tasks.json", "policy.md", "split_tasks.json"))
        for name, expected in body.get("data_hashes", {}).items():
            if name not in data_files:
                raise ValueError("invalid source data reference")
            if hashlib.sha256((DATA_DIR / "tau2/domains" / domain / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"tau2 source data changed: {domain}/{name}")
        task = self.Task.model_validate(body["task"])
        env = self.constructor(domain)(solo_mode=False)
        initial = task.initial_state
        messages = list(initial.message_history or []) if initial else []
        env.set_state(initialization_data=initial.initialization_data if initial else None,
                      initialization_actions=initial.initialization_actions if initial else None,
                      message_history=messages, strict=True)
        from tau2.user.user_simulator import UserSimulator
        from tau2.user.user_simulator_base import is_valid_user_history_message
        user_tools = (env.get_user_tools(include=task.user_tools) or None) if env.user_tools is not None else None
        customer = UserSimulator(llm="budgeted-external-callback", instructions=str(task.user_scenario), tools=user_tools)
        customer_state = customer.get_init_state([m for m in messages if is_valid_user_history_message(m)])
        return {"env": env, "task": task, "domain": domain, "messages": messages,
                "customer": customer, "customer_state": customer_state, "user_stopped": False,
                "snapshot0": self._snapshot(env, domain)}

    def describe(self, state):
        env = state["env"]
        return {"domain": state["domain"], "policy": env.policy,
                "tools": [t.openai_schema["function"] for t in env.get_tools()]}

    @staticmethod
    def _snapshot(env, domain):
        state = {"tau2-" + domain: env.tools.db.model_dump(mode="json") if env.tools is not None else {}}
        if env.user_tools is not None and env.user_tools.db is not None:
            state["tau2-" + domain + "-customer"] = env.user_tools.db.model_dump(mode="json")
        return canonical(state)

    def snapshot(self, state):
        return self._snapshot(state["env"], state["domain"])

    def call(self, state, name, arguments, requestor="assistant"):
        call = self.ToolCall(id=uuid.uuid4().hex, name=name, arguments=arguments, requestor=requestor)
        cls = self.AssistantMessage if requestor == "assistant" else self.UserMessage
        message = cls(role=requestor, tool_calls=[call])
        response = state["env"].get_response(call)
        state["messages"].extend([message, response])
        return response.content

    def agent_message(self, state, content):
        if content:
            message = self.AssistantMessage(role="assistant", content=content)
            state["messages"].append(message)
            state["customer_state"].messages.append(message)

    def customer_request(self, state, message=None):
        if state["user_stopped"]:
            return {"stopped": True, "content": "The simulated customer has ended the conversation."}
        self.agent_message(state, message)
        messages = state["customer_state"].system_messages + state["customer_state"].flip_roles()
        converted = []
        for m in messages:
            entry = {"role": m.role, "content": m.content}
            if m.role == "tool":
                entry["tool_call_id"] = m.id
            if getattr(m, "tool_calls", None):
                entry["tool_calls"] = [{"id": t.id, "type": "function", "function": {"name": t.name, "arguments": json.dumps(t.arguments)}} for t in m.tool_calls]
            converted.append(entry)
        return {"messages": converted, "tools": [t.openai_schema["function"] for t in state["customer"].tools or []]}

    def customer_response(self, state, response):
        calls = [self.ToolCall(id=t.get("id") or uuid.uuid4().hex, name=t["name"], arguments=t["arguments"], requestor="user")
                 for t in response.get("tool_calls") or []]
        message = self.UserMessage(role="user", content=response.get("content"), tool_calls=calls or None,
                                   usage=response.get("usage"), cost=response.get("cost_usd"))
        state["messages"].append(message)
        state["customer_state"].messages.append(message)
        for call in calls:
            result = state["env"].get_response(call)
            state["messages"].append(result)
            state["customer_state"].messages.append(result)
        state["user_stopped"] = state["customer"].is_stop(message)
        return {"content": message.content, "needs_generation": bool(calls), "stopped": state["user_stopped"]}

    def evidence(self, state):
        return {"domain": state["domain"], "task_id": state["task"].id,
                "messages": [m.model_dump(mode="json") for m in state["messages"]],
                "snapshot0": state["snapshot0"], "snapshot1": self.snapshot(state),
                "termination_reason": "user_stop" if state["user_stopped"] else "agent_stop"}


def grade_saved(payload):
    """Strict replay of stored evidence, in a process with no live attempt handle."""
    from pydantic import TypeAdapter
    from tau2.data_model.message import Message
    from tau2.data_model.simulation import SimulationRun
    from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
    engine = SourceEngine()
    ref, evidence = payload["source_ref"], payload["evidence"]
    task = engine.Task.model_validate(ref["task"])
    if evidence.get("task_id") != task.id or evidence.get("domain") != ref["domain"]:
        raise ValueError("tau2 trajectory identifies a different source task or domain")
    if "NL_ASSERTION" in [v.value for v in task.evaluation_criteria.reward_basis]:
        raise ValueError("tau2 paid natural-language judge requires an independently budgeted route")
    state = engine.create(ref)
    if state["snapshot0"] != payload["snapshot0"] or evidence["snapshot0"] != payload["snapshot0"]:
        raise ValueError("tau2 stored initial state does not match the pinned source")
    messages = TypeAdapter(list[Message]).validate_python(evidence["messages"])
    initial = task.initial_state
    state["env"].set_state(initialization_data=initial.initialization_data if initial else None,
                           initialization_actions=initial.initialization_actions if initial else None,
                           message_history=messages, strict=True)
    if engine.snapshot(state) != payload["snapshot1"] or evidence["snapshot1"] != payload["snapshot1"]:
        raise ValueError("tau2 strict replay does not reproduce the stored final snapshot")
    simulation = SimulationRun(id="stored-evidence", task_id=task.id, start_time="stored", end_time="stored",
                               duration=0, termination_reason=evidence["termination_reason"], messages=messages)
    reward = evaluate_simulation(simulation=simulation, task=task, evaluation_type=EvaluationType.ALL,
                                 solo_mode=False, domain=ref["domain"], strict_replay=True)
    return reward.model_dump(mode="json")


def make_server(address, service, token):
    if not token:
        raise ValueError("WB_TAU2_ADMIN_TOKEN is required for the private tau2 server")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"benchmark": "tau2", "ready": True})
            else:
                self.reply(404, {"error": "not found"})

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("X-WB-Admin-Token", ""), token):
                return self.reply(403, {"error": "private world administration"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8_000_000:
                    return self.reply(413, {"error": "invalid request size"})
                result = service.dispatch(self.path, json.loads(self.rfile.read(length)))
                self.reply(200, result)
            except Exception as exc:
                self.reply(400, {"error": str(exc)})

        def reply(self, status, body):
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18082)
    parser.add_argument("--grade", nargs=2, metavar=("INPUT", "OUTPUT"))
    args = parser.parse_args()
    if args.grade:
        source, dest = map(Path, args.grade)
        result = grade_saved(json.loads(source.read_text(encoding="utf-8")))
        dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    else:
        make_server((args.host, args.port), WorldService(SourceEngine()), os.environ.get("WB_TAU2_ADMIN_TOKEN", "")).serve_forever()
