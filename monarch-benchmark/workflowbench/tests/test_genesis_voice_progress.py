"""Live narration uses recorded state, never generated progress claims."""
import json

import pytest

from tests.test_genesis_voice import voice, start, event


def begin(voice):
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Investigate the failures', start_ms=0, end_ms=1)
    event(voice, 'session.delegation.created', delegation={'id': 'request', 'target': 'client'})
    return voice[4]['turns', voice[1].chat.call_args.args[0]['id']]


def commentary(voice):
    return [json.loads(c.args[0])['content'] for c in voice[2].attach.return_value.send.call_args_list
            if json.loads(c.args[0])['type'] == 'session.commentary.append']


def test_running_tool_is_spoken_before_completion_once_and_rate_limited(voice, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('wb_studio.genesis_voice.time.monotonic', lambda: now[0])
    turn = begin(voice)
    turn['events'] = [{'id': 1, 'type': 'tool_started', 'action': 'read_run', 'payload': 'I won 99%'}]
    voice[0]._tick('live_test')
    assert commentary(voice) == ['Genesis is reading the recorded run evidence.']
    assert turn['status'] == 'running'
    voice[0]._tick('live_test')
    turn['events'] += [{'id': 2, 'type': 'tool_completed', 'action': 'read_run'},
                       {'id': 3, 'type': 'tool_started', 'action': 'compare'}]
    now[0] = 109.9
    voice[0]._tick('live_test')
    assert len(commentary(voice)) == 1
    now[0] = 110.0
    voice[0]._tick('live_test')
    assert commentary(voice)[-1] == 'Genesis is comparing the recorded results.'
    now[0] = 150.0
    voice[0]._tick('live_test')
    assert len(commentary(voice)) == 2


@pytest.mark.parametrize('events', [
    [{'type': 'text_delta', 'text': 'I won 99%'}],
    [{'type': 'tool_started', 'action': 'I won 99%'}],
    [{'type': 'tool_started', 'action': 'compare'}, {'type': 'tool_completed', 'action': 'compare'}],
    [{'type': 'tool_started', 'action': 'compare'}, {'type': 'tool_failed', 'action': 'compare'}],
])
def test_arbitrary_or_finished_activity_is_not_spoken_as_in_progress(voice, events):
    turn = begin(voice)
    turn['events'] = events
    voice[0]._tick('live_test')
    assert commentary(voice) == []


def test_terminal_receipt_is_not_delayed_by_progress_throttle(voice):
    turn = begin(voice)
    turn['events'] = [{'id': 1, 'type': 'tool_started', 'action': 'save_architecture'}]
    voice[0]._tick('live_test')
    turn.update(status='completed', events=turn['events'] + [{'id': 2, 'type': 'tool_completed',
        'action': 'save_architecture', 'detail': '{"id":"candidate","revision":2}'}])
    voice[0]._tick('live_test')
    assert commentary(voice) == ['Genesis is saving the architecture draft.',
        'Saved architecture candidate, revision 2. This is a draft, not a deployment.']



def mission_card(voice, **metadata):
    session = voice[0].sessions['live_test']
    card = {'id': 'mission-a', 'revision': 1, 'mission': {
        'owner': session['by'], 'thread': session['thread'], 'status': 'working',
        'summary': 'Unverified 99% improvement', **metadata}, 'work': {'turn': 'worker'}}
    voice[4]['cards', card['id']] = card
    voice[1].listing = lambda kind: [value for (k, _), value in voice[4].items() if k == kind]
    voice[4]['turns', 'worker'] = {'id': 'worker', 'status': 'running', 'events': [
        {'id': 1, 'type': 'tool_started', 'action': 'compare'}]}
    return card


def test_mission_progress_survives_a_followup_and_never_cancels_worker(voice, monkeypatch):
    from unittest.mock import Mock
    now = [100.0]
    monkeypatch.setattr('wb_studio.genesis_voice.time.monotonic', lambda: now[0])
    first = begin(voice)
    first['status'] = 'completed'
    card = mission_card(voice)
    stopper = Mock()
    voice[1].active['worker'] = stopper
    voice[0]._tick('live_test')
    assert commentary(voice)[-1] == 'The research mission is working.'
    event(voice, 'session.input_transcript.delta', delta='What are you doing?', start_ms=2, end_ms=3)
    event(voice, 'session.delegation.created', delegation={'id': 'question', 'target': 'client'})
    now[0] = 110.0
    voice[0]._tick('live_test')
    assert commentary(voice)[-1] == 'Genesis is comparing the recorded results.'
    now[0] = 120.0
    voice[0]._tick('live_test')
    assert commentary(voice).count('The research mission is working.') == 1
    card['mission'].update(status='waiting', checkpoint_turn='worker')
    now[0] = 130.0
    voice[0]._tick('live_test')
    assert commentary(voice)[-1] == 'The research mission is waiting on its linked experiment.'
    stopper.kill.assert_not_called()
    assert 'stop_requested' not in voice[4]['turns', 'worker']
    assert '99%' not in str(commentary(voice))


@pytest.mark.parametrize('metadata', [{'owner': 'human:someone'}, {'thread': 'foreign'}])
def test_foreign_mission_progress_is_not_spoken(voice, metadata):
    begin(voice)
    mission_card(voice, **metadata)
    voice[0]._tick('live_test')
    assert commentary(voice) == []


def test_mission_checkpoint_and_completion_only_report_recorded_status(voice, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('wb_studio.genesis_voice.time.monotonic', lambda: now[0])
    begin(voice)
    card = mission_card(voice)
    voice[0]._tick('live_test')
    card['mission']['checkpoint_turn'] = 'worker'
    now[0] += 10
    voice[0]._tick('live_test')
    assert commentary(voice)[-1] == 'A mission checkpoint is recorded. The research mission is working.'
    card['mission']['status'] = 'completed'
    now[0] += 10
    voice[0]._tick('live_test')
    assert commentary(voice)[-1] == 'The mission is marked completed. Review its evidence for the findings; this status alone does not establish an improvement.'
    now[0] += 10
    voice[0]._tick('live_test')
    assert len(commentary(voice)) == 3


@pytest.mark.parametrize('status,phrase', [
    ('queued', 'The research mission is queued.'),
    ('blocked', 'The research mission is blocked. Review its checkpoint for the required next step.'),
    ('stopped', 'The mission is marked stopped. This does not establish that in-flight actions were undone.'),
])
def test_mission_refusal_and_stop_states_do_not_claim_active_work(voice, status, phrase):
    begin(voice)
    mission_card(voice, status=status)
    voice[0]._tick('live_test')
    assert commentary(voice) == [phrase]


def test_voice_close_does_not_cancel_independent_mission(voice):
    from unittest.mock import Mock
    begin(voice)
    mission_card(voice)
    stopper = Mock()
    voice[1].active['worker'] = stopper
    voice[0].close('live_test', 'human:lucas')
    voice[0]._tick('live_test')
    stopper.kill.assert_not_called()
    assert commentary(voice) == []
    assert 'stop_requested' not in voice[4]['turns', 'worker']


def test_mission_disk_polling_is_bounded(voice, monkeypatch):
    from unittest.mock import Mock
    now = [100.0]
    monkeypatch.setattr('wb_studio.genesis_voice.time.monotonic', lambda: now[0])
    begin(voice)
    mission_card(voice)
    voice[1].listing = Mock(wraps=voice[1].listing)
    voice[0]._tick('live_test')
    now[0] = 101.9
    voice[0]._tick('live_test')
    assert voice[1].listing.call_count == 1
    now[0] = 102.0
    voice[0]._tick('live_test')
    assert voice[1].listing.call_count == 2


def test_fast_tool_receipt_is_spoken_while_next_model_request_runs(voice):
    turn = begin(voice)
    turn['events'] = [
        {'id': 1, 'type': 'tool_started', 'action': 'save_architecture'},
        {'id': 2, 'type': 'tool_completed', 'action': 'save_architecture',
         'detail': '{"id":"candidate","revision":2}'},
        {'id': 3, 'type': 'model_started'},
    ]
    voice[0]._tick('live_test')
    voice[0]._tick('live_test')
    assert commentary(voice) == [
        'Saved architecture candidate, revision 2. This is a draft, not a deployment.']
    assert turn['status'] == 'running'


def test_model_wait_is_delayed_and_announced_once_without_generated_text(voice, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('wb_studio.genesis_voice.time.monotonic', lambda: now[0])
    turn = begin(voice)
    turn['events'] = [{'id': 1, 'type': 'model_started'},
                      {'id': 2, 'type': 'text_delta', 'text': 'I won 99%'}]
    voice[0]._tick('live_test')
    now[0] = 104.9
    voice[0]._tick('live_test')
    assert commentary(voice) == []
    now[0] = 105.0
    voice[0]._tick('live_test')
    now[0] = 140.0
    voice[0]._tick('live_test')
    assert commentary(voice) == ['The backend is still responding. Its task is running.']


def test_known_voice_turns_are_omitted_without_hiding_new_delegations(voice):
    turn = begin(voice)
    turn['answer'] = 'large answer ' * 10000
    manager = voice[0]
    initial = manager.status('live_test', 'human:lucas')
    assert initial['turns'][0]['answer'] == turn['answer']
    compact = manager.status('live_test', 'human:lucas', known=[turn['id']])
    assert compact['turns'] == []
    assert len(json.dumps(compact)) < 1000
    turn['status'] = 'completed'
    event(voice, 'session.input_transcript.delta', delta='Open the budget', start_ms=2, end_ms=3)
    event(voice, 'session.delegation.created', delegation={'id': 'next', 'target': 'client'})
    fresh = manager.status('live_test', 'human:lucas', known=[turn['id']])
    assert [row['id'] for row in fresh['turns']] == [voice[1].chat.call_args.args[0]['id']]
    assert fresh['turns'][0]['id'] != turn['id']


def test_saved_memory_is_spoken_from_profile_receipt_without_generated_answer(voice):
    from wb_studio.genesis_voice import voice_facts
    turn = begin(voice)
    profile = {'person': 'lucas', 'text': 'I prefer short English answers.\nUse dark mode.'}
    projected = voice_facts('person_read', profile)
    turn.update(status='completed', answer='Invented preference', events=[{
        'id': 1, 'type': 'tool_completed', 'action': 'person_read',
        'detail': json.dumps(profile), 'voice_facts': projected}])
    voice[0]._tick('live_test')
    assert commentary(voice) == ['Recorded profile entry: "I prefer short English answers.". Recorded profile entry: "Use dark mode.".']
    assert 'Invented preference' not in ' '.join(commentary(voice))


def test_empty_and_long_profile_receipts_do_not_invent_or_cut_memories():
    from wb_studio.genesis_voice import voice_facts
    assert voice_facts('person_read', {'person': 'lucas', 'text': ''}) == [
        'Recorded profile: no personal memories are saved yet.']
    assert voice_facts('person_read', {'person': 'lucas', 'text': 'x' * 500}) == []
    assert voice_facts('person_read', {'error': 'Unavailable'}) == []
