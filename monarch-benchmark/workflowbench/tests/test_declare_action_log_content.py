"""A rule for an action-log service must say WHAT was asked for, not just where.

`airtable_record_exists` on a service that only logs actions used to derive
`airtable.*` — "anything in Airtable is expected" — which accepts the requested
write plus any number of writes nobody asked for. The assertion already carries
the table and the fields; the matcher now carries them too.
"""
from __future__ import annotations

from wb_orchestrator import config, declare

SIDE_EFFECTS = config.load_side_effects(
    config.from_workflowbench("config/side-effects.yaml"))


def _derive(assertion, initial_state=None):
    task = {"info": {"assertions": [assertion],
                     "initial_state": initial_state or {"airtable": {"actions": {}}}}}
    return declare.derive(task, SIDE_EFFECTS)["expected"]


def test_airtable_record_exists_pins_the_table_and_the_fields():
    [m] = _derive({"type": "airtable_record_exists", "applicationId": "base_crm",
                   "tableName": "Contacts", "fields": {"Status": "VIP"}})
    assert m["where"]["params.tableName"] == "Contacts"
    assert m["where"]["params.fields.Status"] == "VIP"
    assert m["count"] == 1
    assert m["path"] != "airtable.*", "the whole-service wildcard is the bug"


def test_an_assertion_without_content_keeps_the_old_wildcard():
    """No content to pin: the rule must not invent one."""
    [m] = _derive({"type": "airtable_record_exists", "applicationId": "base_crm"})
    assert "where" not in m and "count" not in m
