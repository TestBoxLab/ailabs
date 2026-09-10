"""Feature 022, lane B: a conversation is a thread a person owns; a card keeps its history."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    ledger = Mock(); ledger.status.return_value = SimpleNamespace(blocked=False, available_usd=Decimal('100'))
    studio = SimpleNamespace(directory=tmp_path, create=Mock(return_value={'id': 'run-1'}), jobs=Mock(return_value=[]), job=Mock(), events=Mock(return_value=[]), ledger=ledger)
    return Genesis(studio)


def test_a_first_message_opens_a_thread_and_later_messages_join_it(genesis, monkeypatch):
    route = {'id': 'm', 'available': True, 'name': 'Model'}
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [route])
    monkeypatch.setattr('wb_studio.genesis_harness.start_turn', lambda g, t: None)
    class P: adapter = 'openai'
    monkeypatch.setattr('wb_arms.providers.get', lambda i: P())
    monkeypatch.setattr('wb_studio.gateways.resolve_effort', lambda p, e: 'default')
    first = genesis.chat({'message': 'Why does Monarch fail on two-app tasks?', 'model': 'm'})
    assert first['thread'] and first['by'] == 'human:studio'
    thread = genesis.thread(first['thread'])
    assert thread['title'] == 'Why does Monarch fail on two-app tasks?' and [t['id'] for t in thread['turns']] == [first['id']]
    second = genesis.chat({'message': 'And on one-app tasks?', 'model': 'm', 'thread': first['thread']})
    assert second['thread'] == first['thread'] and len(genesis.thread(first['thread'])['turns']) == 2
    listed = genesis.threads()
    assert listed[0]['id'] == first['thread'] and listed[0]['turn_count'] == 2
    # a watcher turn is not a conversation
    work = genesis.chat({'message': 'Work this card', 'model': 'm', 'purpose': 'Genesis watcher'})
    assert work['thread'] is None


def test_card_history_lists_earlier_revisions(genesis):
    card = genesis.card({'title': 'A claim', 'body': 'x', 'stage': 'hypothesis'})
    genesis.card({**card, 'body': 'y', 'stage': 'review'})
    rows = genesis.card_history(card['id'])
    assert [r['revision'] for r in rows] == [1] and rows[0]['stage'] == 'hypothesis'
    assert genesis.card_history('nope') == []
