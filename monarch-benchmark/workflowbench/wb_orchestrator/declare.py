"""wb corpus declare: derive the dual-invariant contract for imported tasks.

AutomationBench tasks carry assertions only. Two mechanical rules give the
invariant without judgment calls:

  expected_changes  <- one matcher per assertion, from its type:
      *_field_equals / *_has_property / *_field_contains with a record id
          -> op "changed" on <service>.<collection>[id=<id>].<field>
      *_exists / *_sent / *_in_* (a record must appear)
          -> op "added" on <service>.<collection>[*]  (collection from the
             world model; "*" when the service only logs actions)
  allowed_changes   <- SIDE_EFFECTS: housekeeping a real platform performs
      alongside the asked-for write (read markers, thread updates, the
      Salesforce is_closed/is_won pair when a stage closes). Kept short; the
      next run's unexpected_changes is the review queue for additions.

Derivation is deterministic, so re-running is idempotent. The contract hash
changes; tasks that already ran under the old contract will not regrade.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from wb_orchestrator.orchestrator import contract_hash

# assertion type -> (service, collection or "*", id key or None)
_TYPES: dict[str, tuple[str, str, str | None]] = {
    "airtable_record_exists": ("airtable", "*", None),
    "asana_action_exists": ("asana", "actions", None),
    "trello_action_exists": ("trello", "actions", None),
    "jira_action_exists": ("jira", "*", None),
    "jira_issue_exists_with_summary": ("jira", "*", None),
    "buffer_post_exists": ("buffer", "posts", None),
    "gmail_message_sent": ("gmail", "messages", None),
    "google_calendar_event_exists": ("google_calendar", "events", None),
    "google_sheets_row_exists": ("google_sheets", "rows", None),
    "hubspot_contact_exists": ("hubspot", "contacts", None),
    "hubspot_deal_exists": ("hubspot", "deals", None),
    "hubspot_contact_has_property": ("hubspot", "contacts", None),
    "mailchimp_subscriber_in_list": ("mailchimp", "*", None),
    "salesforce_case_exists": ("salesforce", "cases", None),
    "salesforce_note_exists": ("salesforce", "notes", None),
    "salesforce_task_exists": ("salesforce", "tasks", None),
    "salesforce_record_exists": ("salesforce", "$collection", None),
    "salesforce_contact_exists_with_field": ("salesforce", "contacts", None),
    "salesforce_lead_exists_with_field": ("salesforce", "leads", None),
    "salesforce_contact_field_equals": ("salesforce", "contacts", "contact_id"),
    "salesforce_lead_field_equals": ("salesforce", "leads", "lead_id"),
    "salesforce_lead_field_contains": ("salesforce", "leads", "lead_id"),
    "salesforce_field_equals": ("salesforce", "$collection", "record_id"),
    "slack_direct_message_sent": ("slack", "*", None),
    "slack_message_exists": ("slack", "messages", None),
    "slack_message_in_channel": ("slack", "messages", None),
    "zendesk_ticket_exists": ("zendesk", "tickets", None),
    "zoom_meeting_exists": ("zoom", "meetings", None),
    "zoom_meeting_exists_with_field": ("zoom", "meetings", None),
}

# Assertion field names that differ from the world-model field they check.
_FIELD_ALIAS = {"stage": "stage_name"}

# Legitimate side effects: (service, condition, matchers). condition is a
# substring of any expected path that must be present, or None for "always
# when the service is seeded".
SIDE_EFFECTS: list[tuple[str, str | None, list[dict[str, Any]]]] = [
    ("gmail", None, [
        {"service": "gmail", "op": "*", "path": "gmail.messages[*].is_read"},
        {"service": "gmail", "op": "*", "path": "gmail.messages[*].label_ids"},
        {"service": "gmail", "op": "*", "path": "gmail.threads*"},
    ]),
    ("salesforce", ".stage_name", [
        {"service": "salesforce", "op": "*", "path": "salesforce.opportunities[*].is_closed"},
        {"service": "salesforce", "op": "*", "path": "salesforce.opportunities[*].is_won"},
        {"service": "salesforce", "op": "*", "path": "salesforce.opportunities[*].probability"},
    ]),
    ("google_sheets", None, [
        {"service": "google_sheets", "op": "changed", "path": "google_sheets.worksheets*"},
        {"service": "google_sheets", "op": "changed", "path": "google_sheets.spreadsheets*"},
    ]),
    ("slack", None, [
        {"service": "slack", "op": "changed", "path": "slack.channels*"},
        {"service": "slack", "op": "changed", "path": "slack.dms*"},
    ]),
]


def derive(task: dict[str, Any]) -> dict[str, Any]:
    """Return {"expected": [...], "allowed": [...], "unmapped": [types]}."""
    expected: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for a in task["info"].get("assertions", []):
        spec = _TYPES.get(a["type"])
        if spec is None:
            unmapped.append(a["type"])
            continue
        service, collection, id_key = spec
        if collection == "$collection":
            collection = a.get("collection", "*")
        field = _FIELD_ALIAS.get(a.get("field") or a.get("property") or "", a.get("field") or a.get("property"))
        rid = a.get(id_key) if id_key else None
        if rid and field:
            m = {"service": service, "op": "changed",
                 "path": f"{service}.{collection}[id={rid}].{field}"}
        elif field and collection != "*":
            # property asserted on a record found by a non-id key: created or changed
            m = {"service": service, "op": "*", "path": f"{service}.{collection}[*].{field}"}
        else:
            m = {"service": service, "op": "added",
                 "path": f"{service}.{collection}[*]" if collection != "*" else f"{service}.*"}
        if m not in expected:
            expected.append(m)

    seeded = set(task["info"].get("initial_state", {}).keys())
    touched = seeded | {m["service"] for m in expected}
    allowed: list[dict[str, Any]] = []
    paths = " ".join(m["path"] for m in expected)
    for service, cond, matchers in SIDE_EFFECTS:
        if service in touched and (cond is None or cond in paths):
            allowed.extend(m for m in matchers if m not in allowed)
    return {"expected": expected, "allowed": allowed, "unmapped": sorted(set(unmapped))}


def declare_dir(src: str | Path, out: str | Path | None = None,
                overwrite: bool = False) -> dict[str, Any]:
    """Write declared copies. out=None means in place (only with overwrite)."""
    src = Path(src)
    dst = Path(out) if out else src
    if dst == src and not overwrite:
        raise ValueError("declaring in place rewrites contract hashes; pass overwrite=True")
    dst.mkdir(parents=True, exist_ok=True)
    report = {"declared": 0, "already_declared": 0, "unmapped": {}, "tasks": []}
    for p in sorted(src.glob("*.json")):
        task = json.loads(p.read_text(encoding="utf-8"))
        info = task["info"]
        if info.get("expected_changes") and not overwrite:
            report["already_declared"] += 1
            if dst != src:
                (dst / p.name).write_text(json.dumps(task, indent=1, default=str), encoding="utf-8")
            continue
        d = derive(task)
        if d["unmapped"]:
            report["unmapped"][task["task"]] = d["unmapped"]
        info["expected_changes"] = d["expected"]
        info["allowed_changes"] = d["allowed"]
        task["contract_sha256"] = contract_hash(task)
        (dst / p.name).write_text(json.dumps(task, indent=1, default=str), encoding="utf-8")
        report["declared"] += 1
        report["tasks"].append({"task": task["task"], "n_expected": len(d["expected"]),
                                "n_allowed": len(d["allowed"])})
    return report
