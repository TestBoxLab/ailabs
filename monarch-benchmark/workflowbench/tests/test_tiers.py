"""Feature 005: the difficulty score, the tercile cuts and the stratified draw.

Everything here is offline and runs against tests/fixtures/mini-corpus, twelve
hand-written tasks whose scores are arithmetic anyone can check:

    alpha: 2, 3, 4, 5
    beta:  6, 7, 8 (with a "meta" key that must not count), one with no rule
    gamma: 9, 11, 13, one whose embedded hash does not match its content

Ten usable tasks with scores 2 3 4 5 6 7 8 9 11 13 -> terciles at 4 and 8.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from wb_world.episode import contract_hash, load_task_file

FIXTURE = Path(__file__).parent / "fixtures" / "mini-corpus"
CORPUS_DIRS = sorted(FIXTURE.glob("imported-*"))
REPO = Path(__file__).resolve().parents[1]


# --- Phase 2: the hash ignores the two labels ---------------------------------

def test_label_keys_are_not_hashed():
    task = load_task_file(FIXTURE / "imported-alpha" / "alpha.a_two.json")
    before = contract_hash(task)
    labelled = json.loads(json.dumps(task))
    labelled["info"]["tier"] = "simple"
    labelled["info"]["domain"] = "alpha"
    assert contract_hash(labelled) == before

    # any other field still moves it
    moved = json.loads(json.dumps(task))
    moved["info"]["zapier_tools"] = ["something_else"]
    assert contract_hash(moved) != before
    renamed = json.loads(json.dumps(task))
    renamed["task"] = "alpha.other"
    assert contract_hash(renamed) != before


# Recorded before info.tier/info.domain were added to the hash's ignore list.
PILOT_HASHES = {
    "simple.email_sf_contact_city_update": "d44c785ac30f7594",
    "simple.email_sf_contact_department_update": "b9cc657f5211f6dd",
    "simple.email_sf_contact_email_update": "9ab50a805eb61fd0",
    "simple.email_sf_contact_mobile_update": "4a2dd47d40568336",
    "simple.email_sf_contact_phone_update": "ba8207061c75d326",
    "simple.email_sf_contact_title_update": "defdeebff5f5cee5",
    "simple.sf_opp_amount_update": "e747c8f680e2fb2d",
    "simple.sf_opp_closed_won": "e4a3adbe074495d5",
    "simple.sf_opp_next_step_update": "e327964ce7bccc6f",
    "simple.sf_opp_stage_proposal": "7a0ebbefc91c3147",
}


def test_existing_hashes_do_not_move():
    """The ten pilot tasks and twenty sampled corpus tasks keep their hash.

    Adding keys to the ignore list must move no hash that exists today, or every
    stored row becomes non-regradable (data-model.md section 8). The pilot files
    embed no contract_sha256, so their hashes are pinned above instead.
    """
    pilot = sorted((REPO / "tasks").glob("*.json"))
    assert len(pilot) == 10, pilot
    for p in pilot:
        assert contract_hash(load_task_file(p)) == PILOT_HASHES[p.stem], p.name

    sampled = sorted((REPO / "corpus" / "imported-simple").glob("*.json"))[:20]
    assert len(sampled) == 20
    for p in sampled:
        task = load_task_file(p)
        assert task["contract_sha256"] == contract_hash(task), p.name


# --- Phase 3: the measure -----------------------------------------------------

def test_score_task():
    from wb_orchestrator import tiers

    # two services, three expected changes, four tools -> 9
    task = {"info": {"initial_state": {"gmail": {}, "salesforce": {}},
                     "expected_changes": [1, 2, 3],
                     "zapier_tools": ["a", "b", "c", "d"]}}
    assert tiers.score_task(task) == 9

    # "meta" in the starting data is bookkeeping, not a service
    with_meta = {"info": {"initial_state": {"meta": {}, "gmail": {}, "salesforce": {}},
                          "expected_changes": [1, 2, 3],
                          "zapier_tools": ["a", "b", "c", "d"]}}
    assert tiers.score_task(with_meta) == 9

    # no tools, one service, one expected change -> 2
    small = {"info": {"initial_state": {"gmail": {}}, "expected_changes": [1],
                      "zapier_tools": []}}
    assert tiers.score_task(small) == 2


def test_score_task_on_the_fixture():
    from wb_orchestrator import tiers
    scored = {load_task_file(p)["task"]: tiers.score_task(load_task_file(p))
              for d in CORPUS_DIRS for p in sorted(d.glob("*.json"))}
    assert scored["alpha.a_two"] == 2
    assert scored["beta.b_eight_meta"] == 8      # the meta key is not counted
    assert scored["gamma.g_thirteen"] == 13


def test_tier_cuts_and_tier_of():
    from wb_orchestrator import tiers

    # nine values, terciles unambiguous: 1 2 3 | 4 5 6 | 7 8 9
    cuts = tiers.tier_cuts([9, 1, 8, 2, 7, 3, 6, 4, 5])
    assert cuts == {"low": 3, "high": 6}

    assert tiers.tier_of(1, cuts) == "simple"
    assert tiers.tier_of(3, cuts) == "simple"     # on the low cut -> lower tier
    assert tiers.tier_of(4, cuts) == "medium"
    assert tiers.tier_of(6, cuts) == "medium"     # on the high cut -> lower tier
    assert tiers.tier_of(7, cuts) == "complex"    # strictly above high


def test_usable_pool():
    from wb_orchestrator import tiers
    pool = tiers.load_corpus(CORPUS_DIRS)

    by_id = {e.task_id: e for e in pool.entries}
    assert set(by_id) == {
        "alpha.a_two", "alpha.a_three", "alpha.a_three_b", "alpha.a_four",
        "alpha.a_five", "beta.b_six", "beta.b_six_b", "beta.b_seven",
        "beta.b_eight_meta", "gamma.g_nine", "gamma.g_ten", "gamma.g_eleven",
        "gamma.g_thirteen",
    }
    assert by_id["gamma.g_nine"].domain == "gamma"
    assert by_id["gamma.g_nine"].score == 9
    assert by_id["gamma.g_nine"].contract_sha256 == load_task_file(
        FIXTURE / "imported-gamma" / "gamma.g_nine.json")["contract_sha256"]

    assert set(pool.excluded) == {"beta.b_no_rule", "gamma.g_bad_hash"}
    assert pool.excluded["beta.b_no_rule"] == (
        "no approval rule (unmapped assertion types: ['mini_unmappable'])")
    assert pool.excluded["gamma.g_bad_hash"] == "contract hash does not match content"

    # the excluded two are not scored and not in the pool
    assert "beta.b_no_rule" not in by_id and "gamma.g_bad_hash" not in by_id
    # counts per folder are recorded for the manifest
    assert pool.counts == {"alpha": (5, 5), "beta": (5, 4), "gamma": (5, 4)}


# --- Phase 4: the draw --------------------------------------------------------

def _entries(spec):
    """spec: {domain: [task ids]} -> a flat list of Entry, score and hash unused."""
    from wb_orchestrator import tiers
    return [tiers.Entry(t, d, 1, "0" * 16, Path(t))
            for d in sorted(spec) for t in spec[d]]


def test_stratified_draw():
    from wb_orchestrator import tiers
    pool = _entries({"delta": ["d1"], "alpha": ["a1", "a2", "a3", "a4"],
                     "charlie": ["c1", "c2"], "bravo": ["b1", "b2", "b3"]})

    got = tiers.draw_tier(pool, 4, random.Random(1))
    assert len({e.domain for e in got}) == 4      # as many domains as the counts allow
    assert [e.domain for e in got] == ["alpha", "bravo", "charlie", "delta"]

    # the shortfall is filled from the domains that still have candidates
    got = tiers.draw_tier(pool, 8, random.Random(1))
    assert len(got) == 8 and len({e.task_id for e in got}) == 8
    by_domain = {}
    for e in got:
        by_domain[e.domain] = by_domain.get(e.domain, 0) + 1
    # passes of 4, then 3, then 1 (alpha alone still has candidates): 4 + 3 + 1 = 8
    assert by_domain == {"alpha": 3, "bravo": 2, "charlie": 2, "delta": 1}
    # first pass walks the domains alphabetically
    assert [e.domain for e in got[:4]] == ["alpha", "bravo", "charlie", "delta"]


def test_tier_too_small_refuses(tmp_path):
    from wb_orchestrator import tiers
    with pytest.raises(ValueError) as e:
        tiers.draw(CORPUS_DIRS, seed=1, per_tier=10, out=tmp_path)
    assert "simple" in str(e.value) and "4 usable tasks" in str(e.value)
    assert not list(tmp_path.iterdir())            # nothing was written


def test_drawn_task_is_a_frozen_copy(tmp_path):
    from wb_orchestrator import corpus as corpus_mod
    from wb_orchestrator import tiers
    result = tiers.draw(CORPUS_DIRS, seed=1, per_tier=3, out=tmp_path)

    originals = {load_task_file(p)["task"]: load_task_file(p)
                 for d in CORPUS_DIRS for p in d.glob("*.json")}
    n = 0
    for set_name in tiers.SET_NAMES:
        folder = tmp_path / set_name
        for p in sorted(folder.glob("*.json")):
            drawn = load_task_file(p)
            original = originals[drawn["task"]]
            assert drawn["info"].pop("tier") in ("simple", "medium", "complex", "random")
            assert drawn["info"].pop("domain") in ("alpha", "beta", "gamma")
            assert drawn == original                       # nothing else differs
            assert drawn["contract_sha256"] == original["contract_sha256"]
            n += 1
        v = corpus_mod.validate_corpus(folder)
        assert v["contract_drift"] == 0, folder
    assert n == 12          # four sets of three
    assert result.cuts == {"low": 4, "high": 7}


def test_draw_is_deterministic(tmp_path):
    from wb_orchestrator import tiers
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    tiers.draw(CORPUS_DIRS, seed=1, per_tier=3, out=a)
    tiers.draw(CORPUS_DIRS, seed=1, per_tier=3, out=b)
    tiers.draw(CORPUS_DIRS, seed=2, per_tier=3, out=c)

    def tree(root):
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in sorted(root.rglob("*")) if p.is_file()
                and p.name != "tiers-manifest.yaml"}

    assert tree(a) == tree(b)
    def manifest(root):
        import yaml
        return yaml.safe_load((root / "tiers-manifest.yaml").read_text())
    ma, mb, mc = manifest(a), manifest(b), manifest(c)
    for m in (ma, mb, mc):
        m.pop("generated_at")
    assert ma == mb
    assert mc["sets"] != ma["sets"]                 # a different seed is a different set


def test_manifest(tmp_path):
    import yaml
    from wb_orchestrator import tiers
    tiers.draw(CORPUS_DIRS, seed=1, per_tier=3, out=tmp_path)
    m = yaml.safe_load((tmp_path / "tiers-manifest.yaml").read_text())

    assert "services seeded" in m["measure"] and "terciles" in m["measure"]
    assert m["cuts"] == {"low": 4, "high": 7}
    assert m["seed"] == 1 and m["per_tier"] == 3 and m["generated_at"]
    assert m["corpus"] == [
        {"dir": (FIXTURE / "imported-alpha").as_posix(), "domain": "alpha", "tasks": 5, "usable": 5},
        {"dir": (FIXTURE / "imported-beta").as_posix(), "domain": "beta", "tasks": 5, "usable": 4},
        {"dir": (FIXTURE / "imported-gamma").as_posix(), "domain": "gamma", "tasks": 5, "usable": 4},
    ]
    assert set(m["excluded"]) == {"beta.b_no_rule", "gamma.g_bad_hash"}

    assert list(m["sets"]) == list(tiers.SET_NAMES)
    for name, s in m["sets"].items():
        assert len(s["tasks"]) == 3
        assert sum(s["by_domain"].values()) == 3
        for row in s["tasks"]:
            assert set(row) == {"task", "domain", "score", "tier", "contract_sha256"}
            assert row["tier"] in ("simple", "medium", "complex")   # never "random"

    # a drawn file's own info.tier is the set's name for the three tiers…
    for tier in ("simple", "medium", "complex"):
        for row in m["sets"][f"tier-{tier}"]["tasks"]:
            assert row["tier"] == tier
    # …and the literal "random" in random-10, whose rows carry the real tier
    for p in (tmp_path / "random-10").glob("*.json"):
        assert load_task_file(p)["info"]["tier"] == "random"


def test_corpus_is_not_written(tmp_path):
    from wb_orchestrator import tiers
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
              for d in CORPUS_DIRS for p in d.glob("*.json")}
    tiers.draw(CORPUS_DIRS, seed=1, per_tier=3, out=tmp_path)
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns)
             for d in CORPUS_DIRS for p in d.glob("*.json")}
    assert before == after


def test_cli(tmp_path, capsys):
    from wb_orchestrator.cli import main

    argv = ["corpus", "tiers", "--seed", "1", "--per-tier", "3",
            "--out", str(tmp_path)] + [f"--corpus={d}" for d in CORPUS_DIRS]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "corpus: 3 folders, 15 tasks, 13 usable" in out
    assert ("  excluded 2: 1 with no approval rule (unmapped assertion types), "
            "1 whose hash does not match its content - see the manifest") in out
    assert "measure: services seeded + expected changes + tools needed" in out
    assert "cuts: simple <= 4 < medium <= 7 < complex" in out
    assert "draw (seed 1, 3 per set):" in out
    assert "tier-simple" in out and "random-10" in out
    assert "[ok] write" in out and "tiers-manifest.yaml" in out
    assert ("random-10 is drawn from the usable corpus minus the thirty tier "
            "tasks, so the four sets share no task") in out
    assert ("every drawn task keeps its corpus hash; info.tier and info.domain "
            "are not hashed") in out
    assert (tmp_path / "tiers-manifest.yaml").exists()

    # a tier with fewer usable tasks than --per-tier refuses, exit 1, writes nothing
    empty = tmp_path / "refused"
    argv = ["corpus", "tiers", "--seed", "1", "--per-tier", "10",
            "--out", str(empty)] + [f"--corpus={d}" for d in CORPUS_DIRS]
    assert main(argv) == 1
    assert "simple" in capsys.readouterr().err
    assert not empty.exists()

    # a missing corpus folder is exit 3
    assert main(["corpus", "tiers", "--seed", "1", "--out", str(tmp_path / "x"),
                 f"--corpus={tmp_path / 'nowhere'}"]) == 3


def test_random_set_excludes_the_tier_tasks(tmp_path):
    """The random round is an independent check, so it reuses no tier task.

    Decision of 4 Sep 2026 (Carlos): the random set is drawn from the usable
    corpus minus the tasks already drawn into the three tiers.
    """
    from wb_orchestrator import tiers
    r = tiers.draw(CORPUS_DIRS, seed=1, per_tier=3, out=tmp_path)

    drawn = [set(r.sets[n]) for n in tiers.SET_NAMES]
    for i, a in enumerate(drawn):
        for b in drawn[i + 1:]:
            assert not (a & b), f"the four sets share {a & b}"
    assert len(set().union(*drawn)) == 12   # four disjoint sets of three

    # thirteen usable minus twelve tier tasks leaves one: too few for a set of four
    with pytest.raises(ValueError) as e:
        tiers.draw(CORPUS_DIRS, seed=1, per_tier=4, out=tmp_path / "refused")
    assert "random" in str(e.value)
    assert not (tmp_path / "refused").exists()
