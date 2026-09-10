"""`wb corpus slate`: freeze a task set listed by id, with its manifest.

Unblock plan of 8 Sep 2026, milestone M2. A slate is a frozen task set whose
members were listed by hand (an id per line) rather than drawn by a seed. Every
copy is byte for byte its corpus original; the manifest records the selection
rule, why the set exists, the suite revision, and every task's hash, difficulty
score and tier label, so a round on the slate has the same source line a tier
round has.

Everything here is offline and runs against tests/fixtures/mini-corpus, the
same twelve hand-written tasks test_tiers.py describes:

    alpha: 2, 3, 3, 4, 5
    beta:  6, 6, 7, 8 (with a "meta" key), one with no rule
    gamma: 9, 10, 11, 13, one whose embedded hash does not match its content

Thirteen usable tasks -> terciles at 4 and 7 when no tiers manifest is present.
"""
from __future__ import annotations

import importlib.metadata
import json
import shutil
from pathlib import Path

import pytest
import yaml

from wb_orchestrator import slate
from wb_world.episode import contract_hash, load_task_file

FIXTURE = Path(__file__).parent / "fixtures" / "mini-corpus"
CORPUS_DIRS = sorted(FIXTURE.glob("imported-*"))
REPO = Path(__file__).resolve().parents[1]

THREE = ["alpha.a_two", "beta.b_six", "gamma.g_nine"]


def _ids_file(path: Path, ids, header="# three tasks, one per domain\n# picked by hand\n") -> Path:
    path.write_text(header + "\n".join(ids) + "\n", encoding="utf-8", newline="\n")
    return path


def _corpus_file(task_id: str) -> Path:
    domain = task_id.split(".", 1)[0]
    return FIXTURE / f"imported-{domain}" / f"{task_id}.json"


def _manifest(out: Path) -> dict:
    return yaml.safe_load((out.parent / f"{out.name}-manifest.yaml").read_text(encoding="utf-8"))


# --- the id list ---------------------------------------------------------------

