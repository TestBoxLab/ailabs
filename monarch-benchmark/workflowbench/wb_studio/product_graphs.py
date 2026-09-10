"""Product graphs: versioned, reusable, extendable knowledge about the corpus products.

A product graph version is a schema (typed fields with descriptions) plus a record for
every product in the benchmark corpus, filled once by an agent with catalog access.
Versions are immutable once prepared. A new version extends its parent: fields that did
not change keep the parent's values, new or changed fields are researched again, and the
result is a new pinned version. Architectures reference a version through a
``product-graph`` step; scored runs bind to the version hash and never rewrite it.

Layout under ``<studio>/product-graphs/<id>/``:

    draft.json        the editable schema, research instructions and runner
    vNNNN.json        a prepared version (records, provenance, cost, hash)
    vNNNN.events.jsonl  the preparation events (requests, billing, tool calls)
    vNNNN.claimed     single-dispatch guard for that version number
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import uuid

from wb_arms import runtime_manifest as rm
from wb_results.evidence import write_json
from wb_studio.agents import run_loop
from wb_studio.runners import runner_config
from wb_world.episode import api_search

SCHEMA = "ailabs-product-graph-v1"
ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
FIELD_PATH = re.compile(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*")
TYPES = ("string", "number", "boolean", "object", "array")
MAX_PREPARE_TURNS = 12
RESEARCH_SYSTEM = ("You prepare reusable product knowledge for workflow-automation agents. You may call api_search to "
                   "inspect the available application actions. Base every field on what the catalog actually offers; "
                   "say 'unknown' rather than invent. Your final message must be only a JSON object, no prose and no fences.")


def folder(studio, identity: str) -> Path:
    if not isinstance(identity, str) or not ID.fullmatch(identity):
        raise ValueError("Invalid product graph ID")
    return Path(studio.directory) / "product-graphs" / identity


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def corpus_products(tasks: dict) -> list[str]:
    return sorted({service for task in tasks.values() for service in task.get("info", {}).get("initial_state", {})
                   if not service.startswith("_") and service != "meta"})


def validate_fields(fields) -> list[dict]:
    """Normalized, unique, typed fields; the first defect raises."""
    if not isinstance(fields, list) or len(fields) > 60:
        raise ValueError("Declare up to 60 fields")
    seen, out = set(), []
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("Each field needs a path, a type and a description")
        path = str(field.get("path", "")).strip()
        if not FIELD_PATH.fullmatch(path) or len(path) > 120:
            raise ValueError(f"Field path '{path[:40]}' must look like product.summary")
        if field.get("type") not in TYPES:
            raise ValueError(f"Field {path}: choose a type among {', '.join(TYPES)}")
        if path in seen:
            raise ValueError(f"Duplicate field {path}")
        description = str(field.get("description", "")).strip()
        if len(description) > 600:
            raise ValueError(f"Field {path}: keep the description under 600 characters")
        seen.add(path)
        out.append({"path": path, "type": field["type"], "description": description})
    return out


def listing(studio) -> list[dict]:
    root = Path(studio.directory) / "product-graphs"
    items = []
    for graph_dir in sorted(root.glob("*")) if root.exists() else []:
        draft = graph_dir / "draft.json"
        if not draft.is_file():
            continue
        record = _read(draft)
        versions = _versions(graph_dir)
        by_number = {v["version"]: v for v in versions}
        record["versions"] = [summary(v, by_number.get(v.get("parent_version"))) for v in versions]
        items.append(record)
    return items


def summary(version: dict, parent: dict | None = None) -> dict:
    """A version without the raw model answer, plus its sentence; records stay (they are the point)."""
    return {k: v for k, v in version.items() if k != "final_text"} | {"summary": describe(version, parent)}


def _unknown(value) -> bool:
    return isinstance(value, str) and value.strip().lower() == "unknown"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def describe(version: dict, parent: dict | None) -> str:
    """One or two sentences from the diff counts against the parent, never from a model."""
    if version.get("status") == "failed":
        return "Failed before any field was filled."
    fields = [f["path"] for f in version.get("fields", [])]
    products = version.get("products") or sorted(version.get("records", {}))
    before, after = (parent or {}).get("records", {}), version.get("records", {})
    filled = changed = unknown = missing = 0
    for product in products:
        for path in fields:
            old, new = before.get(product, {}), after.get(product, {})
            if path not in new:
                missing += 1
            elif _unknown(new[path]):
                unknown += 1
            elif path not in old:
                filled += 1
            elif old[path] != new[path]:
                changed += 1
    slots, dropped = len(products) * len(fields), len(version.get("removed") or [])
    tail = ([f"changed {_count(changed, 'value')}"] if changed else []) + ([f"{unknown} stayed unknown"] if unknown else [])         + ([f"{missing} still missing"] if missing else []) + ([f"dropped {_count(dropped, 'field')}"] if dropped else [])
    if parent and not (filled or changed or unknown or missing):
        return "; ".join([f"Nothing new: all {_count(slots, 'field')} match version {parent['version']}"] + tail) + "."
    return "; ".join([f"Filled {filled} of {_count(slots, 'field')} across {_count(len(products), 'product')}"] + tail) + "."


def drilldown(studio, identity: str, number: int) -> dict:
    """Every product's values in a version, each with the research events (of the version that researched it) that produced it."""
    version = load_version(studio, identity, number)
    graph_dir, logs = folder(studio, identity), {}

    def events_of(since: int) -> list[dict]:
        if since not in logs:
            path = graph_dir / f"v{since:04d}.events.jsonl"
            logs[since] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []
        return logs[since]

    products = []
    for product in version.get("products") or sorted(version.get("records", {})):
        record, fields = version.get("records", {}).get(product, {}), []
        for field in version.get("fields", []):
            path, since, present = field["path"], field.get("since", number), field["path"] in record
            fields.append({"path": path, "type": field["type"], "value": record.get(path), "present": present, "unknown": present and _unknown(record[path]),
                           "since": since, "events": {"version": since, "ids": [e["id"] for e in events_of(since) if present and _produced(e, product)]}})
        products.append({"product": product, "fields": fields})
    return {"id": identity, "version": number, "products": products}


