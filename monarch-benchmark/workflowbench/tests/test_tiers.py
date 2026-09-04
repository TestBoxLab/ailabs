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
        "alpha.a_two", "alpha.a_three", "alpha.a_four", "alpha.a_five",
        "beta.b_six", "beta.b_seven", "beta.b_eight_meta",
        "gamma.g_nine", "gamma.g_eleven", "gamma.g_thirteen",
    }
    assert by_id["gamma.g_nine"].domain == "gamma"
    assert by_id["gamma.g_nine"].score == 9
    assert by_id["gamma.g_nine"].contract_sha256 == load_task_file(
        FIXTURE / "imported-gamma" / "gamma.g_nine.json")["contract_sha256"]

    assert set(pool.excluded) == {"beta.b_no_rule", "gamma.g_bad_hash"}
    assert pool.excluded["beta.b_no_rule"] == (
        "no approval rule (unmapped assertion types: "
        "['mini_also_unmappable', 'mini_unmappable'])")
    assert pool.excluded["gamma.g_bad_hash"] == "contract hash does not match content"

    # the excluded two are not scored and not in the pool
    assert "beta.b_no_rule" not in by_id and "gamma.g_bad_hash" not in by_id
    # counts per folder are recorded for the manifest
    assert pool.counts == {"alpha": (4, 4), "beta": (4, 3), "gamma": (4, 3)}