def test_read_ids_keeps_order_and_the_comment_lines(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text(
        "# rule: every 595/50-th task of the sorted achievable universe\n"
        "# source: .references/ApplicationBench/evidence/runs/x/README.md\n"
        "\n"
        "  gamma.g_nine  \n"
        "alpha.a_two\n"
        "\n"
        "beta.b_six\n", encoding="utf-8", newline="\n")
    got = slate.read_ids(path)
    assert got.ids == ["gamma.g_nine", "alpha.a_two", "beta.b_six"]   # as listed, not sorted
    assert got.selection_rule == (
        "rule: every 595/50-th task of the sorted achievable universe\n"
        "source: .references/ApplicationBench/evidence/runs/x/README.md")
    assert got.path == path


def test_read_ids_refuses_a_duplicate_and_an_empty_list(tmp_path):
    with pytest.raises(slate.Refusal) as e:
        slate.read_ids(_ids_file(tmp_path / "dup.txt", ["alpha.a_two", "beta.b_six", "alpha.a_two"]))
    assert e.value.offenders == [("alpha.a_two", "listed more than once")]

    with pytest.raises(slate.Refusal) as e:
        slate.read_ids(_ids_file(tmp_path / "empty.txt", [], header="# nothing\n"))
    assert "no task id" in str(e.value)

    with pytest.raises(FileNotFoundError):
        slate.read_ids(tmp_path / "nowhere.txt")


# --- the freeze ----------------------------------------------------------------

def test_freeze_copies_each_task_unchanged_and_writes_the_manifest(tmp_path):
    ids = _ids_file(tmp_path / "mini-3-ids.txt", THREE)
    out = tmp_path / "tasks" / "mini-3"
    r = slate.freeze(ids, out, because="three tasks for the test", dirs=CORPUS_DIRS)

    # byte for byte: no label added, no re-serialisation (unlike the tier draw)
    for task_id in THREE:
        assert (out / f"{task_id}.json").read_bytes() == _corpus_file(task_id).read_bytes()
    assert sorted(p.name for p in out.iterdir()) == [f"{t}.json" for t in sorted(THREE)]

    m = _manifest(out)
    assert r.manifest == out.parent / "mini-3-manifest.yaml"
    assert m["name"] == "mini-3"
    assert m["generated_at"] and "refrozen_at" not in m
    assert m["selection_rule"] == "three tasks, one per domain\npicked by hand"
    assert m["because"] == "three tasks for the test"
    assert m["source_ids"] == ids.as_posix()
    assert m["suite_revision"] == importlib.metadata.version("automation-bench")
    # no tiers manifest beside the set: the cuts are the corpus's own terciles
    assert m["cuts"] == {"low": 4, "high": 7}
    assert m["cuts_source"] == "computed from the corpus"
    assert "services seeded" in m["measure"]
    assert m["corpus"] == [
        {"dir": (FIXTURE / "imported-alpha").as_posix(), "domain": "alpha", "tasks": 5, "usable": 5},
        {"dir": (FIXTURE / "imported-beta").as_posix(), "domain": "beta", "tasks": 5, "usable": 4},
        {"dir": (FIXTURE / "imported-gamma").as_posix(), "domain": "gamma", "tasks": 5, "usable": 4},
    ]
    assert m["count"] == 3
    assert m["count_per_domain"] == {"alpha": 1, "beta": 1, "gamma": 1}
    assert m["tasks"] == [
        {"task": "alpha.a_two", "domain": "alpha", "score": 2, "tier": "simple",
         "contract_sha256": contract_hash(load_task_file(_corpus_file("alpha.a_two")))},
        {"task": "beta.b_six", "domain": "beta", "score": 6, "tier": "medium",
         "contract_sha256": contract_hash(load_task_file(_corpus_file("beta.b_six")))},
        {"task": "gamma.g_nine", "domain": "gamma", "score": 9, "tier": "complex",
         "contract_sha256": contract_hash(load_task_file(_corpus_file("gamma.g_nine")))},
    ]
    # the manifest's hash is the file's own embedded hash: the copy is regradable
    for row in m["tasks"]:
        assert row["contract_sha256"] == load_task_file(out / f"{row['task']}.json")["contract_sha256"]

    assert r.name == "mini-3" and r.count == 3
    assert r.by_domain == {"alpha": 1, "beta": 1, "gamma": 1}
    assert r.by_tier == {"simple": 1, "medium": 1, "complex": 1}
    assert r.suite_revision == m["suite_revision"]
    assert set(r.written) == {out / f"{t}.json" for t in THREE} | {r.manifest}


def test_cuts_and_measure_come_from_the_tiers_manifest_when_present(tmp_path):
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()
    (tasks_root / "tiers-manifest.yaml").write_text(yaml.safe_dump(
        {"measure": "the tier measure, in words", "seed": 1, "per_tier": 3,
         "cuts": {"low": 1, "high": 5}, "sets": {}}), encoding="utf-8")
    ids = _ids_file(tmp_path / "ids.txt", THREE)
    r = slate.freeze(ids, tasks_root / "mini-3", because="x", dirs=CORPUS_DIRS)

    m = _manifest(tasks_root / "mini-3")
    assert m["cuts"] == {"low": 1, "high": 5}
    assert m["cuts_source"] == (tasks_root / "tiers-manifest.yaml").as_posix()
    assert m["measure"] == "the tier measure, in words"
    # the labels follow the reused cut points, not the corpus's own terciles
    assert {row["task"]: row["tier"] for row in m["tasks"]} == {
        "alpha.a_two": "medium", "beta.b_six": "complex", "gamma.g_nine": "complex"}
    assert r.by_tier == {"simple": 0, "medium": 1, "complex": 2}


def test_corpus_is_not_written(tmp_path):
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
              for d in CORPUS_DIRS for p in d.glob("*.json")}
    slate.freeze(_ids_file(tmp_path / "ids.txt", THREE), tmp_path / "tasks" / "mini-3",
                 because="x", dirs=CORPUS_DIRS)
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns)
             for d in CORPUS_DIRS for p in d.glob("*.json")}
    assert before == after


