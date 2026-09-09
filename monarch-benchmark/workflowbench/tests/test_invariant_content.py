"""Judge B must be able to say WHICH write it expected, not just where.

Action-log services address a write by an id minted during the run, so a frozen
approval rule cannot name it. Matching on the write's own content — and counting
how many writes match — is what lets the rule say "exactly one VIP contact",
which is the difference between "did the asked-for thing" and "did the asked-for
thing and nothing else".
"""
from __future__ import annotations

from grader.invariant import check_invariant
from wb_world.snapshot import diff_snapshots


def _airtable(actions):
    return {"airtable": {"actions": actions, "bases": []}}


def _write(rid, table, fields):
    return {"id": rid, "action_key": "createRecord",
            "params": {"applicationId": "base_crm", "tableName": table, "fields": fields}}


VIP = {"Name": "Jordan Lee", "Email": "jordan@example.com", "Status": "VIP"}


def test_the_diff_keeps_the_content_of_an_added_write():
    """`after` must carry the write itself; "<object>" hides what Judge B needs."""
    s1 = _airtable({"createRecord": [_write("a1", "Contacts", VIP)]})
    change = diff_snapshots(_airtable({}), s1)[0]
    assert change["after"]["params"]["tableName"] == "Contacts"
    assert change["after"]["params"]["fields"]["Status"] == "VIP"


def test_where_matches_on_content_not_on_the_generated_id():
    changes = diff_snapshots(_airtable({}), _airtable({"createRecord": [
        _write("a1", "Contacts", VIP),
        _write("a2", "Leads", {"Name": "Someone", "Status": "VIP"}),
    ]}))
    rule = {"service": "airtable", "op": "added",
            "path": "airtable.actions.createRecord*",
            "where": {"params.tableName": "Contacts"}}
    inv = check_invariant(changes, [rule])
    assert not inv["passed"]
    assert [c["path"] for c in inv["unexpected_changes"]] == [
        "airtable.actions.createRecord[id=a2]"]


def test_count_pins_exactly_one_matching_write():
    """The 200-junk-records hole: same table, same field, right thing done too."""
    junk = [_write(f"j{i}", "Contacts", {"Name": f"JUNK{i}", "Status": "VIP"})
            for i in range(200)]
    changes = diff_snapshots(_airtable({}), _airtable({
        "createRecord": [_write("a1", "Contacts", VIP)] + junk}))
    rule = {"service": "airtable", "op": "added",
            "path": "airtable.actions.createRecord*",
            "where": {"params.tableName": "Contacts", "params.fields.Status": "VIP"},
            "count": 1}
    inv = check_invariant(changes, [rule])
    assert not inv["passed"]
    assert inv["count_violations"], "a rule pinning one write must report 201"


def test_the_correct_answer_alone_passes():
    changes = diff_snapshots(_airtable({}), _airtable({
        "createRecord": [_write("a1", "Contacts", VIP)]}))
    rule = {"service": "airtable", "op": "added",
            "path": "airtable.actions.createRecord*",
            "where": {"params.tableName": "Contacts", "params.fields.Status": "VIP"},
            "count": 1}
    assert check_invariant(changes, [rule])["passed"]


def test_a_rule_without_where_or_count_behaves_as_before():
    """Every frozen rule keeps its current verdict; nothing re-hashes."""
    changes = diff_snapshots(_airtable({}), _airtable({
        "createRecord": [_write("a1", "Contacts", VIP), _write("a2", "Contacts", {})]}))
    inv = check_invariant(changes, [{"service": "airtable", "op": "added",
                                     "path": "airtable.*"}])
    assert inv["passed"]
