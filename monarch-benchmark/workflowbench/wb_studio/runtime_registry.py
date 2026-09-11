"""Capability matrix: which comparison version can run which runner, and why not.

The picker and the launcher both read this module, so an unsupported
combination fails before a job, a reservation or a provider request exists.
No effort level is silently ignored and no provider is silently substituted.

Runners that can execute today are the rate-carded API controls in
``config/models`` (Claude, GPT, Gemini, Fireworks, Moonshot, Z.ai), each with
the effort vocabulary its API accepts. Native harnesses report the isolation
preflight; a host installation of Claude Code or Codex is not a verified
runtime. Facts about the stock Enterprise product are pinned to one commit
and were read from the named source files; their hashes are recorded so a
later revision cannot inherit them unnoticed.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from wb_arms import providers
from wb_arms.native_sandbox import preflight
from wb_arms import runtime_manifest as rm
from wb_studio.gateways import EFFORTS

ENTERPRISE_COMMIT = "60faf2a238fcfd3dd420d52b558f6a78181baa68"
ENTERPRISE_REPOSITORY = "https://github.com/TestBoxLab/monarch"
ENTERPRISE_DIRECTORY = "monarch-enterprise"

# Read on 2026-09-08 from the pinned checkout. Keys are Anthropic-native ids;
# Enterprise translates them to `us.`-prefixed Bedrock inference profiles at
# its provider boundary. There is no direct-API path in the stock product.
ENTERPRISE_FACTS = {
    "commit": ENTERPRISE_COMMIT,
    "provider": "bedrock",
    "source_files": {
        "apps/backend/src/config/bedrock.ts": "7790ecc721fcb5096e50c59275a43b0cf7223cbc0e95a7e030b52c7155da286a",
        "apps/backend/src/config/bedrock-models.json": "f6a2b1e01fe1ab79d7965d84c939e112762b870f550513e8a7dc1fe8361b6fcc",
        "apps/backend/src/workflows/recipe-agent/brain-presets.ts": "f8b5cc84255716800edaa65c46421f70619b69da225fbd827f358485a0f73d52",
        "apps/backend/src/config/env.ts": "7a34f470f9860815af4ea15fae6ec86264c96e7306c02f6c22d5e7c836d4e37b",
        "apps/backend/.env.example": "3a47a2bdf320592c2b34193f5e3a34b62f7cca8702afd01e3599fcd4ccb57951",
        "apps/backend/src/operator/operator.controller.ts": "4ce40f41d7418737f36b017c03091536a8331536d692b6e910c513d4d917526c",
        "apps/backend/src/workflows/recipe-agent/recipe-run.controller.ts": "fb85fe7e07f40fea390c28faf66bdb455dd55295718454c54af6253acb450414",
        "apps/backend/src/product-graph/product-graph.source.ts": "87bee20d2ca251c59e3b7a7b787945bcfa5e2ec6ed31db981ee573fa2bb70d58",
    },
    "lockfile": {"path": "pnpm-lock.yaml", "git_blob": "13305d43a698fa7686327bb79680cc99111a9deb",
                 "sha256": "c6c429fd03cefd2188a1d2bcaaf2841d91cd26a3fbb249a05522300e7306533f"},
    "models": ["claude-opus-4-8", "claude-opus-5", "claude-sonnet-5", "claude-sonnet-4-6",
               "claude-haiku-4-5-20251001", "claude-haiku-4-5"],
    "barred_models": ["claude-fable-5", "claude-mythos-5"],
    "operator": {  # POST /api/operator/runs: goal, productSlug, origin, threadId only
        "model_env": "ANTHROPIC_MODEL", "default_model": "claude-opus-4-8",
        "per_run_model_override": False, "per_run_effort_override": False,
        "max_steps_env": "OPERATOR_MAX_STEPS", "default_max_steps": 40,
    },
    "create_run": {  # POST /api/workflows/recipes/runs: `brain` is a preset NAME
        "brain_presets": {"opus-medium": {"model": "claude-opus-4-8", "effort": "medium"},
                          "sonnet-high": {"model": "claude-sonnet-5", "effort": "high"}},
        "default_model_env": "ANTHROPIC_RECIPE_MODEL", "default_model": "claude-opus-4-8",
        "default_effort_env": "RECIPE_BRAIN_EFFORT", "default_effort": "medium",
    },
    "required_env": ["AWS_REGION or BEDROCK_REGION", "AWS credential chain", "DATABASE_URL",
                     "SESSION_SECRET", "FD_API_URL"],
    "required_services": ["postgres (feature_discovery database, monarch_enterprise schema)",
                          "fdapi", "backend", "workflow-orchestrator"],
    "billing": "AWS Bedrock; direct Anthropic/OpenAI keys do not establish access or accounting",
}

# From C:/Users/Lucas Wakigawa/Monarch_Main/Monarch_Report.html (sha256 in
# specs/011-monarch-runtime-integration/investigation-sources.json). Report
# claims, not recomputed results.
BRIDGE_SETTINGS = {
    "identity": "bridge-v2-v9.12",
    "name": "Product graph enrichment — BRIDGE v2 + v9.12",
    "model": "claude-opus-5", "effort": "medium", "provider": "anthropic",
    "graph_artifact": "config/monarch/graph-inline-v6-evalrepair10.json",
    "suite_revision": "1.0.6+evalrepair.10",
    "report_claim": "361/600 with Monarch v9.12 (Opus 5, medium) versus 289/600 bare (Opus 5, max); unverified",
}

VERSION_NAMES = {"without-monarch": "Without Monarch",
                 "default-monarch-enterprise": "Default Monarch Enterprise",
                 "bridge-v2-v9.12": BRIDGE_SETTINGS["name"]}
RUNNER_PROVIDERS = ("anthropic", "openai", "fireworks", "gemini", "moonshot", "zai", "claude-code", "codex", "bedrock")
CONTROL_NAMES = {"claude-opus-5": "Claude Opus 5", "claude-opus-4-8": "Claude Opus 4.8", "gemini-3.7-flash": "Gemini 3.7 Flash",
                 "gpt-5.6-sol": "GPT-5.6 Sol", "gpt-5.6-terra": "GPT-5.6 Terra", "kimi-k3-fireworks": "Kimi K3 (Fireworks)",
                 "glm-5.3-fireworks": "GLM 5.3 (Fireworks)", "kimi-k3": "Kimi K3 (Moonshot)", "glm-5.3": "GLM 5.3 (Z.ai)"}
SCRIPTED_NAMES = {"oracle": "Scripted reference", "sloppy": "Near-miss control", "null": "Null control"}
HARNESS_NAMES = {"claude-code": "Claude Code", "codex": "Codex", "gemini-cli": "Gemini CLI",
                 "opencode": "OpenCode", "monarch": "Monarch"}
# The generic tool loop is how a model is run by default; saying so adds nothing.
PLAIN_HARNESS = "api"
BUILD_CHARS = "@+*/"
RESEARCH_DIR = Path(__file__).resolve().parents[3] / "research"


def _titled(token: str) -> str:
    """An unknown identifier as a name; anything already capitalised is left alone."""
    text = str(token or "").strip()
    return text.replace("-", " ").title() if text and text == text.lower() else text


def _without_build(text: str) -> str:
    """Drop the words a build stamps in: commit hashes and branch tokens."""
    words = [w for w in str(text or "").split()
             if not any(ch in w for ch in BUILD_CHARS) and not re.fullmatch(r"[0-9a-f]{7,40}", w)]
    return " ".join(words)


def _one_setup(ident: str) -> str:
    """One competitor token: a model, a model/harness pair, or a model@effort pair."""
    base, _, effort = str(ident or "").partition("@")
    model, _, harness = base.partition("/")
    name = (CONTROL_NAMES.get(model) or SCRIPTED_NAMES.get(model)
            or HARNESS_NAMES.get(model) or _titled(model))
    parts = [name]
    if harness and harness != PLAIN_HARNESS:
        parts.append(HARNESS_NAMES.get(harness) or _titled(harness))
    if effort:
        # A build token travels after an @ as readily as after a separator
        # (monarch@0cf63a74e+feat/railway-dev-deploy*); a label cannot hold it either.
        parts.append(_without_build(effort))
    return " · ".join(p for p in parts if p)


def display_name(setup_id, given=None) -> str:
    """One readable name for a competitor, wherever the run was launched from.

    A run launched from a config plan names its competitors ``model/harness``
    (``kimi-k3-fireworks/api``); a run launched in the Studio carries a name on
    the arm. Both land here, and both lose the build tokens no label can hold:
    ``monarch · 0cf63a74e+feat/railway-dev-deploy* reasoning`` is ``Monarch ·
    reasoning``. The full identifier stays in the record and in the method notes.
    """
    raw = str(given or setup_id or "").strip()
    if not raw:
        return str(setup_id or "")
    head, separator, tail = raw.partition(" · ")
    if not separator:
        return _one_setup(raw)
    return " · ".join(p for p in (_one_setup(head), _without_build(tail)) if p)


def fit_name(name: str, width: int = 34) -> str:
    """A name a figure label can hold, cut on a word boundary, never leaving the
    separator dangling ("Monarch ·…" said less than "Monarch…")."""
    text = str(name or "")
    return text if len(text) <= width else text[:width - 1].rsplit(" ", 1)[0].rstrip(" ·/-") + "…"


def _research_dir(studio) -> Path:
    return Path(getattr(studio, "research_dir", RESEARCH_DIR))


def _provider_family(provider: providers.Provider) -> str:
    if provider.adapter == "anthropic":
        return "anthropic"
    if provider.adapter == "openai_responses":
        return "openai"
    if provider.adapter == "gemini":
        return "gemini"
    base = provider.base_url or ""
    return "fireworks" if "fireworks" in base else "moonshot" if "moonshot" in base else "zai" if "z.ai" in base else "openai-compatible"


def api_controls() -> dict:
    """Every rate-carded API control, with the effort vocabulary its API accepts."""
    from wb_studio.gateways import request_ceiling
    catalog = {}
    for key, provider in providers.REGISTRY.items():
        efforts = EFFORTS[provider.adapter]
        catalog[key] = {"id": key, "name": CONTROL_NAMES.get(key, key.replace("-", " ").title()), "provider": _provider_family(provider),
                        "model": provider.model_id, "adapter": provider.adapter, "key_env": provider.key_env,
                        "efforts": list(efforts), "default_effort": ("low" if provider.adapter == "gemini" else provider.effort) if efforts else None,
                        "rate_card": f"config/models/{key}.yaml", "request_ceiling_usd": str(request_ceiling(key)),
                        "prices_per_million": {"input": provider.price_in, "cached": provider.price_cached, "output": provider.price_out}}
    return catalog


def version_request_ceiling(version: dict) -> str | None:
    """The largest first-request reservation among a version's agent steps."""
    ceilings = []
    for node in version.get("graph", {}).get("nodes", []):
        if node.get("type") == "agent":
            resolved = resolve_api_control((node.get("config") or {}).get("runner") or {})
            if resolved:
                ceilings.append(resolved["control"]["request_ceiling_usd"])
    return max(ceilings, key=lambda c: float(c)) if ceilings else None


