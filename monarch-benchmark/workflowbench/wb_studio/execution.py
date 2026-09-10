"""Compile published node definitions into executable steps and run them.

A published version is a directed acyclic graph. Execution binds to the version
hash and to the hash of every product graph version the graph references
(a prepared, immutable knowledge artifact; see ``product_graphs``).

Step semantics at run time, in topological order:

    input         the task brief and system prompt
    product-graph the records of a prepared product graph version, delivered to
                  agents directly connected to it
    agent         one agent loop; ``mode`` "act" executes tools against the
                  episode world, "advise" answers in text only
    merge         the joined outputs of its direct predecessors
    output        the final answer: the joined outputs of its predecessors
    monarch       never executed here; a stock adapter is a separate track
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import re

from wb_arms import runtime_manifest as rm
from wb_arms.api_loop import ArmResult
from wb_studio.agents import episode_executor, run_loop
from wb_studio.workflows import WORKFLOW_GUIDE, discovery_executor, execute_workflow
from wb_studio.product_graphs import load_version as load_graph_version, render

RUNTIME_KINDS = {"input", "product-graph", "agent", "merge", "workflow", "output"}


def version_path(studio, identity: str, number: int, suffix: str = ".json") -> Path:
    return Path(studio.directory) / "blueprints" / identity / f"v{number:04d}{suffix}"


def load_version(studio, identity: str, number: int) -> dict:
    path = version_path(studio, identity, number)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", str(identity)) or type(number) is not int or not path.is_file():
        raise ValueError("Unknown architecture version")
    return json.loads(path.read_text(encoding="utf-8"))


def compile_version(version: dict) -> dict:
    """Steps in execution order with their direct and transitive dependencies."""
    from wb_studio.runtime_registry import resolve_api_control
    graph = version["graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    incoming = {i: [] for i in nodes}
    for edge in graph["edges"]:
        incoming[edge["to"]].append(edge["from"])
    order = version.get("order") or list(nodes)
    ancestors = {}
    for node_id in order:
        seen = set()
        for parent in incoming[node_id]:
            seen.add(parent)
            seen |= ancestors.get(parent, set())
        ancestors[node_id] = seen
    problems, steps = [], []
    for node_id in order:
        node = nodes[node_id]
        kind = node["type"]
        if kind not in RUNTIME_KINDS:
            problems.append({"node": node_id, "message": f"{node['label']}: {kind} steps are not executed by the node runtime; a stock Monarch adapter is a separate track."})
        runner = None
        if kind == "agent":
            runner = resolve_api_control((node.get("config") or {}).get("runner") or {})
            if runner is None:
                problems.append({"node": node_id, "message": f"{node['label']}: its runner has no rate-carded API control; choose a catalogued model."})
        steps.append({"id": node_id, "type": kind, "label": node["label"], "config": node.get("config") or {},
                      "upstream": list(incoming[node_id]), "ancestors": sorted(ancestors[node_id]), "runner": runner})
    return {"version_id": version.get("id"), "version": version.get("version"), "sha256": version.get("sha256"),
            "order": list(order), "steps": steps, "problems": problems,
            "graph_steps": [s["id"] for s in steps if s["type"] == "product-graph"]}


def bound_graphs(studio, version: dict) -> dict:
    """The product graph versions a published architecture references, by step id; missing ones are absent."""
    bound = {}
    for node in version["graph"]["nodes"]:
        if node.get("type") != "product-graph":
            continue
        config = node.get("config") or {}
        try:
            bound[node["id"]] = load_graph_version(studio, config.get("graph"), config.get("version"))
        except ValueError:
            pass
    return bound


def bind_comparison_model(version, runner):
    """Bind every experimental agent to the selected model without changing the published version."""
    from copy import deepcopy
    bound = deepcopy(version)
    for node in bound['graph']['nodes']:
        if node['type'] == 'agent':
            node.setdefault('config', {})['runner'] = dict(runner)
    bound['source_sha256'] = version['sha256']
    bound['sha256'] = rm.sha256_json({'graph': bound['graph'], 'track': bound.get('track', 'agentic-request')})
    return bound


def execution_manifest(version: dict, graphs: dict) -> dict:
    """What a run of this version binds to: the graph hash and every referenced product graph version."""
    pinned = {step: {"graph": g["id"], "version": g["version"], "sha256": g["sha256"]} for step, g in sorted(graphs.items())}
    knowledge = rm.sha256_json({step: g["sha256"] for step, g in pinned.items()}) if pinned else None
    artifacts = {"graph": {"status": "present", "sha256": version["sha256"]}}
    if pinned:
        artifacts["product_graphs"] = {"status": "present", "sha256": knowledge, "versions": pinned}
    return {"version": f"blueprint.{version['id']}.v{version['version']}", "graph_sha256": version["sha256"],
            "knowledge_sha256": knowledge, "artifacts": artifacts,
            "identity_sha256": rm.sha256_json({"graph": version["sha256"], "knowledge": knowledge})}


class ArchitectureArm:
    """Runs one published version on one task, step by step, on the episode world."""
    provider_key = None
    message_evidence = "normalized"

    def __init__(self, studio, identity: str, arm_id: str, task_id: str, cancel, maximum: Decimal, version: dict, graphs: dict, config: dict):
        self.studio, self.identity, self.name, self.task_id = studio, identity, arm_id, task_id
        self.cancel, self.maximum, self.version, self.graphs, self.config = cancel, maximum, version, graphs or {}, config
        self.plan = compile_version(version)
        self.output = ""
        self.sequence = 0
        self.step = None

    def emit(self, kind, **data):
        return self.studio.emit(self.identity, kind, model=self.name, task=self.task_id, **data)

    def _system(self, ep, step: dict, outputs: dict) -> str:
        by_id = {s["id"]: s for s in self.plan["steps"]}
        parts = [ep.task["prompt"][0]["content"]]
        if self.config.get("prompt"):
            parts.append("Experiment instructions:\n" + self.config["prompt"])
        for ancestor in self.plan["order"]:
            if ancestor in step["upstream"] and by_id[ancestor]["type"] == "product-graph" and self.graphs.get(ancestor):
                parts.append(render(self.graphs[ancestor]))
        instructions = str(step["config"].get("instructions", "")).strip()
        if instructions:
            parts.append(f"Your role in this step ('{step['label']}'):\n" + instructions)
        if step["config"].get("mode") == "advise":
            parts.append("You cannot call tools in this step. Answer in text only; a later step acts on your answer.")
        if self.version.get("track") == "create-and-run":
            parts.append(WORKFLOW_GUIDE)
        # Reusable instructions precede per-attempt outputs for prefix caching.
        for parent in step["upstream"]:
            if by_id[parent]["type"] not in ("input", "product-graph") and outputs.get(parent):
                parts.append(f"Output of the previous step '{by_id[parent]['label']}':\n" + outputs[parent])
        return "\n\n".join(parts)

    def run(self, ep, deadline=None) -> ArmResult:
        if self.plan["problems"]:
            raise ValueError("; ".join(p["message"] for p in self.plan["problems"]))
        original = ep._observe

        def observe(tool, arguments, call):
            node = f"{self.step}:tool-{self.sequence}"
            self.sequence += 1
            self.emit("node_started", node=node, label=tool, arguments=arguments, step=self.step)
            try:
                value = original(tool, arguments, call)
                self.emit("node_finished", node=node, label=tool, output=value, status="completed", step=self.step)
                return value
            except Exception:
                self.emit("node_finished", node=node, label=tool, output="Tool failed; inspect the retained trace.", status="error", step=self.step)
                raise
        ep._observe = observe
        total = ArmResult()
        outputs, final = {}, ""
        by_id = {s["id"]: s for s in self.plan["steps"]}
        for step in self.plan["steps"]:
            kind = step["type"]
            if kind == "input":
                outputs[step["id"]] = ep.task["prompt"][1]["content"]
                self.emit("step_finished", step=step["id"], label=step["label"], status="completed", output=outputs[step["id"]])
                continue
            self.step = step["id"]
            self.emit("step_started", step=step["id"], label=step["label"], step_type=kind)
            if kind == "product-graph":
                graph = self.graphs.get(step["id"])
                receivers = [s["label"] for s in self.plan["steps"] if step["id"] in s["upstream"]]
                delivered = (f"Delivered {len(graph['records'])} products × {len(graph['fields'])} fields from '{graph['name']}' v{graph['version']} "
                             f"({', '.join(f['path'] for f in graph['fields'])}) to " + (", ".join(receivers) or "no step")) if graph else "No prepared product graph version is bound to this step."
                self.emit("step_finished", step=step["id"], label=step["label"], status="completed" if graph else "error", output=delivered)
                if not graph:
                    total.termination, total.error = "error", f"{step['label']}: no prepared product graph version"
                    break
                continue
            if kind == "workflow" or (kind == "output" and self.version.get("track") == "create-and-run" and not any(s["type"] == "workflow" for s in self.plan["steps"])):
                authored = "\n\n".join(outputs[p] for p in step["upstream"] if outputs.get(p))
                result = execute_workflow(authored, execute=self.studio.component(self.identity, "action_builder")(ep),
                                          emit=self.emit, record=ep.record_agent_event, cancel=self.cancel, deadline=deadline)
                outputs[step["id"]] = result.final_text or ""
                if kind == "output":
                    final = result.final_text or ""
                total.tool_calls += result.tool_calls
                self.emit("step_finished", step=step["id"], label=step["label"], status="completed" if result.termination == "completed" else "error", output=result.final_text or result.error)
                if result.termination != "completed":
                    total.termination, total.error = result.termination, result.error
                    break
                continue
            if kind == "merge":
                outputs[step["id"]] = "\n\n".join(outputs[p] for p in step["upstream"] if outputs.get(p))
                self.emit("step_finished", step=step["id"], label=step["label"], status="completed", output=outputs[step["id"]])
                continue
            if kind == "output":
                final = "\n\n".join(outputs[p] for p in step["upstream"] if outputs.get(p))
                self.emit("step_finished", step=step["id"], label=step["label"], status="completed", output=final)
                continue
            mode = step["config"].get("mode", "act")
            gateway = self.studio.gateway_for(step["config"]["runner"], with_tools=mode != "advise")
            self.emit("step_runner", step=step["id"], runner=gateway.describe())
            execute = self.studio.component(self.identity, "action_builder")(ep)
            if self.version.get("track") == "create-and-run":
                execute = discovery_executor(execute)
            for source in step["upstream"]:
                if source in self.graphs:
                    self.emit("knowledge_delivered", step=step["id"], source=source,
                              label=self.graphs[source].get("name","Product knowledge"),
                              products=len(self.graphs[source].get("records",{})))
            result = self.studio.component(self.identity, "brain")(gateway, system=self._system(ep, step, outputs), brief=ep.task["prompt"][1]["content"],
                              execute_tool=execute, emit=self.emit, scope_id=self.identity, scope_limit_usd=self.maximum,
                              request_prefix=f"{self.identity}-{self.task_id}-{self.name}-{step['id']}",
                              max_turns=int(step["config"].get("max_turns") or self.config.get("max_turns", 20)),
                              cancel=self.cancel, deadline=deadline, step=step["id"], record=ep.record_agent_event, budget=self.studio.budget)
            total.turns += result.turns
            total.tool_calls += result.tool_calls
            total.tokens_prompt += result.tokens_prompt
            total.tokens_cached += result.tokens_cached
            total.tokens_cache_write += result.tokens_cache_write
            total.tokens_output += result.tokens_output
            total.cost_usd += result.cost_usd
            total.flags += [f for f in result.flags if f not in total.flags]
            total.turn_log += result.turn_log
            outputs[step["id"]] = result.final_text or ""
            self.emit("step_finished", step=step["id"], label=step["label"], status="completed" if result.termination == "completed" else "error",
                      output=result.final_text or result.error)
            if result.termination != "completed":
                total.termination, total.error = result.termination, f"{step['label']}: {result.error}"
                break
        self.output = final or next((outputs[s["id"]] for s in reversed(self.plan["steps"]) if outputs.get(s["id"])), "")
        total.final_text = self.output
        return total
