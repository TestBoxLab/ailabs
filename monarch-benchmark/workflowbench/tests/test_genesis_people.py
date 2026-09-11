"""People files and episodes, offline. No model is called."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_harness as harness
from wb_studio import genesis_people as people
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path):
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    return studio.genesis


def test_a_person_file_respects_the_budget_and_the_scan_and_is_written_through_the_tools(genesis):
    assert genesis.tool('person_read', {'person': 'human:lucas'}) == {'person': 'lucas', 'text': '', 'size': 0, 'budget': 1000}
    out = genesis.tool('person_write', {'person': 'human:Lucas', 'text': 'Lucas decides the design. Answers: outcome first, evidence in one line.'})
    assert out['person'] == 'lucas' and out['size'] == 72
    assert (genesis.root / 'people' / 'lucas.md').read_text(encoding='utf8').endswith('one line.\n')
    assert genesis.autonomy.tail(1)[0]['kind'] == 'person-file'
    assert people.listing(genesis) == [{'person': 'lucas', 'size': 72, 'budget': 1000}]

    assert 'invisible characters' in genesis.tool('person_write', {'person': 'lucas', 'text': 'a​b'})['error']
    full = genesis.tool('person_write', {'person': 'lucas', 'text': ('x' * 200 + '\n') * 6})
    assert 'at most 1,000 characters' in full['error']
    assert genesis.tool('person_read', {'person': 'lucas'})['size'] == 72   # nothing refused was written
    assert 'Name the person' in genesis.tool('person_read', {'person': 'not a name!'})['error']


def test_the_file_of_the_person_named_by_the_turn_enters_the_prompt(genesis, monkeypatch):
    monkeypatch.setattr(harness, 'freshness', lambda now=None: 'FRESHNESS')
    people.write(genesis, 'lucas', 'Lucas decides the design and QAs.')
    people.write(genesis, 'ana', 'Ana runs the graders.')
    prompt = harness.prompt_text(genesis, {'id': 'x', 'message': 'hello', 'by': 'human:lucas'})
    assert 'What you know about lucas' in prompt and 'Lucas decides the design and QAs.' in prompt
    assert 'Ana runs the graders' not in prompt
    assert prompt.index('What you know about lucas') < prompt.index('Previous exchange:')
    assert 'What you know about' not in harness.prompt_text(genesis, {'id': 'y', 'message': 'hello'})
    assert 'What you know about ana' in harness.prompt_text(genesis, {'id': 'z', 'message': 'hi', 'person': 'ana'})


def _conversation(genesis, thread_id='th-1'):
    turn = {'id': 't1', 'purpose': 'Genesis conversation', 'status': 'completed', 'by': 'human:lucas',
            'created_at': '2026-09-09T10:00:00+00:00', 'thread': thread_id, 'events': [],
            'message': 'What did we learn about retry caps?', 'answer': 'Retry caps cut gateway failures by a third.'}
    genesis.path('turns', turn['id']).write_text(json.dumps(turn), encoding='utf8')
    genesis.path('threads', thread_id).write_text(json.dumps(
        {'id': thread_id, 'owner': 'human:lucas', 'title': 'Retry caps', 'created_at': turn['created_at'],
         'updated_at': turn['created_at'], 'turns': [turn['id']], 'card': None}), encoding='utf8')
    return turn


def test_an_episode_lands_in_the_record_and_never_in_core(genesis):
    turn = _conversation(genesis)
    people.ON_TURN(genesis, turn)
    hits = genesis.memory.search('retry caps')
    assert [(h['kind'], h['id'], h['tag']) for h in hits] == [('episode', 'th-1', '[rec:episode:th-1]')]
    assert genesis.memory.search('lucas')[0]['id'] == 'th-1'
    assert not genesis.memory.lab.exists()                       # never into core
    people.ON_TURN(genesis, turn)
    assert len(genesis.memory.search('retry caps')) == 1         # the same thread stays one line

    other = {**turn, 'id': 't2', 'thread': None, 'message': 'And the grader rubric?', 'answer': 'It disagreed twice.'}
    people.ON_TURN(genesis, other)                               # until threads exist, one line per turn
    assert [h['id'] for h in genesis.memory.search('rubric')] == ['t2']
    people.ON_TURN(genesis, {**other, 'purpose': 'Genesis watcher', 'id': 't3', 'message': 'work'})
    people.ON_TURN(genesis, {**other, 'status': 'failed', 'id': 't4', 'message': 'work'})
    assert [h['id'] for h in genesis.memory.search('rubric')] == ['t2']   # only finished conversations
