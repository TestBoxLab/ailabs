"""Pause must stop every paid activity, not only the watcher (feature 024, FR-003).

The dial was read in four places â€” `may_launch`, `work_now`, the initiative job and
the watcher â€” and never in `Genesis.chat`, which is the single funnel every paid turn
passes through. So a person could hit Pause because Genesis was doing something wrong,
go to bed, and the 03:00 consolidation, the 05:00 ranking and the channel sweeps would
each start a paid turn anyway: roughly three to six dollars a night, indefinitely,
against a lab that had spent US$276 of a US$300 week.
"""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio.genesis import Genesis
from wb_studio.scheduler import Scheduler


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes',
                        lambda: [{'id': 'gemini-3.7-flash', 'available': True}])
    ledger = Mock()
    ledger.reserve_run.side_effect = AssertionError('a paused Genesis reserved money')
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]),
                             job=Mock(), events=Mock(return_value=[]), ledger=ledger)
    g = Genesis(studio)
    # This fixture deliberately exercises its stub route, independently of the partner default.
    g.config.set({'models': {'chat': 'gemini-3.7-flash', 'reading': 'gemini-3.7-flash'}}, routes=[{'id': 'gemini-3.7-flash', 'available': True}])
    g.autonomy.set({'cards': 'act', 'runs': 'smoke'}, by='human:lucas')
    g.autonomy.set({'paused': True}, by='human:lucas')
    return g


def test_a_paused_genesis_refuses_an_unattended_turn(genesis):
    with pytest.raises(ValueError, match='paused'):
        genesis.chat({'message': 'Consolidate the day.', 'purpose': 'Genesis night'})


def test_a_paused_genesis_refuses_every_scheduled_purpose(genesis):
    for purpose in ('Genesis night', 'Genesis ranking', 'Genesis channels',
                    'Genesis extraction', 'Genesis initiative'):
        with pytest.raises(ValueError, match='paused'):
            genesis.chat({'message': 'work', 'purpose': purpose})


def test_a_person_at_the_keyboard_is_not_stopped_by_pause(genesis):
    """Pause stops unattended work. Someone typing in the chat box is attended, and
    can turn the dial back on in the same breath; refusing them would teach people to
    leave Pause off."""
    genesis.studio.ledger.reserve_run.side_effect = None
    turn = genesis.chat({'message': 'Why did you do that?', 'purpose': 'Genesis conversation'})
    assert turn['status'] == 'running'


def test_the_scheduler_runs_nothing_while_paused_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    studio = SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    studio.genesis.autonomy.set({'cards': 'act'}, by='human:lucas')
    studio.genesis.autonomy.set({'paused': True}, by='human:lucas')
    ran = []
    scheduler = Scheduler(studio, tmp_path / 'schedule.json')
    scheduler.daily('nightly', 0, lambda s: ran.append('nightly'))
    entries = scheduler.run_due(datetime.fromisoformat('2026-09-11T23:00:00'))
    assert ran == []
    assert [e['status'] for e in entries] == ['skipped']
    assert 'paused' in entries[0]['reason']
    kinds = [e['kind'] for e in studio.genesis.autonomy.tail()]
    assert 'job-skipped' in kinds


def test_the_scheduler_runs_again_once_pause_is_lifted(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    studio = SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    studio.genesis.autonomy.set({'cards': 'act', 'paused': True}, by='human:lucas')
    ran = []
    scheduler = Scheduler(studio, tmp_path / 'schedule.json')
    scheduler.daily('nightly', 0, lambda s: ran.append('nightly'))
    scheduler.run_due(datetime.fromisoformat('2026-09-11T23:00:00'))
    assert ran == []
    studio.genesis.autonomy.set({'paused': False}, by='human:lucas')
    scheduler.run_due(datetime.fromisoformat('2026-09-11T23:30:00'))
    assert ran == ['nightly']
