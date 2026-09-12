"""The day's allowance and the weekly envelope must count what Genesis actually spends.

Feature 024, FR-004 and FR-005. Two defects, both of which let the gate pass work it
should refuse:

- `today_usd` summed only Genesis's own turns, so a run Genesis launched — by far the
  most expensive thing it can do — never touched the daily allowance. N self-launched
  runs each passed the same test.
- A ledger line's allowance was decided by its display name (`who == 'Genesis'`), and
  `usage.who` maps a conversation turn's `by='person'` to 'Studio user' before it ever
  reaches the Genesis test. So a person-initiated Genesis turn counted against
  benchmark rounds instead of research, and the envelope it was meant to bound never
  saw it.

Attribution and accounting are different questions: "who asked for this" is a display
fact, "which allowance does it draw on" is a money fact. Deciding the second from the
first is the bug.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import allowances
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDIO_GENESIS_DAILY_USD', '6.00')
    monkeypatch.setenv('STUDIO_GENESIS_CARD_USD', '2.00')
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes',
                        lambda: [{'id': 'gemini-3.7-flash', 'available': True}])
    studio = SimpleNamespace(directory=tmp_path, create=Mock(return_value={'id': 'run-1'}),
                             jobs=Mock(return_value=[]), job=Mock(), events=Mock(return_value=[]),
                             ledger=Mock())
    g = Genesis(studio)
    g.autonomy.set({'cards': 'act', 'runs': 'smoke'}, by='human:lucas')
    return g


# --- FR-004: the day's allowance counts the runs Genesis launches ----------------------

def test_a_launched_run_counts_against_the_day(genesis):
    before = genesis.watcher.today_usd()
    genesis.autonomy.record('launch', card='c1', job='run-1', by='genesis:smoke', maximum_usd='2.00')
    assert genesis.watcher.today_usd() == before + Decimal('2.00')


def test_many_launched_runs_do_not_each_see_an_untouched_allowance(genesis):
    for i in range(3):
        genesis.autonomy.record('launch', card=f'c{i}', job=f'run-{i}', by='genesis:smoke', maximum_usd='2.00')
    assert genesis.watcher.today_usd() == Decimal('6.00')
    allowed, reason = genesis.autonomy.may_launch(
        {'attempts_per_competitor': 1, 'maximum_usd': '2.00'},
        genesis.watcher.today_usd(), Decimal('2'), Decimal('6'))
    assert allowed is False and 'allowance' in reason.lower()


def test_a_launch_a_person_made_still_counts(genesis):
    """Who pressed the button does not change what the day spent."""
    genesis.autonomy.record('launch', card='c1', job='run-1', by='human:lucas', maximum_usd='1.50')
    assert genesis.watcher.today_usd() == Decimal('1.50')


def test_a_launch_recorded_on_another_day_does_not_count(genesis):
    genesis.autonomy.record('launch', card='c1', job='run-1', by='genesis:smoke',
                            maximum_usd='2.00', at='2020-01-01T10:00:00+00:00')
    assert genesis.watcher.today_usd() == Decimal('0')


# --- FR-005: the envelope counts every Genesis line, however it is attributed ----------

def line(**changes):
    base = {'kind': 'request', 'id': 'r1', 'what': 'Genesis conversation', 'who': 'Studio user',
            'created_at': '2026-09-11T10:00:00+00:00', 'closed_at': None, 'maximum_usd': '2.00',
            'actual_usd': None, 'requests': 1, 'settled': 0, 'state': 'open', 'run': None}
    return {**base, **changes}


def test_a_person_initiated_genesis_turn_draws_on_the_research_allowance():
    assert allowances.kind_of(line(allowance='genesis')) == 'genesis'


def test_the_display_name_no_longer_decides_the_allowance():
    """'Studio user' is the right thing to show a reader and the wrong thing to budget by."""
    assert allowances.kind_of(line(who='Studio user', allowance='genesis')) == 'genesis'
    assert allowances.kind_of(line(who='Genesis', allowance='rounds')) == 'rounds'


def test_a_line_from_before_this_change_still_counts_by_its_name():
    """Lines already on disk carry no allowance field; they keep their old meaning."""
    assert allowances.kind_of(line(who='Genesis')) == 'genesis'
    assert allowances.kind_of(line(who='Lucas', what='tier-simple')) == 'rounds'


def test_an_open_genesis_hold_is_counted_at_its_ceiling():
    held, settled = allowances._spent([line(allowance='genesis', maximum_usd='2.00')], 'genesis')
    assert (held, settled) == (Decimal('2.00'), Decimal('0'))


# --- FR-005 verified end to end: the three kinds of Genesis spend all reach the gate ----
# This is the check T023 exists for. Until it passes, a standing research envelope
# (FR-035) must not be built on top of this accounting.

def test_every_kind_of_genesis_spend_reaches_the_research_allowance():
    """A chat turn a person started, a watcher turn Genesis started, and a run it
    launched. All three are research; none may be invisible to the allowance."""
    lines = [
        # a person typed in the chat box: shown as theirs, budgeted as research
        line(id='r1', who='Studio user', allowance='genesis', what='Genesis conversation', maximum_usd='2.00'),
        # the watcher worked a card on its own
        line(id='r2', who='Genesis', allowance='genesis', what='Genesis card', maximum_usd='2.00'),
        # a run Genesis launched, settled
        line(id='r3', kind='run', who='Genesis', allowance='genesis', what='Genesis experiment',
             maximum_usd='3.00', actual_usd='1.25', state='closed'),
        # a benchmark round a person launched is not research and must not be counted here
        line(id='r4', who='Lucas', allowance='rounds', what='tier-simple', maximum_usd='40.00'),
    ]
    held, settled = allowances._spent(lines, 'genesis')
    assert (held, settled) == (Decimal('4.00'), Decimal('1.25'))
    assert allowances._spent(lines, 'rounds') == (Decimal('40.00'), Decimal('0'))


def test_the_allowance_refuses_once_the_week_is_committed(tmp_path):
    studio = SimpleNamespace(directory=tmp_path)
    allowances.set_limit(studio, 'genesis', '5.00')
    lines = [line(allowance='genesis', maximum_usd='4.50')]
    ok, reason = allowances.allows(studio, 'genesis', '2.00', lines=lines)
    assert ok is False and '$0.50 left of $5.00' in reason
    ok, _ = allowances.allows(studio, 'genesis', '0.25', lines=lines)
    assert ok is True