def resolve_api_control(runner: dict) -> dict | None:
    """Map a runner config (provider, model, effort) to a rate-carded control, or None."""
    if not isinstance(runner, dict):
        return None
    provider, model, effort = runner.get("provider"), (runner.get("model") or "").strip(), runner.get("effort", "default")
    for key, control in api_controls().items():
        if control["provider"] != provider:
            continue
        if model in (key, control["model"]) or (provider == "gemini" and model == ""):
            return {"key": key, "effort": effort, "control": control}
    return None


def credential_present(control: dict) -> bool:
    return bool(os.getenv(control["key_env"], "").strip())


def parse_runner(studio, selection) -> dict:
    """Normalize a Studio selection or a node runner config to provider/model/effort."""
    if isinstance(selection, dict):
        provider, model, effort = selection.get("provider"), selection.get("model"), selection.get("effort", "default")
        kind = "native" if provider in ("claude-code", "codex") else "api-control" if provider in ("anthropic", "openai", "fireworks", "gemini", "moonshot", "zai") else provider
        return {"id": None, "provider": provider, "model": model, "effort": effort, "kind": kind}
    if not isinstance(selection, str):
        raise ValueError("Unknown runner selection")
    base, _, effort = selection.partition("@")
    if base in ("oracle", "sloppy"):
        return {"id": selection, "provider": "scripted", "model": base, "effort": "default", "kind": "scripted"}
    controls = api_controls()
    if base in controls:
        control = controls[base]
        return {"id": selection, "provider": control["provider"], "model": control["model"], "effort": effort or "default", "kind": "api-control", "control": base}
    if base in ("claude-code", "codex"):
        return {"id": selection, "provider": base, "model": "claude-opus-5" if base == "claude-code" else "gpt-5.6-sol", "effort": effort or "default", "kind": "native"}
    if base.startswith("config-") and studio is not None:
        path = Path(studio.directory) / "runner-configs" / (base[len("config-"):] + ".json")
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            return {**parse_runner(None, saved), "id": selection, "name": saved.get("name")}
    return {"id": selection, "provider": None, "model": base, "effort": effort or "default", "kind": "unknown"}


