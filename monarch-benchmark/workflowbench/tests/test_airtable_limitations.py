"""Document upstream behavior without changing the benchmark world or assertions."""
import json

from grader.grade import grade
from wb_orchestrator.config import from_workflowbench
from wb_world.episode import Episode, load_task_file


def test_upstream_vip_filter_returns_active_contact_and_explains_no_write():
    task = load_task_file(from_workflowbench(
        "tasks/tier-simple/simple.airtable_find_update.json"))
    ep = Episode(task, "upstream-filter-probe")
    responses = [json.loads(ep.api_fetch(
        "GET", "https://api.airtable.com/v0/base_crm/Contacts",
        params=json.dumps({"filterByFormula": formula}))) for formula in (
            "{Email}='jordan@example.com'",
            "AND({Email}='jordan@example.com',{Status}='VIP')")]
    assert responses[0] == responses[1]
    assert responses[1]["records"][0]["fields"]["Status"] == "Active"
    assert ep.snapshot() == ep.snapshot0
    result = grade(task, ep.snapshot0, ep.finish())
    assert not result["passed"]
    assert not result["assertions_passed"]
