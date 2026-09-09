"""Gateways, the shared agent loop, and executable architectures, all offline."""
from decimal import Decimal
import json

import pytest

from wb_arms.api_loop import InfraError
from wb_orchestrator.budget import BudgetLedger
from wb_studio import blueprints, execution, product_graphs
from wb_studio.app import ROOT, Studio
from wb_studio.gateways import GatewayError, GeminiGateway, ProviderGateway, ceiling_cost, resolve_effort
from wb_studio.runtime_registry import api_controls, resolve_api_control
from wb_world.episode import load_suite


class FakeAdapter:
    """Scripted provider adapter: one tool call, then a final answer; usage optional."""
    def __init__(self, provider, tools, *, usage=True, fail=None, answer="Worker finished the request."):
        self.provider, self.tools, self.usage, self.fail, self.answer = provider, tools, usage, fail, answer
        self.effort = "unset"
        self.calls = 0
        self.history = []

    def start(self, system, brief):
        self.system = system
        return [{"role": "system", "content": system}, {"role": "user", "content": brief}]

    def turn(self, messages, timeout=None):
        self.calls += 1
        if self.fail:
            raise self.fail
        tokens = {"prompt_tokens": 100, "cached_tokens": 20, "output_tokens": 30, "cache_write_tokens": 5} if self.usage else {"prompt_tokens": 0, "cached_tokens": 0, "output_tokens": 0}
        if self.calls == 1 and self.tools:
            messages.append({"role": "assistant", "tool_calls": [{"id": "c1"}]})
            return {"text": None, "tool_calls": [{"id": "c1", "name": "base64_encode", "args": {"text": "hello"}}], "cache_source": "x", **tokens}
        messages.append({"role": "assistant", "content": self.answer})
        return {"text": self.answer, "tool_calls": [], "cache_source": "x", **tokens}

    def append_tool_result(self, messages, call, result):
        self.history.append((call["id"], result))
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})


class FakeGemini:
    """Scripted Gemini control: api_search while preparing knowledge, base64 tool otherwise."""
    def __init__(self, ledger, model):
        assert model == "gemini-3.7-flash"
        self.ledger, self.thinking_level, self.requests = ledger, None, []

    def request(self, contents, system, tools, *, scope_id, scope_limit_usd, request_id):
        self.requests.append({"contents": json.loads(json.dumps(contents)), "system": system, "tools": tools})
        self.ledger.reserve(request_id, "0.01", scope_id=scope_id, scope_limit_usd=scope_limit_usd)
        self.ledger.claim(request_id)
        self.ledger.settle(request_id, "0.01")
        preparing = "prepare reusable product knowledge" in system
        answered = any("functionResponse" in p for c in contents for p in c["parts"])
        if not answered and tools:
            call = {"id": "g1", "name": "api_search" if preparing else "base64_encode", "args": {"query": "salesforce"} if preparing else {"text": "visible"}}
            parts = [{"functionCall": call}]
        elif preparing:
            parts = [{"text": json.dumps({"gmail": {"summary": "Mail service", "risk": 2}, "salesforce": {"summary": "CRM records", "risk": 4}, "zendesk": {"summary": "x"}})}]
        else:
            parts = [{"text": "Worker done: " + ("with plan" if "Output of the previous step" in system else "alone")}]
        return {"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "thoughtsTokenCount": 2, "totalTokenCount": 16},
                "_billing": {"actual_usd": "0.01"}}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    for name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FIREWORKS_API_KEY"):
        monkeypatch.setenv(name, "offline-placeholder")
    adapters = []
    def adapter_factory(provider, tools):
        adapters.append(FakeAdapter(provider, tools))
        return adapters[-1]
    app = Studio(tmp_path / "studio", tasks=load_suite(ROOT / "tasks")[:1], gateway_factory=FakeGemini, adapter_factory=adapter_factory)
    app.adapters = adapters
    return app


def node(identity, kind, x=0, **config):
    return {"id": identity, "type": kind, "label": identity.title(), "x": x, "y": 100, "config": config}


def edges(*pairs):
    return [{"from": a, "to": b} for a, b in pairs]


