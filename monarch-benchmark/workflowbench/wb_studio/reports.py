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

def tool_error(completion):
    """The error a tool call ended with, whether the harness raised or the
    application answered with an error body ({"error": {"code", "message"}})."""
    if completion is None:
        return None
    output = decode(completion.get("output"))
    if completion.get("status") == "error":
        return (output.get("error") if isinstance(output, dict) else None) or completion.get("output") or "tool failed"
    if isinstance(output, dict) and output.get("error"):
        return output["error"]
    return None


def _error_text(error):
    if isinstance(error, dict):
        return " ".join(str(error[k]) for k in ("code", "message") if error.get(k) not in (None, "")) or json.dumps(error)
    return str(error)


def resolve_service(url: str) -> str:
    """Resolve the service name from the full host and path, distinguishing Google services."""
    parsed = urlsplit(url or "")
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if not host:
        return "application"
    if "salesforce" in host:
        return "Salesforce"
    if host.endswith(".googleapis.com") or host == "googleapis.com" or host.endswith(".google.com"):
        if host.startswith("googleads.") or "googleads" in host:
            return "Google Ads"
        if host.startswith("sheets.") or "sheets" in host:
            return "Google Sheets"
        if host.startswith("calendar.") or "/calendar" in path:
            return "Google Calendar"
        if host.startswith("drive.") or "/drive" in path:
            return "Google Drive"
        if host.startswith("gmail.") or "gmail" in host or "/gmail" in path:
            return "Gmail"
        first = host.split(".")[0]
        if first not in ("www", "api"):
            return first.replace("_", " ").title()
        return "Google"
    if "airtable" in host:
        return "Airtable"
    if "mailchimp" in host:
        return "Mailchimp"
    if "slack" in host:
        return "Slack"
    if "freshdesk" in host:
        return "Freshdesk"
    if "hubapi" in host or "hubspot" in host:
        return "HubSpot"
    if "github" in host:
        return "GitHub"
    if "notion" in host:
        return "Notion"
    if "asana" in host:
        return "Asana"
    if "linear" in host:
        return "Linear"
    if "atlassian" in host or "jira" in host:
        return "Jira"
    if "gorgias" in host:
        return "Gorgias"
    if "stripe" in host:
        return "Stripe"
    if "zendesk" in host:
        return "Zendesk"
    if "intercom" in host:
        return "Intercom"
    parts = host.split(".")
    sub = parts[0]
    if sub in ("api", "www", "app", "rest", "us1") and len(parts) > 1:
        sub = parts[1]
    return sub.replace("_", " ").title()


def action(event, completion):
    args = event.get("arguments", {})
    error = tool_error(completion)
    method = args.get("method", "GET")
    service = resolve_service(args.get("url", ""))
    body = decode(args.get("body"))
    if event.get("label") == "api_search":
        title, detail = "Find the right action", 'Searched available application actions for "' + str(args.get("query", "")) + '".'
    elif event.get("label") == "api_fetch":
        title = {"GET": "Read", "PATCH": "Update", "PUT": "Update", "POST": "Create", "DELETE": "Delete"}.get(method, "Use") + " in " + service
        detail = "; ".join(words(k).capitalize() + ": " + str(v) for k, v in body.items()) if isinstance(body, dict) else "Requested records from " + service + "." if method == "GET" else "Submitted an application change."
    else:
        title, detail = "Prepare the next action", "Processed content for the task."
    return {"title": title, "detail": detail, "event_id": event["id"], "node": event.get("node"),
            "method": method if event.get("label") == "api_fetch" else None, "url": args.get("url"),
            "status": "pending" if completion is None else "error" if error is not None else "observed",
            "error": _error_text(error) if error is not None else None,
            "qualification": "Application response recorded; outcome checked separately."}

IDENTITY_KEYS = ("to", "channel", "channel_name", "action_key")
SKIPPED_KEYS = ("type", "repair_contract")


def _text(value):
    if isinstance(value, list):
        return ", ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(words(k) + " " + _text(v) for k, v in value.items())
    return str(value)


def requirement(assertion, index):
    """One line naming the check and what it looks for: the type's words with
    the assertion's values slotted in ("sent to" + to), the rest appended."""
    if "field" in assertion and "value" in assertion:
        return words(assertion["field"]).capitalize() + " should be " + str(assertion["value"])
    if assertion.get("description"): return assertion["description"]
    kind = assertion.get("type")
    if not kind: return "Requirement " + str(index + 1)
    label, parts = words(kind), []
    for key, value in assertion.items():
        if key in SKIPPED_KEYS: continue
        name, text = words(key), _text(value)
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        if pattern.search(label):
            label = pattern.sub(lambda m: name.replace("contains", "containing") + " " + text, label, count=1)
        else:
            parts.append(name + " " + text)
    label = "; ".join([label] + parts)
    return label[:1].upper() + label[1:]