# --- refusals: every offender named, nothing written -----------------------------

def _freeze_elsewhere(tasks_root: Path, set_name: str, task_ids, manifest: bool = False):
    """Plant a frozen set beside the slate: tier-*, random-10, or a named manifest."""
    folder = tasks_root / set_name
    folder.mkdir(parents=True)
    for task_id in task_ids:
        shutil.copyfile(_corpus_file(task_id), folder / f"{task_id}.json")
    if manifest:
        (tasks_root / f"{set_name}-manifest.yaml").write_text(
            yaml.safe_dump({"name": set_name, "tasks": [{"task": t} for t in task_ids]}),
            encoding="utf-8")


def test_freeze_refuses_and_names_every_offender(tmp_path):
    tasks_root = tmp_path / "tasks"
    _freeze_elsewhere(tasks_root, "tier-simple", ["alpha.a_three"])
    _freeze_elsewhere(tasks_root, "random-10", ["beta.b_seven"])
    _freeze_elsewhere(tasks_root, "other-slate", ["gamma.g_ten"], manifest=True)
    # a folder with no manifest and no tier name is not a frozen set
    _freeze_elsewhere(tasks_root, "scratch", ["gamma.g_eleven"])

    ids = _ids_file(tmp_path / "ids.txt", [
        "alpha.a_two",            # fine
        "nobody.missing",         # not in the corpus
        "beta.b_no_rule",         # no approval rule
        "gamma.g_bad_hash",       # embedded hash does not match the content
        "alpha.a_three",          # frozen in tier-simple
        "beta.b_seven",           # frozen in random-10
        "gamma.g_ten",            # frozen in other-slate (named by its manifest)
        "gamma.g_eleven",         # only in a scratch folder: fine
    ])
    out = tasks_root / "mini"
    with pytest.raises(slate.Refusal) as e:
        slate.freeze(ids, out, because="x", dirs=CORPUS_DIRS)

    assert e.value.offenders == [
        ("nobody.missing", "not in the corpus"),
        ("beta.b_no_rule", "no approval rule (expected_changes is empty)"),
        ("gamma.g_bad_hash", "contract hash does not match content"),
        ("alpha.a_three", "already frozen in tier-simple"),
        ("beta.b_seven", "already frozen in random-10"),
        ("gamma.g_ten", "already frozen in other-slate"),
    ]
    text = str(e.value)
    assert text.startswith("refusing to freeze mini: 6 of 8 ids cannot be frozen")
    for task_id, reason in e.value.offenders:
        assert f"  {task_id}: {reason}" in text
    assert not out.exists()
    assert not (tasks_root / "mini-manifest.yaml").exists()


def test_no_rule_means_either_key_absent(tmp_path):
    """A derived rule has both halves: what must change and what may change."""
    corpus = tmp_path / "corpus" / "imported-alpha"
    corpus.mkdir(parents=True)
    for name in ("alpha.a_two", "alpha.a_three", "alpha.a_four"):
        task = load_task_file(_corpus_file(name))
        if name == "alpha.a_two":
            del task["info"]["allowed_changes"]
        if name == "alpha.a_three":
            del task["info"]["expected_changes"]
        task["contract_sha256"] = contract_hash(task)        # so drift is not the reason
        (corpus / f"{name}.json").write_text(json.dumps(task), encoding="utf-8")

    ids = _ids_file(tmp_path / "ids.txt", ["alpha.a_two", "alpha.a_three", "alpha.a_four"])
    with pytest.raises(slate.Refusal) as e:
        slate.freeze(ids, tmp_path / "tasks" / "mini", because="x", dirs=[corpus])
    assert e.value.offenders == [
        ("alpha.a_two", "no approval rule (allowed_changes is absent)"),
        ("alpha.a_three", "no approval rule (expected_changes is absent)"),
    ]