def _native_reason(studio=None) -> str | None:
    if studio is not None:
        from wb_studio.native import status
        report = status(studio)
        if report["launchable"]:
            return None
        return "Native isolation requires verification (native-isolation-v1; acceptance native-isolation-v2): " + report["reason"] + "; missing checks: " + ", ".join(preflight().missing_checks)
    report = preflight()
    return f"Native runtime requires a verified Studio container ({report.contract_version}); missing checks: {', '.join(report.missing_checks)}"


def _api_control_support(runner: dict) -> dict:
    resolved = resolve_api_control({"provider": runner["provider"], "model": runner["model"], "effort": runner["effort"]})
    if resolved is None:
        return {**runner, "supported": False, "reason": f"No verified rate card for {runner['provider']} model {runner['model'] or '(none)'}; add config/models/<name>.yaml with prices before it can spend."}
    control, effort = resolved["control"], runner["effort"]
    if effort != "default" and effort not in control["efforts"]:
        return {**runner, "supported": False, "reason": f"{control['name']} accepts " + (", ".join(control["efforts"]) if control["efforts"] else "no reasoning-effort setting") + f", not {effort}."}
    row = {**runner, "control": control["id"], "supported": True, "reason": f"{control['name']} API control ({control['rate_card']})"}
    if not credential_present(control):
        row["launch_block"] = f"Add {control['key_env']} to .env"
    return row