def publish(studio, name, graph):
    draft = blueprints.save_draft(studio, {"id": name, "name": name, "graph": graph})
    return blueprints.publish(studio, {"id": name, "revision": draft["revision"]})


# ---------------------------------------------------------------- gateways

def test_provider_gateway_reserves_claims_settles_each_turn_and_applies_effort(tmp_path):
    ledger = BudgetLedger(tmp_path / "b.sqlite")
    made = []
    gateway = ProviderGateway(ledger, "claude-opus-5", "medium", adapter_factory=lambda p, t: made.append(FakeAdapter(p, t)) or made[-1])
    messages = gateway.start("system", "brief")
    assert made[0].effort == "medium" and [t["name"] for t in made[0].tools] == ["api_search", "api_fetch", "base64_encode"]
    first = gateway.turn(messages, scope_id="run", scope_limit_usd=Decimal("5"), request_id="r1")
    assert first["tool_calls"][0]["name"] == "base64_encode"
    billing = first["_billing"]
    assert billing["status"] == "estimated_from_usage" and Decimal(billing["maximum_usd"]) > Decimal(billing["actual_usd"]) > 0
    # 100 prompt (20 cached, 5 cache-write, 75 uncached) + 30 output at the Opus 5 card.
    assert billing["actual_usd"] == "0.001167"
    assert ledger.status().held_usd == 0 and ledger.status().actual_usd == Decimal("0.001167")
    gateway.append_tool_result(messages, first["tool_calls"][0], "aGVsbG8=")
    second = gateway.turn(messages, scope_id="run", scope_limit_usd=Decimal("5"), request_id="r2")
    assert second["text"].startswith("Worker finished") and made[0].history == [("c1", "aGVsbG8=")]
    assert ledger.status().actual_usd == Decimal("0.002334")


def test_provider_failure_is_sanitized_and_keeps_its_hold(tmp_path):
    ledger = BudgetLedger(tmp_path / "b.sqlite")
    boom = InfraError("infra:rate_limit", "429 from https://api.example/v1?key=sk-secret")
    gateway = ProviderGateway(ledger, "gpt-5.6-sol", "high", adapter_factory=lambda p, t: FakeAdapter(p, t, fail=boom))
    messages = gateway.start("s", "b")
    with pytest.raises(GatewayError) as error:
        gateway.turn(messages, scope_id="run", scope_limit_usd=Decimal("5"), request_id="r1")
    assert "sk-secret" not in str(error.value) and "rate_limit" in str(error.value)
    assert ledger.status().held_usd > 0


def test_unknown_usage_keeps_the_maximum_held(tmp_path):
    ledger = BudgetLedger(tmp_path / "b.sqlite")
    gateway = ProviderGateway(ledger, "kimi-k3-fireworks", "default", with_tools=False, adapter_factory=lambda p, t: FakeAdapter(p, t, usage=False))
    assert gateway.tools == [] and gateway.effort is None
    reply = gateway.turn(gateway.start("s", "b"), scope_id="run", scope_limit_usd=Decimal("5"), request_id="r1")
    assert reply["_billing"]["status"] == "unknown_hold" and reply["_billing"]["actual_usd"] is None
    assert ledger.status().held_usd == Decimal(reply["_billing"]["maximum_usd"])


@pytest.mark.parametrize("key,effort,fragment", [("gpt-5.6-sol", "max", "low, medium, high, xhigh"), ("kimi-k3-fireworks", "high", "no reasoning-effort"), ("gemini-3.7-flash", "xhigh", "low, medium, high")])
def test_efforts_the_api_does_not_accept_are_refused(key, effort, fragment):
    from wb_arms import providers
    with pytest.raises(ValueError, match=fragment):
        resolve_effort(providers.get(key), effort)


def test_ceiling_cost_uses_the_dearest_input_rate_and_rounds_up():
    from wb_arms import providers
    assert ceiling_cost(providers.get("claude-opus-5"), 1_000_000, 0) == Decimal("6.25")      # cache-write rate beats input
    assert ceiling_cost(providers.get("gpt-5.6-terra"), 1, 1) == Decimal("0.000014")


