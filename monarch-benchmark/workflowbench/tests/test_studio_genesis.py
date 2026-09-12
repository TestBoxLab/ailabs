"""Offline contracts for durable Genesis records and its model capability boundary."""
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio.genesis import Genesis


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_plugins.gate_launch', lambda g, c: (True, None))  # feature 022's Reviewer gate has its own tests
    studio = SimpleNamespace(
        directory=tmp_path,
        create=Mock(return_value={'id': 'run-accepted'}),
        jobs=Mock(return_value=[]),
        job=Mock(),
        events=Mock(return_value=[]),
        ledger=Mock(),
    )
    return Genesis(studio)


def proposal_card(genesis):
    return genesis.card({
        'id': 'research-1', 'title': '  Compare recovery  ', 'stage': 'approval',
        'body': 'Compare against the frozen baseline.',
        'evidence': [{'run': 'baseline', 'event': 'event-7'}],
        'parent': 'prior-hypothesis',
        'proposal': {'title': 'Recovery replication', 'maximum_usd': '3',
                     'configuration': {'model': 'frozen-model', 'task_set': 'development'}},
    })


def approval_payload(card):
    return {'revision': card['revision'], 'digest': card['proposal_digest']}


def test_card_revision_and_evidence_survive_new_genesis_instance(genesis):
    card = proposal_card(genesis)
    expected_digest = hashlib.sha256(json.dumps(card['proposal'], sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
    assert card['title'] == 'Compare recovery'
    assert card['revision'] == 1
    assert card['proposal_digest'] == expected_digest
    reopened = Genesis(genesis.studio)
    updated = reopened.card({**card, 'title': 'Recovery with retry cap',
                             'proposal': {**card['proposal'], 'maximum_usd': '4'}})
    persisted = Genesis(genesis.studio).read('cards', card['id'])
    assert persisted['revision'] == 2
    assert persisted['created_at'] == card['created_at']
    assert persisted['title'] == 'Recovery with retry cap'
    assert persisted['proposal_digest'] != expected_digest
    assert persisted['proposal_digest'] == updated['proposal_digest']
    assert persisted['evidence'] == [{'run': 'baseline', 'event': 'event-7'}]
    assert persisted['parent'] == 'prior-hypothesis'
    assert persisted['approval'] is None
    archived = json.loads((genesis.root / 'card-history' / card['id'] / '1.json').read_text(encoding='utf8'))
    assert archived == card
    genesis.studio.create.assert_not_called()


@pytest.mark.parametrize('revision', [None, 0, 2, '1'])
def test_stale_card_revision_does_not_overwrite_evidence(genesis, revision):
    card = proposal_card(genesis)
    path = genesis.path('cards', card['id'])
    before = path.read_bytes()
    with pytest.raises(ValueError, match='changed'):
        genesis.card({**card, 'revision': revision, 'body': 'overwrite'})
    assert path.read_bytes() == before
    genesis.studio.create.assert_not_called()


@pytest.mark.parametrize('field,value', [('revision', 0), ('revision', None),
                                         ('digest', 'wrong'), ('digest', None)])
def test_invalid_approval_revision_or_digest_never_dispatches(genesis, field, value):
    card = proposal_card(genesis)
    with pytest.raises(ValueError, match='proposal changed'):
        genesis.approve(card['id'], {**approval_payload(card), field: value})
    assert genesis.read('cards', card['id']) == card
    genesis.studio.create.assert_not_called()
    genesis.studio.ledger.reserve_run.assert_not_called()


def test_edit_invalidates_previously_reviewed_approval_snapshot(genesis):
    original = proposal_card(genesis)
    changed = genesis.card({**original, 'proposal': {**original['proposal'], 'maximum_usd': '5'}})
    with pytest.raises(ValueError, match='proposal changed'):
        genesis.approve(original['id'], approval_payload(original))
    assert genesis.read('cards', original['id'])['approval'] is None
    genesis.studio.create.assert_not_called()
    approved = genesis.approve(changed['id'], approval_payload(changed))
    assert approved['approval']['digest'] == changed['proposal_digest']
    assert approved['approval']['revision'] == 2
    assert genesis.studio.create.call_args.args[0]['maximum_usd'] == '5'


def test_approval_is_durable_idempotent_and_running_card_is_immutable(genesis):
    card = proposal_card(genesis)
    approved = genesis.approve(card['id'], approval_payload(card))
    reopened = Genesis(genesis.studio)
    repeated = reopened.approve(card['id'], approval_payload(card))
    assert repeated == approved
    assert approved['stage'] == 'running'
    assert approved['job'] == 'run-accepted'
    assert approved['approval']['digest'] == card['proposal_digest']
    assert approved['approval']['revision'] == 1
    genesis.studio.create.assert_called_once_with({**card['proposal'], 'request_id': 'genesis-research-1-1'})
    with pytest.raises(ValueError, match='cannot be edited'):
        reopened.card({**approved, 'title': 'Replace dispatched configuration'})
    assert reopened.read('cards', card['id']) == approved


def test_failed_studio_admission_does_not_record_approval(genesis):
    card = proposal_card(genesis)
    genesis.studio.create.side_effect = ValueError('Weekly envelope exhausted')
    with pytest.raises(ValueError, match='Weekly envelope exhausted'):
        genesis.approve(card['id'], approval_payload(card))
    assert Genesis(genesis.studio).read('cards', card['id']) == card
    genesis.studio.create.assert_called_once()


@pytest.mark.parametrize('action', ['approve', 'approve_experiment', 'launch', 'create',
                                   'create_run', 'run_experiment', 'analyze'])
def test_model_cannot_approve_or_launch(genesis, action):
    card = proposal_card(genesis)
    with pytest.raises(ValueError, match='require approval in the interface'):
        genesis.tool(action, {'id': card['id'], **approval_payload(card)})
    assert genesis.read('cards', card['id']) == card
    genesis.studio.create.assert_not_called()
    genesis.studio.ledger.reserve_run.assert_not_called()


@pytest.mark.parametrize('field', ['request_id', 'approved', 'approval', 'benchmark'])
def test_model_cannot_smuggle_approval_or_server_identity_in_proposal(genesis, field):
    with pytest.raises(ValueError, match='server-owned identities'):
        genesis.tool('save_research', {'id': 'injected', 'title': 'Injected approval',
                                     'proposal': {field: True}})
    assert genesis.listing('cards') == []
    genesis.studio.create.assert_not_called()


def test_model_can_save_reviewable_proposal_without_dispatch(genesis):
    saved = genesis.tool('save_research', {'id': 'model-proposal', 'title': 'Recovery idea',
                                         'stage': 'approval', 'proposal': {'maximum_usd': '2'}})
    assert saved['stage'] == 'approval'
    assert saved['revision'] == 1
    assert saved['approval'] is None
    assert Genesis(genesis.studio).read('cards', saved['id'])['proposal'] == {'maximum_usd': '2'}
    genesis.studio.create.assert_not_called()


def test_existing_analysis_is_reused_with_evidence_without_paid_work(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    jobs = [{'id': 'completed-run', 'title': 'Completed run', 'status': 'completed'},
            {'id': 'pending-run', 'title': 'Pending run', 'status': 'running'}]
    genesis.studio.jobs.return_value = jobs
    genesis.studio.job.side_effect = lambda identity: next(j for j in jobs if j['id'] == identity)
    genesis.studio.events.return_value = [{'id': 7, 'type': 'task_completed'}]
    folder = genesis.studio.directory / 'completed-run'
    folder.mkdir()
    analysis = {'status': 'completed', 'findings': [{'event': 7, 'claim': 'Observed recovery'}]}
    path = folder / 'analysis.json'
    path.write_text(json.dumps(analysis), encoding='utf8')
    before = path.read_bytes()
    state = genesis.tool('research_state', {})
    assert state['analyzed'] == [{'run': 'completed-run', 'title': 'Completed run', 'status': 'completed'}]
    first = genesis.tool('read_run', {'id': 'completed-run'})
    second = genesis.tool('read_run', {'id': 'completed-run'})
    assert first == second  # reading twice is the same read: nothing is recomputed and nothing is spent
    # The evidence this test is about, named rather than matched whole: read_run also carries the
    # authored report and its progress, which belong to the report cycle's own tests.
    assert {k: first[k] for k in ('job', 'events', 'analysis', 'genesis_analyses', 'next_after', 'remaining_events')} == {
        'job': jobs[0], 'events': [{'id': 7, 'type': 'task_completed'}], 'analysis': analysis,
        'genesis_analyses': [], 'next_after': None, 'remaining_events': 0}
    assert genesis.tool('read_run', {'id': 'pending-run'})['analysis'] is None
    assert path.read_bytes() == before
    genesis.studio.create.assert_not_called()
    genesis.studio.ledger.reserve_run.assert_not_called()



def test_record_analysis_deduplicates_same_evidence_and_preserves_original_findings(genesis):
    genesis.studio.job.return_value = {'id': 'run-1', 'results': [{'task': 'a', 'success': True}]}
    genesis.studio.events.return_value = [{'id': 7, 'type': 'task_completed'}]
    payload = {'run': 'run-1', 'summary': 'Recovery observed',
               'findings': [{'kind': 'fact', 'event_ids': [7], 'text': 'Task completed'}]}
    first = genesis.tool('record_analysis', payload)
    reopened = Genesis(genesis.studio)
    repeated = reopened.tool('record_analysis', {**payload, 'summary': 'Overwrite',
                                                'findings': [{'kind': 'fact', 'event_ids': [7], 'text': 'Replacement'}]})
    assert repeated == {'reused': True, **first}
    assert repeated['summary'] == 'Recovery observed'
    assert repeated['findings'] == payload['findings']
    assert len(list((genesis.root / 'analyses').glob('*.json'))) == 1
    assert reopened.tool('read_run', {'id': 'run-1'})['genesis_analyses'] == [first]
    genesis.studio.create.assert_not_called()
    genesis.studio.ledger.reserve_run.assert_not_called()


@pytest.mark.parametrize('findings', [[], [{'kind': 'fact', 'event_ids': []}],
                                      [{'kind': 'fact', 'event_ids': [999]}],
                                      [{'kind': 'causal_proof', 'event_ids': [7]}]])
def test_record_analysis_rejects_missing_invalid_or_unclassified_evidence(genesis, findings):
    genesis.studio.job.return_value = {'id': 'run-1'}
    genesis.studio.events.return_value = [{'id': 7, 'type': 'task_completed'}]
    with pytest.raises(ValueError, match='existing events and distinguish fact from hypothesis'):
        genesis.tool('record_analysis', {'run': 'run-1', 'findings': findings})
    assert list((genesis.root / 'analyses').glob('*.json')) == []
    genesis.studio.create.assert_not_called()


@pytest.mark.parametrize('changed', ['events', 'results'])
def test_changed_run_evidence_produces_separate_analysis_record(genesis, changed):
    job = {'id': 'run-1', 'results': [{'task': 'a', 'success': False}]}
    genesis.studio.job.return_value = job
    genesis.studio.events.return_value = [{'id': 7, 'type': 'task_completed'}]
    payload = {'run': 'run-1', 'findings': [{'kind': 'hypothesis', 'event_ids': [7], 'text': 'May need retry'}]}
    first = genesis.tool('record_analysis', payload)
    if changed == 'events':
        genesis.studio.events.return_value = [{'id': 7, 'type': 'task_completed'}, {'id': 8, 'type': 'retry'}]
    else:
        genesis.studio.job.return_value = {**job, 'results': [{'task': 'a', 'success': True}]}
    second = genesis.tool('record_analysis', payload)
    assert second['fingerprint'] != first['fingerprint']
    assert len(list((genesis.root / 'analyses').glob('*.json'))) == 2
    retained = genesis.tool('read_run', {'id': 'run-1'})['genesis_analyses']
    assert {r['fingerprint'] for r in retained} == {first['fingerprint'], second['fingerprint']}
    genesis.studio.create.assert_not_called()



@pytest.mark.parametrize('options,count,remaining,cursor', [
    ({}, 100, 105, 100),
    ({'limit': 999}, 205, 0, None),
    ({'limit': 0}, 1, 204, 1),
])
def test_read_run_paginates_with_default_and_bounded_limits(genesis, options, count, remaining, cursor):
    genesis.studio.job.return_value = {'id': 'run-1'}
    genesis.studio.events.return_value = [{'id': i, 'task': 'a'} for i in range(1, 206)]
    result = genesis.tool('read_run', {'id': 'run-1', **options})
    assert [e['id'] for e in result['events']] == list(range(1, count + 1))
    assert result['next_after'] == cursor
    assert result['remaining_events'] == remaining
    assert len(genesis.studio.events.return_value) == 205
    genesis.studio.create.assert_not_called()


def test_read_run_caps_large_pages_at_500_events(genesis):
    genesis.studio.job.return_value = {'id': 'run-1'}
    genesis.studio.events.return_value = [{'id': i, 'task': 'a'} for i in range(1, 506)]
    result = genesis.tool('read_run', {'id': 'run-1', 'limit': 900})
    assert [e['id'] for e in result['events']] == list(range(1, 501))
    assert result['next_after'] == 500
    assert result['remaining_events'] == 5
    final = genesis.tool('read_run', {'id': 'run-1', 'after': result['next_after']})
    assert [e['id'] for e in final['events']] == [501, 502, 503, 504, 505]
    assert final['next_after'] is None
    assert final['remaining_events'] == 0


def test_read_run_filters_task_and_exclusive_cursor_before_paginating(genesis):
    genesis.studio.job.return_value = {'id': 'run-1'}
    genesis.studio.events.return_value = [
        {'id': 1, 'task': 'a'}, {'id': 2, 'task': 'b'}, {'id': 3, 'task': 'a'},
        {'id': 4, 'task': 'b'}, {'id': 5, 'task': 'a'}, {'id': 6, 'task': 'a'},
    ]
    result = genesis.tool('read_run', {'id': 'run-1', 'task': 'a', 'after': 3, 'limit': 1})
    assert result['events'] == [{'id': 5, 'task': 'a'}]
    assert result['next_after'] == 5
    assert result['remaining_events'] == 1
    final = genesis.tool('read_run', {'id': 'run-1', 'task': 'a', 'after': 5, 'limit': 1})
    assert final['events'] == [{'id': 6, 'task': 'a'}]
    assert final['next_after'] is None
    assert final['remaining_events'] == 0
    empty = genesis.tool('read_run', {'id': 'run-1', 'task': 'a', 'after': 6})
    assert empty['events'] == []
    assert empty['next_after'] is None
    assert empty['remaining_events'] == 0
    assert len(genesis.studio.events.return_value) == 6


def test_recover_interrupted_fails_running_turn_once_and_preserves_completed_records(genesis, monkeypatch):
    running = {'id': 'interrupted', 'status': 'running', 'answer': 'Partial observed output',
               'events': [{'id': 1, 'type': 'text_delta', 'text': 'Partial observed output'}]}
    completed = {'id': 'finished', 'status': 'completed', 'answer': 'Done',
                 'events': [{'id': 1, 'type': 'completed'}]}
    for record in (running, completed):
        genesis.path('turns', record['id']).write_text(json.dumps(record), encoding='utf8')
    completed_path = genesis.path('turns', completed['id'])
    completed_bytes = completed_path.read_bytes()
    worker = Genesis(genesis.studio)
    assert worker.read('turns', running['id']) == running
    genesis.studio.ledger.finish_run.assert_not_called()
    forbidden_thread = Mock(side_effect=AssertionError('Recovery must not launch a worker'))
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', forbidden_thread)
    worker.recover_interrupted()
    recovered = Genesis(genesis.studio).read('turns', running['id'])
    assert recovered['status'] == 'failed'
    assert recovered['answer'] == 'Partial observed output'
    assert recovered['events'][0] == running['events'][0]
    assert len(recovered['events']) == 2
    assert recovered['events'][1]['id'] == 2
    assert recovered['events'][1]['type'] == 'failed'
    assert 'uncertain charges remain reserved' in recovered['events'][1]['message']
    assert completed_path.read_bytes() == completed_bytes
    worker.recover_interrupted()
    assert worker.read('turns', running['id']) == recovered
    genesis.studio.ledger.finish_run.assert_called_once_with('genesis-interrupted')
    genesis.studio.create.assert_not_called()
    forbidden_thread.assert_not_called()


def test_recover_interrupted_only_moves_unbacked_running_preparations_to_review(genesis, monkeypatch):
    proposal = proposal_card(genesis)
    preparation = {**proposal, 'stage': 'running', 'approval': {'digest': proposal['proposal_digest'], 'revision': 1}}
    genesis.path('cards', preparation['id']).write_text(json.dumps(preparation), encoding='utf8')
    job_card = {**preparation, 'id': 'active-experiment', 'job': 'run-active'}
    completed_card = {**preparation, 'id': 'finished-preparation', 'stage': 'complete', 'artifact': {'id': 'frozen-graph'}}
    for record in (job_card, completed_card):
        genesis.path('cards', record['id']).write_text(json.dumps(record), encoding='utf8')
    untouched = {r['id']: genesis.path('cards', r['id']).read_bytes() for r in (job_card, completed_card)}
    worker = Genesis(genesis.studio)
    assert worker.read('cards', preparation['id']) == preparation
    forbidden_thread = Mock(side_effect=AssertionError('Recovery must not relaunch preparation'))
    monkeypatch.setattr('wb_studio.genesis.threading.Thread', forbidden_thread)
    worker.recover_interrupted()
    result = worker.read('cards', preparation['id'])
    assert result['stage'] == 'review'
    assert 'server restarted' in result['error']
    assert result['approval'] == preparation['approval']
    assert result['proposal'] == preparation['proposal']
    assert result['evidence'] == preparation['evidence']
    for identity, original_bytes in untouched.items():
        assert genesis.path('cards', identity).read_bytes() == original_bytes
    worker.recover_interrupted()
    assert worker.read('cards', preparation['id']) == result
    genesis.studio.create.assert_not_called()
    genesis.studio.ledger.finish_run.assert_not_called()
    forbidden_thread.assert_not_called()


@pytest.mark.parametrize('status,stage', [
    ('completed', 'review'), ('failed', 'review'), ('cancelled', 'review'),
    ('queued', 'running'), ('running', 'running'), ('cancelling', 'running'),
])
def test_state_moves_only_terminal_job_cards_to_durable_review(genesis, monkeypatch, status, stage):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    card = proposal_card(genesis)
    approved = genesis.approve(card['id'], approval_payload(card))
    genesis.studio.job.return_value = {'id': approved['job'], 'status': status}
    genesis.debrief()  # the watcher moves the card; a read never does
    result = genesis.state()['cards'][0]
    assert result['stage'] == stage
    assert result['run_status'] == status
    persisted = Genesis(genesis.studio).read('cards', card['id'])
    assert persisted['stage'] == stage
    assert persisted['job'] == approved['job']
    assert persisted['approval'] == approved['approval']
    assert persisted['proposal_digest'] == approved['proposal_digest']
    assert genesis.state()['cards'][0]['stage'] == stage
    genesis.studio.create.assert_called_once()


def test_state_reports_missing_job_without_fabricating_completion(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    card = proposal_card(genesis)
    approved = genesis.approve(card['id'], approval_payload(card))
    genesis.studio.job.side_effect = FileNotFoundError('Missing job')
    result = genesis.state()['cards'][0]
    assert result['stage'] == 'running'
    assert result['run_status'] == 'unavailable'
    assert genesis.read('cards', card['id']) == approved


def test_completed_experiment_can_record_decision_without_rewriting_approval(genesis):
    original=proposal_card(genesis)
    approved=genesis.approve(original['id'],approval_payload(original))
    genesis.studio.job.return_value={'status':'completed'}
    decision=genesis.card({**approved,'stage':'complete','body':'Observed improvement; replicate before promotion.'})
    assert decision['stage']=='complete'
    assert decision['body']=='Observed improvement; replicate before promotion.'
    assert decision['proposal']==approved['proposal']
    assert decision['proposal_digest']==approved['proposal_digest']
    assert decision['approval']==approved['approval']
    assert decision['job']==approved['job']
    assert decision['revision']==approved['revision']+1
    assert genesis.studio.create.call_count==1
    with pytest.raises(ValueError,match='cannot be edited'):
        genesis.card({**decision,'proposal':{**decision['proposal'],'maximum_usd':'99'}})
    assert genesis.read('cards',decision['id'])==decision


def test_chat_persists_selected_thinking_without_client_spend_field(genesis,monkeypatch):
    from unittest.mock import Mock
    thread=Mock()
    monkeypatch.setattr('wb_studio.genesis.threading.Thread',thread)
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes',lambda:[{'id':'gemini-3.7-flash','available':True}])
    turn=genesis.chat({'model':'gemini-3.7-flash','message':'Inspect the evidence','effort':'high'})
    assert turn['effort']=='high'
    assert turn['maximum_usd']=='2'
    assert genesis.read('turns',turn['id'])['effort']=='high'
    assert genesis.studio.ledger.reserve_run.call_args.args[1]=='2'
    assert thread.call_args.kwargs['args'][1]['effort']=='high'
    thread.return_value.start.assert_called_once()


def test_chat_rejects_unsupported_thinking_before_spending(genesis,monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes',lambda:[{'id':'gemini-3.7-flash','available':True}])
    with pytest.raises(ValueError,match='accepts'):
        genesis.chat({'model':'gemini-3.7-flash','message':'Inspect','effort':'xhigh'})
    genesis.studio.ledger.reserve_run.assert_not_called()
    assert genesis.listing('turns')==[]


def test_an_edit_that_omits_kind_and_evidence_keeps_them(genesis):
    """The watcher's dedup key is the card's kind and evidence; the model's save_research omits both."""
    card = genesis.intake('run', 'Smoke run', 'run-1', [{'kind': 'run', 'id': 'run-1'}])
    assert card['kind'] == 'run' and card['evidence'] == [{'kind': 'run', 'id': 'run-1'}]
    saved = genesis.card({'id': card['id'], 'revision': card['revision'], 'title': card['title'], 'body': 'worked', 'stage': 'review'})
    assert saved['kind'] == 'run' and saved['evidence'] == [{'kind': 'run', 'id': 'run-1'}]


def test_the_answer_is_the_last_model_response_not_the_narration(genesis):
    """Text the model writes between tool calls stays in the events; the answer is what follows the last tool call."""
    turn = {'id': 'narrated', 'status': 'running', 'answer': '', 'events': [], 'card': None}
    genesis.path('turns', turn['id']).write_text(json.dumps(turn), encoding='utf8')
    genesis.event('narrated', 'model_started', request=1)
    genesis.event('narrated', 'text_delta', text='I am checking the run. ')
    genesis.event('narrated', 'tool_started', action='measures')
    genesis.event('narrated', 'model_started', request=2)
    genesis.event('narrated', 'text_delta', text='The run passed 0 of 1 ')
    genesis.event('narrated', 'text_delta', text='and cost $0.07.')
    saved = genesis.read('turns', 'narrated')
    assert saved['answer'] == 'The run passed 0 of 1 and cost $0.07.'
    assert [e['text'] for e in saved['events'] if e['type'] == 'text_delta'][0] == 'I am checking the run. '

