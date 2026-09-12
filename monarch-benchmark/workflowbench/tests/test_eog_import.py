"""Focused import tests; synthetic rows exercise validation, not benchmark scores."""
import json
from pathlib import Path

import pytest

from wb_worlds.enterprise_ops.importer import import_eog
from wb_world.episode import contract_hash

PIN = "a" * 40
SOURCE = "b" * 40


def inputs(tmp_path):
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "itsm.sql").write_text("CREATE TABLE incident (incident_id TEXT PRIMARY KEY);", encoding="utf-8")
    row = {"task_id": "task_probe", "domain": "itsm", "system_prompt": "Preserve unrelated records.",
           "user_prompt": "Create an incident.", "selected_tools": ["create_incident"],
           "gym_servers_config": json.dumps([{"mcp_server_name": "gym-itsm-mcp", "seed_database_file": "itsm.sql"}]),
           "verifiers": json.dumps([{"verifier_type": "database_state", "gym_name": "gym-itsm-mcp",
               "name": "created", "validation_config": {"query": "SELECT COUNT(*) FROM incident", "expected_value": 1, "comparison_type": "equals"}}])}
    rule = {"rationale": "Only the requested incident may be created.", "reviewed_by": "test fixture",
            "expected_changes": [{"service": "gym-itsm-mcp", "op": "added", "path": "gym-itsm-mcp.incident[id=INC_001]", "count": 1}], "allowed_changes": []}
    return row, seeds, {"task_probe": rule}


def run(tmp_path, row, seeds, rules):
    return import_eog(["itsm"], tmp_path / "corpus" / "imported-{domain}", rows=[row],
                      reviewed_rules=rules, revision=PIN, source_revision=SOURCE, seed_root=seeds)


def test_import_preserves_exact_prompts_checks_and_pins(tmp_path):
    row, seeds, rules = inputs(tmp_path)
    result = run(tmp_path, row, seeds, rules)
    task = json.loads(Path(result["written"][0]).read_text(encoding="utf-8"))
    assert task["prompt"] == [{"role": "system", "content": row["system_prompt"]}, {"role": "user", "content": row["user_prompt"]}]
    assert task["source_ref"]["verifiers"] == json.loads(row["verifiers"])
    assert task["source_ref"]["servers"] == json.loads(row["gym_servers_config"])
    assert task["info"]["world"] == {"package": "enterprise-ops-gym", "version": SOURCE, "revision": PIN, "split": "itsm/oracle"}
    assert task["contract_sha256"] == contract_hash(task)
    assert len(task["source_ref"]["seed_sha256"]["gym-itsm-mcp"]) == 64


def test_identical_import_does_not_rewrite_files(tmp_path):
    row, seeds, rules = inputs(tmp_path)
    first = run(tmp_path, row, seeds, rules)
    paths = [Path(first["written"][0]), Path(first["manifest"])]
    mtimes = [p.stat().st_mtime_ns for p in paths]
    second = run(tmp_path, row, seeds, rules)
    assert second["written"] == []
    assert second["unchanged"] == [str(paths[0])]
    assert [p.stat().st_mtime_ns for p in paths] == mtimes


@pytest.mark.parametrize("failure", ["missing rule", "missing seed", "unsupported verifier", "missing query"])
def test_unusable_task_records_exclusion_without_task_file(tmp_path, failure):
    row, seeds, rules = inputs(tmp_path)
    if failure == "missing rule":
        rules = {}
    if failure == "missing seed":
        (seeds / "itsm.sql").unlink()
    if failure == "unsupported verifier":
        row["verifiers"] = json.dumps([{"verifier_type": "response_check"}])
    if failure == "missing query":
        verifiers = json.loads(row["verifiers"])
        del verifiers[0]["validation_config"]["query"]
        row["verifiers"] = json.dumps(verifiers)
    result = run(tmp_path, row, seeds, rules)
    assert result["written"] == []
    assert not list((tmp_path / "corpus").glob("imported-*/*.json"))
    assert result["excluded"][0]["task"] == "task_probe"
    assert failure.split()[1] in result["excluded"][0]["reason"]


def test_moving_pin_is_refused_before_writing(tmp_path):
    row, seeds, rules = inputs(tmp_path)
    with pytest.raises(ValueError, match="immutable"):
        import_eog(["itsm"], tmp_path / "out", rows=[row], reviewed_rules=rules,
                   revision="main", source_revision=SOURCE, seed_root=seeds)
    assert not (tmp_path / "out").exists()
