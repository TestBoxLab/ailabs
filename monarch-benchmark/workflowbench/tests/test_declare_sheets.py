"""A derived Google Sheets rule must match the diff a real sheets write makes.

The world model flattens the seed's nested `spreadsheets[].worksheets[].rows[]`
into three sibling collections at load time, so a real write diffs as

    added   google_sheets.rows[id=<uuid>]                  (append)
    changed google_sheets.rows[id=<uuid>].cells.<Column>   (in-place edit)

The rule the deriver used to emit named `google_sheets.spreadsheets[id=..]*`,
a subtree a sheets write never touches: it landed in `missing_expected` and a
perfect answer could not pass. Every check here drives the write through
`Episode.api_fetch` against the vendored simulator, because a synthetic dict
built from the raw seed is what let that defect survive.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from grader.grade import grade
from grader.invariant import check_invariant
from wb_orchestrator.declare import derive, load_side_effects
from wb_world.episode import Episode, load_task_file
from wb_world.snapshot import diff_snapshots

ROOT = Path(__file__).resolve().parents[1]
SIDE_EFFECTS = load_side_effects(ROOT / "config" / "side-effects.yaml")

APPEND_TASK = ROOT / "tasks" / "tier-simple" / "finance.annual_budget_prep.json"
EDIT_TASK = ROOT / "corpus" / "imported-simple" / "simple.sheets_update_status.json"


def _sheets_rules(task: dict) -> list[dict]:
    return [m for m in derive(task, SIDE_EFFECTS)["expected"]
            if m["service"] == "google_sheets"]


def _episode_diff(task: dict, writes) -> list[dict]:
    """Drive real writes through the simulator; return (episode, diff)."""
    ep = Episode(copy.deepcopy(task), episode_id="t")
    s0 = ep.snapshot()
    for method, url, body in writes:
        ep.api_fetch(method, url, body=json.dumps(body))
    return s0, ep.snapshot(), diff_snapshots(s0, ep.snapshot())


# -- the append case -----------------------------------------------------------

APPEND_ROWS = [
    ("POST", "https://sheets.googleapis.com/v4/spreadsheets/ss_budget_prep/values/2026 Budget:append",
     {"values": [[dept, sal, trav, soft]]})
    for dept, sal, trav, soft in [
        ("Engineering", "1,560,000", "0", "240,000"),
        ("Sales", "832,000", "165,000", "0"),
        ("Marketing", "520,000", "66,000", "120,000"),
    ]
]


def test_append_rule_matches_a_real_appended_row():
    task = load_task_file(APPEND_TASK)
    rules = _sheets_rules(task)
    assert rules, "the task carries a sheets assertion, so it must carry a sheets rule"
    _, _, changes = _episode_diff(task, APPEND_ROWS[:1])
    assert changes, "the append must show in the diff"
    for m in rules:
        assert any(_m(m, c) for c in changes), (m, changes)


def test_append_rule_does_not_match_a_write_to_another_spreadsheet():
    """The rule anchors on the spreadsheet the assertion names, not on any sheet."""
    task = load_task_file(APPEND_TASK)
    rules = _sheets_rules(task)
    stray = {"service": "google_sheets", "op": "added",
             "path": "google_sheets.rows[id=deadbeef]", "before": None,
             "after": {"id": "deadbeef", "spreadsheet_id": "ss_somewhere_else",
                       "worksheet_id": "ws_other", "row_id": 2,
                       "cells": {"Department": "Engineering"}}}
    assert not any(_m(m, stray) for m in rules), rules


def test_append_rule_does_not_match_a_row_on_the_wrong_worksheet():
    """The assertion names ws_2026_budget; the rate card is a different sheet."""
    task = load_task_file(APPEND_TASK)
    rules = _sheets_rules(task)
    _, _, changes = _episode_diff(task, [
        ("POST", "https://sheets.googleapis.com/v4/spreadsheets/ss_budget_prep/values/Rate Card:append",
         {"values": [["Junk", "0%"]]})])
    assert changes
    assert not any(_m(m, c) for m in rules for c in changes), (rules, changes)


def test_a_correct_append_answer_passes_the_invariant():
    task = load_task_file(APPEND_TASK)
    d = derive(task, SIDE_EFFECTS)
    ep = Episode(copy.deepcopy(task), episode_id="t")
    s0 = ep.snapshot()
    for method, url, body in APPEND_ROWS:
        ep.api_fetch(method, url, body=json.dumps(body))
    changes = diff_snapshots(s0, ep.snapshot())
    sheets = [c for c in changes if c["service"] == "google_sheets"]
    inv = check_invariant(sheets, [m for m in d["expected"] if m["service"] == "google_sheets"],
                          [m for m in d["allowed"] if m["service"] == "google_sheets"])
    assert inv["passed"], inv


# -- the in-place edit case ----------------------------------------------------

def test_edit_rule_matches_a_real_cell_edit():
    task = load_task_file(EDIT_TASK)
    rules = _sheets_rules(task)
    assert rules
    _, _, changes = _episode_diff(task, [
        ("PUT", "https://sheets.googleapis.com/v4/spreadsheets/ss_leads/values/Leads!D3",
         {"values": [["Qualified"]]})])
    assert changes and changes[0]["op"] == "changed", changes
    for m in rules:
        assert any(_m(m, c) for c in changes), (m, changes)


def test_a_correct_edit_answer_passes_grade():
    task = load_task_file(EDIT_TASK)
    d = derive(task, SIDE_EFFECTS)
    task["info"]["expected_changes"] = d["expected"]
    task["info"]["allowed_changes"] = d["allowed"]
    ep = Episode(copy.deepcopy(task), episode_id="t")
    s0 = ep.snapshot()
    ep.api_fetch("PUT", "https://sheets.googleapis.com/v4/spreadsheets/ss_leads/values/Leads!D3",
                 body=json.dumps({"values": [["Qualified"]]}))
    r = grade(task, s0, ep.snapshot())
    assert r["passed"], r["invariant"]


def test_edit_rule_does_not_match_an_unrelated_column():
    """Changing a company name is not changing a status."""
    task = load_task_file(EDIT_TASK)
    rules = _sheets_rules(task)
    _, _, changes = _episode_diff(task, [
        ("PUT", "https://sheets.googleapis.com/v4/spreadsheets/ss_leads/values/Leads!B2",
         {"values": [["Junk Corp"]]})])
    assert changes
    assert not any(_m(m, c) for m in rules for c in changes), (rules, changes)


# -- regression: nothing else moves --------------------------------------------

def test_a_non_sheets_rule_is_untouched():
    """The gmail half of the same task keeps the rule it always had."""
    task = load_task_file(APPEND_TASK)
    gmail = [m for m in derive(task, SIDE_EFFECTS)["expected"]
             if m["service"] == "gmail"]
    assert gmail == [{"service": "gmail", "op": "added", "path": "gmail.messages[*]"}]


def test_pilot_contracts_are_unchanged():
    """No frozen pilot task changes verdict because of this edit."""
    for p in sorted((ROOT / "tasks").glob("*.json")):
        task = json.loads(p.read_text(encoding="utf-8"))
        assert derive(task, SIDE_EFFECTS)["expected"] == task["info"]["expected_changes"], task["task"]


# -- every affected frozen task ------------------------------------------------

AFFECTED = [
    "finance.annual_budget_prep", "finance.audit_sample_selection",
    "finance.employee_reimbursement", "hr.comp_adjustment_batch",
    "hr.job_board_monitoring", "marketing.event_sponsorship_screen",
    "marketing.featured_snippet", "marketing.industry_event_tracking",
    "marketing.trending_topic", "support.freshdesk_auto_merge",
    "support.helpcrunch_trial_nurture", "support.reamaze_cross_platform_dedup",
]


@pytest.mark.parametrize("name", AFFECTED)
def test_no_affected_task_keeps_a_rule_on_the_spreadsheet_subtree(name):
    """`google_sheets.spreadsheets*` names a subtree a sheets write never touches."""
    path = next(p for p in (ROOT / "tasks").rglob(f"{name}.json"))
    rules = _sheets_rules(json.loads(path.read_text(encoding="utf-8")))
    assert rules, name
    assert all(m["path"].startswith("google_sheets.rows") for m in rules), rules


def test_no_corpus_task_keeps_a_rule_on_the_spreadsheet_subtree():
    """All 173 corpus tasks carrying a sheets rule, not just the frozen twelve."""
    stale = []
    for p in (ROOT / "corpus").rglob("*.json"):
        task = json.loads(p.read_text(encoding="utf-8"))
        stale += [(p.name, m["path"]) for m in _sheets_rules(task)
                  if not m["path"].startswith("google_sheets.rows")]
    assert not stale, stale


# -- the answer key passes, driven through the simulator -----------------------

CORRECT = {
    # task -> the writes a correct answer makes
    "finance.audit_sample_selection": [
        ("POST", "https://sheets.googleapis.com/v4/spreadsheets/ss_audit_sample"
                 "/values/Selected Samples:append", {"values": [["Q1-001"]]}),
        ("POST", "https://sheets.googleapis.com/v4/spreadsheets/ss_audit_sample"
                 "/values/Selected Samples:append", {"values": [["Q1-008"]]}),
    ],
    "marketing.trending_topic": [
        ("POST", "https://sheets.googleapis.com/v4/spreadsheets/ss_ideas"
                 "/values/Backlog:append",
         {"values": [["Compliance Updates", "social", "high"]]}),
    ],
    "hr.comp_adjustment_batch": [
        ("PUT", f"https://sheets.googleapis.com/v4/spreadsheets/ss_compadj_5132"
                f"/values/Adjustments!H{n}", {"values": [["Processed"]]})
        for n in (2, 5, 7)
    ],
}


@pytest.mark.parametrize("name", sorted(CORRECT))
def test_the_correct_answer_now_passes_the_sheets_rule(name):
    """The old rule put every one of these in missing_expected."""
    path = next(p for p in (ROOT / "tasks").rglob(f"{name}.json"))
    task = load_task_file(path)
    d = derive(task, SIDE_EFFECTS)
    _, _, changes = _episode_diff(task, CORRECT[name])
    sheets = [c for c in changes if c["service"] == "google_sheets"]
    assert sheets, "the writes must show in the diff"
    inv = check_invariant(
        sheets, [m for m in d["expected"] if m["service"] == "google_sheets"],
        [m for m in d["allowed"] if m["service"] == "google_sheets"])
    assert inv["passed"], inv
    # and the shape that shipped before could not: it named the spreadsheet
    # subtree, which the loader empties when it flattens rows into their own
    # collection. Written out rather than read from the task, because the task
    # files have since been re-derived and no longer carry it.
    spreadsheet_id = next(iter(
        m["where"]["spreadsheet_id"] for m in d["expected"]
        if m["service"] == "google_sheets" and (m.get("where") or {}).get("spreadsheet_id")), None)
    if spreadsheet_id:
        broken = [{"service": "google_sheets", "op": "*",
                   "path": f"google_sheets.spreadsheets[id={spreadsheet_id}]*"}]
        assert not check_invariant(sheets, broken, [])["passed"], broken


def _m(matcher: dict, change: dict) -> bool:
    from grader.invariant import _matches
    return _matches(matcher, change)
