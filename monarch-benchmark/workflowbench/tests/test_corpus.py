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


def test_service_check_survives_a_re_import(stub_vendor, tmp_path):
    """The check reads what the domains seed, not what this call happened to write.

    A second import skips every task it already wrote; if the seeded services were
    only collected on the write path, the re-import would report nothing missing
    and exit 0 with the corpus unchanged.
    """
    stub_vendor["finance"] = [_row("finance", 1, services=("airtable", "not_a_product_app"))]

    first = corpus_mod.import_ab(["finance"], tmp_path, product_services=["airtable"])
    assert first["written"] == 1 and first["missing_services"] == ["not_a_product_app"]

    second = corpus_mod.import_ab(["finance"], tmp_path, product_services=["airtable"])
    assert second["written"] == 0 and second["unchanged"] == 1
    assert second["missing_services"] == ["not_a_product_app"]


def test_structural_difficulty_scores_arbitrary_task():
    task = {
        "info": {
            "initial_state": {"airtable": {"contacts": [{"id": 1}]}},
            "expected_changes": [{"service": "airtable", "action": "update"}],
            "zapier_tools": ["airtable_create_record", "gmail_send_mail"],
        }
    }
    # 1 seeded service + 1 expected change + 2 zapier tools = 4
    assert corpus_mod.structural_difficulty(task) == 4
    assert corpus_mod.score_task(task) == 4


def test_cli_corpus_split(tmp_path, capsys):
    from pathlib import Path
    from wb_orchestrator.cli import main

    fixture = Path(__file__).parent / "fixtures" / "mini-corpus"
    corpus_dirs = sorted(fixture.glob("imported-*"))
    corpus_arg = ",".join(d.as_posix() for d in corpus_dirs)

    dev_out = tmp_path / "tasks" / "dev-4"
    heldout_out = tmp_path / "tasks" / "heldout-4"
    manifest_path = tmp_path / "tasks" / "split-manifest.yaml"

    argv = [
        "corpus", "split",
        f"--corpus={corpus_arg}",
        "--size", "4",
        "--seed", "20260911",
        "--dev-out", dev_out.as_posix(),
        "--heldout-out", heldout_out.as_posix(),
        "--manifest", manifest_path.as_posix(),
        "--because", "cli test split",
    ]

    rc = main(argv)
    assert rc == 0
    out = capsys.readouterr().out
    assert "drawn from 13 usable tasks across 3 domains" in out
    assert "development  4 tasks" in out
    assert "held-out     4 tasks" in out
    assert "domains balanced:" in out
    assert "frozen:" in out
    assert f"manifest: {manifest_path.as_posix()}" in out
    assert dev_out.is_dir() and len(list(dev_out.glob("*.json"))) == 4
    assert heldout_out.is_dir() and len(list(heldout_out.glob("*.json"))) == 4
    assert manifest_path.is_file()

    # Redrawing against the frozen held-out slate exits 2 with refusal text
    rc_redraw = main(argv)
    assert rc_redraw == 2
    err = capsys.readouterr().err
    assert f"refused: {heldout_out.as_posix()} is a frozen held-out slate. A held-out slate is never redrawn." in err