def test_frozen_overlap_can_be_allowed_explicitly_and_is_recorded(tmp_path):
    """The rule stays; an explicit override records the overlap in the manifest."""
    tasks_root = tmp_path / "tasks"
    _freeze_elsewhere(tasks_root, "tier-complex", ["gamma.g_nine"])
    ids = _ids_file(tmp_path / "ids.txt", THREE)
    out = tasks_root / "mini-3"

    with pytest.raises(slate.Refusal):
        slate.freeze(ids, out, because="x", dirs=CORPUS_DIRS)
    r = slate.freeze(ids, out, because="x", dirs=CORPUS_DIRS, allow_frozen_overlap=True)
    assert r.frozen_overlap == {"gamma.g_nine": "tier-complex"}
    assert _manifest(out)["frozen_overlap"] == {"gamma.g_nine": "tier-complex"}
    # the override never covers the other refusals
    bad = _ids_file(tmp_path / "bad.txt", ["alpha.a_two", "nobody.missing"])
    with pytest.raises(slate.Refusal) as e:
        slate.freeze(bad, tasks_root / "mini-bad", because="x", dirs=CORPUS_DIRS,
                     allow_frozen_overlap=True)
    assert e.value.offenders == [("nobody.missing", "not in the corpus")]


# --- a non-empty folder: refuse, or refreeze the same ids ------------------------

def test_non_empty_folder_refuses_without_refreeze(tmp_path):
    ids = _ids_file(tmp_path / "ids.txt", THREE)
    out = tmp_path / "tasks" / "mini-3"
    slate.freeze(ids, out, because="x", dirs=CORPUS_DIRS)
    stamp = {p: p.stat().st_mtime_ns for p in out.iterdir()}

    with pytest.raises(slate.Refusal) as e:
        slate.freeze(ids, out, because="x", dirs=CORPUS_DIRS)
    assert "already holds 3 files" in str(e.value) and "--refreeze" in str(e.value)
    assert {p: p.stat().st_mtime_ns for p in out.iterdir()} == stamp

    # an empty folder is not a frozen set yet (other ids: mini-3 now holds THREE)
    empty = tmp_path / "tasks" / "mini-empty"
    empty.mkdir()
    others = _ids_file(tmp_path / "others.txt", ["alpha.a_three", "beta.b_seven", "gamma.g_ten"])
    slate.freeze(others, empty, because="x", dirs=CORPUS_DIRS)
    assert len(list(empty.glob("*.json"))) == 3