def _record(assertion):
    collection, parts = assertion.get("collection"), []
    for key, value in assertion.items():
        if key.endswith("_id"):
            parts.append((collection if key == "record_id" and collection else key[:-3].replace("_", " ")) + " " + str(value))
        elif key in IDENTITY_KEYS:
            parts.append(words(key.replace("_name", "")) + " " + str(value))
    return "; ".join(parts) or None


def requirement_facts(assertion):
    """The record, field and expected value a check names, for the Checks tab."""
    field = assertion.get("field") or assertion.get("column")
    rest = {k: v for k, v in assertion.items()
            if not k.endswith("_id") and k not in IDENTITY_KEYS and k not in SKIPPED_KEYS + ("field", "column", "collection")}
    expected = _text(rest["value"]) if list(rest) == ["value"] else "; ".join(words(k) + " " + _text(v) for k, v in rest.items())
    return {"record": _record(assertion), "field": words(field) if field else None, "expected": expected or None}


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
                         "passed": c["passed"], "check_index": i, **requirement_facts(assertions[i] if i < len(assertions) else {})}
                        for i, c in enumerate(checks) if c["type"] != "allowed_changes_only"]
        invariant = row.get("invariant_passed", next((c["passed"] for c in checks if c["type"] == "allowed_changes_only"), None))
        infra = result["termination"].startswith("infra:")
        title = "Execution could not be evaluated" if infra else "Task completed correctly" if result["passed"] else "Requested work changed more than allowed" if changes else "Task requirements were not all satisfied"
        summary = "The run stopped before it produced a valid quality measurement." if infra else f'{sum(c["passed"] for c in requirements)} of {len(requirements)} recorded requirements met.'
        if invariant is False: summary += " Changes outside the permitted scope caused the overall failure."
        elif invariant is True: summary += " No changes outside the permitted scope were found."
        elif not result["passed"] and all(c["passed"] for c in requirements): summary += " Visible requirement checks passed, but the overall verdict did not; inspect the full evaluator evidence."
        ends = {}
        for e in trace:
            if e["type"] == "node_finished":
                ends.setdefault(e.get("node"), e)
        actions = [action(e, ends.get(e.get("node"))) for e in trace if e["type"] == "node_started"]
        reports.append({"task": task_id, "model": model, "title": title, "summary": summary, "passed": result["passed"], "infrastructure": infra,
                        "requirements": [] if infra else requirements, "scope_respected": None if infra else invariant, "unexpected_changes": changes, "change_summaries": [change_summary(c) for c in changes], "changes": [change_row(c) for c in changes], "actions": actions,
                        "basis": "Recorded actions and deterministic task checks", "causal_claim": None,
                        "next_question": "Was the right entity selected, and were all required effects produced without additional changes?" if not result["passed"] else "Does this result repeat on the same frozen task under independent attempts?",
                        "event_ids": [e["id"] for e in trace], "limitations": "This account describes evidence. A reasoning-model review is a separate interpretation, not a replacement verdict."})
        from wb_studio.narrative import story
        reports[-1]["story"] = story(result, trace, reports[-1], assertions)
    from wb_studio.performance import performance_report
    return {"version": 1, "run": job["id"], "attempts": reports,
            "performance": performance_report(job, events)}


def _singular(name):
    return name[:-3] + "y" if name.endswith("ies") else name[:-1] if name.endswith("s") else name


def _record_and_field(path):
    """gmail.messages[id=msg_9].label_ids[0] -> ("message msg_9", "labels")."""
    segments = re.findall(r"[^.\[\]]+(?:\[[^\]]*\])?", str(path))[1:]
    records, field = [], None
    for segment in segments:
        name, _, key = segment.partition("[")
        if key and not key.rstrip("]").isdigit():
            records.append(_singular(words(name)) + " " + key.rstrip("]").removeprefix("id="))
        else:
            field = words(name).replace("label ids", "labels")
    return "; ".join(records) or None, field


def change_row(change):
    record, field = _record_and_field(change.get("path", "record"))
    return {"service": words(change.get("service", "Application")).title(), "record": record, "field": field,
            "op": change.get("op") or "changed", "before": change.get("before"), "after": change.get("after")}


def change_summary(change):
    row = change_row(change)
    subject = " ".join(p for p in (row["service"], row["record"]) if p)
    if row["op"] in ("added", "removed") and not row["field"]:
        return subject + " " + row["op"] + "."
    if "<object>" in (row["before"], row["after"]):
        return subject + " " + (row["field"] or "record") + " " + row["op"] + "."
    return subject + " " + (row["field"] or "record") + " changed from " + str(row["before"]) + " to " + str(row["after"]) + "."
