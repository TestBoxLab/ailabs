"""The approval rule for the six scored domains must allow exactly what the
assertions require.

Found on 6 Sep 2026: `finance.qb_void_stale_invoices` asked for QuickBooks
invoices to be voided and people e-mailed; a competitor that did exactly that
still failed, because the derivation mapped none of those assertion types and
so declared no matcher for them. Every real change landed in
`unexpected_changes`. 218 of the 600 scored tasks derived no rule at all.

The two halves of every test here: the change the assertions require must
pass, and one extra change on another record must still fail.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from grader.grade import grade
from grader.invariant import check_invariant
from wb_orchestrator.declare import derive, load_side_effects
from wb_world.snapshot import diff_snapshots

ROOT = Path(__file__).resolve().parents[1]
SIDE_EFFECTS = load_side_effects(ROOT / "config" / "side-effects.yaml")
SCORED = ("finance", "hr", "marketing", "operations", "sales", "support")


def _graded(task, s0, s1):
    """Grade with the freshly derived rule rather than whatever is on disk."""
    task = copy.deepcopy(task)
    d = derive(task, SIDE_EFFECTS)
    task["info"]["expected_changes"] = d["expected"]
    task["info"]["allowed_changes"] = d["allowed"]
    return grade(task, s0, s1)


def _invariant(task, s0, s1):
    """Only the "nothing else changed" half, on a synthetic world.

    The drawn-set regression builds the minimal satisfying change from the
    matchers themselves, so the records are skeletons that the vendor's
    pydantic world model would refuse. The assertions are not what is under
    test here; the invariant is.
    """
    d = derive(task, SIDE_EFFECTS)
    return check_invariant(diff_snapshots(s0, s1), d["expected"], d["allowed"])


def _task(assertions, initial_state):
    return {"task": "t", "prompt": "p", "answer": "",
            "info": {"assertions": assertions, "initial_state": initial_state,
                     "zapier_tools": [], "expected_changes": [], "allowed_changes": []}}


# --------------------------------------------------------------- the reported defect

def test_the_reported_task_passes_when_the_assertions_are_satisfied():
    """finance.qb_void_stale_invoices: void two invoices, mail two people, post to Slack."""
    task = json.loads((ROOT / "tasks" / "tier-complex"
                       / "finance.qb_void_stale_invoices.json").read_text(encoding="utf-8"))
    s0 = copy.deepcopy(task["info"]["initial_state"])
    s1 = copy.deepcopy(s0)
    for inv in s1["quickbooks"]["invoices"]:
        if inv["id"] in ("qi_601", "qi_602"):
            inv["voided"] = True
            inv["balance"] = 0            # the void endpoint's own side effect
    for who in ("alice", "bob"):
        s1["gmail"]["messages"].append(
            {"id": f"m_{who}", "to": [f"{who}@company.example.com"], "cc": [],
             "label_ids": ["SENT"], "subject": "Invoice voided",
             "body_plain": "Your stale invoice was voided."})
    s1["slack"]["messages"].append(
        {"id": "sm_summary", "channel_id": "C_BILLING", "user_id": "U_BOT",
         "text": "Voided qi_601 and qi_602"})

    g = _graded(task, s0, s1)
    assert g["invariant"]["passed"], (g["invariant"]["missing_expected"],
                                      g["invariant"]["unexpected_changes"])


def test_the_reported_task_still_fails_on_a_collateral_write():
    task = json.loads((ROOT / "tasks" / "tier-complex"
                       / "finance.qb_void_stale_invoices.json").read_text(encoding="utf-8"))
    s0 = copy.deepcopy(task["info"]["initial_state"])
    s1 = copy.deepcopy(s0)
    for inv in s1["quickbooks"]["invoices"]:
        if inv["id"] in ("qi_601", "qi_602"):
            inv["voided"] = True
    # qi_603 must stay untouched: the task asserts voided == "false" on it
    for inv in s1["quickbooks"]["invoices"]:
        if inv["id"] == "qi_603":
            inv["balance"] = 999
    assert not _graded(task, s0, s1)["invariant"]["passed"]


# --------------------------------------------------------------- per assertion type

def test_gmail_sent_to_allows_an_added_message_and_nothing_else():
    task = _task([{"type": "gmail_message_sent_to", "to": "a@x.com"}],
                 {"gmail": {"messages": []}, "slack": {"messages": []}})
    s0 = copy.deepcopy(task["info"]["initial_state"])
    s1 = copy.deepcopy(s0)
    s1["gmail"]["messages"].append({"id": "m1", "to": ["a@x.com"], "cc": [],
                                    "label_ids": ["SENT"], "subject": "s",
                                    "body_plain": "b"})
    assert _graded(task, s0, s1)["invariant"]["passed"]
    s1["slack"]["messages"].append({"id": "s1", "channel_id": "C", "user_id": "U",
                                    "text": "extra"})
    assert not _graded(task, s0, s1)["invariant"]["passed"]


def test_a_not_sent_assertion_allows_nothing_extra():
    """A negative assertion is satisfied by doing nothing; it grants no change."""
    task = _task([{"type": "gmail_message_not_sent_to", "to": "a@x.com"}],
                 {"gmail": {"messages": []}})
    assert derive(task, SIDE_EFFECTS)["expected"] == []


def test_sheets_row_exists_allows_a_row_on_that_sheet_only():
    task = _task([{"type": "google_sheets_row_exists", "spreadsheet_id": "ss_a",
                   "worksheet_id": "ws_a", "cell_contains": {"Name": "X"}}],
                 {"google_sheets": {"spreadsheets": [], "worksheets": [], "rows": []}})
    s0 = copy.deepcopy(task["info"]["initial_state"])
    s1 = copy.deepcopy(s0)
    s1["google_sheets"]["rows"].append(
        {"id": "r1", "spreadsheet_id": "ss_a", "worksheet_id": "ws_a", "row_id": 2,
         "cells": {"Name": "X"}})
    assert _graded(task, s0, s1)["invariant"]["passed"]


def test_quickbooks_field_equals_allows_that_field_on_that_record_only():
    state = {"quickbooks": {"invoices": [{"id": "qi_1", "balance": 10, "voided": False},
                                         {"id": "qi_2", "balance": 20, "voided": False}]}}
    task = _task([{"type": "quickbooks_invoice_field_equals", "id": "qi_1",
                   "field": "voided", "value": "true"}], state)
    s0 = copy.deepcopy(state)
    s1 = copy.deepcopy(s0)
    s1["quickbooks"]["invoices"][0]["voided"] = True
    assert _graded(task, s0, s1)["invariant"]["passed"]
    s1["quickbooks"]["invoices"][1]["voided"] = True      # a second record
    assert not _graded(task, s0, s1)["invariant"]["passed"]


def test_action_exists_allows_that_action_key_only():
    state = {"monday": {"actions": {}}}
    task = _task([{"type": "monday_action_exists", "action_key": "create_item",
                   "params": {"name_contains": "X"}}], state)
    s0 = copy.deepcopy(state)
    s1 = copy.deepcopy(s0)
    s1["monday"]["actions"]["create_item"] = [{"id": "a1", "action_key": "create_item",
                                               "params": {"item_name": "X"}}]
    assert _graded(task, s0, s1)["invariant"]["passed"]
    s1["monday"]["actions"]["delete_item"] = [{"id": "a2", "action_key": "delete_item",
                                               "params": {}}]
    assert not _graded(task, s0, s1)["invariant"]["passed"]


def test_slack_message_exists_allows_an_added_message():
    task = _task([{"type": "slack_message_exists", "channel_name": "ops",
                   "text_contains": "hi"}],
                 {"slack": {"messages": [], "channels": []}})
    s0 = copy.deepcopy(task["info"]["initial_state"])
    s1 = copy.deepcopy(s0)
    s1["slack"]["messages"].append({"id": "s1", "channel_id": "C_OPS", "user_id": "U",
                                    "text": "hi"})
    assert _graded(task, s0, s1)["invariant"]["passed"]


def test_ticket_has_tag_allows_that_ticket_only():
    state = {"zendesk": {"tickets": [{"id": "t1", "subject": "a", "tags": []},
                                     {"id": "t2", "subject": "b", "tags": []}]}}
    task = _task([{"type": "zendesk_ticket_has_tag", "ticket_id": "t1", "tag": "x"}],
                 state)
    s0 = copy.deepcopy(state)
    s1 = copy.deepcopy(s0)
    s1["zendesk"]["tickets"][0]["tags"] = ["x"]
    assert _graded(task, s0, s1)["invariant"]["passed"]
    s1["zendesk"]["tickets"][1]["tags"] = ["x"]
    assert not _graded(task, s0, s1)["invariant"]["passed"]


def test_calendar_event_exists_allows_an_added_event():
    task = _task([{"type": "google_calendar_event_exists", "summary": "Review"}],
                 {"google_calendar": {"events": [], "calendars": []}})
    s0 = copy.deepcopy(task["info"]["initial_state"])
    s1 = copy.deepcopy(s0)
    s1["google_calendar"]["events"].append({"id": "e1", "summary": "Review"})
    assert _graded(task, s0, s1)["invariant"]["passed"]


def test_salesforce_field_equals_uses_the_named_collection():
    state = {"salesforce": {"opportunities": [{"id": "o1", "stage_name": "New"},
                                              {"id": "o2", "stage_name": "New"}]}}
    task = _task([{"type": "salesforce_field_equals", "collection": "opportunities",
                   "record_id": "o1", "field": "stage_name", "value": "Won"}], state)
    s0 = copy.deepcopy(state)
    s1 = copy.deepcopy(s0)
    s1["salesforce"]["opportunities"][0]["stage_name"] = "Won"
    assert _graded(task, s0, s1)["invariant"]["passed"]
    s1["salesforce"]["opportunities"][1]["stage_name"] = "Won"
    assert not _graded(task, s0, s1)["invariant"]["passed"]


# --------------------------------------------------------------- coverage over the corpus

def _scored_tasks():
    for domain in SCORED:
        for p in sorted((ROOT / "corpus" / f"imported-{domain}").glob("*.json")):
            yield domain, p, json.loads(p.read_text(encoding="utf-8"))


def test_every_positive_assertion_type_in_the_scored_domains_is_mapped():
    """The 218 tasks that derived no rule must now derive one."""
    unmapped: dict[str, int] = {}
    no_rule = []
    for _domain, _p, task in _scored_tasks():
        d = derive(task, SIDE_EFFECTS)
        for t in d["unmapped"]:
            unmapped[t] = unmapped.get(t, 0) + 1
        if not d["expected"]:
            no_rule.append(task["task"])
    assert not unmapped, f"unmapped assertion types: {sorted(unmapped)}"
    # A task whose assertions are *all* negative legitimately requires no change.
    for name in no_rule:
        task = next(t for _d, _p, t in _scored_tasks() if t["task"] == name)
        from automationbench.rubric.registry import AssertionRegistry
        import automationbench.rubric.assertions  # noqa: F401
        assert all(AssertionRegistry.is_negative(a["type"])
                   for a in task["info"]["assertions"]), name


@pytest.mark.parametrize("set_name", ["tier-simple", "tier-medium", "tier-complex",
                                      "random-10"])
def test_drawn_sets_pass_when_the_expected_changes_are_applied(set_name):
    """For every drawn task, applying its own declared expected changes to the
    initial state must satisfy the invariant. A rule that forbids what it
    itself demands is the defect this file exists for."""
    paths = sorted((ROOT / "tasks" / set_name).glob("*.json"))
    assert paths, set_name
    for p in paths:
        task = json.loads(p.read_text(encoding="utf-8"))
        expected = derive(task, SIDE_EFFECTS)["expected"]
        # A service a task writes to but the seed never mentions (gmail, most
        # often) starts as an empty collection rather than absent, so the diff
        # shows the added record and not the whole service node appearing.
        s0 = copy.deepcopy(task["info"]["initial_state"])
        for m in expected:
            service, _, rest = m["path"].partition(".")
            collection = rest.split("[")[0].split(".")[0]
            if not collection:
                continue
            default: Any = {} if collection == "actions" else []
            node = s0.setdefault(service, {}).setdefault(collection, default)
            # `[*].field` can only be satisfied by changing a record that
            # already exists, so an empty collection gets one to change.
            field = re.match(r".*\[\*\]\.(.+?)\*?$", m["path"])
            if field and isinstance(node, list) and not node:
                node.append({"id": "seed_0", field.group(1): ""})
        s1 = apply_expected(s0, expected)
        inv = _invariant(task, s0, s1)
        assert inv["passed"], (p.name, inv["missing_expected"],
                               inv["unexpected_changes"])


def apply_expected(s0: dict, expected: list[dict]) -> dict:
    """Make the minimal change each expected matcher asks for.

    A matcher path is `<service>.<collection>[<selector>]` optionally followed
    by `.<field>`. `[id=X]` names a record that must already exist, so the
    field on it is flipped to a different value; `[*]` means a record must
    appear, so one is appended. This is the oracle-like change: exactly what
    the rule demands and nothing else.
    """
    s1 = copy.deepcopy(s0)
    for i, m in enumerate(expected):
        # An action log: <service>.actions.<action_key>*
        log = re.match(r"([^.]+)\.actions(?:\.([^.*\[]+))?\*?$", m["path"])
        if log:
            service, key = log.groups()
            key = key or "createRecord"   # a matcher with no action_key: any key
            # A `where` matcher names the content the write must carry, so the
            # oracle-like change writes exactly that and nothing more.
            params: dict[str, Any] = {}
            for dotted, value in (m.get("where") or {}).items():
                target, _, leaf = dotted.rpartition(".")
                node = params
                for part in target.split(".")[1:]:   # drop the leading "params"
                    node = node.setdefault(part, {})
                node[leaf] = value
            record = {"id": f"a_{i}", "action_key": key, "params": params}
            actions = s1.setdefault(service, {}).setdefault("actions", {})
            if isinstance(actions, list):          # a service that logs a flat list
                actions.append(record)
            else:
                actions.setdefault(key, []).append(record)
            continue
        # A worksheet: google_sheets.spreadsheets[id=..].worksheets[id=..]*
        ws = re.match(r"google_sheets\.spreadsheets(?:\[id=([^\]]+)\])?"
                      r"(?:\.worksheets(?:\[id=([^\]]+)\])?)?\*?$", m["path"])
        if ws:
            ssid, wsid = ws.groups()
            sheets = (s1.setdefault("google_sheets", {})
                        .setdefault("spreadsheets", []))
            sheet = next((s for s in sheets
                          if ssid is None or str(s.get("id")) == ssid),
                         sheets[0] if sheets else None)
            if sheet is None:
                continue
            worksheets = sheet.setdefault("worksheets", [])
            sheet_ws = next((w for w in worksheets
                             if wsid is None or str(w.get("id")) == wsid),
                            worksheets[0] if worksheets else None)
            if sheet_ws is None:
                continue
            sheet_ws.setdefault("rows", []).append(
                {"row_id": 9000 + i, "cells": {"x": "y"}})
            continue
        # A whole-service wildcard: any change under it will do.
        whole = re.match(r"([^.]+)\.\*$", m["path"])
        if whole:
            service = whole.group(1)
            node = s1.setdefault(service, {})
            collection = next((k for k, v in node.items() if isinstance(v, list)),
                              "records")
            node.setdefault(collection, []).append({"id": f"new_{i}"})
            continue
        parsed = re.match(r"([^.]+)\.([^.\[]+)\[([^\]]*)\](?:\.(.+?))?\*?$", m["path"])
        if not parsed:
            continue                      # a shape the matcher set does not use
        service, collection, selector, field = parsed.groups()
        field = field.rstrip("*") if field else None
        records = s1.setdefault(service, {}).setdefault(collection, [])
        if not isinstance(records, list):
            continue
        if selector.startswith("id="):
            rid = selector[3:]
            rec = next((r for r in records if isinstance(r, dict)
                        and str(r.get("id")) == rid), None)
            if rec is None:
                continue                  # the seed does not carry it; nothing to change
            # No field means "this record must change somehow"; pick any field
            # it already has rather than inventing one the schema would refuse.
            key = field or next((k for k in rec if k != "id"), "note")
            rec[key] = _flip(rec.get(key))
        elif field:
            # `[*].field` asks for that field to change on some record of the
            # collection. A record created whole diffs as one `added` at record
            # level, never at field level, so the change is made on a record
            # the seed already carries; an empty collection is seeded with one
            # first, which is what creating the record amounts to.
            if not records:
                continue        # nothing to change; the caller seeds it in s0
            rec = records[0]
            rec[field] = _flip(rec.get(field))
        else:
            records.append({"id": f"new_{i}"})
    return s1


def _flip(v):
    """A value different from the one already there, whatever its type."""
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v + 1
    return "changed" if v != "changed" else "changed2"