def test_refreeze_keeps_the_ids_and_refreshes_content_and_hashes(tmp_path):
    corpus = tmp_path / "corpus" / "imported-alpha"
    corpus.mkdir(parents=True)
    for name in ("alpha.a_two", "alpha.a_three"):
        shutil.copyfile(_corpus_file(name), corpus / f"{name}.json")
    ids = _ids_file(tmp_path / "ids.txt", ["alpha.a_two", "alpha.a_three"])
    out = tmp_path / "tasks" / "mini-2"
    first = slate.freeze(ids, out, because="the first freeze", dirs=[corpus])
    old = _manifest(out)

    # an approval-rule change rewrites a corpus task and its hash
    task = load_task_file(corpus / "alpha.a_two.json")
    task["info"]["allowed_changes"] = [{"op": "changed", "path": "airtable.*", "service": "airtable"}]
    task["contract_sha256"] = contract_hash(task)
    (corpus / "alpha.a_two.json").write_text(json.dumps(task, indent=1), encoding="utf-8")

    # the ids file is not needed: the manifest already records them
    r = slate.freeze(None, out, because="rules changed", dirs=[corpus], refreeze=True)
    assert [t.task_id for t in r.tasks] == ["alpha.a_three", "alpha.a_two"]   # sorted by id
    assert (out / "alpha.a_two.json").read_bytes() == (corpus / "alpha.a_two.json").read_bytes()
    m = _manifest(out)
    assert m["refrozen_at"] and m["refrozen_because"] == "rules changed"
    assert m["because"] == "the first freeze"                    # why the set exists, unchanged
    assert m["selection_rule"] == old["selection_rule"]
    assert m["source_ids"] == old["source_ids"]
    assert [t["task"] for t in m["tasks"]] == [t["task"] for t in old["tasks"]]
    new_row = {t["task"]: t for t in m["tasks"]}["alpha.a_two"]
    old_row = {t["task"]: t for t in old["tasks"]}["alpha.a_two"]
    assert new_row["contract_sha256"] == task["contract_sha256"] != old_row["contract_sha256"]
    assert first.manifest == r.manifest

    # the set's own members are not "already frozen" while it is refrozen…
    assert r.frozen_overlap == {}
    # …but an ids file that lists a different set is refused
    other = _ids_file(tmp_path / "other.txt", ["alpha.a_two"])
    with pytest.raises(slate.Refusal) as e:
        slate.freeze(other, out, because="x", dirs=[corpus], refreeze=True)
    assert "alpha.a_three" in str(e.value) and "manifest" in str(e.value)

    # a refreeze needs a manifest to take the ids from
    with pytest.raises(FileNotFoundError):
        slate.freeze(None, tmp_path / "tasks" / "never-frozen", because="x",
                     dirs=[corpus], refreeze=True)


def test_refreeze_refuses_when_a_member_left_the_corpus(tmp_path):
    corpus = tmp_path / "corpus" / "imported-alpha"
    corpus.mkdir(parents=True)
    for name in ("alpha.a_two", "alpha.a_three"):
        shutil.copyfile(_corpus_file(name), corpus / f"{name}.json")
    out = tmp_path / "tasks" / "mini-2"
    slate.freeze(_ids_file(tmp_path / "ids.txt", ["alpha.a_two", "alpha.a_three"]),
                 out, because="x", dirs=[corpus])
    (corpus / "alpha.a_three.json").unlink()
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(slate.Refusal) as e:
        slate.freeze(None, out, because="x", dirs=[corpus], refreeze=True)
    assert e.value.offenders == [("alpha.a_three", "not in the corpus")]
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before   # untouched


# --- the command -----------------------------------------------------------------

def test_cli(tmp_path, capsys, monkeypatch):
    from wb_orchestrator.cli import main

    monkeypatch.chdir(tmp_path)
    ids = _ids_file(tmp_path / "mini-3-ids.txt", THREE)
    corpus_args = [f"--corpus={d}" for d in CORPUS_DIRS]
    argv = ["corpus", "slate", "--ids", str(ids), "--out", "tasks/mini-3",
            "--because", "three tasks for the test"] + corpus_args
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert ("mini-3: 3 tasks frozen from 3 corpus folders (15 tasks, 13 usable) "
            "at suite revision " + importlib.metadata.version("automation-bench")) in out
    assert "per domain: alpha 1, beta 1, gamma 1" in out
    assert "cuts 4/7 computed from the corpus: simple 1, medium 1, complex 1" in out
    assert "every copy is byte for byte its corpus original and keeps its hash" in out
    assert "[ok] write tasks/mini-3/ (3 files)" in out
    assert "[ok] write tasks/mini-3-manifest.yaml" in out
    assert (tmp_path / "tasks" / "mini-3-manifest.yaml").exists()

    # a refusal lists every offender on stderr and exits 2, writing nothing
    # (alpha.a_three is fine: mini-3 froze THREE, not it)
    bad = _ids_file(tmp_path / "bad.txt", ["alpha.a_three", "nobody.missing", "beta.b_no_rule"])
    assert main(["corpus", "slate", "--ids", str(bad), "--out", "tasks/mini-bad",
                 "--because", "x"] + corpus_args) == 2
    err = capsys.readouterr().err
    assert "refusing to freeze mini-bad: 2 of 3 ids cannot be frozen" in err
    assert "  nobody.missing: not in the corpus" in err
    assert "  beta.b_no_rule: no approval rule (expected_changes is empty)" in err
    assert not (tmp_path / "tasks" / "mini-bad").exists()

    # the same set again without --refreeze is a refusal too
    assert main(argv) == 2
    assert "--refreeze" in capsys.readouterr().err

    # --refreeze rewrites the same ids and says so
    assert main(["corpus", "slate", "--out", "tasks/mini-3", "--refreeze",
                 "--because", "rules changed"] + corpus_args) == 0
    out = capsys.readouterr().out
    assert "mini-3: 3 tasks refrozen" in out and "rules changed" in out

    # a missing ids file or corpus folder is exit 3
    assert main(["corpus", "slate", "--ids", "nowhere.txt", "--out", "tasks/x",
                 "--because", "x"] + corpus_args) == 3
    assert main(["corpus", "slate", "--ids", str(ids), "--out", "tasks/x",
                 "--because", "x", f"--corpus={tmp_path / 'nowhere'}"]) == 3
    # and a fresh freeze without --ids is a usage error, not a crash
    assert main(["corpus", "slate", "--out", "tasks/x", "--because", "x"] + corpus_args) == 2
    assert "--ids" in capsys.readouterr().err


