"""Milestone M1 of the unblock plan (8 Sep 2026): the world's revision travels
with every task, into the suite id of every row, and a task set never runs on
a world other than the one it was imported under.

Offline throughout. The vendored benchmark is replaced by the stub from
test_corpus, and the "installed world" is whatever each test says it is.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.test_config import ENV, site  # noqa: F401  (site is a fixture)
from tests.test_corpus import _row, stub_vendor  # noqa: F401  (stub_vendor is a fixture)
from wb_orchestrator import config, corpus as corpus_mod
from wb_orchestrator.config import ConfigError
from wb_world import episode
from wb_world.episode import contract_hash, load_task_file, suite_id

FIXTURE = Path(__file__).parent / "fixtures" / "mini-corpus"
NEW = "1.0.6+evalrepair.10"


def _stamp(path: Path, version: str = NEW, revision: str = "evalrepair10") -> dict:
    """Give one task file a world record, re-hash it, and return the task."""
    task = load_task_file(path)
    task["info"]["world"] = {"package": "automation-bench", "version": version,
                             "revision": revision}
    task["contract_sha256"] = contract_hash(task)
    path.write_text(json.dumps(task, indent=1, sort_keys=True) + "\n", newline="\n")
    return task


def _stamped_set(tmp_path: Path, name: str = "set", **kw) -> Path:
    folder = tmp_path / name
    shutil.copytree(FIXTURE / "imported-alpha", folder)
    for p in sorted(folder.glob("*.json")):
        _stamp(p, **kw)
    return folder


# --- the suite id ---------------------------------------------------------------

def test_suite_id_keeps_the_old_label_for_sets_that_record_no_world():
    tasks = [load_task_file(p) for p in sorted((FIXTURE / "imported-alpha").glob("*.json"))]
    assert episode.recorded_world_version(tasks) == episode.UPSTREAM_WORLD_VERSION == "1.0.6"
    assert suite_id(tasks) == "workflowbench-synthetic@0.1"


def test_suite_id_carries_the_recorded_world_version(tmp_path):
    folder = _stamped_set(tmp_path)
    tasks = [load_task_file(p) for p in sorted(folder.glob("*.json"))]
    assert episode.recorded_world_version(tasks) == NEW
    assert suite_id(tasks) == f"workflowbench-synthetic@{NEW}"
    assert "1.0.6+evalrepair.10" in suite_id(tasks)


def test_a_set_mixing_worlds_is_refused_by_name(tmp_path):
    folder = _stamped_set(tmp_path)
    odd = sorted(folder.glob("*.json"))[0]
    _stamp(odd, version="2.0.0", revision="other")
    tasks = [load_task_file(p) for p in sorted(folder.glob("*.json"))]
    with pytest.raises(ValueError) as e:
        suite_id(tasks)
    msg = str(e.value)
    assert "2.0.0" in msg and NEW in msg and load_task_file(odd)["task"] in msg


def test_the_world_record_is_part_of_the_hash(tmp_path):
    """A task under a new world is a different contract, even with the same text."""
    src = FIXTURE / "imported-alpha" / "alpha.a_two.json"
    before = contract_hash(load_task_file(src))
    dst = tmp_path / src.name
    shutil.copy(src, dst)
    after = _stamp(dst)["contract_sha256"]
    assert after != before
    # the two drawn-set labels still do not move it
    labelled = load_task_file(dst)
    labelled["info"]["tier"], labelled["info"]["domain"] = "simple", "alpha"
    assert contract_hash(labelled) == after


# --- wb corpus import-ab --revision / --out --------------------------------------

def test_import_with_a_revision_stamps_every_task_and_writes_the_manifest(
        stub_vendor, tmp_path, monkeypatch):
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    for d in ("finance", "hr"):
        stub_vendor[d] = [_row(d, 1), _row(d, 2)]
    root = tmp_path / "corpus-evalrepair10"
    res = corpus_mod.import_ab(["finance", "hr"], root / "imported-{domain}",
                               revision="evalrepair10")

    assert res["written"] == 4 and res["revision"] == "evalrepair10"
    assert res["world_version"] == NEW
    for p in root.glob("imported-*/*.json"):
        t = load_task_file(p)
        assert t["info"]["world"] == {"package": "automation-bench", "version": NEW,
                                      "revision": "evalrepair10"}
        assert t["contract_sha256"] == contract_hash(t)    # hashed with the world in it

    manifest = yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8"))
    assert manifest["revision"] == "evalrepair10"
    assert manifest["world"]["package"] == "automation-bench"
    assert manifest["world"]["version"] == NEW
    assert manifest["imported_at"].startswith("20")
    by_domain = {f["domain"]: f for f in manifest["folders"]}
    assert by_domain["finance"]["tasks"] == 2 and by_domain["hr"]["tasks"] == 2
    assert manifest["tasks_total"] == 4
    # nothing has a rule yet: nothing is usable, and every task is listed
    assert manifest["usable_total"] == 0
    assert sorted(t["task"] for t in manifest["without_rule"]) == [
        "finance.task_1", "finance.task_2", "hr.task_1", "hr.task_2"]


def test_manifest_counts_usable_tasks_after_declare(stub_vendor, tmp_path, monkeypatch):
    from wb_orchestrator import declare
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    stub_vendor["finance"] = [_row("finance", 1), _row("finance", 2)]
    root = tmp_path / "corpus-evalrepair10"
    corpus_mod.import_ab(["finance"], root / "imported-{domain}", revision="evalrepair10")
    first = yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8"))

    declare.declare_dir(root / "imported-finance", overwrite=True)
    manifest = corpus_mod.write_manifest(root)
    assert manifest["usable_total"] == 2 and manifest["without_rule"] == []
    assert manifest["folders"][0]["usable"] == 2
    assert manifest["imported_at"] == first["imported_at"]      # kept from the import
    assert manifest["world"]["version"] == NEW                    # read from the tasks
    on_disk = yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8"))
    assert on_disk == manifest


def test_import_without_a_revision_is_refused_on_a_world_other_than_upstream(
        stub_vendor, tmp_path, monkeypatch):
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    stub_vendor["finance"] = [_row("finance", 1)]
    with pytest.raises(ValueError) as e:
        corpus_mod.import_ab(["finance"], tmp_path / "corpus" / "imported-{domain}")
    assert NEW in str(e.value) and "--revision" in str(e.value)
    assert not list(tmp_path.glob("**/*.json"))

    # on the upstream world the default import is what it always was: no stamp
    monkeypatch.setattr(episode, "installed_world_version", lambda: "1.0.6")
    res = corpus_mod.import_ab(["finance"], tmp_path / "corpus" / "imported-{domain}")
    assert res["written"] == 1 and res["revision"] is None
    t = load_task_file(tmp_path / "corpus" / "imported-finance" / "finance.task_1.json")
    assert "world" not in t["info"]


def test_cli_import_ab_revision_and_out(stub_vendor, tmp_path, capsys, monkeypatch):
    from wb_orchestrator.cli import main
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    monkeypatch.chdir(tmp_path)
    for d in ("finance", "hr"):
        stub_vendor[d] = [_row(d, 1)]

    assert main(["corpus", "import-ab", "--domains", "finance,hr",
                 "--revision", "evalrepair10", "--out", "corpus-evalrepair10",
                 "--product", "simulated-apps"]) == 0
    out = capsys.readouterr().out
    assert (tmp_path / "corpus-evalrepair10" / "imported-finance" / "finance.task_1.json").exists()
    assert (tmp_path / "corpus-evalrepair10" / "imported-hr" / "hr.task_1.json").exists()
    assert (tmp_path / "corpus-evalrepair10" / "MANIFEST.yaml").exists()
    assert "revision: evalrepair10" in out and NEW in out

    # --dest and --out together is a usage error; a bad label too
    assert main(["corpus", "import-ab", "--domains", "finance", "--out", "x",
                 "--dest", "y/imported-{domain}", "--product", "simulated-apps"]) == 2
    assert main(["corpus", "import-ab", "--domains", "finance", "--out", "x",
                 "--revision", "bad label/with spaces", "--product", "simulated-apps"]) == 2

    # wb corpus manifest rewrites the manifest from the folders as they are
    assert main(["corpus", "manifest", "corpus-evalrepair10"]) == 0
    printed = capsys.readouterr().out
    assert "usable" in printed and "corpus-evalrepair10" in printed


def test_cli_import_ab_defaults_are_unchanged(stub_vendor, tmp_path, capsys, monkeypatch):
    """No flags beyond --domains: the folders land under corpus/, unstamped."""
    from wb_orchestrator.cli import main
    monkeypatch.chdir(tmp_path)
    stub_vendor["finance"] = [_row("finance", 1)]
    assert main(["corpus", "import-ab", "--domains", "finance",
                 "--product", "simulated-apps"]) == 0
    t = load_task_file(tmp_path / "corpus" / "imported-finance" / "finance.task_1.json")
    assert "world" not in t["info"]
    assert not (tmp_path / "corpus" / "MANIFEST.yaml").exists()


# --- config.resolve: the installed world must be the recorded one ----------------

def _resolve(site):
    return config.resolve(site / "config/products/simulated-apps.yaml",
                          site / "config/plans/smoke-frontier.yaml",
                          env=ENV)


def test_resolve_refuses_a_set_recorded_under_another_world(site, monkeypatch):
    # the shipped pilot tasks record no world: they were imported under 1.0.6
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    with pytest.raises(ConfigError) as e:
        _resolve(site)
    assert e.value.field == "tasks"
    assert "1.0.6" in e.value.why and NEW in e.value.why       # both worlds named
    assert "automation-bench" in e.value.why

    # and a set stamped with the new world does not run on the old one
    for p in (site / "tasks").glob("*.json"):
        _stamp(p)
    monkeypatch.setattr(episode, "installed_world_version", lambda: "1.0.6")
    with pytest.raises(ConfigError) as e:
        _resolve(site)
    assert e.value.field == "tasks" and NEW in e.value.why and "1.0.6" in e.value.why


def test_resolve_accepts_a_set_recorded_under_the_installed_world(site, monkeypatch):
    monkeypatch.setattr(episode, "installed_world_version", lambda: "1.0.6")
    assert len(_resolve(site).tasks) == len(list((site / "tasks").glob("*.json")))

    for p in (site / "tasks").glob("*.json"):
        _stamp(p)
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    rc = _resolve(site)
    assert suite_id(rc.tasks) == f"workflowbench-synthetic@{NEW}"


def test_resolve_refuses_a_set_mixing_worlds(site, monkeypatch):
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    files = sorted((site / "tasks").glob("*.json"))
    for p in files[1:]:
        _stamp(p)
    with pytest.raises(ConfigError) as e:
        _resolve(site)
    assert e.value.field == "tasks" and files[0].stem in e.value.why


def test_wb_run_names_both_worlds_when_it_refuses(site, monkeypatch, capsys):
    from wb_orchestrator.cli import main
    monkeypatch.setattr(episode, "installed_world_version", lambda: NEW)
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert main(["run", "--product", str(site / "config/products/simulated-apps.yaml"),
                 "--plan", str(site / "config/plans/smoke-frontier.yaml")]) == 2
    err = capsys.readouterr().err
    assert "1.0.6" in err and NEW in err


# --- the rows carry the suite id of their world -------------------------------------

def test_a_round_on_a_new_world_set_records_its_suite_id(tmp_path):
    from wb_orchestrator.orchestrator import Orchestrator
    from wb_results.store import Store

    folder = _stamped_set(tmp_path)
    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator(store, folder, ["null"], 1, out_dir=tmp_path / "out")
    run_id = orch.run("run-new-world")
    expected = f"workflowbench-synthetic@{NEW}"
    assert store.run(run_id)["suite"] == expected
    rows = store.episodes(run=run_id)["rows"]
    assert rows and all(r["suite"] == expected for r in rows)
    assert store.episodes(run=run_id)["source"]["suite_version"] == [NEW]

    # a set without a record keeps the label every stored row already has
    old = Orchestrator(store, FIXTURE / "imported-alpha", ["null"], 1, out_dir=tmp_path / "out2")
    old_run = old.run("run-old-world")
    assert store.run(old_run)["suite"] == "workflowbench-synthetic@0.1"


def test_resume_refuses_a_run_recorded_under_another_suite(tmp_path):
    from wb_orchestrator.orchestrator import ConfigDrift, Orchestrator
    from wb_results.store import Store

    folder = _stamped_set(tmp_path)
    store = Store(tmp_path / "wb.sqlite3")
    orch = Orchestrator(store, folder, ["null"], 1, out_dir=tmp_path / "out")
    # a run whose stored hash matches but whose suite is another world's
    store.create_run("run-x", orch._hash(), "workflowbench-synthetic@0.1", orch._config())
    with pytest.raises(ConfigDrift) as e:
        orch.resume("run-x")
    assert "workflowbench-synthetic@0.1" in str(e.value) and NEW in str(e.value)


# --- reports never pool rounds of different suites -----------------------------------

def _run(store, run_id, suite, plan, passed=True):
    from runner.schema import EpisodeRow, PhaseMetrics, TokenUsage
    store.create_run(run_id, f"cfg-{run_id}", suite,
                     {"suite_dir": "tasks", "arms": ["alpha"], "k": 1, "n_tasks": 1,
                      "plan": plan, "product": "simulated-apps"})
    store.record_episode(EpisodeRow(
        episode_id=f"{run_id}/t1/alpha/t0", run_id=run_id, suite=suite, task_id="t1",
        arm="alpha", trial=0, passed=passed, assertions_passed=passed,
        invariant_passed=passed, invariant_declared=True,
        contract_sha256="abc123def4567890",
        phases={"run": PhaseMetrics(turns=1, tool_calls=1, cost_usd=0.01, wall_clock_s=1.0)},
        tokens=TokenUsage(prompt=10, cached=0, output=5), cost_usd=0.01))
    store.finish_run(run_id)


def test_summary_refuses_rounds_of_different_suites(tmp_path):
    from wb_report.report import GateError, build_summary
    from wb_results.store import Store

    store = Store(tmp_path / "wb.sqlite3")
    _run(store, "run-old", "workflowbench-synthetic@0.1", "tier-simple")
    _run(store, "run-new", f"workflowbench-synthetic@{NEW}", "achievable-50")
    _run(store, "run-new-2", f"workflowbench-synthetic@{NEW}", "achievable-50-b")

    with pytest.raises(GateError) as e:
        build_summary(store, ["run-old", "run-new"])
    assert "workflowbench-synthetic@0.1" in str(e.value) and NEW in str(e.value)

    # rounds of one suite still summarise
    s = build_summary(store, ["run-new", "run-new-2"])
    assert [r["run_id"] for r in s["rounds"]] == ["run-new", "run-new-2"]


def test_summary_cli_refuses_and_writes_nothing(tmp_path, capsys):
    from wb_orchestrator.cli import main
    from wb_results.store import Store

    store = Store(tmp_path / "wb.sqlite3")
    _run(store, "run-old", "workflowbench-synthetic@0.1", "tier-simple")
    _run(store, "run-new", f"workflowbench-synthetic@{NEW}", "achievable-50")
    out = tmp_path / "summary.html"
    assert main(["--db", str(store.path), "summary", "--runs", "run-old,run-new",
                 "--out", str(out)]) == 1
    assert NEW in capsys.readouterr().err
    assert not out.exists()


def test_report_refuses_a_run_whose_rows_span_suites(tmp_path):
    from runner.schema import EpisodeRow
    from wb_report.report import GateError, build_report
    from wb_results.store import Store

    store = Store(tmp_path / "wb.sqlite3")
    _run(store, "run-mixed", f"workflowbench-synthetic@{NEW}", "achievable-50")
    store.record_episode(EpisodeRow(
        episode_id="run-mixed/t2/alpha/t0", run_id="run-mixed",
        suite="workflowbench-synthetic@0.1", task_id="t2", arm="alpha", trial=0,
        passed=True, assertions_passed=True, invariant_passed=True, invariant_declared=True))
    with pytest.raises(GateError, match="refusing to pool"):
        build_report(store, "run-mixed")


# --- "seeded" under a world that spells out every app's empty default ------------

def _materialized(**seeds):
    """A starting state the repaired world would write: every app's default,
    plus the seeds given, the way the vendor's dataset loader spells them."""
    from automationbench.runner import strip_none_values
    from automationbench.schema.world import WorldState
    state = strip_none_values(WorldState().model_dump(mode="json"))
    state.update(seeds)
    state["meta"] = {"schema_version": "0.1.0", "current_time": "2026-02-10T10:00:00Z"}
    return state


