"""Offline voice admission, authoritative billing and delegated-work regressions."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio.genesis_voice import VoiceSessions


@pytest.fixture
def voice(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-never-sent')
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'test', 'available': True}])
    ledger = BudgetLedger(tmp_path / 'budget.sqlite')
    records = {}
    g = SimpleNamespace(root=tmp_path, studio=SimpleNamespace(ledger=ledger),
                        autonomy=SimpleNamespace(read=lambda: {'paused': False}),
                        allowance_allows=lambda amount: (True, None), active={},
                        config=SimpleNamespace(route_for=lambda *a, **kw: {'available': True}))
    def read(kind, identity):
        if (kind, identity) not in records:
            raise FileNotFoundError(identity)
        return records[kind, identity]
    g.read = read
    def chat(payload):
        result = {**payload, 'id': payload['id'], 'thread': payload['thread'],
                  'status': 'running', 'events': [], 'answer': ''}
        records['turns', result['id']] = result
        return result
    g.chat = Mock(side_effect=chat)
    provider = Mock()
    provider.create.return_value = {'session': {'id': 'live_test'}, 'transport': {'type': 'webrtc', 'sdp': 'answer'}}
    manager = VoiceSessions(g, provider=provider, background=False)
    manager._billing_verified = lambda: True
    return manager, g, provider, ledger, records


def start(voice, **payload):
    return voice[0].start({'sdp': 'offer', **payload}, 'human:lucas')


def event(voice, kind, **data):
    voice[0]._event('live_test', {'type': kind, **data})


def test_reserves_and_claims_before_create_with_server_owned_configuration(voice):
    manager, g, provider, ledger, _ = voice
    def create(payload, actor):
        assert actor == 'human:lucas'
        hold, = ledger.reservations()
        assert hold.dispatched_at is not None
        assert hold.maximum_usd > 0
        assert payload['session']['model'] == 'gpt-live-1'
        assert payload['session']['delegation'] == {'type': 'client'}
        server_events = {e['type'] for e in payload['session']['client']['data_channel']['allowed_server_events']}
        assert {'session.input_audio.muted', 'session.input_audio.unmuted'} <= server_events
        assert 'api_key' not in payload
        return {'session': {'id': 'live_test'}, 'transport': {'type': 'webrtc', 'sdp': 'answer'}}
    provider.create.side_effect = create
    result = start(voice, model='attacker', maximum_usd='0')
    assert result['transport']['sdp'] == 'answer'
    assert result['maximum_usd'] != '0'
    provider.attach.assert_called_once_with('live_test', 'human:lucas')


@pytest.mark.parametrize('reason', ['paused', 'allowance'])
def test_refusal_happens_before_paid_creation(voice, reason):
    manager, g, provider, ledger, _ = voice
    if reason == 'paused':
        g.autonomy.read = lambda: {'paused': True}
    else:
        g.allowance_allows = lambda amount: (False, 'allowance exhausted')
    with pytest.raises(ValueError, match=reason):
        start(voice)
    provider.create.assert_not_called()
    assert ledger.reservations() == []


def test_session_and_existing_conversation_ownership_cannot_be_spoofed(voice):
    manager, _, _, _, records = voice
    records['threads', 'foreign'] = {'id': 'foreign', 'owner': 'human:carlos'}
    with pytest.raises(PermissionError):
        start(voice, thread='foreign')
    result = start(voice)
    for method, args in [(manager.close, ()), (manager.status, ()), (manager.context, ({},))]:
        with pytest.raises(PermissionError):
            method(result['id'], *args, 'human:carlos')


def test_duplicate_delegation_runs_once_with_transcript_parent_and_workspace(voice):
    manager, g, _, _, records = voice
    records['threads', 'conversation'] = {'id': 'conversation', 'owner': 'human:lucas'}
    records['turns', 'prior'] = {'id': 'prior', 'thread': 'conversation', 'by': 'human:lucas'}
    start(voice, thread='conversation', parent='prior', workspace={'route': '#budget'})
    event(voice, 'session.input_transcript.delta', delta='Show the budget', start_ms=0, end_ms=100)
    for _ in range(2):
        event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'}, offset_ms=100)
    g.chat.assert_called_once()
    payload = g.chat.call_args.args[0]
    assert 'Show the budget' in payload['message']
    assert payload['thread'] == 'conversation'
    assert payload['parent'] == 'prior'
    assert payload['by'] == 'human:lucas'
    assert payload['workspace']['route'] == '#budget'
    assert payload['input_mode'] == 'voice'
    assert manager.status('live_test', 'human:lucas')['turns'][0]['id'] == payload['id']


def test_no_transcript_is_not_an_action_and_output_speech_is_not_user_intent(voice):
    start(voice)
    event(voice, 'session.output_transcript.delta', delta='I could delete that.', start_ms=0, end_ms=100)
    event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'})
    voice[1].chat.assert_not_called()


def test_superseded_turn_is_stopped_and_late_result_not_spoken(voice):
    manager, g, provider, _, records = voice
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Open budget', start_ms=0, end_ms=100)
    event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'})
    first = g.chat.call_args.args[0]['id']
    stopper = Mock()
    g.active[first] = stopper
    event(voice, 'session.input_transcript.delta', delta='Actually open research', start_ms=110, end_ms=200)
    event(voice, 'session.delegation.created', delegation={'id': 'item_2', 'target': 'client'})
    stopper.kill.assert_called_once()
    records['turns', first].update(status='completed', answer='DELETED EVERYTHING')
    manager._tick('live_test')
    assert all('DELETED' not in str(c) for c in provider.attach.return_value.send.call_args_list)


def test_terminal_answer_is_not_misrepresented_as_verified_receipt(voice):
    manager, g, provider, _, records = voice
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Compare results', start_ms=0, end_ms=10)
    event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'})
    identity = g.chat.call_args.args[0]['id']
    records['turns', identity].update(status='completed', answer='A verified 99% win rate!')
    manager._tick('live_test')
    sent = str(provider.attach.return_value.send.call_args_list)
    assert '99%' not in sent
    assert 'review' in sent.lower()


def test_usage_snapshots_are_not_increments_and_only_final_provider_usage_settles(voice):
    manager, _, _, ledger, _ = voice
    start(voice)
    event(voice, 'session.usage.updated', usage={'seconds': 12})
    event(voice, 'session.usage.updated', usage={'seconds': 20})
    assert ledger.reservations()[0].actual_usd is None
    manager.context('live_test', {'usage': {'seconds': 0}}, 'human:lucas')
    manager.close('live_test', 'human:lucas')
    assert ledger.reservations()[0].actual_usd is None
    event(voice, 'session.closed', usage={'seconds': 60}, reason='close_requested')
    assert ledger.reservations()[0].actual_usd == Decimal('0.05')
    assert manager.status('live_test', 'human:lucas')['billing'] == 'final'


def test_lost_connection_and_failed_creation_keep_unknown_hold(voice):
    manager, _, provider, ledger, _ = voice
    provider.create.side_effect = TimeoutError('secret provider detail')
    with pytest.raises(ValueError, match='creation'):
        start(voice)
    hold, = ledger.reservations()
    assert hold.actual_usd is None
    assert ledger.status().held_usd == hold.maximum_usd


def test_pause_closes_running_voice_and_cancels_backend(voice):
    manager, g, provider, ledger, _ = voice
    start(voice)
    g.autonomy.read = lambda: {'paused': True}
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['status'] == 'closing'
    assert 'session.close' in str(provider.attach.return_value.send.call_args_list)
    assert ledger.reservations()[0].actual_usd is None


def test_failed_tool_result_never_becomes_a_successful_voice_receipt(voice):
    manager, g, provider, _, records = voice
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Save it', start_ms=0, end_ms=1)
    event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'})
    identity = g.chat.call_args.args[0]['id']
    records['turns', identity].update(status='completed', events=[{'type': 'tool_completed',
        'action': 'save_architecture', 'detail': '{"error":"Unsaved human edits"}'}])
    manager._tick('live_test')
    assert 'save has a recorded' not in str(provider.attach.return_value.send.call_args_list)


def test_two_delegation_ids_without_new_user_input_do_not_repeat_an_action(voice):
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Save it', start_ms=0, end_ms=1)
    for key in ('item_1', 'item_2'):
        event(voice, 'session.delegation.created', delegation={'id': key, 'target': 'client'})
    assert voice[1].chat.call_count == 1


def test_deadline_closes_and_retains_hold_when_final_usage_never_arrives(voice):
    manager, _, provider, ledger, _ = voice
    start(voice)
    manager.sessions['live_test']['deadline'] = 0
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['status'] == 'closing'
    manager.sessions['live_test']['close_deadline'] = 0
    manager._tick('live_test')
    provider.hangup.assert_called_once_with('live_test')
    assert manager.status('live_test', 'human:lucas')['billing'] == 'unknown'
    assert ledger.reservations()[0].actual_usd is None


@pytest.mark.parametrize('seconds', [None, -1, float('nan'), True])
def test_invalid_final_usage_keeps_the_hold(voice, seconds):
    start(voice)
    event(voice, 'session.closed', usage={'seconds': seconds})
    assert voice[3].reservations()[0].actual_usd is None


def test_new_context_reaches_the_running_backend_turn(voice):
    manager, g, _, _, records = voice
    start(voice, workspace={'route': '#budget'})
    event(voice, 'session.input_transcript.delta', delta='Review this page', start_ms=0, end_ms=1)
    event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'})
    identity = g.chat.call_args.args[0]['id']
    manager.context('live_test', {'workspace': {'route': '#runs'}}, 'human:lucas')
    assert records['turns', identity]['workspace'] == {'route': '#runs'}


def test_startup_restores_identity_and_same_thread_requests_without_claiming_old_prose(voice):
    _, g, provider, _, records = voice
    g.memory = SimpleNamespace(soul_block=lambda: 'Genesis studies AI Labs evidence.')
    records['threads', 'thread'] = {'id': 'thread', 'owner': 'human:lucas', 'turns': ['old']}
    records['turns', 'old'] = {'id': 'old', 'by': 'human:lucas', 'thread': 'thread', 'message': 'Build a router',
                             'answer': 'Unverified 99% claim', 'status': 'completed', 'events': []}
    start(voice, thread='thread', parent='old')
    body = provider.create.call_args.args[0]['session']
    assert 'Genesis studies AI Labs evidence.' in str(body)
    assert 'Build a router' in str(body['input'])
    assert 'Unverified 99%' not in str(body['input'])


def test_delegation_waits_for_late_matching_transcript_and_ignores_future_speech(voice):
    manager, g, _, _, _ = voice
    start(voice)
    manager.background = True
    event(voice, 'session.delegation.created', delegation={'id': 'item_1', 'target': 'client'}, offset_ms=100)
    g.chat.assert_not_called()
    event(voice, 'session.input_transcript.delta', delta='Open budget', start_ms=0, end_ms=100)
    event(voice, 'session.input_transcript.delta', delta='Future unrelated speech', start_ms=200, end_ms=300)
    manager.sessions['live_test']['delegations']['item_1']['ready_at'] = 0
    manager._tick('live_test')
    g.chat.assert_called_once()
    assert 'Open budget' in g.chat.call_args.args[0]['message']
    assert 'Future unrelated' not in g.chat.call_args.args[0]['message']


def test_restart_hangs_up_orphan_and_preserves_unknown_hold_without_replaying_work(voice):
    manager, g, provider, ledger, _ = voice
    start(voice)
    restarted = VoiceSessions(g, provider=provider, background=False)
    provider.hangup.assert_called_once_with('live_test')
    assert ledger.reservations()[0].actual_usd is None
    assert restarted.availability()['available'] is False
    assert 'reconcil' in restarted.availability()['reason'].lower()
    g.chat.assert_not_called()


def test_full_transcript_evidence_survives_bounded_context(voice):
    manager, _, _, _, _ = voice
    start(voice)
    for index in range(165):
        event(voice, 'session.input_transcript.delta', delta='fragment-' + str(index), start_ms=index, end_ms=index + 1)
    session = manager.sessions['live_test']
    assert len(session['transcripts']) == 160
    evidence = (manager.root / (session['record_id'] + '.jsonl')).read_text()
    assert 'fragment-0"' in evidence
    assert 'fragment-164"' in evidence


def test_real_transport_adapter_uses_live_endpoints_and_server_authentication(monkeypatch):
    from wb_studio.genesis_voice import LiveProvider
    import httpx
    import websockets.sync.client
    monkeypatch.setenv('OPENAI_API_KEY', 'server-only-key')
    connection = Mock()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(websockets.sync.client, 'connect', connect)
    provider = LiveProvider()
    assert provider.attach('live_id', 'human:lucas') is connection
    assert connect.call_args.args[0] == 'wss://api.openai.com/v1/live/sessions/live_id/attach'
    attach_headers = connect.call_args.kwargs['additional_headers']
    assert attach_headers['Authorization'] == 'Bearer server-only-key'
    assert attach_headers['OpenAI-Safety-Identifier']
    assert 'lucas' not in attach_headers['OpenAI-Safety-Identifier']
    client = Mock()
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=client)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(httpx, 'Client', factory)
    client.post.return_value.json.return_value = {'session': {'id': 'live_id'}}
    assert provider.create({'session': {'model': 'gpt-live-1'}}, 'human:lucas') == {'session': {'id': 'live_id'}}
    assert client.post.call_args.args[0] == 'https://api.openai.com/v1/live/sessions'
    create_headers = client.post.call_args.kwargs['headers']
    assert create_headers == attach_headers


def test_successful_action_receipts_report_specific_committed_state():
    from wb_studio.genesis_voice import receipt_speech
    turn = {'events': [
        {'type': 'tool_completed', 'action': 'save_architecture',
         'detail': '{"id":"router","revision":3,"status":"draft"}'},
        {'type': 'tool_completed', 'action': 'show', 'detail': '{"route":"#studio/router"}'},
        {'type': 'tool_completed', 'action': 'edit_architecture', 'detail': '{"saved":false,"steps":2}'}]}
    spoken = ' '.join(receipt_speech(turn))
    assert 'Saved architecture router, revision 3' in spoken
    assert '#studio/router' in spoken
    assert '2 recorded steps' in spoken
    assert 'not saved yet' in spoken



def test_unverified_billing_refuses_voice_before_reserving_or_calling_provider(voice):
    manager, _, provider, ledger, _ = voice
    manager._billing_verified = lambda: False
    availability = manager.availability()
    assert availability['available'] is False
    assert 'billing verification' in availability['reason'].lower()
    with pytest.raises(ValueError, match='billing verification'):
        start(voice)
    provider.create.assert_not_called()
    assert ledger.reservations() == []
    assert ledger.run_reservations() == []



def test_billing_verification_uses_only_the_current_week_reconciliation(voice):
    import json
    from wb_orchestrator import reconcile
    manager, _, _, ledger, _ = voice
    del manager._billing_verified
    assert manager._billing_verified() is False
    folder = reconcile.default_dir(ledger)
    folder.mkdir()
    (folder / 'old.json').write_text(json.dumps({'week_start': '2000-01-03', 'historical_billing_verified': True}))
    assert manager._billing_verified() is False
    (folder / 'current.json').write_text(json.dumps({'week_start': ledger.status().week_start, 'historical_billing_verified': True}))
    assert manager._billing_verified() is True


def test_delayed_old_speech_does_not_supersede_newer_delegated_work(voice):
    manager, g, _, _, _ = voice
    start(voice)
    manager.background = True
    event(voice, 'session.delegation.created', delegation={'id': 'old', 'target': 'client'}, offset_ms=100)
    event(voice, 'session.input_transcript.delta', delta='The newer request', start_ms=150, end_ms=190)
    event(voice, 'session.delegation.created', delegation={'id': 'new', 'target': 'client'}, offset_ms=200)
    entries = manager.sessions['live_test']['delegations']
    for entry in entries.values():
        entry['ready_at'] = 0
    manager._tick('live_test')
    g.chat.assert_called_once()
    newest = g.chat.call_args.args[0]['id']
    stopper = Mock()
    g.active[newest] = stopper
    event(voice, 'session.input_transcript.delta', delta='Delayed old request', start_ms=50, end_ms=90)
    manager._tick('live_test')
    assert entries['old']['status'] == 'superseded'
    assert entries['new']['status'] == 'running'
    stopper.kill.assert_not_called()
    g.chat.assert_called_once()



def test_final_save_receipt_supersedes_provisional_state_and_old_saved_revision():
    from wb_studio.genesis_voice import receipt_speech
    turn = {'events': [
        {'type': 'tool_completed', 'action': 'edit_architecture', 'detail': '{"saved":false,"steps":2}'},
        {'type': 'tool_completed', 'action': 'save_architecture', 'detail': '{"id":"router","revision":1}'},
        {'type': 'tool_completed', 'action': 'save_architecture', 'detail': '{"id":"router","revision":2}'}]}
    spoken = ' '.join(receipt_speech(turn))
    assert 'revision 2' in spoken
    assert 'revision 1' not in spoken
    assert 'not saved yet' not in spoken


def test_full_structured_measures_become_substantive_spoken_facts_before_truncation():
    from wb_studio.genesis_voice import voice_facts, receipt_speech
    from wb_studio.measures import run_measures
    job = {'id': 'run-1', 'status': 'completed', 'settings': {'models': ['candidate']}, 'results': [
        {'task': 'a', 'model': 'candidate', 'passed': True, 'termination': 'completed'},
        {'task': 'b', 'model': 'candidate', 'passed': False, 'termination': 'completed'}]}
    result = {'run': 'run-1', 'status': 'completed', 'measures': run_measures(job, []), 'tags': ['[rec:run:run-1]']}
    facts = voice_facts('measures', result)
    spoken = ' '.join(facts)
    assert '1 of 2 evaluated attempts' in spoken
    assert 'unknown' in spoken.lower()
    assert all(fact.startswith('Recorded ') for fact in facts)
    turn = {'events': [{'type': 'tool_completed', 'action': 'measures', 'detail': '{"truncated":...', 'voice_facts': facts}]}
    assert receipt_speech(turn) == facts


@pytest.mark.parametrize('result', [None, [], {'error': 'provider failed'},
    {'measures': {'setups': {'x': {'name': 'x', 'pass': {'passed': True, 'attempts': 2}}}}},
    {'measures': {'setups': {'x': {'name': 'x', 'pass': {'passed': 9, 'attempts': 2}}}}}])
def test_voice_fact_extraction_rejects_errors_and_malformed_evidence(result):
    from wb_studio.genesis_voice import voice_facts
    assert voice_facts('measures', result) == []


def test_voice_compare_respects_the_per_setup_comparability_gate():
    from wb_studio.genesis_voice import voice_facts
    result = {'run': 'run-1', 'comparable': True, 'setups': [{'setup': 'candidate', 'paired': {
        'comparable': False, 'tasks': 2, 'wins': 2, 'losses': 0, 'ties': 0}}]}
    spoken = ' '.join(voice_facts('compare', result))
    assert 'cannot be paired' in spoken
    assert 'better on 2' not in spoken
    result['setups'][0]['paired']['comparable'] = True
    spoken = ' '.join(voice_facts('compare', result))
    assert '2 matched tasks' in spoken
    assert 'better on 2' in spoken

@pytest.fixture
def voice_clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr('wb_studio.genesis_voice.time.monotonic', lambda: now[0])
    return now


def test_idle_closes_without_browser_and_keeps_final_billing_authoritative(voice, voice_clock):
    manager, g, provider, ledger, _ = voice
    result = start(voice)
    assert result['idle_seconds'] == manager.availability()['idle_seconds'] == 60
    voice_clock[0] += 59
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['status'] == 'running'
    voice_clock[0] += 1
    manager._tick('live_test')
    status = manager.status('live_test', 'human:lucas')
    assert (status['status'], status['close_reason']) == ('closing', 'idle_timeout')
    assert 'session.close' in str(provider.attach.return_value.send.call_args_list)
    assert ledger.reservations()[0].actual_usd is None
    event(voice, 'session.closed', usage={'seconds': 61}, reason='close_requested')
    assert manager.status('live_test', 'human:lucas')['close_reason'] == 'idle_timeout'
    assert ledger.reservations()[0].actual_usd == Decimal('0.050834')
    import json
    session = manager.sessions['live_test']
    persisted = json.loads((manager.root / (session['record_id'] + '.json')).read_text())
    assert persisted['close_reason'] == 'idle_timeout'
    assert persisted['provider_close_reason'] == 'close_requested'
    provider.create.assert_called_once()
    g.chat.assert_not_called()


def test_only_new_user_transcript_resets_idle_not_output_telemetry_or_browser(voice, voice_clock):
    manager = voice[0]
    start(voice)
    voice_clock[0] += 50
    event(voice, 'session.input_transcript.delta', delta='Hello', event_id='speech')
    voice_clock[0] += 50
    event(voice, 'session.input_transcript.delta', delta='Hello', event_id='speech')
    event(voice, 'session.input_transcript.delta', delta='   ')
    event(voice, 'session.output_transcript.delta', delta='Still here.')
    event(voice, 'session.usage.updated', usage={'seconds': 100})
    manager.context('live_test', {'workspace': {'route': '#budget'}}, 'human:lucas')
    manager.status('live_test', 'human:lucas')
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['status'] == 'running'
    voice_clock[0] += 10
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['close_reason'] == 'idle_timeout'


def test_ordinary_work_defers_idle_with_terminal_grace_but_never_hard_deadline(voice, voice_clock):
    manager, g, _, _, records = voice
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Compare results')
    event(voice, 'session.delegation.created', delegation={'id': 'work', 'target': 'client'})
    turn = records['turns', g.chat.call_args.args[0]['id']]
    voice_clock[0] += 70
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['status'] == 'running'
    turn['status'] = 'completed'
    manager._tick('live_test')
    voice_clock[0] += 14
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['status'] == 'running'
    voice_clock[0] += 1
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['close_reason'] == 'idle_timeout'


def test_busy_work_cannot_extend_hard_lifetime(voice, voice_clock):
    manager, g, _, _, records = voice
    start(voice)
    event(voice, 'session.input_transcript.delta', delta='Compare results')
    event(voice, 'session.delegation.created', delegation={'id': 'work', 'target': 'client'})
    voice_clock[0] += 300
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['close_reason'] == 'max_duration'
    assert not records['turns', g.chat.call_args.args[0]['id']].get('stop_requested')


def test_mission_progress_cannot_keep_idle_voice_open_or_cancel_mission(voice, voice_clock):
    manager, g, _, _, records = voice
    result = start(voice)
    g.listing = lambda kind: [{'id': 'mission', 'mission': {'thread': result['thread'],
        'owner': 'human:lucas', 'status': 'working'}, 'work': {'turn': 'worker'}}]
    records['turns', 'worker'] = {'id': 'worker', 'status': 'running', 'events': [
        {'type': 'tool_started', 'action': 'read_run'}]}
    voice_clock[0] += 50
    manager._tick('live_test')
    event(voice, 'session.output_transcript.delta', delta='The mission is working.')
    voice_clock[0] += 10
    manager._tick('live_test')
    assert manager.status('live_test', 'human:lucas')['close_reason'] == 'idle_timeout'
    assert records['turns', 'worker']['status'] == 'running'
    assert 'stop_requested' not in records['turns', 'worker']


def test_idle_timeout_retains_unknown_hold_without_final_usage(voice, voice_clock):
    manager, _, provider, ledger, _ = voice
    start(voice)
    voice_clock[0] += 60
    manager._tick('live_test')
    voice_clock[0] += 15
    manager._tick('live_test')
    provider.hangup.assert_called_once_with('live_test')
    status = manager.status('live_test', 'human:lucas')
    assert (status['status'], status['billing'], status['close_reason']) == ('disconnected', 'unknown', 'idle_timeout')
    assert ledger.status().held_usd == ledger.reservations()[0].maximum_usd


@pytest.mark.parametrize('configured, expected', [('15', 15), ('120', 120), ('0', 60), ('601', 60), ('invalid', 60)])
def test_idle_configuration_is_bounded(voice, monkeypatch, configured, expected):
    monkeypatch.setenv('WB_GENESIS_VOICE_IDLE_SECONDS', configured)
    assert start(voice)['idle_seconds'] == expected


def test_idle_configuration_cannot_extend_short_hard_limit(voice, monkeypatch):
    monkeypatch.setenv('WB_GENESIS_VOICE_MAX_SECONDS', '30')
    assert start(voice)['idle_seconds'] == 30
