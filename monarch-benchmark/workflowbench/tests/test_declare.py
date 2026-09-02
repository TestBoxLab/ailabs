"""Derived invariants must reproduce Lucas's hand-written pilot contracts and
add only the documented side effects. Regression anchor: smoke-frontier-001's
Opus failure on sf_opp_closed_won was a contract gap, not a model error."""
from __future__ import annotations

import json
from pathlib import Path

from grader.grade import grade
from wb_orchestrator.declare import derive, _TYPES

ROOT = Path(__file__).resolve().parents[1]


def test_derived_expected_matches_manual_pilot_contracts():
    for p in sorted((ROOT / "tasks").glob("*.json")):
        task = json.loads(p.read_text(encoding="utf-8"))
        assert derive(task)["expected"] == task["info"]["expected_changes"], task["task"]


def test_closed_won_allows_the_salesforce_close_pair():
    task = json.loads((ROOT / "tasks" / "simple.sf_opp_closed_won.json").read_text(encoding="utf-8"))
    d = derive(task)
    paths = {m["path"] for m in d["allowed"]}
    assert "salesforce.opportunities[*].is_closed" in paths and "salesforce.opportunities[*].is_won" in paths
    # an agent that sets stage + is_closed + is_won now passes; a collateral write still fails
    task["info"].update(expected_changes=d["expected"], allowed_changes=d["allowed"])
    s0 = json.loads(json.dumps(task["info"]["initial_state"]))
    s0.setdefault("gmail", {"messages": []})
    s1 = json.loads(json.dumps(s0))
    opp = s1["salesforce"]["opportunities"][0]
    opp.update(stage_name="Closed Won", is_closed=True, is_won=True)
    assert grade(task, s0, s1)["passed"]
    opp["amount"] = 1
    assert not grade(task, s0, s1)["passed"]


def test_every_corpus_assertion_type_is_mapped():
    types = set()
    for p in (ROOT / "corpus" / "imported-simple").glob("*.json"):
        types |= {a["type"] for a in json.loads(p.read_text(encoding="utf-8"))["info"]["assertions"]}
    assert types <= set(_TYPES), sorted(types - set(_TYPES))
