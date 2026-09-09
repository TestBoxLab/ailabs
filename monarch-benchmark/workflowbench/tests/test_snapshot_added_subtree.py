"""An added subtree must not hide the writes inside it.

Action-log services (airtable, jira, trello, notion, asana, monday, ...) keep
every write under one key. When that key is new, collapsing the whole subtree
into one change makes an unrequested write invisible to the collateral half of
the grader, and no tightening of a task's approval rule can recover it.
"""
from __future__ import annotations

from grader.invariant import check_invariant
from wb_world.snapshot import diff_snapshots


def _airtable(actions):
    return {"airtable": {"actions": actions, "bases": []}}


def test_added_action_log_addresses_each_write():
    s0 = _airtable({})
    s1 = _airtable({"createRecord": [
        {"id": "a1", "params": {"tableName": "Invoices"}},
        {"id": "a2", "params": {"tableName": "Unrequested"}},
    ]})
    paths = [c["path"] for c in diff_snapshots(s0, s1)]
    assert "airtable.actions.createRecord[id=a1]" in paths
    assert "airtable.actions.createRecord[id=a2]" in paths


def test_unrequested_write_in_a_new_action_log_is_caught():
    """The `simple.invoice_airtable_slack` collateral hole, at the diff level."""
    s0 = _airtable({})
    s1 = _airtable({"createRecord": [
        {"id": "a1", "params": {"tableName": "Invoices"}},
        {"id": "a2", "params": {"tableName": "Unrequested"}},
    ]})
    inv = check_invariant(
        diff_snapshots(s0, s1),
        expected=[{"service": "airtable", "op": "added",
                   "path": "airtable.actions.createRecord[id=a1]"}],
    )
    assert not inv["passed"]
    assert [c["path"] for c in inv["unexpected_changes"]] == [
        "airtable.actions.createRecord[id=a2]"]


def test_an_added_leaf_still_reports_its_value():
    s0 = {"svc": {}}
    s1 = {"svc": {"name": "Jordan"}}
    assert diff_snapshots(s0, s1) == [
        {"service": "svc", "op": "added", "path": "svc.name",
         "before": None, "after": "Jordan"}]


def test_a_removed_subtree_addresses_each_entry():
    s0 = _airtable({"createRecord": [{"id": "a1", "params": {}}]})
    s1 = _airtable({})
    paths = [c["path"] for c in diff_snapshots(s0, s1)]
    assert paths == ["airtable.actions.createRecord[id=a1]"]
