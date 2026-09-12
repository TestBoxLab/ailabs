"""Server restart closes stranded report stages without replaying paid work."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_results.evidence import write_json
from wb_studio import genesis_reports as reports
from wb_studio import report_recovery


@pytest.fixture
def lab(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.sqlite3')
    genesis = SimpleNamespace(studio=SimpleNamespace(directory=tmp_path, ledger=ledger),
                              lock=threading.RLock(), chat=Mock(), active={},
                              autonomy=SimpleNamespace(record=Mock()), read=Mock(side_effect=FileNotFoundError))
    folder = tmp_path / 'run1' / 'report-work' / 'work1'
    folder.mkdir(parents=True)
    state = {'id': 'work1', 'run': 'run1', 'stage': 'analysis', 'processed': [],
             'analysis_keys': ['analysis', 'analysis_2'], 'analysis_cursor': 1,
             'turns': {'analysis': {'id': 'a1', 'started': True},
                       'analysis_2': {'id': 'a2', 'started': True},
                       'author': {'id': 'author'}}}
    for entry in state['turns'].values():
        ledger.reserve_run('genesis-' + entry['id'], '1')
    reports._save(genesis, state)
    write_json(folder / 'attempts.json', {'0': {'observed': 'Retained analysis'}})
    write_json(folder / 'evidence.json', {'original': 'retained'})
    return genesis, state, folder


def test_missing_dispatched_child_becomes_retryable_and_unused_holds_close(lab):
    genesis, _, folder = lab
    genesis.read.side_effect = lambda kind, identity: ({'id': 'a1', 'status': 'completed'} if identity == 'a1'
                                                       else (_ for _ in ()).throw(FileNotFoundError()))
    recovered = report_recovery.recover(genesis)
    state = reports._state(genesis, 'run1')
    assert recovered == ['run1']
    assert state['stage'] == 'failed'
    assert state['turns']['analysis']['started'] is True
    assert state['turns']['analysis_2']['started'] is False
    assert 'restart' in state['reason'].lower()
    assert genesis.studio.ledger.status().held_usd == Decimal('0')
    assert reports._read(folder / 'attempts.json')['0']['observed'] == 'Retained analysis'
    assert reports._read(folder / 'evidence.json') == {'original': 'retained'}
    genesis.chat.assert_not_called()


def test_completed_child_without_callback_fails_and_retains_unknown_charge(lab):
    genesis, _, _ = lab
    genesis.read.side_effect = lambda kind, identity: {'id': identity, 'status': 'completed'}
    ledger = genesis.studio.ledger
    ledger.reserve('unknown', '.4', scope_id='genesis-a2')
    ledger.claim('unknown')
    ledger.settle('unknown', None, outcome='error')
    assert report_recovery.recover(genesis) == ['run1']
    assert reports._state(genesis, 'run1')['stage'] == 'failed'
    assert ledger.status().held_usd == Decimal('.4')
    assert ledger.scope_committed('genesis-a2') == Decimal('.4')
    assert all(ledger.run_reservation('genesis-' + key).closed_at for key in ('a1', 'a2', 'author'))
    genesis.chat.assert_not_called()


def test_published_and_already_failed_reports_are_not_recovered_twice(lab):
    genesis, state, _ = lab
    write_json(genesis.studio.directory / 'run1' / 'report-publication.json', {'summary': 'Earlier reviewed report'})
    report_recovery.recover(genesis)
    assert report_recovery.recover(genesis) == []
    assert reports.published(genesis.studio, 'run1') == {'summary': 'Earlier reviewed report'}
    state['stage'] = 'published'
    reports._save(genesis, state)
    assert report_recovery.recover(genesis) == []
    genesis.chat.assert_not_called()


def test_recovery_refuses_to_touch_a_live_worker(lab):
    genesis, _, _ = lab
    genesis.active['a2'] = object()
    with pytest.raises(ValueError, match='startup'):
        report_recovery.recover(genesis)
    assert reports._state(genesis, 'run1')['stage'] == 'analysis'
    assert genesis.studio.ledger.status().held_usd == Decimal('3')