def test_gemini_gateway_merges_tool_results_into_one_user_turn(tmp_path):
    ledger = BudgetLedger(tmp_path / "b.sqlite")
    fake = FakeGemini(ledger, "gemini-3.7-flash")
    gateway = GeminiGateway(fake, "high")
    assert fake.thinking_level == "high"
    contents = gateway.start("s", "b")
    reply = gateway.turn(contents, scope_id="run", scope_limit_usd=Decimal("5"), request_id="r1")
    assert reply["output_tokens"] == 6 and reply["tool_calls"][0]["id"] == "g1"
    gateway.append_tool_result(contents, reply["tool_calls"][0], "one")
    gateway.append_tool_result(contents, {"id": "g2", "name": "base64_encode"}, "two")
    assert [p["functionResponse"]["response"]["result"] for p in contents[-1]["parts"]] == ["one", "two"]


def test_every_rate_carded_model_is_a_catalogued_api_control():
    controls = api_controls()
    assert {"claude-opus-5", "gpt-5.6-sol", "gemini-3.7-flash", "kimi-k3-fireworks", "glm-5.3-fireworks", "kimi-k3", "glm-5.3", "gpt-5.6-terra", "claude-opus-4-8"} <= set(controls)
    assert controls["kimi-k3-fireworks"]["provider"] == "fireworks" and controls["kimi-k3-fireworks"]["efforts"] == []
    assert resolve_api_control({"provider": "fireworks", "model": "accounts/fireworks/models/kimi-k3"})["key"] == "kimi-k3-fireworks"
    assert resolve_api_control({"provider": "anthropic", "model": "claude-opus-5"})["key"] == "claude-opus-5"
    assert resolve_api_control({"provider": "fireworks", "model": "accounts/fireworks/models/unpriced"}) is None


# ------------------------------------------------------------- execution

def planner_worker_graph():
    return {"nodes": [node("input", "input"), node("planner", "agent", 300, mode="advise", instructions="Plan the work. Verify the record before writing.", runner={"provider": "anthropic", "model": "claude-opus-5", "effort": "medium"}),
                      node("worker", "agent", 450, instructions="Do the work.", runner={"provider": "gemini", "model": "gemini-3.7-flash", "effort": "low"}),
                      node("output", "output", 600)],
            "edges": edges(("input", "planner"), ("planner", "worker"), ("worker", "output"))}


def test_run_budget_below_the_first_request_reservation_is_refused_before_any_job(studio):
    from wb_studio.gateways import request_ceiling
    gemini = request_ceiling("gemini-3.7-flash")
    assert Decimal("1.00") < gemini < Decimal("1.20")            # 1M-token input ceiling plus thinking and candidate caps
    assert request_ceiling("claude-opus-5") == Decimal("0.4375")   # 6000 input at the cache-write rate + 16000 output
    with pytest.raises(ValueError, match="Run budget too low"):
        studio.create({"architectures": ["without-monarch"], "models": ["gemini-3.7-flash@low"], "tasks": list(studio.tasks), "maximum_usd": "0.50"}, start=False)
    publish(studio, "planner", planner_worker_graph())
    with pytest.raises(ValueError, match="reserves up to"):
        studio.create({"architectures": ["blueprint.planner.v1"], "tasks": list(studio.tasks), "maximum_usd": "0.90"}, start=False)
    assert studio.jobs() == []
    job = studio.create({"architectures": ["blueprint.planner.v1"], "tasks": list(studio.tasks), "maximum_usd": "1.10"}, start=False)
    assert job["settings"]["arms"][0]["request_ceiling_usd"] == str(gemini)


