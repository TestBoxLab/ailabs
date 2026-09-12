from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest

from tests.test_genesis_loop import genesis, turn_record, FakeAdapter
from tests.test_genesis_voice import voice, start
from wb_studio import genesis_harness as harness, genesis_people as people
from wb_studio.genesis import Genesis
from wb_studio.genesis_voice import receipt_speech
from wb_studio.genesis_show import direct_request


def test_remember_survives_restart_and_enters_new_conversation(genesis):
    genesis.tool('person_remember', {'person': 'lucas', 'text': 'Prefers concise answers.'})
    saved = genesis.tool('person_remember', {'person': 'lucas', 'text': 'Uses the budget page daily.'})
    assert saved['text'] == 'Prefers concise answers.\nUses the budget page daily.\n'
    again = genesis.tool('person_remember', {'person': 'lucas', 'text': 'Uses the budget page daily.'})
    assert again == saved
    restarted = Genesis(genesis.studio)
    prompt = harness.prompt_text(restarted, {'id': 'fresh', 'message': 'Hello', 'by': 'human:lucas'})
    assert 'Prefers concise answers.' in prompt
    assert 'Uses the budget page daily.' in prompt
    assert 'Uses the budget page daily.' not in harness.prompt_text(
        restarted, {'id': 'other', 'message': 'Hello', 'by': 'human:ana'})


def test_memory_correction_and_refusal_preserve_other_entries(genesis):
    genesis.tool('person_remember', {'person': 'lucas', 'text': 'Prefers dark mode.'})
    genesis.tool('person_remember', {'person': 'lucas', 'text': 'Uses budget daily.'})
    saved = genesis.tool('person_remember', {'person': 'lucas', 'old': 'dark mode', 'text': 'Prefers light mode.'})
    assert saved['text'] == 'Prefers light mode.\nUses budget daily.\n'
    rejected = genesis.tool('person_remember', {'person': 'lucas', 'old': 'missing', 'text': 'Replacement.'})
    assert 'error' in rejected
    assert people.read(genesis, 'lucas') == saved
    for i in range(2):
        genesis.tool('person_remember', {'person': 'lucas', 'text': str(i) + 'x' * 350})
    before = people.read(genesis, 'lucas')
    full = genesis.tool('person_remember', {'person': 'lucas', 'text': 'z' * 350})
    assert 'at most' in full['error']
    assert people.read(genesis, 'lucas') == before
    assert receipt_speech({'events': [{'type': 'tool_completed', 'action': 'person_remember',
                                      'detail': json.dumps(full)}]}) == []


def test_voice_loads_own_saved_profile_and_confirms_real_memory_receipt(voice):
    _, g, provider, _, _ = voice
    g.autonomy.record = Mock()
    people.remember(g, 'lucas', 'Prefers concise answers.')
    people.remember(g, 'ana', 'Prefers lengthy answers.')
    start(voice)
    context = str(provider.create.call_args.args[0]['session']['input'])
    assert 'Prefers concise answers.' in context
    assert 'Prefers lengthy answers.' not in context
    assert receipt_speech({'events': [{'type': 'tool_completed', 'action': 'person_remember',
        'detail': json.dumps(people.read(g, 'lucas'))}]}) == [
            'Your saved profile has been updated for future conversations.']


@pytest.mark.parametrize('mode', ['text', 'voice'])
def test_direct_navigation_emits_receipt_without_model_request(genesis, mode):
    turn = turn_record(genesis)
    turn.update(message='Open the budget page', input_mode=mode)
    if mode == 'voice':
        turn.update(message='Voice transcript reference: user: Open the budget page', voice_request='Open the budget page')
    harness.start_turn(genesis, turn)
    saved = genesis.read('turns', turn['id'])
    assert saved['status'] == 'completed'
    completed = [e for e in saved['events'] if e['type'] == 'tool_completed']
    assert len(completed) == 1
    assert json.loads(completed[0]['detail'])['route'] == '#budget'
    assert FakeAdapter.made == []
    genesis.studio.ledger.claim.assert_not_called()
    genesis.studio.ledger.finish_run.assert_called_once_with('genesis-t1')


@pytest.mark.parametrize('utterance', [
    'Do not open budget', 'Open budget and delete a run',
    'Open the budget if spending is high', 'Explain the budget',
    'Open my last report', 'Someone said open budget',
])
def test_compound_conditional_or_ambiguous_requests_do_not_fast_navigate(utterance):
    assert direct_request(utterance) is None


@pytest.mark.parametrize('reason', ['page_detached', 'max_duration'])
def test_media_detach_keeps_accepted_work_running_through_final_usage(voice, reason):
    from tests.test_genesis_voice_progress import begin
    from tests.test_genesis_voice import event
    turn = begin(voice)
    stopper = Mock()
    voice[1].active[turn['id']] = stopper
    voice[0].close('live_test', 'human:lucas', reason=reason)
    event(voice, 'session.closed', usage={'seconds': 2})
    stopper.kill.assert_not_called()
    assert not turn.get('stop_requested')
    assert turn['status'] == 'running'
    assert voice[0].status('live_test', 'human:lucas')['billing'] == 'final'


def test_media_transport_loss_preserves_task_but_retains_unknown_billing(voice):
    from tests.test_genesis_voice_progress import begin
    turn = begin(voice)
    stopper = Mock()
    voice[1].active[turn['id']] = stopper
    voice[0]._unknown(voice[0].sessions['live_test'], 'Transport lost')
    stopper.kill.assert_not_called()
    assert not turn.get('stop_requested')
    assert voice[0].status('live_test', 'human:lucas')['billing'] == 'unknown'


def test_direct_web_read_pages_evidence_without_starting_another_turn(monkeypatch):
    from wb_studio import genesis_web, genesis_plugins
    from wb_studio.genesis_schemas import tool_defs
    from types import SimpleNamespace
    from unittest.mock import Mock
    g = SimpleNamespace(chat=Mock(side_effect=AssertionError('no extraction turn')))
    monkeypatch.setattr(genesis_web, 'fetch_source', lambda url: {
        'title': 'Example', 'text': 'A source with useful evidence', 'kind': 'page', 'note': 'Complete'})
    found, first = genesis_plugins.dispatch(g, 'read_web', {'url': 'https://example.com', 'limit': 8})
    _, second = genesis_plugins.dispatch(g, 'read_web', {'url': first['url'], 'offset': first['next_offset']})
    assert found and first['text'] + second['text'] == 'A source with useful evidence'
    assert first['next_offset'] == 8 and second['next_offset'] is None
    assert first['url'] == 'https://example.com' and first['retrieved_at']
    assert tool_defs(['read_web'])[0]['parameters']['required'] == ['url']
    monkeypatch.setattr(genesis_web, 'fetch_source', lambda url: {'text': '', 'note': 'Unavailable'})
    assert genesis_web.read_web(g, {'url': first['url']}) == {'error': 'Unavailable', 'url': first['url']}


def test_source_redirect_refuses_private_destination_before_following(monkeypatch):
    from urllib.request import Request
    from wb_studio import genesis_ingest
    monkeypatch.setattr(genesis_ingest, '_resolve', lambda host: ['127.0.0.1'])
    with pytest.raises(ValueError, match='public'):
        genesis_ingest._PublicRedirect().redirect_request(
            Request('https://example.com'), None, 302, 'Found', {}, 'http://internal.example/secret')
    with pytest.raises(ValueError, match='credentials'):
        genesis_ingest.fetch_source('https://user:password@example.com/private')
