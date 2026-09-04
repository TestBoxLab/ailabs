"""Feature 005: importing the six scored AutomationBench domains.

The vendored benchmark is slow and may be absent, so every test here drives
`import_ab` against a stub `get_domain_dataset` instead. The conversion itself
is not re-tested: it is the same one the two hundred baseline tasks came through.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from wb_orchestrator import corpus as corpus_mod


def _row(domain: str, i: int, services=("airtable",), tools=("airtable_create_record",)):
    info = {
        "task_name": f"{domain}.task_{i}",
        "zapier_tools": list(tools),
        "initial_state": {"meta": {"seeded": True}, **{s: {} for s in services}},
        "assertions": [{"type": "airtable_record_exists", "applicationId": "base_crm",
                        "tableName": "Contacts", "fields": {"Name": f"row {i}"}}],
    }
    return {"example_id": 500 + i, "answer": "",
            "prompt": [{"role": "system", "content": "You are a workflow automation agent."},
                       {"role": "user", "content": f"Do task {i} of {domain}."}],
            "info": json.dumps(info)}   # the vendor serialises info to a string


@pytest.fixture
def stub_vendor(monkeypatch):
    """Install a fake automationbench.domains with two rows per domain."""
    rows: dict[str, list[dict]] = {}

    def get_domain_dataset(domain):
        if domain not in rows:
            raise ValueError(f"unknown domain {domain}")
        return rows[domain]

    mod = types.ModuleType("automationbench.domains")
    mod.get_domain_dataset = get_domain_dataset
    mod.PUBLIC_DOMAINS = ["sales", "marketing", "operations", "support", "finance", "hr"]
    monkeypatch.setitem(sys.modules, "automationbench.domains", mod)
    return rows


def test_import_writes_the_task_shape(stub_vendor, tmp_path):
    stub_vendor["finance"] = [_row("finance", 1), _row("finance", 2)]
    res = corpus_mod.import_ab(["finance"], tmp_path)

    assert res["written"] == 2
    written = sorted(tmp_path.glob("*.json"))
    assert [p.name for p in written] == ["finance.task_1.json", "finance.task_2.json"]

    t = json.loads(written[0].read_text())
    assert t["task"] == "finance.task_1"
    assert t["prompt"][1]["content"] == "Do task 1 of finance."      # the request text
    assert t["info"]["zapier_tools"] == ["airtable_create_record"]   # the tools needed
    assert "airtable" in t["info"]["initial_state"]                  # the starting data
    assert t["info"]["assertions"][0]["type"] == "airtable_record_exists"
    assert t["info"]["expected_changes"] == [] and t["info"]["allowed_changes"] == []
    assert len(t["contract_sha256"]) == 16                           # and a hash


def test_per_domain_destination(stub_vendor, tmp_path):
    for d in ("finance", "hr"):
        stub_vendor[d] = [_row(d, 1)]
    res = corpus_mod.import_ab(["finance", "hr"], tmp_path / "imported-{domain}")

    assert (tmp_path / "imported-finance" / "finance.task_1.json").exists()
    assert (tmp_path / "imported-hr" / "hr.task_1.json").exists()
    assert res["by_domain"] == {"finance": {"written": 1, "unchanged": 0},
                                "hr": {"written": 1, "unchanged": 0}}


def test_several_domains_need_the_domain_pattern(stub_vendor, tmp_path):
    for d in ("finance", "hr"):
        stub_vendor[d] = [_row(d, 1)]
    with pytest.raises(ValueError) as e:
        corpus_mod.import_ab(["finance", "hr"], tmp_path)
    assert "{domain}" in str(e.value)
    assert not list(tmp_path.glob("**/*.json"))


def test_all_domains(stub_vendor, tmp_path):
    for d in ("simple", "sales", "marketing", "operations", "support", "finance", "hr"):
        stub_vendor[d] = [_row(d, 1)]
    res = corpus_mod.import_ab(["all"], tmp_path / "imported-{domain}")

    # the vendor's own public list plus the baseline domain, in a fixed order
    assert list(res["by_domain"]) == ["simple", "finance", "hr", "marketing",
                                      "operations", "sales", "support"]


def test_unknown_domain_is_refused(stub_vendor, tmp_path):
    with pytest.raises(ValueError) as e:
        corpus_mod.import_ab(["nope"], tmp_path)
    assert "nope" in str(e.value) and "simple" in str(e.value) and "finance" in str(e.value)


def test_missing_services_reported(stub_vendor, tmp_path):
    stub_vendor["finance"] = [_row("finance", 1, services=("airtable", "not_a_product_app"))]
    res = corpus_mod.import_ab(["finance"], tmp_path, product_services=["airtable", "gmail"])
    assert res["missing_services"] == ["not_a_product_app"]

    stub_vendor["hr"] = [_row("hr", 1, services=("airtable",))]
    res = corpus_mod.import_ab(["hr"], tmp_path, product_services=["airtable", "gmail"])
    assert res["missing_services"] == []          # "meta" is bookkeeping, never a service


def test_cli_import_ab(stub_vendor, tmp_path, capsys, monkeypatch):
    from wb_orchestrator.cli import main
    monkeypatch.chdir(tmp_path)
    for d in ("finance", "hr"):
        stub_vendor[d] = [_row(d, 1), _row(d, 2)]

    dest = (tmp_path / "imported-{domain}").as_posix()
    assert main(["corpus", "import-ab", "--domains", "finance,hr", "--dest", dest,
                 "--product", "simulated-apps"]) == 0
    out = capsys.readouterr().out
    assert "finance:" in out and "2 written, 0 unchanged" in out
    assert "total: 4 tasks in 2 folders" in out
    assert ("services seeded by these domains and NOT listed by product "
            "simulated-apps: none") in out

    # a service the product does not list names it and exits 1
    stub_vendor["sales"] = [_row("sales", 1, services=("airtable", "not_a_product_app"))]
    assert main(["corpus", "import-ab", "--domains", "sales", "--dest", dest,
                 "--product", "simulated-apps"]) == 1
    assert "not_a_product_app" in capsys.readouterr().out

    # several domains without {domain} in --dest is a usage error
    assert main(["corpus", "import-ab", "--domains", "finance,hr",
                 "--dest", str(tmp_path / "flat"), "--product", "simulated-apps"]) == 2