def test_published_planner_worker_architecture_is_ready_and_executes_step_by_step(studio):
    version = publish(studio, "planner", planner_worker_graph())
    assert version["readiness"]["runtime"] == "ready" and version["readiness"]["launchable"] is True
    arm = f"blueprint.planner.v{version['version']}"
    job = studio.create({"request_id": "run-1", "architectures": [arm], "tasks": list(studio.tasks), "maximum_usd": "2.00"}, start=False)
    assert job["settings"]["models"] == [arm] and job["settings"]["arms"][0]["kind"] == "version"
    assert job["execution_manifests"][arm]["graph_sha256"] == version["sha256"]
    studio.execute(job["id"])
    done = studio.job(job["id"])
    assert done["status"] == "completed", done
    result = done["results"][0]
    assert result["output"] == "Worker done: with plan"
    assert result["tool_calls"] == 1 and result["cost_usd"] == pytest.approx(0.02 + 0.001167)
    planner = studio.adapters[0]
    assert planner.tools == [] and planner.effort == "medium"
    assert "Your role in this step" in planner.system and "Verify the record" in planner.system and "Instructions from" not in planner.system
    assert "You cannot call tools in this step" in planner.system
    events = studio.events(job["id"])
    steps = [(e["step"], e["status"]) for e in events if e["type"] == "step_finished"]
    assert steps == [("input", "completed"), ("planner", "completed"), ("worker", "completed"), ("output", "completed")]
    assert all(e.get("step") == "worker" for e in events if e["type"] in ("node_started", "node_finished"))
    assert [e["runner"]["adapter"] for e in events if e["type"] == "step_runner"] == ["anthropic", "gemini"]


def test_without_monarch_and_a_version_run_side_by_side_with_distinct_arms(studio):
    publish(studio, "planner", planner_worker_graph())
    job = studio.create({"request_id": "run-2", "architectures": ["without-monarch", "blueprint.planner.v1"], "models": ["oracle", "claude-opus-5@high"],
                         "tasks": list(studio.tasks), "maximum_usd": "3.00"}, start=False)
    assert job["settings"]["models"] == ["oracle", "claude-opus-5@high", "blueprint.planner.v1"]
    assert job["total"] == 3
    studio.execute(job["id"])
    done = studio.job(job["id"])
    assert done["status"] == "completed", done
    by_arm = {r["model"]: r for r in done["results"]}
    assert by_arm["oracle"]["passed"] is True
    assert by_arm["claude-opus-5@high"]["output"].startswith("Worker finished")
    assert by_arm["blueprint.planner.v1"]["output"] == "Worker done: with plan"


def test_without_monarch_needs_a_runner_and_rejects_unpriced_or_wrong_effort_runners(studio):
    with pytest.raises(ValueError, match="at least one runner"):
        studio.create({"architectures": ["without-monarch"], "tasks": list(studio.tasks)}, start=False)
    with pytest.raises(ValueError, match="accepts no reasoning-effort"):
        studio.create({"architectures": ["without-monarch"], "models": ["kimi-k3-fireworks@high"], "tasks": list(studio.tasks)}, start=False)
    with pytest.raises(ValueError, match="Unknown runner"):
        studio.create({"architectures": ["without-monarch"], "models": ["not-a-model"], "tasks": list(studio.tasks)}, start=False)
    assert studio.jobs() == []


CATALOG_FIELDS = [{"path": "product.summary", "type": "string", "description": "What the product does"}, {"path": "product.risk", "type": "number", "description": "Write risk 1-5"}]
GEMINI = {"provider": "gemini", "model": "gemini-3.7-flash", "effort": "low"}


def save_catalog(studio, fields, revision=0, **extra):
    return product_graphs.save_draft(studio, {"id": "catalog", "name": "Catalog", "fields": fields, "runner": GEMINI, "instructions": "Describe every product.", "revision": revision, **extra})


def knowledge_graph(version=1):
    return {"nodes": [node("input", "input"), node("knowledge", "product-graph", 150, graph="catalog", version=version),
                      node("worker", "agent", 450, instructions="Do the work.", runner=GEMINI), node("output", "output", 600)],
            "edges": edges(("input", "worker"), ("knowledge", "worker"), ("worker", "output"))}