def _produced(event: dict, product: str) -> bool:
    """A catalog search that names the product, or a completed model answer that carries its record."""
    if event.get("type") == "node_started":
        return product.lower() in json.dumps(event.get("arguments", {})).lower()
    return event.get("type") == "model_finished" and event.get("status") == "completed" and f'"{product}"' in (event.get("output") or "")


def load_version(studio, identity: str, number: int) -> dict:
    if not isinstance(identity, str) or not ID.fullmatch(identity) or type(number) is not int or number < 1:
        raise ValueError("Unknown product graph version")
    path = folder(studio, identity) / f"v{number:04d}.json"
    if not path.is_file():
        raise ValueError(f"Product graph '{identity}' has no version {number}")
    return _read(path)


def usable(version: dict | None) -> bool:
    return bool(version) and version.get("status") in ("complete", "incomplete")


def save_draft(studio, payload: dict) -> dict:
    identity = payload.get("id") or uuid.uuid4().hex
    graph_dir = folder(studio, identity)
    name = payload.get("name", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("Name the product graph in up to 100 characters")
    fields = validate_fields(payload.get("fields", []))
    instructions = str(payload.get("instructions", ""))
    if len(instructions) > 4000:
        raise ValueError("Keep the research instructions under 4000 characters")
    runner = runner_config(payload.get("runner") or {})
    from wb_studio.runtime_registry import resolve_api_control
    if runner["provider"] in ("claude-code", "codex") or resolve_api_control(runner) is None:
        raise ValueError("Choose a rate-carded API control to research the fields (its provider and model must have a rate card in config/models)")
    with studio.lock:
        file = graph_dir / "draft.json"
        old = _read(file) if file.exists() else None
        revision = old["revision"] if old else 0
        if payload.get("revision", 0) != revision:
            raise ValueError("This product graph changed in another editor. Reload it before saving.")
        data = {"id": identity, "name": name.strip(), "notes": str(payload.get("notes", ""))[:2000], "fields": fields,
                "instructions": instructions, "runner": runner, "revision": revision + 1,
                "updated_at": datetime.now(timezone.utc).isoformat()}
        graph_dir.mkdir(parents=True, exist_ok=True)
        write_json(file, data)
    return data


def _versions(graph_dir: Path) -> list[dict]:
    return [_read(p) for p in sorted(graph_dir.glob("v????.json"))]


def plan(studio, identity: str) -> dict:
    """What the next preparation would do: which fields are new, carried or changed, and its version number."""
    graph_dir = folder(studio, identity)
    draft = _read(graph_dir / "draft.json")
    existing = _versions(graph_dir)
    parent = next((v for v in reversed(existing) if usable(v)), None)
    last = existing[-1] if existing else None
    number = last["version"] if last and last.get("status") == "failed" else len(existing) + 1
    parent_fields = {f["path"]: f for f in (parent or {}).get("fields", [])}
    new, carried, changed = [], [], []
    for field in draft["fields"]:
        before = parent_fields.get(field["path"])
        if before is None:
            new.append(field)
        elif before["type"] != field["type"] or before["description"] != field["description"]:
            changed.append(field)
        else:
            carried.append(field)
    removed = [p for p in parent_fields if p not in {f["path"] for f in draft["fields"]}]
    return {"id": identity, "revision": draft["revision"], "version": number, "parent_version": parent["version"] if parent else None,
            "retrying_failed": bool(last) and last.get("status") == "failed", "new": new, "changed": changed, "carried": carried,
            "removed": removed, "products": corpus_products(studio.tasks), "to_research": new + changed}


def prepare(studio, identity: str, *, maximum_usd, revision=None) -> dict:
    """Research the new and changed fields once, merge with the parent, pin the result as the next version."""
    graph_dir = folder(studio, identity)
    if not (graph_dir / "draft.json").is_file():
        raise ValueError("Unknown product graph")
    maximum = Decimal(str(maximum_usd))
    if not maximum.is_finite() or maximum <= 0 or maximum > 300 or maximum.as_tuple().exponent < -2:
        raise ValueError("Preparation budget must be between $0.01 and $300, with at most two decimals")
    work = plan(studio, identity)
    draft = _read(graph_dir / "draft.json")
    if revision is not None and revision != draft["revision"]:
        raise ValueError("Save the product graph before preparing it")
    if not draft["fields"]:
        raise ValueError("Declare at least one field to research")
    if not work["to_research"]:
        raise ValueError(f"Nothing new to research: every field is already filled in version {work['parent_version']}. Add a field or change a description, or reuse that version.")
    if not work["products"]:
        raise ValueError("The task corpus names no products to research")
    floor = request_floor(draft["runner"])
    if maximum < floor:
        raise ValueError(f"Preparation budget too low: {draft['runner']['model']} reserves up to ${floor:.2f} for one request before it is admitted. Set at least that much.")
    number = work["version"]
    claim = graph_dir / f"v{number:04d}.claimed"
    with studio.lock:
        if claim.exists() and not work["retrying_failed"]:
            raise ValueError(f"Version {number} was already dispatched. Inspect its events; a version is prepared once.")
        claim.unlink(missing_ok=True)
        with claim.open("x") as handle:
            handle.write(datetime.now(timezone.utc).isoformat())
            handle.flush()
            os.fsync(handle.fileno())
    events_path = graph_dir / f"v{number:04d}.events.jsonl"
    events_path.unlink(missing_ok=True)
    counter = {"n": 0}

    def emit(kind, **data):
        counter["n"] += 1
        event = {"id": counter["n"], "type": kind, "at": datetime.now(timezone.utc).isoformat(), **data}
        with events_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event

    parent = load_version(studio, identity, work["parent_version"]) if work["parent_version"] else None
    products, fields = work["products"], work["to_research"]
    emit("step_started", step="research", label=draft["name"], step_type="product-graph", version=number, fields=[f["path"] for f in fields])
    searches = {"n": 0}

    def research_tool(name, args):
        """Catalog searches go to the research log, like tool calls in an attempt, so a value can point back at them."""
        node = f"research:tool-{searches['n']}"
        searches["n"] += 1
        emit("node_started", node=node, label=name, arguments=args, step="research")
        value = _catalog_tool(name, args)
        emit("node_finished", node=node, label=name, output=value, status="completed", step="research")
        return value
    gateway = studio.gateway_for(draft["runner"], with_tools=True)
    brief = ("Products in the benchmark corpus: " + ", ".join(products) + "\n\nFields to fill for every product:\n"
             + "\n".join(f"- {f['path']} ({f['type']}): {f['description'] or 'no description'}" for f in fields)
             + ("\n\nResearch instructions from the author:\n" + draft["instructions"].strip() if draft["instructions"].strip() else "")
             + "\n\nReturn only a JSON object of the form {\"<product>\": {\"<field name without the product. prefix>\": value}} covering every product.")
    scope = f"product-graph-{identity}-v{number}"
    result = run_loop(gateway, system=RESEARCH_SYSTEM, brief=brief, execute_tool=research_tool, emit=emit, scope_id=scope,
                      scope_limit_usd=maximum, request_prefix=scope, max_turns=MAX_PREPARE_TURNS, step="research", budget=studio.budget)
    researched, problems = parse_knowledge(result.final_text or "", products, fields)
    answered = result.termination == "completed" and not any(p.startswith("The preparation answer") for p in problems)
    status = "failed" if not answered else ("incomplete" if _incomplete(problems) else "complete")
    carried_paths = {f["path"] for f in work["carried"]}
    records = {}
    for product in products:
        record = {k: v for k, v in ((parent or {}).get("records", {}).get(product, {})).items() if k in carried_paths}
        record.update(researched.get(product, {}))
        records[product] = record
    since = {f["path"]: f.get("since", parent["version"]) for f in (parent or {}).get("fields", [])} if parent else {}
    version_fields = [{**f, "since": number if f["path"] in {x["path"] for x in fields} else since.get(f["path"], number)} for f in draft["fields"]]
    emit("step_finished", step="research", label=draft["name"], status="completed" if answered else "error", output=result.final_text or result.error)
    body = {"schema": SCHEMA, "id": identity, "name": draft["name"], "version": number, "parent_version": work["parent_version"],
            "draft_revision": draft["revision"], "notes": draft.get("notes", ""), "fields": version_fields, "instructions": draft["instructions"],
            "runner": gateway.describe(), "products": products, "records": records if answered else {},
            "researched": [f["path"] for f in fields], "carried": sorted(carried_paths), "removed": work["removed"],
            "problems": problems, "status": status, "termination": result.termination, "error": result.error, "flags": result.flags,
            "turns": result.turns, "tool_calls": result.tool_calls, "cost_usd": str(Decimal(str(result.cost_usd))),
            "tokens": {"prompt": result.tokens_prompt, "cached": result.tokens_cached, "output": result.tokens_output},
            "prepared_at": datetime.now(timezone.utc).isoformat(), "maximum_usd": str(maximum), "final_text": result.final_text}
    version = {**body, "sha256": rm.sha256_json({k: v for k, v in body.items() if k != "final_text"})}
    write_json(graph_dir / f"v{number:04d}.json", version)
    return version


def request_floor(runner: dict) -> Decimal:
    """The first-request reservation of the researcher; a budget below it can never be admitted."""
    from wb_studio.runtime_registry import resolve_api_control
    control = resolve_api_control(runner)
    return Decimal(str(control["control"]["request_ceiling_usd"])) if control else Decimal(0)


def render(version: dict) -> str:
    """The knowledge as a system-prompt section for the steps downstream of a product-graph step."""
    paths = [f["path"] for f in version.get("fields", [])]
    lines = [f"Product graph '{version['name']}' v{version['version']} ({version['sha256'][:12]}; {len(version.get('records', {}))} products; fields: {', '.join(paths)}):"]
    for product, record in version.get("records", {}).items():
        if record:
            lines.append(f"- {product}: " + "; ".join(f"{_leaf(k)}: {json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}" for k, v in record.items()))
    return "\n".join(lines)


def _leaf(path: str) -> str:
    return path.split(".", 1)[1] if path.startswith("product.") else path


def _typed(value, kind: str) -> bool:
    return {"string": lambda v: isinstance(v, str), "number": lambda v: type(v) in (int, float) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool), "object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list)}[kind](value)


def parse_knowledge(text: str, products: list[str], fields: list[dict]) -> tuple[dict, list[str]]:
    """The model's JSON, filtered to known products and typed fields; problems listed, never invented."""
    problems = []
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except ValueError:
        return {}, ["The preparation answer was not a JSON object."]
    if not isinstance(data, dict):
        return {}, ["The preparation answer was not a JSON object."]
    knowledge = {}
    for product in products:
        record = data.get(product)
        if not isinstance(record, dict):
            problems.append(f"No record for {product}.")
            continue
        entry = {}
        for field in fields:
            leaf = _leaf(field["path"])
            value = record.get(leaf, record.get(field["path"]))
            if value is None:
                problems.append(f"{product}: {field['path']} missing.")
            elif not _typed(value, field["type"]):
                problems.append(f"{product}: {field['path']} is not a {field['type']}.")
            else:
                entry[field["path"]] = value
        knowledge[product] = entry
    extra = sorted(set(data) - set(products))
    if extra:
        problems.append("Ignored products outside the corpus: " + ", ".join(extra[:8]) + ("…" if len(extra) > 8 else ""))
    return knowledge, problems


def _incomplete(problems: list[str]) -> bool:
    """Missing or mistyped fields make a version incomplete; ignored extras are only noted."""
    return any(not p.startswith("Ignored products") for p in problems)


def _catalog_tool(name: str, args: dict) -> str:
    if name == "api_search":
        try:
            return api_search(str(args.get("query", "")), int(args.get("top_k") or 5))
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    return json.dumps({"error": f"{name} is not available while preparing a product graph; only api_search is."})