# --- the repository state: the achievable-50 slate ---------------------------------

SCORED_DOMAINS = ("finance", "hr", "marketing", "operations", "sales", "support")


def test_achievable_50_ids_file():
    """The ApplicationBench achievable50 slate, as listed for the gauntlet."""
    got = slate.read_ids(REPO / "tasks" / "achievable-50-ids.txt")
    assert len(got.ids) == 50 and len(set(got.ids)) == 50
    assert got.ids == sorted(got.ids)
    assert not [t for t in got.ids if t.startswith("simple.")]
    per_domain = {d: sum(t.startswith(d + ".") for t in got.ids) for d in SCORED_DOMAINS}
    assert sum(per_domain.values()) == 50
    assert all(8 <= n <= 9 for n in per_domain.values()), per_domain
    assert "595" in got.selection_rule and "ApplicationBench" in got.selection_rule
    for task_id in got.ids:
        domain = task_id.split(".", 1)[0]
        assert (REPO / "corpus" / f"imported-{domain}" / f"{task_id}.json").exists(), task_id


def test_achievable_50_frozen_set_matches_the_corpus_and_its_manifest():
    """Once frozen, the copies, the manifest and the corpus must agree."""
    out = REPO / "tasks" / "achievable-50"
    manifest = REPO / "tasks" / "achievable-50-manifest.yaml"
    if not out.is_dir() or not manifest.exists():
        pytest.skip("tasks/achievable-50 is not frozen in this checkout")
    m = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    ids = slate.read_ids(REPO / "tasks" / "achievable-50-ids.txt").ids
    assert [row["task"] for row in m["tasks"]] == sorted(ids)
    assert m["count"] == 50 and sum(m["count_per_domain"].values()) == 50
    # The originals live in the corpus folders the manifest records (a re-freeze may
    # have moved the set to another revision's corpus, e.g. corpus-evalrepair10/).
    folders = {}
    for entry in m.get("corpus") or []:
        folder = Path(entry["dir"])
        if not folder.is_absolute():
            folder = REPO / folder
        elif not folder.is_dir() and "workflowbench" in folder.parts:
            folder = REPO.joinpath(*folder.parts[folder.parts.index("workflowbench") + 1:])
        folders[entry["domain"]] = folder
    for row in m["tasks"]:
        copy = out / f"{row['task']}.json"
        original = folders.get(row["domain"], REPO / "corpus" / f"imported-{row['domain']}") / copy.name
        assert copy.read_bytes() == original.read_bytes(), row["task"]
        task = load_task_file(copy)
        assert row["contract_sha256"] == task["contract_sha256"] == contract_hash(task), row["task"]