def test_product_graph_is_prepared_once_and_its_records_flow_into_scored_attempts(studio):
    version = publish(studio, "informed", knowledge_graph())
    assert version["readiness"]["runtime"] == "preparation_required" and "no version 1" in version["readiness"]["reasons"][0]
    with pytest.raises(ValueError, match="cannot launch yet"):
        studio.create({"architectures": ["blueprint.informed.v1"], "tasks": list(studio.tasks)}, start=False)
    draft = save_catalog(studio, CATALOG_FIELDS)
    assert draft["revision"] == 1 and draft["runner"]["model"] == "gemini-3.7-flash"
    work = product_graphs.plan(studio, "catalog")
    assert work["version"] == 1 and work["parent_version"] is None and [f["path"] for f in work["to_research"]] == ["product.summary", "product.risk"]
    graph = product_graphs.prepare(studio, "catalog", maximum_usd="2.00", revision=1)
    assert graph["status"] == "complete" and graph["products"] == ["gmail", "salesforce"] and graph["version"] == 1
    assert graph["records"] == {"gmail": {"product.summary": "Mail service", "product.risk": 2}, "salesforce": {"product.summary": "CRM records", "product.risk": 4}}
    assert graph["problems"] == ["Ignored products outside the corpus: zendesk"] and graph["tool_calls"] == 1
    assert [f["since"] for f in graph["fields"]] == [1, 1]
    assert Decimal(graph["cost_usd"]) == Decimal("0.02") and Decimal(studio.budget()["actual"]) >= Decimal("0.02")
    assert product_graphs.load_version(studio, "catalog", 1)["sha256"] == graph["sha256"]
    with pytest.raises(ValueError, match="Nothing new to research"):
        product_graphs.prepare(studio, "catalog", maximum_usd="2.00")     # immutable: a second dispatch needs a schema change
    events = json.loads((studio.directory / "product-graphs" / "catalog" / "v0001.events.jsonl").read_text().splitlines()[0])
    assert events["type"] == "step_started" and events["step_type"] == "product-graph" and events["fields"] == ["product.summary", "product.risk"]
    listed = product_graphs.listing(studio)[0]
    assert listed["name"] == "Catalog" and listed["versions"][0]["status"] == "complete" and "final_text" not in listed["versions"][0]
    from wb_studio.runtime_registry import versions
    row = {v["id"]: v for v in versions(studio)}["blueprint.informed.v1"]
    assert row["readiness"]["runtime"] == "ready" and row["graphs"]["knowledge"]["sha256"] == graph["sha256"] and row["graphs"]["knowledge"]["products"] == 2
    job = studio.create({"request_id": "run-3", "architectures": ["blueprint.informed.v1"], "tasks": list(studio.tasks), "maximum_usd": "2.00"}, start=False)
    manifest = job["execution_manifests"]["blueprint.informed.v1"]
    assert manifest["artifacts"]["product_graphs"]["versions"]["knowledge"]["sha256"] == graph["sha256"] and manifest["knowledge_sha256"] == row["knowledge_sha256"]
    studio.execute(job["id"])
    done = studio.job(job["id"])
    assert done["status"] == "completed", done
    steps = [(e["step"], e["status"], e.get("output", "")) for e in studio.events(job["id"]) if e["type"] == "step_finished" and e["step"] != "input"]
    assert steps[0][0] == "knowledge" and steps[0][1] == "completed" and steps[0][2].startswith("Delivered 2 products × 2 fields from 'Catalog' v1 (product.summary, product.risk) to Worker")
    evidence = sorted((studio.directory / job["id"] / "evidence").rglob("*.jsonl"))
    joined = "\n".join(p.read_text(encoding="utf-8") for p in evidence)
    assert "Product graph 'Catalog' v1" in joined and "salesforce: summary: CRM records" in joined


def test_extending_a_product_graph_researches_only_the_new_fields_and_carries_the_rest(studio):
    save_catalog(studio, CATALOG_FIELDS)
    first = product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    save_catalog(studio, CATALOG_FIELDS + [{"path": "product.owner", "type": "string", "description": "Team that owns it"}], revision=1)
    work = product_graphs.plan(studio, "catalog")
    assert work["version"] == 2 and work["parent_version"] == 1 and [f["path"] for f in work["new"]] == ["product.owner"] and len(work["carried"]) == 2
    second = product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    assert second["version"] == 2 and second["parent_version"] == 1 and second["researched"] == ["product.owner"] and second["carried"] == ["product.risk", "product.summary"]
    # The scripted model never answers the new field: the carried values survive, the version is honest about the gap.
    assert second["status"] == "incomplete" and "gmail: product.owner missing." in second["problems"]
    assert second["records"]["salesforce"] == {"product.summary": "CRM records", "product.risk": 4}
    assert [(f["path"], f["since"]) for f in second["fields"]] == [("product.summary", 1), ("product.risk", 1), ("product.owner", 2)]
    assert second["sha256"] != first["sha256"] and product_graphs.usable(second)
    version = publish(studio, "informed", knowledge_graph(2))
    assert version["readiness"]["runtime"] == "ready"