def _enterprise_support(runner: dict, track: str) -> tuple[bool, str]:
    facts = ENTERPRISE_FACTS
    if runner["provider"] != "bedrock":
        return False, ("Default Monarch Enterprise runs its own Claude brain on AWS Bedrock; it does not accept "
                       f"{runner['provider'] or 'this'} runners. Use a Bedrock model from the pinned catalog.")
    if runner["model"] in facts["barred_models"]:
        return False, f"{runner['model']} is barred by the product's data-retention decision."
    if runner["model"] not in facts["models"]:
        return False, f"{runner['model']} is not in the pinned Enterprise Bedrock catalog ({', '.join(facts['models'])})."
    if track == "agentic-request":
        operator = facts["operator"]
        if runner["model"] != operator["default_model"]:
            return False, (f"The stock operator accepts no per-run model; it runs {operator['model_env']} "
                           f"(default {operator['default_model']}). A different model is a custom Enterprise build.")
        if runner["effort"] != "default":
            return False, "The stock operator accepts no per-run reasoning effort; choose Default."
        return True, "Stock operator settings"
    presets = facts["create_run"]["brain_presets"]
    for name, spec in presets.items():
        if spec == {"model": runner["model"], "effort": runner["effort"]}:
            return True, f"Stock recipe brain preset {name}"
    if runner["effort"] == "default" and runner["model"] == facts["create_run"]["default_model"]:
        return True, "Stock recipe brain environment default"
    return False, ("Create-and-run accepts only the stock brain presets: "
                   + ", ".join(f"{n} ({s['model']} {s['effort']})" for n, s in presets.items()) + ".")


