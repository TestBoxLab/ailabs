"""Outcome-first reporting. Evaluator-side only; never supplied to competitors."""
from __future__ import annotations
import json
import re
from urllib.parse import urlsplit
from wb_results.store import Store

CATEGORIES = {"simple": "Everyday requests", "finance": "Finance", "hr": "People & HR", "marketing": "Marketing", "operations": "Operations", "sales": "Sales", "support": "Customer support"}

def words(value):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(value)).replace("_", " ")

def public_task(task):
    brief = task["prompt"][1]["content"]
    first = " ".join(brief.split())
    title = first if len(first) <= 180 else first[:177].rsplit(" ", 1)[0] + "..."
    return {"id": task["task"], "title": title, "brief": brief,
            "category": CATEGORIES.get(task["task"].split(".")[0], "Other"),
            "applications": [words(k).title() for k in task["info"].get("initial_state", {}) if not k.startswith("_") and k != "meta"],
            "source": "AutomationBench imported corpus", "version": "Frozen local import"}

def decode(value):
    if isinstance(value, str):
        try: return json.loads(value)
        except ValueError: pass
    return value

def action(event, completion):
    args = event.get("arguments", {})
    method = args.get("method", "GET")
    service = urlsplit(args.get("url", "")).hostname or "application"
    service = "Salesforce" if "salesforce" in service else "Gmail" if "gmail" in service or "googleapis" in service else service.split(".")[0].title()
    body = decode(args.get("body"))
    if event.get("label") == "api_search":
        title, detail = "Find the right action", 'Searched available application actions for "' + str(args.get("query", "")) + '".'
    elif event.get("label") == "api_fetch":
        title = {"GET": "Read", "PATCH": "Update", "PUT": "Update", "POST": "Create", "DELETE": "Delete"}.get(method, "Use") + " in " + service
        detail = "; ".join(words(k).capitalize() + ": " + str(v) for k, v in body.items()) if isinstance(body, dict) else "Requested records from " + service + "." if method == "GET" else "Submitted an application change."
    else:
        title, detail = "Prepare the next action", "Processed content for the task."
    return {"title": title, "detail": detail, "event_id": event["id"], "node": event.get("node"),
            "status": "pending" if completion is None else "error" if completion.get("status") == "error" else "observed",
            "qualification": "Application response recorded; outcome checked separately."}

def requirement(assertion, index):
    if "field" in assertion and "value" in assertion:
        return words(assertion["field"]).capitalize() + " should be " + str(assertion["value"])
    if assertion.get("description"): return assertion["description"]
    return words(assertion.get("type", "Requirement " + str(index + 1))).capitalize()

def outcome_report(job, events, tasks, database=None):
    rows = {}
    if database and database.exists():
        store = Store(database)
        try: rows = {(r["task_id"], r["arm"]): r for r in store.episodes(run=job["id"])["rows"]}
        finally: store.close()
    reports = []
    for result in job["results"]:
        task_id, model = result["task"], result["model"]
        trace = [e for e in events if e.get("task") == task_id and e.get("model") == model]
        row = rows.get((task_id, model), {})
        changes = row.get("unexpected_changes", result.get("unexpected_changes", []))
        checks = result.get("checks", [])
        assertions = tasks.get(task_id, {}).get("info", {}).get("assertions", [])
        requirements = [{"title": requirement(assertions[i], i) if i < len(assertions) else words(c["type"]).capitalize(),
                         "passed": c["passed"], "check_index": i} for i, c in enumerate(checks) if c["type"] != "allowed_changes_only"]
        invariant = row.get("invariant_passed", next((c["passed"] for c in checks if c["type"] == "allowed_changes_only"), None))
        infra = result["termination"].startswith("infra:")
        title = "Execution could not be evaluated" if infra else "Task completed correctly" if result["passed"] else "Requested work changed more than allowed" if changes else "Task requirements were not all satisfied"
        summary = "The run stopped before it produced a valid quality measurement." if infra else f'{sum(c["passed"] for c in requirements)} of {len(requirements)} recorded requirements met.'
        if invariant is False: summary += " Changes outside the permitted scope caused the overall failure."
        elif invariant is True: summary += " No changes outside the permitted scope were found."
        elif not result["passed"] and all(c["passed"] for c in requirements): summary += " Visible requirement checks passed, but the overall verdict did not; inspect the full evaluator evidence."
        actions = [action(e, next((end for end in trace if end.get("node") == e.get("node") and end["type"] == "node_finished"), None)) for e in trace if e["type"] == "node_started"]
        reports.append({"task": task_id, "model": model, "title": title, "summary": summary, "passed": result["passed"], "infrastructure": infra,
                        "requirements": [] if infra else requirements, "scope_respected": None if infra else invariant, "unexpected_changes": changes, "change_summaries": [change_summary(c) for c in changes], "actions": actions,
                        "basis": "Recorded actions and deterministic task checks", "causal_claim": None,
                        "next_question": "Was the right entity selected, and were all required effects produced without additional changes?" if not result["passed"] else "Does this result repeat on the same frozen task under independent attempts?",
                        "event_ids": [e["id"] for e in trace], "limitations": "This account describes evidence. A reasoning-model review is a separate interpretation, not a replacement verdict."})
    return {"version": 1, "run": job["id"], "attempts": reports}


def change_summary(change):
    service = words(change.get("service", "Application")).title()
    path = change.get("path", "record")
    field = words(re.sub(r"\[.*?\]", "", path.split(".")[-1])).replace("label ids", "message labels")
    before, after = change.get("before"), change.get("after")
    return service + " " + field + " changed from " + str(before) + " to " + str(after) + "."