def test_failed_preparation_is_recorded_blocks_launch_and_can_be_retried(studio):
    save_catalog(studio, CATALOG_FIELDS)
    class Broken(FakeGemini):
        def request(self, contents, system, tools, **kw):
            raise RuntimeError("provider down key=fixture-secret-token")
    working, studio.gateway_factory = studio.gateway_factory, Broken
    failed = product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    assert failed["status"] == "failed" and failed["records"] == {} and "fixture-secret-token" not in json.dumps(failed)
    from wb_studio.runtime_registry import blueprint_readiness
    state = blueprint_readiness(studio, publish(studio, "informed", knowledge_graph()))
    assert state["readiness"]["runtime"] == "preparation_required" and "failed" in state["readiness"]["reasons"][0]
    studio.gateway_factory = working
    retried = product_graphs.prepare(studio, "catalog", maximum_usd="2.00")
    assert retried["version"] == 1 and retried["status"] == "complete"
    assert blueprint_readiness(studio, execution.load_version(studio, "informed", 1))["readiness"]["runtime"] == "ready"


def test_preparation_budget_below_the_first_request_reservation_is_refused_before_any_claim(studio):
    save_catalog(studio, CATALOG_FIELDS)
    with pytest.raises(ValueError, match="Preparation budget too low"):
        product_graphs.prepare(studio, "catalog", maximum_usd="0.50")
    graph_dir = studio.directory / "product-graphs" / "catalog"
    assert not list(graph_dir.glob("v*")) and Decimal(studio.budget()["actual"]) == 0
    assert product_graphs.request_floor(GEMINI) > Decimal("1")


def test_parse_knowledge_types_and_missing_fields():
    fields = [{"path": "product.summary", "type": "string"}, {"path": "product.risk", "type": "number"}]
    knowledge, problems = product_graphs.parse_knowledge('```json\n{"gmail": {"summary": "x", "risk": "high"}}\n```', ["gmail", "slack"], fields)
    assert knowledge == {"gmail": {"product.summary": "x"}}
    assert problems == ["gmail: product.risk is not a number.", "No record for slack."]
    assert product_graphs.parse_knowledge("not json", ["gmail"], fields) == ({}, ["The preparation answer was not a JSON object."])


def test_product_graph_drafts_are_validated():
    with pytest.raises(ValueError, match="look like product.summary"):
        product_graphs.validate_fields([{"path": "bad path", "type": "string"}])
    with pytest.raises(ValueError, match="Duplicate field"):
        product_graphs.validate_fields([{"path": "product.a", "type": "string"}, {"path": "product.a", "type": "number"}])
    assert product_graphs.validate_fields([{"path": " product.a ", "type": "string", "description": " x "}]) == [{"path": "product.a", "type": "string", "description": "x"}]


def test_monarch_nodes_never_execute_and_are_reported_before_launch(studio, monkeypatch):
    monkeypatch.setattr(blueprints, "default_status", lambda s, refresh=False: {"id": "default-monarch-enterprise", "repository": "https://github.com/TestBoxLab/monarch", "directory": "monarch-enterprise", "commit": "a" * 40})
    graph = {"nodes": [node("input", "input"), node("monarch", "monarch", 300, runner={"provider": "bedrock", "model": "claude-opus-4-8", "effort": "default"}), node("output", "output", 600)],
             "edges": edges(("input", "monarch"), ("monarch", "output"))}
    with pytest.raises(ValueError, match="separate reference implementation"):
        publish(studio, "stock", graph)
    assert blueprints.listing(studio)[0]["versions"] == []
    # Historical definitions still receive a concrete unsupported-node diagnostic.
    plan = execution.compile_version({"id": "stock", "version": 1, "graph": graph})
    assert plan["problems"] and "not executed by the node runtime" in plan["problems"][0]["message"]
    with pytest.raises(ValueError, match="Unknown comparison version"):
        studio.create({"architectures": ["blueprint.stock.v1"], "tasks": list(studio.tasks)}, start=False)
    assert studio.jobs() == []