def runner_support(studio, version_id: str, selection, track: str = "agentic-request") -> dict:
    """Is this runner a valid configuration for this version? Launchability is separate."""
    runner = parse_runner(studio, selection)
    if track not in rm.TRACKS:
        raise ValueError("Unknown evaluation track")
    if version_id == "without-monarch":
        if runner["kind"] == "scripted":
            return {**runner, "supported": True, "reason": "Scripted control for internal tests"}
        if runner["kind"] == "api-control":
            return _api_control_support(runner)
        if runner["kind"] == "native":
            blocked = _native_reason(studio)
            row = {**runner, "supported": True, "reason": "Native harness for this model family"}
            if blocked:
                return {**row, "launch_block": blocked}
            family = "anthropic" if runner["provider"] == "claude-code" else "openai"
            control = _api_control_support({**runner, "provider": family})
            return {**control, "provider": runner["provider"], "kind": "native", "reason": "Verified isolated native harness" if control["supported"] else control["reason"]}
        if runner["provider"] == "bedrock":
            return {**runner, "supported": False, "reason": "Bedrock models are the stock Enterprise brain, not a Without Monarch runner."}
        return {**runner, "supported": False, "reason": "Unknown runner"}
    if version_id == "default-monarch-enterprise":
        supported, reason = _enterprise_support(runner, track)
        return {**runner, "supported": supported, "reason": reason}
    if version_id == "bridge-v2-v9.12":
        expected = {"model": BRIDGE_SETTINGS["model"], "effort": BRIDGE_SETTINGS["effort"]}
        if {"model": runner["model"], "effort": runner["effort"]} == expected and runner["provider"] in ("anthropic", "bedrock"):
            return {**runner, "supported": True, "reason": "Matches the recovered v9.12 setting (Claude Opus 5, medium)"}
        return {**runner, "supported": False,
                "reason": f"The recovered v9.12 setting is {expected['model']} at {expected['effort']}; any other runner is a new variant, not a reproduction."}
    if version_id.startswith("blueprint."):
        return {**runner, "supported": False, "reason": "Published architectures carry their runners in their nodes; select the version, not a runner."}
    raise ValueError("Unknown comparison version")


def node_support(studio, node: dict, track: str = "agentic-request") -> dict | None:
    """Capability row for one published node; None for nodes without a runner."""
    kind = node.get("type")
    runner = (node.get("config") or {}).get("runner")
    if kind == "monarch":
        row = runner_support(studio, "default-monarch-enterprise", runner or {}, track)
    elif kind == "agent":
        row = runner_support(studio, "without-monarch", runner or {}, track)
    else:
        return None
    if row.get("kind") == "native" and not row.get("launch_block"):
        row["launch_block"] = "Native harnesses currently run as standalone controls; native execution inside architecture nodes is not implemented"
    return {"node": node.get("id"), "label": node.get("label"), "type": kind, **row}


def blueprint_readiness(studio, version: dict) -> dict:
    """Readiness of one published definition, from its nodes and the product graph versions it references.

    unsupported          a runner choice the platform refuses
    adapter_required     a stock Monarch node: no Enterprise adapter serves requests
    blocked              a valid runner the platform cannot serve yet (isolation, credential)
    preparation_required a product-graph step whose version is missing or failed
    ready                every step can execute against the corpus today
    """
    nodes = version["graph"]["nodes"]
    rows = [r for r in (node_support(studio, n) for n in nodes) if r]
    unsupported = [r for r in rows if not r["supported"]]
    blocked = [r for r in rows if r["supported"] and r.get("launch_block")]
    monarch = [n for n in nodes if n["type"] == "monarch"]
    unprepared = _unprepared_graphs(studio, nodes)
    source = "frozen" if monarch else "not_applicable"
    if unsupported:
        state, reasons = "unsupported", [f"{r['label']}: {r['reason']}" for r in unsupported]
    elif monarch:
        state, reasons = "adapter_required", ["No pinned Enterprise build serves requests yet; the stock node cannot execute in the node runtime."]
    elif blocked:
        state, reasons = "blocked", [f"{r['label']}: {r['launch_block']}" for r in blocked]
    elif unprepared:
        state, reasons = "preparation_required", unprepared
    else:
        state, reasons = "ready", []
    return {"readiness": rm.readiness(source, "published", state, reasons), "capabilities": rows}


def _unprepared_graphs(studio, nodes: list[dict]) -> list[str]:
    """One reason per product-graph step whose version cannot be used today."""
    from wb_studio.product_graphs import load_version, usable
    reasons = []
    for node in nodes:
        if node.get("type") != "product-graph":
            continue
        config = node.get("config") or {}
        if studio is None:
            reasons.append(f"{node.get('label')}: product graph versions are checked at launch.")
            continue
        try:
            version = load_version(studio, config.get("graph"), config.get("version"))
        except ValueError as exc:
            reasons.append(f"{node.get('label')}: {exc}. Prepare it in Product graphs.")
            continue
        if not usable(version):
            reasons.append(f"{node.get('label')}: product graph '{version['name']}' v{version['version']} {version.get('status')} ({version.get('error') or 'no records'}). Prepare it again in Product graphs.")
    return reasons


