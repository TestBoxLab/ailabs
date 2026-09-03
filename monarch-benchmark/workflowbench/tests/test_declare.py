"""Derived invariants must reproduce Lucas's hand-written pilot contracts and
add only the documented side effects. Regression anchor: smoke-frontier-001's
Opus failure on sf_opp_closed_won was a contract gap, not a model error."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from grader.grade import grade
from wb_orchestrator.config import ConfigError
from wb_orchestrator.declare import declare_dir, derive, load_side_effects, _TYPES

ROOT = Path(__file__).resolve().parents[1]
SIDE_EFFECTS = load_side_effects(ROOT / "config" / "side-effects.yaml")


def test_derived_expected_matches_manual_pilot_contracts():
    for p in sorted((ROOT / "tasks").glob("*.json")):
        task = json.loads(p.read_text(encoding="utf-8"))
        assert derive(task, SIDE_EFFECTS)["expected"] == task["info"]["expected_changes"], task["task"]


def test_closed_won_allows_the_salesforce_close_pair():
    task = json.loads((ROOT / "tasks" / "simple.sf_opp_closed_won.json").read_text(encoding="utf-8"))
    d = derive(task, SIDE_EFFECTS)
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


# ---------------------------------------------------------------- T042/T044: side effects from the product file

# The constant that used to live in declare.py, frozen here as the byte-identity anchor.
OLD_SIDE_EFFECTS = [
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
SIDE_EFFECTS_FILE = ROOT / "config" / "side-effects.yaml"


def test_side_effects_file_equals_the_old_constant():
    assert SIDE_EFFECTS == OLD_SIDE_EFFECTS


def test_declare_dir_with_the_file_matches_the_old_constant(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    for p in sorted((ROOT / "corpus" / "imported-simple").glob("*.json"))[:20]:
        shutil.copy(p, src / p.name)  # the corpus is already declared; overwrite=True re-derives
    declare_dir(src, tmp_path / "a", overwrite=True, side_effects=OLD_SIDE_EFFECTS)
    declare_dir(src, tmp_path / "b", overwrite=True, side_effects=load_side_effects(SIDE_EFFECTS_FILE))
    a, b = sorted((tmp_path / "a").glob("*.json")), sorted((tmp_path / "b").glob("*.json"))
    assert len(a) == 20 and [p.name for p in a] == [p.name for p in b]
    for pa, pb in zip(a, b):
        assert pa.read_bytes() == pb.read_bytes(), pa.name


def test_declare_dir_defaults_to_the_simulated_apps_side_effects(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    shutil.copy(ROOT / "tasks" / "simple.sf_opp_closed_won.json", src / "t.json")
    declare_dir(src, tmp_path / "out", overwrite=True)
    task = json.loads((tmp_path / "out" / "t.json").read_text(encoding="utf-8"))
    assert "salesforce.opportunities[*].is_won" in {m["path"] for m in task["info"]["allowed_changes"]}


@pytest.mark.parametrize("text,field", [
    ("service: gmail\n", "<root>"),                                    # not a list
    ("- allowed: []\n", "[0].service"),                                # service missing
    ("- service: gmail\n  when: 3\n  allowed: []\n", "[0].when"),      # when not a str
    ("- service: gmail\n  allowed: [{service: gmail, op: '*'}]\n", "[0].allowed[0].path"),
    ("- service: gmail\n  allowed: [{service: gmail, op: '*', path: x, extra: 1}]\n", "[0].allowed[0].extra"),
    ("- service: gmail\n  allowed: []\n  bogus: 1\n", "[0].bogus"),
])
def test_side_effects_file_validation(tmp_path, text, field):
    p = tmp_path / "side-effects.yaml"
    p.write_text(text)
    with pytest.raises(ConfigError) as exc:
        load_side_effects(p)
    assert exc.value.path == str(p) and exc.value.field == field