def test_problems_lists_every_defect_and_diff_reads_node_changes(studio):
    graph = planner_worker_graph()
    graph["nodes"][1]["config"]["instructions"] = ""
    graph["nodes"][2]["config"]["runner"] = {"provider": "fireworks", "model": "accounts/fireworks/models/unpriced", "effort": "default"}
    graph["edges"].pop()
    found = blueprints.problems(graph)
    assert [p["node"] for p in found] == ["planner", "worker", "output"] or {p["node"] for p in found} >= {"planner", "worker"}
    assert any("Add instructions" in p["message"] for p in found) and any("rate-carded" in p["message"] for p in found)
    first = publish(studio, "evolving", planner_worker_graph())
    changed = planner_worker_graph()
    changed["nodes"][1]["config"]["instructions"] = "Plan carefully, then list risks."
    changed["nodes"].append(node("reviewer", "agent", 520, instructions="Review.", runner={"provider": "openai", "model": "gpt-5.6-sol", "effort": "high"}))
    changed["edges"] = edges(("input", "planner"), ("planner", "worker"), ("worker", "reviewer"), ("reviewer", "output"))
    draft = blueprints.save_draft(studio, {"id": "evolving", "name": "evolving", "revision": 1, "graph": changed})
    second = blueprints.publish(studio, {"id": "evolving", "revision": draft["revision"]})
    diff = second["diff"]
    assert diff["from"] == 1 and diff["to"] == 2 and diff["identical"] is False
    assert [n["id"] for n in diff["added"]] == ["reviewer"] and diff["removed"] == []
    assert diff["changed"][0]["id"] == "planner" and diff["changed"][0]["fields"][0]["field"] == "instructions"
    assert {"from": "Worker", "to": "Reviewer"} in diff["edges_added"] and {"from": "Worker", "to": "Output"} in diff["edges_removed"]
    assert blueprints.diff_versions(first, first)["identical"] is True

"""Offline regression checks for one architecture with several model settings."""
from copy import deepcopy
from wb_studio import execution

def test_comparison_freezes_each_model_without_mutating_published_graph(studio):
    original = publish(studio, 'comparison', planner_worker_graph())
    job = studio.create({'architectures':['blueprint.comparison.v1'], 'comparison_models':True,
                         'models':['claude-opus-5@medium','claude-opus-5@high'],
                         'tasks':list(studio.tasks), 'maximum_usd':'5'}, start=False)
    arms = job['settings']['arms']
    assert len(arms) == 2
    assert [a['runner_override']['effort'] for a in arms] == ['medium','high']
    assert job['total'] == len(studio.tasks)*2
    assert execution.load_version(studio,'comparison',1)['graph'] == original['graph']
    manifests = job['execution_manifests']
    assert manifests[arms[0]['id']]['identity_sha256'] != manifests[arms[1]['id']]['identity_sha256']
    for arm in arms:
        bound = studio._arm(job,arm,next(iter(studio.tasks)),studio.cancelled[job['id']])
        assert all(s['config']['runner']['effort']==arm['runner_override']['effort'] for s in bound.plan['steps'] if s['type']=='agent')

def test_binding_changes_every_agent_but_preserves_roles_and_edges():
    version = {'id':'x','version':1,'sha256':'original','graph':planner_worker_graph()}
    before=deepcopy(version)
    bound=execution.bind_comparison_model(version,{'provider':'anthropic','model':'claude-opus-5','effort':'high'})
    assert version==before
    assert bound['graph']['edges']==version['graph']['edges']
    assert [n['config'].get('mode') for n in bound['graph']['nodes']]==[n['config'].get('mode') for n in version['graph']['nodes']]
    assert {n['config']['runner']['model'] for n in bound['graph']['nodes'] if n['type']=='agent'}=={'claude-opus-5'}