def graph_bindings(studio, version: dict) -> dict:
    """Per product-graph step: which prepared version it binds to, summarized for the picker and the canvas."""
    from wb_studio.execution import bound_graphs
    out = {}
    for step, graph in bound_graphs(studio, version).items():
        out[step] = {"graph": graph["id"], "name": graph["name"], "version": graph["version"], "status": graph["status"], "sha256": graph["sha256"],
                     "fields": [f["path"] for f in graph["fields"]], "products": len(graph.get("records", {})), "cost_usd": graph["cost_usd"]}
    return out


def annotate_listing(studio, items: list[dict]) -> list[dict]:
    """Attach live readiness to every stored version; the files stay untouched."""
    for record in items:
        for version in record.get("versions", []):
            state = blueprint_readiness(studio, version)
            version["readiness"], version["capabilities"] = state["readiness"], state["capabilities"]
            version["execution_status"] = state["readiness"]["runtime"]
            version["execution_note"] = " ".join(state["readiness"]["reasons"])
            version["readiness_computed_live"] = True
            version["graphs"] = graph_bindings(studio, version)
    return items


def bridge_status(studio) -> dict:
    """Provenance state of the historical bundle, from the research inventory when present."""
    path = _research_dir(studio) / "architectures" / "bridge-v2-v9.12" / "source-manifest.json"
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        summary = record.get("summary", {})
        missing = [e["role"] for e in record.get("entries", []) if e.get("status") == "missing"]
        reasons = [f"Historical source not fully recovered: {summary.get('missing', len(missing))} required components missing"
                   + (f" ({', '.join(missing[:6])}{'…' if len(missing) > 6 else ''})" if missing else "")]
        return {"inventory": str(path), "summary": summary, "missing": missing,
                "readiness": rm.readiness("source_required", "not_applicable", "source_required", reasons)}
    return {"inventory": None, "summary": None, "missing": None,
            "readiness": rm.readiness("source_required", "not_applicable", "source_required",
                                      ["No provenance inventory has been generated for the BRIDGE v2 + v9.12 bundle."])}


def versions(studio) -> list[dict]:
    from wb_studio.architectures import cached_default
    from wb_studio.blueprints import listing
    native = _native_reason(studio)
    items = [{"id": "without-monarch", "name": VERSION_NAMES["without-monarch"], "kind": "control",
              "description": "The runner works directly with the task and application tools. No Monarch graph, contract, gates or memory.",
              "readiness": rm.readiness("not_applicable", "not_applicable", "ready"),
              "notes": [f"Rate-carded API controls run today. Native harnesses: {native or 'container and native CLI acceptance verified'}"]}]
    baseline = cached_default(studio)
    from wb_studio.enterprise import version_record
    record = version_record(studio)
    live = record["readiness"]
    reasons = list(live["reasons"])
    if baseline is None:
        source = "unavailable"
        reasons.append("The latest official revision has not been resolved yet; refresh from GitHub to pin it.")
    else:
        source = "frozen"
        if baseline.get("commit") != ENTERPRISE_COMMIT:
            reasons.append(f"Capability facts were read at {ENTERPRISE_COMMIT[:12]}; the frozen revision is {baseline['commit'][:12]}. "
                           "Re-verify the model catalog, brain presets and request shapes before trusting the matrix for this revision.")
    ready = rm.readiness(source, "not_applicable", live["runtime"], reasons)
    items.append({"id": "default-monarch-enterprise", "name": record["name"], "kind": "stock",
                  "description": f"Official {ENTERPRISE_REPOSITORY}/{ENTERPRISE_DIRECTORY}, driven through its own API on the bench's front door; "
                                 "verified against the deployment the harness names before every launch.",
                  "commit": baseline.get("commit") if baseline else None, "facts_commit": ENTERPRISE_COMMIT,
                  "facts_drift": bool(baseline) and baseline.get("commit") != ENTERPRISE_COMMIT, "readiness": ready,
                  "capabilities": ENTERPRISE_FACTS, "manifest": record["manifest"] or (baseline or {}).get("runtime_manifest"),
                  "served": record["served"], "probe": record["probe"], "request_ceiling_usd": record["request_ceiling_usd"]})
    bridge = bridge_status(studio)
    items.append({"id": "bridge-v2-v9.12", "name": BRIDGE_SETTINGS["name"], "kind": "historical",
                  "description": "Recovered BRIDGE v2 + v9.12 knowledge and runtime settings; a versioned experimental architecture, not the stock product.",
                  "settings": BRIDGE_SETTINGS, "readiness": bridge["readiness"], "provenance": bridge})
    for record in annotate_listing(studio, listing(studio)):
        for version in record.get("versions", []):
            items.append({"id": f"blueprint.{record['id']}.v{version['version']}", "name": f"{record['name']} / v{version['version']}",
                          "kind": "custom", "track": version.get("track", "agentic-request"), "blueprint": record["id"], "version": version["version"],
                          "description": version.get("notes") or "Published architecture definition",
                          "sha256": version.get("sha256"), "knowledge_sha256": _graphs_sha(version.get("graphs") or {}), "graphs": version.get("graphs") or {},
                          "request_ceiling_usd": version_request_ceiling(version),
                          "readiness": version["readiness"], "capabilities": version["capabilities"],
                          "steps": [{"id": n["id"], "type": n["type"], "label": n["label"]} for n in version["graph"]["nodes"]]})
    return items


