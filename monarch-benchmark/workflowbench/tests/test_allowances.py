"""Named weekly allowances inside the one lab week.

These replace the Genesis-only envelope of feature 022 lane B. The lab week stays
US$300; an allowance is a smaller gate for one kind of work, checked before a
reservation, never a second pot of money.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from wb_studio import allowances


def studio_for(tmp_path, lines=()):
    directory = tmp_path / "studio"
    directory.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(directory=directory, _lines=list(lines))


def line(who, maximum, actual=None, state="open", what="Genesis conversation"):
    return {"who": who, "what": what, "maximum_usd": maximum, "actual_usd": actual, "state": state}


def test_an_allowance_nobody_set_never_blocks(tmp_path):
    studio = studio_for(tmp_path)
    assert allowances.state(studio, "rounds", lines=[])["limit_usd"] is None
    assert allowances.allows(studio, "rounds", "250.00", lines=[]) == (True, None)


def test_genesis_starts_capped_because_it_is_the_one_that_spends_on_its_own(tmp_path):
    studio = studio_for(tmp_path)
    assert allowances.state(studio, "genesis", lines=[])["limit_usd"] == "25.00"
    ok, reason = allowances.allows(studio, "genesis", "40.00", lines=[])
    assert ok is False and "$25.00" in reason


def test_the_genesis_envelope_migrates_so_a_persons_number_survives(tmp_path):
    studio = studio_for(tmp_path)
    (studio.directory / "genesis").mkdir(parents=True, exist_ok=True)
    (studio.directory / "genesis" / "people.json").write_text(
        json.dumps({"people": [], "envelope_usd": "25.00", "brief_hour": 8}), encoding="utf8")
    assert allowances.limits(studio) == {"genesis": "25.00"}
    # The migration is written once, so a later envelope edit cannot silently move it back.
    assert json.loads((studio.directory / "allowances.json").read_text(encoding="utf8")) == {"genesis": "25.00"}


def test_no_envelope_to_migrate_still_leaves_genesis_at_its_default(tmp_path):
    assert allowances.limits(studio_for(tmp_path)) == {"genesis": "25.00"}


def test_held_and_settled_count_against_the_allowance(tmp_path):
    studio = studio_for(tmp_path)
    allowances.set_limit(studio, "genesis", "25.00")
    lines = [line("Genesis", "2.00"), line("Genesis", "1.00", actual="0.35", state="settled"),
             line("Studio", "9.00"), line("Genesis", "5.00", state="closed")]
    state = allowances.state(studio, "genesis", lines=lines)
    # open holds its ceiling, settled counts what it cost, closed-and-unsettled counts nothing.
    assert (state["held_usd"], state["settled_usd"], state["left_usd"]) == ("2.00", "0.35", "22.65")


def test_a_spend_over_what_is_left_is_refused_with_the_numbers(tmp_path, monkeypatch):
    studio = studio_for(tmp_path)
    allowances.set_limit(studio, "genesis", "5.00")
    monkeypatch.setattr(allowances, "state", lambda s, k, lines=None: {
        "kind": k, "label": "Genesis research", "limit_usd": "5.00",
        "held_usd": "4.00", "settled_usd": "0.50", "left_usd": "0.50"})
    ok, reason = allowances.allows(studio, "genesis", "2.00")
    assert ok is False
    assert "$2.00" in reason and "$0.50 left of $5.00" in reason


@pytest.mark.parametrize("value,expected", [("0", "0.00"), ("25", "25.00"), ("300", "300.00")])
def test_an_allowance_is_stored_to_the_cent(tmp_path, value, expected):
    studio = studio_for(tmp_path)
    assert allowances.set_limit(studio, "genesis", value)["genesis"] == expected


@pytest.mark.parametrize("value", ["-1", "301", "twenty"])
def test_an_allowance_stays_inside_the_lab_week(tmp_path, value):
    with pytest.raises(ValueError):
        allowances.set_limit(studio_for(tmp_path), "genesis", value)


def test_an_empty_value_clears_a_limit_that_has_no_default(tmp_path):
    studio = studio_for(tmp_path)
    allowances.set_limit(studio, "analysis", "10.00")
    allowances.set_limit(studio, "analysis", "")
    assert allowances.state(studio, "analysis", lines=[])["limit_usd"] is None
    assert allowances.allows(studio, "analysis", "100.00", lines=[]) == (True, None)


def test_clearing_genesis_restores_its_default_and_never_uncaps_it(tmp_path):
    studio = studio_for(tmp_path)
    allowances.set_limit(studio, "genesis", "80.00")
    assert allowances.state(studio, "genesis", lines=[])["limit_usd"] == "80.00"
    allowances.set_limit(studio, "genesis", "")
    assert allowances.state(studio, "genesis", lines=[])["limit_usd"] == "25.00"


def test_an_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError):
        allowances.set_limit(studio_for(tmp_path), "whatever", "5.00")


@pytest.mark.parametrize("row,kind", [
    ({"who": "Genesis", "what": "Genesis conversation"}, "genesis"),
    ({"who": "Studio", "what": "post-run-analysis"}, "analysis"),
    ({"who": "Carlos", "what": "Tier rounds, ten tasks"}, "rounds"),
    ({"who": "Studio user", "what": "smoke-frontier-001"}, "rounds"),
])
def test_every_ledger_line_lands_in_one_allowance(row, kind):
    assert allowances.kind_of(row) == kind


def test_a_ledger_that_cannot_be_read_never_blocks_work(tmp_path, monkeypatch):
    """The ledger's own $300 limit is the gate that must hold; an allowance that
    cannot be computed must not become an outage."""
    studio = studio_for(tmp_path)
    allowances.set_limit(studio, "genesis", "5.00")
    monkeypatch.setattr(allowances, "state", lambda *a, **k: (_ for _ in ()).throw(OSError("no ledger")))
    assert allowances.allows(studio, "genesis", "99.00") == (True, None)