def test_workflow_result_output_saves_and_executes_without_workflow_node(studio):
    plan = {'steps':[{'id':'encode','tool':'base64_encode','arguments':{'text':'hello'},'after':[]}]}
    studio.adapter_factory = lambda provider,tools: FakeAdapter(provider,False,answer=json.dumps(plan))
    graph = {'nodes':[node('input','input'),node('builder','agent',mode='advise',instructions='Author a workflow.',runner={'provider':'anthropic','model':'claude-opus-5','effort':'medium'}),node('output','output')], 'edges':edges(('input','builder'),('builder','output'))}
    draft=blueprints.save_draft(studio,{'id':'workflow-output','name':'Workflow output','track':'create-and-run','graph':graph})
    version=blueprints.publish(studio,{'id':draft['id'],'revision':draft['revision']})
    assert [n['type'] for n in version['graph']['nodes']]==['input','agent','output']
    job=studio.create({'architectures':['blueprint.workflow-output.v1'],'tasks':list(studio.tasks),'track':'create-and-run','maximum_usd':'5'},start=False)
    studio.execute(job['id'])
    events=studio.events(job['id'])
    assert any(e['type']=='workflow_recipe' for e in events)
    from wb_results.evidence import _long  # the evidence tree is deeper than Windows allows without the extended prefix
    evidence='\n'.join(p.read_text(encoding='utf8') for p in _long(studio.directory/job['id']/'evidence'/('x'*200)).parent.rglob('*.jsonl'))
    assert 'workflow_action' in evidence and 'aGVsbG8=' in evidence
    finish=next(e for e in events if e['type']=='step_finished' and e.get('step')=='output')
    assert finish['status']=='completed'


def test_bare_coverage_requires_matching_task_model_and_thinking(studio):
    from wb_studio.bare_coverage import coverage
    from wb_world.episode import contract_hash
    task=next(iter(studio.tasks))
    history={'id':'history','settings':{'track':'agentic-request','arms':[{'id':'native','kind':'native','version':'without-monarch','runner':{'model':'claude-opus-5','effort':'medium'}}]},'runner_manifests':{'native':dict.fromkeys(['harness_version','model_version','tools_sha256','world_sha256'],'pinned')},'task_hashes':{task:contract_hash(studio.tasks[task])},'results':[{'task':task,'model':'native','termination':'completed','passed':False}]}
    studio.jobs=lambda:[history]
    payload={'models':['claude-opus-5@medium'],'tasks':[task]}
    assert coverage(studio,payload)['items'][0]['completed']==1
    assert coverage(studio,{**payload,'models':['claude-opus-5@high']})['items'][0]['missing']==[task]
    history['task_hashes'][task]='old-definition'
    assert coverage(studio,payload)['items'][0]['missing']==[task]


def test_product_knowledge_is_a_source_only_agent_plugin():
    graph = knowledge_graph()
    assert blueprints.problems(graph) == []
    for source, target, message in [('input', 'knowledge', 'cannot receive'), ('knowledge', 'output', 'only to agents')]:
        invalid = json.loads(json.dumps(graph))
        invalid['edges'].append({'from': source, 'to': target})
        assert any(message in p['message'] for p in blueprints.problems(invalid))


def test_connected_knowledge_and_previous_output_have_separate_delivery(studio, monkeypatch):
    from types import SimpleNamespace
    from wb_studio.execution import ArchitectureArm
    import wb_studio.execution as execution
    graph = planner_worker_graph()
    graph['nodes'].append(node('knowledge', 'product-graph', graph='catalog', version=1))
    graph['edges'].append({'from':'knowledge','to':'planner'})
    version = {'id':'separate','version':1,'sha256':'offline','graph':graph,'order':blueprints.validate_graph(graph)}
    arm = ArchitectureArm(studio,'offline','arm','task',None,Decimal('2'),version,{'knowledge':{}},{})
    arm.graphs['knowledge'] = {'sentinel':True}
    monkeypatch.setattr(execution, 'render', lambda _: 'EXACT PRODUCT KNOWLEDGE')
    ep = SimpleNamespace(task={'prompt':[{'content':'Stable task system'},{'content':'Task brief'}]})
    steps = {s['id']:s for s in arm.plan['steps']}
    planner = arm._system(ep,steps['planner'],{})
    worker = arm._system(ep,steps['worker'],{'planner':'Exact earlier answer'})
    assert 'EXACT PRODUCT KNOWLEDGE' in planner
    assert 'EXACT PRODUCT KNOWLEDGE' not in worker
    assert worker.endswith('Exact earlier answer')
    assert worker.index('Your role in this step') < worker.index('Exact earlier answer')
    assert 'Stable task system' in planner and 'Stable task system' in worker