def _graphs_sha(graphs: dict) -> str | None:
    return rm.sha256_json({step: g["sha256"] for step, g in sorted(graphs.items())}) if graphs else None


def capability_matrix(studio) -> dict:
    """Everything the picker needs: versions with readiness, and per-runner support cells."""
    rows = versions(studio)
    runners = [m for m in studio.models()] if hasattr(studio, "models") else []
    cells = []
    for version in rows:
        for runner in runners:
            selection = runner["id"]
            support = runner_support(studio, version["id"], selection)
            cells.append({"version": version["id"], "runner": selection, "supported": support["supported"],
                          "launchable": support["supported"] and version["readiness"]["launchable"] and not support.get("launch_block") and runner.get("available", False),
                          "reason": support.get("launch_block") or support["reason"] if support["supported"] else support["reason"]})
    return {"schema_version": "ailabs-capability-matrix-v1", "versions": rows, "cells": cells, "controls": list(api_controls().values()),
            "native_preflight": {"contract": "native-isolation-v2", "status": "blocked" if _native_reason(studio) else "ready",
                                 "missing_checks": list(preflight().missing_checks) if _native_reason(studio) else []}}


def check_launch(studio, architectures, selected, track: str = "agentic-request") -> list[dict]:
    """Refuse an unsupported comparison before any job, reservation or dispatch. Returns the version records."""
    if architectures is None:
        architectures = ["without-monarch"]
    if not isinstance(architectures, list) or not architectures or any(not isinstance(a, str) for a in architectures) or len(set(architectures)) != len(architectures):
        raise ValueError("Monarch comparisons cannot launch yet: choose Without Monarch or a ready published architecture.")
    by_id = {v["id"]: v for v in versions(studio)}
    chosen = []
    for identity in architectures:
        version = by_id.get(identity)
        if version is None:
            raise ValueError("Unknown comparison version")
        purpose = version.get("track", "create-and-run" if identity == "default-monarch-enterprise" else "agentic-request")
        if identity != "without-monarch" and purpose != track:
            raise ValueError(f"{version['name']} belongs to the {purpose} track. Choose a matching architecture.")
        if not version["readiness"]["launchable"]:
            raise ValueError(f"{version['name']} cannot launch yet: " + " ".join(version["readiness"]["reasons"]))
        if identity == "without-monarch":
            for selection in selected or []:
                support = runner_support(studio, identity, selection, track)
                if not support["supported"]:
                    raise ValueError(f"{version['name']} cannot use {selection}: {support['reason']}")
                if support.get("launch_block"):
                    raise ValueError(f"{selection} cannot launch: {support['launch_block']}")
        chosen.append(version)
    return chosen
