import json
from pathlib import Path

import pytest

from wb_worlds.tau2.importer import convert_task, source_pin


def test_import_preserves_private_source_task_and_reward_basis_without_exposing_it():
    row = {"id": "8", "user_scenario": {"instructions": "PRIVATE CUSTOMER"},
           "evaluation_criteria": {"actions": [{"name": "cancel_order", "arguments": {"order_id": "1"}}],
                                   "reward_basis": ["DB", "COMMUNICATE"]}}
    pin = {"package": "tau2", "version": "1.0.1", "revision": "a" * 40, "split": "retail/base"}
    task = convert_task(row, "retail", pin, "SOURCE POLICY")
    assert task["source_ref"]["task"] == row
    assert task["info"]["world"] == pin
    assert task["source_ref"]["reward_basis"] == ["DB", "COMMUNICATE"]
    public = "\n".join(message["content"] for message in task["prompt"])
    assert task["prompt"][0] == {"role": "system", "content": "SOURCE POLICY"}
    assert task["prompt"][1]["role"] == "user"
    assert "PRIVATE CUSTOMER" not in public
    assert "cancel_order" not in public
    assert "SOURCE POLICY" in public
    assert "send_message" in public
    assert task["info"]["expected_changes"] == []


def test_source_pin_refuses_chemistry_distribution_and_pre_101(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="tau2"\nversion="2.4.0"\ndescription="Magnetic relaxation"\n')
    with pytest.raises(ValueError, match="Sierra"):
        source_pin(tmp_path, "retail/base")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="tau2"\nversion="1.0.0"\n[project.urls]\nRepository="https://github.com/sierra-research/tau2-bench"\n')
    with pytest.raises(ValueError, match="1.0.1"):
        source_pin(tmp_path, "retail/base")


def test_import_refuses_paid_natural_language_judge():
    with pytest.raises(ValueError, match="paid.*judge"):
        convert_task({"id": "1", "evaluation_criteria": {"reward_basis": ["NL_ASSERTION"]}},
                     "retail", {}, "policy")


def test_import_excludes_unreviewed_tasks_and_refuses_replacing_a_manifest(tmp_path, monkeypatch):
    from wb_worlds.tau2 import importer
    source = tmp_path / "source"
    data = source / "data/tau2/domains/retail"
    data.mkdir(parents=True)
    rows = [{"id": "33", "evaluation_criteria": {"reward_basis": ["DB"]}},
            {"id": "34", "evaluation_criteria": {"reward_basis": ["DB"]}}]
    for name, value in {"tasks.json": rows, "db.json": {}, "split_tasks.json": {"base": ["33", "34"]}}.items():
        (data / name).write_text(json.dumps(value))
    (data / "policy.md").write_text("unchanged policy")
    pin = {"package": "tau2", "version": "1.0.1", "revision": "a" * 40, "split": "retail/base"}
    monkeypatch.setattr(importer, "source_pin", lambda root, split: pin)
    rules = {"33": {"expected_changes": [], "allowed_changes": []}}
    output = tmp_path / "frozen"
    result = importer.import_tau2(["retail"], output, root=source, rules=rules)
    assert result["written"] == 1
    assert result["exclusions"] == [{"task_id": "34", "reason": "No reviewed task-specific permitted-change rule"}]
    frozen = (output / "tau2.retail.33.json").read_bytes()
    original_manifest = (output / "MANIFEST.yaml").read_bytes()
    with pytest.raises(ValueError, match="frozen.*manifest"):
        importer.import_tau2(["retail"], output, root=source, task_ids=["33"], rules=rules)
    assert (output / "tau2.retail.33.json").read_bytes() == frozen
    assert (output / "MANIFEST.yaml").read_bytes() == original_manifest


def test_source_task_identifier_cannot_become_a_filesystem_path():
    identifier = "[mobile_data_issue]user/abroad[PERSONA:Hard]"
    imported = convert_task({"id": identifier, "evaluation_criteria": {"reward_basis": ["ENV_ASSERTION"]}},
                            "telecom", {}, "policy")
    assert imported["example_id"] == identifier
    assert imported["source_ref"]["task_id"] == identifier
    assert all(char not in imported["task"] for char in '/\\:[]')
    assert imported["task"].startswith("tau2.telecom.")