def test_seeded_services_ignores_spelled_out_empty_defaults():
    from wb_world.episode import seeded_services

    sparse = {"meta": {}, "airtable": {}, "gmail": {"messages": [{"id": "m1"}]}}
    assert seeded_services(sparse) == ["airtable", "gmail"]      # old-style seeds: presence

    state = _materialized(gmail={"messages": [{"id": "m1"}], "threads": []})
    assert len([k for k in state if k != "meta"]) == 48           # every app is present
    assert seeded_services(state) == ["gmail"]                    # only the one with data

    # an app spelled out exactly as its default is not seeded; a default with
    # its None-valued keys left out (what the loader writes) is not either
    assert "calendly" not in seeded_services(state)
    state["calendly"].pop("current_user_id", None)
    assert "calendly" not in seeded_services(state)


def test_score_task_counts_seeded_apps_not_present_keys():
    from wb_orchestrator import tiers

    task = {"info": {"initial_state": _materialized(airtable={"actions": {"x": [1]}}),
                     "expected_changes": [1, 2], "zapier_tools": ["a"]}}
    assert tiers.score_task(task) == 1 + 2 + 1
    assert "own empty default" in tiers.MEASURE


def test_derive_allows_housekeeping_only_where_the_data_is():
    """The gmail read markers are a side effect of a task that has mail; a task
    whose gmail is the world's empty default gets no such allowance."""
    from wb_orchestrator import declare

    side_effects = [("gmail", None, [{"service": "gmail", "op": "*",
                                      "path": "gmail.messages[*].is_read"}])]
    assertion = {"type": "airtable_record_exists", "applicationId": "b", "tableName": "T",
                 "fields": {"Name": "x"}}
    with_mail = {"info": {"assertions": [assertion],
                          "initial_state": _materialized(gmail={"messages": [{"id": "m1"}]})}}
    without = {"info": {"assertions": [assertion], "initial_state": _materialized()}}
    assert declare.derive(with_mail, side_effects)["allowed"] == side_effects[0][2]
    assert declare.derive(without, side_effects)["allowed"] == []


def test_tiers_manifest_names_the_world(tmp_path):
    from wb_orchestrator import tiers

    r = tiers.draw(sorted(FIXTURE.glob("imported-*")), seed=7, per_tier=1,
                   out=tmp_path / "old")
    manifest = yaml.safe_load((tmp_path / "old" / "tiers-manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["world"] == {"package": "automation-bench", "version": "1.0.6"}
    assert r.usable and all(len(v) == 1 for v in r.sets.values())

    stamped = tmp_path / "corpus-new"
    shutil.copytree(FIXTURE, stamped)
    for p in stamped.glob("imported-*/*.json"):
        task = load_task_file(p)
        if task.get("contract_sha256") == contract_hash(task):    # keep the fixture's drift case
            _stamp(p)
    tiers.draw(sorted(stamped.glob("imported-*")), seed=7, per_tier=1, out=tmp_path / "new")
    manifest = yaml.safe_load((tmp_path / "new" / "tiers-manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["world"]["version"] == NEW
    drawn = [load_task_file(p) for p in (tmp_path / "new").glob("tier-*/*.json")]
    assert drawn and suite_id(drawn) == f"workflowbench-synthetic@{NEW}"
