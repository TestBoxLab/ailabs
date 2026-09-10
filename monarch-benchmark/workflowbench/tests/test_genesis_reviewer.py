"""The Reviewer chamber, offline: the JSON contract, the two rounds, and the gate a launch
consults. Every model turn here is a fake `genesis.chat`; nothing is ever sent."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_reviewer as reviewer
from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'cheap', 'available': True}])
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    studio.genesis.chat = Mock(side_effect=[{'id': 'r1'}, {'id': 'r2'}, {'id': 'r3'}])
    return studio.genesis


def planned(genesis, title='Retry caps cut failures'):
    return genesis.card({'title': title, 'stage': 'approval', 'body': 'The claim and its evidence.',
                         'proposal': {'tasks': ['t1'], 'models': ['gemini-3.7-flash'], 'maximum_usd': '1.00'}})


def finished(card_id, turn_id, answer, status='completed'):
    return {'id': turn_id, 'card': card_id, 'purpose': 'Genesis review', 'status': status, 'answer': answer,
            'events': [{'type': 'failed', 'message': 'Genesis could not complete this turn.'}] if status == 'failed' else []}


def test_a_review_is_requested_with_the_protocol_and_comes_back_as_a_verdict(genesis):
    card = planned(genesis)
    out = reviewer.request_review(genesis, card['id'], 'plan')
    payload = genesis.chat.call_args.args[0]
    assert payload['purpose'] == 'Genesis review' and payload['model'] == 'cheap' and payload['maximum_usd'] == '0.50'
    assert '# The Reviewer' in payload['message'] and 'Retry caps cut failures' in payload['message']
    assert 'confound' in payload['message'] and len(payload['message']) <= 16000
    assert out['status'] == 'pending' and out['round'] == 1
    pending = genesis.read('cards', card['id'])['review']
    assert pending == {'status': 'pending', 'turn': 'r1', 'subject': 'plan', 'round': 1,
                       'digest': genesis.read('cards', card['id'])['proposal_digest'], 'at': pending['at']}

    reviewer.ON_TURN(genesis, finished(card['id'], 'r1', '```json\n{"verdict": "accept", "issues": [], "reason": "Bare is shown and the effect is declared."}\n```'))
    review = genesis.read('cards', card['id'])['review']
    assert review['status'] == 'done' and review['verdict'] == 'accept' and review['issues'] == []
    assert review['reason'].startswith('Bare is shown') and review['round'] == 1
    assert reviewer.review_gate(genesis.read('cards', card['id'])) == (True, None)
    logged = genesis.autonomy.tail(3)
    assert [e['kind'] for e in logged] == ['review', 'review-requested', 'card'] and logged[0]['verdict'] == 'accept'


def test_revise_allows_one_more_round_and_the_third_request_is_refused(genesis):
    card = planned(genesis)
    reviewer.request_review(genesis, card['id'], 'plan')
    reviewer.ON_TURN(genesis, finished(card['id'], 'r1', '{"verdict": "revise", "issues": [{"kind": "no_control", "text": "Bare is not shown."},'
                                                         ' {"kind": "made-up", "text": "Unknown kinds are not dropped."}], "reason": "Add the control."}'))
    review = genesis.read('cards', card['id'])['review']
    assert review['verdict'] == 'revise' and [i['kind'] for i in review['issues']] == ['no_control', 'outside_methodology']
    assert reviewer.review_gate(genesis.read('cards', card['id'])) == (False, 'The Reviewer answered revise: Add the control.')

    assert reviewer.request_review(genesis, card['id'], 'plan')['round'] == 2
    reviewer.ON_TURN(genesis, finished(card['id'], 'r2', '{"verdict": "reject", "issues": [], "reason": "It grades its own work."}'))
    assert genesis.read('cards', card['id'])['review']['verdict'] == 'reject'
    with pytest.raises(ValueError, match='twice already'):
        reviewer.request_review(genesis, card['id'], 'plan')
    assert genesis.chat.call_count == 2


def test_a_failed_turn_or_unusable_json_never_yields_a_verdict(genesis):
    card = planned(genesis)
    reviewer.request_review(genesis, card['id'], 'plan')
    reviewer.ON_TURN(genesis, finished(card['id'], 'r1', '', status='failed'))
    review = genesis.read('cards', card['id'])['review']
    assert review['status'] == 'failed' and 'verdict' not in review and review['reason'] == 'Genesis could not complete this turn.'
    assert reviewer.review_gate(genesis.read('cards', card['id'])) == (False, 'The Reviewer has not accepted this plan.')

    reviewer.request_review(genesis, card['id'], 'plan')
    reviewer.ON_TURN(genesis, finished(card['id'], 'r2', 'The plan looks fine to me.'))
    review = genesis.read('cards', card['id'])['review']
    assert review['status'] == 'failed' and 'verdict' not in review and 'did not answer with JSON' in review['reason']
    reviewer.ON_TURN(genesis, finished(card['id'], 'r2', '{"verdict": "maybe"}'))
    assert 'accept, revise or reject' in genesis.read('cards', card['id'])['review']['reason']


def test_the_gate_refuses_a_plan_that_changed_after_the_review(genesis):
    card = planned(genesis)
    reviewer.request_review(genesis, card['id'], 'plan')
    reviewer.ON_TURN(genesis, finished(card['id'], 'r1', '{"verdict": "accept", "issues": [], "reason": "It holds."}'))
    card = genesis.read('cards', card['id'])
    assert reviewer.review_gate(card)[0] is True
    changed = genesis.card({**card, 'proposal': {**card['proposal'], 'tasks': ['t1', 't2']}})
    assert changed['review']['verdict'] == 'accept'                       # the review is kept whole
    assert reviewer.review_gate(changed) == (False, 'The plan changed after the Reviewer accepted it; ask for a new review.')


def test_the_tools_read_back_and_refuse_what_they_cannot_do(genesis):
    card = planned(genesis)
    assert reviewer.TOOLS['read_review'](genesis, {'card': card['id']})['status'] == 'none'
    with pytest.raises(ValueError, match='subject is one of'):
        reviewer.TOOLS['request_review'](genesis, {'card': card['id'], 'subject': 'vibes'})
    with pytest.raises(ValueError, match='Name the card'):
        reviewer.TOOLS['request_review'](genesis, {})
    reviewer.TOOLS['request_review'](genesis, {'card': card['id'], 'subject': 'hypothesis'})
    reviewer.ON_TURN(genesis, finished(card['id'], 'r1', '{"verdict": "accept", "issues": [], "reason": "It holds."}'))
    read = reviewer.TOOLS['read_review'](genesis, {'card': card['id']})
    assert read['verdict'] == 'accept' and read['subject'] == 'hypothesis' and read['accepted_for_this_plan'] is True
    # the plugin seam reaches both tools through Genesis.tool, with refusals as plain sentences
    assert genesis.tool('read_review', {'card': card['id']})['verdict'] == 'accept'
    assert genesis.tool('request_review', {'card': card['id']})['round'] == 2
    assert genesis.tool('request_review', {'card': card['id']}) == {'error': 'The Reviewer has judged this card twice already; the second answer is the last one.'}
