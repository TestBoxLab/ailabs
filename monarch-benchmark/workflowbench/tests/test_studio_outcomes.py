"""Outcome presentation and bounded scientific configuration regressions."""
import hashlib
import json
from decimal import Decimal

import pytest

from wb_studio import analysis
from wb_studio.app import ROOT, Studio
from wb_studio.paid import PaidGateway
from wb_studio.reports import outcome_report, public_task
from wb_studio.setups import PRESETS, save_setup
from wb_world.episode import contract_hash, load_suite


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'offline-only')
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected provider use')
    return Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=forbidden)


def job_payload(studio, **changes):
    return {'request_id': 'outcomes', 'models': ['gemini-3.7-flash@low', 'gemini-3.7-flash@high'],
            'tasks': list(studio.tasks), 'maximum_usd': '10.00', **changes}


def transport_for(data, calls):
    def transport(operation, payload):
        calls.append((operation, json.loads(json.dumps(payload))))
        if operation == 'countTokens':
            return {'totalTokens': 20}
        return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(data)}]}}],
                'usageMetadata': {'promptTokenCount': 20, 'candidatesTokenCount': 10, 'thoughtsTokenCount': 0, 'totalTokenCount': 30}}
    return transport


def test_complete_public_catalog_has_800_categorized_briefs_without_evaluator_data(tmp_path):
    studio = Studio(tmp_path / 'catalog', gateway_factory=lambda *args, **kwargs: None)
    tasks = [public_task(t) for t in studio.tasks.values()]
    assert len(tasks) == len({t['id'] for t in tasks}) == 800
    assert {t['category'] for t in tasks} == {'Everyday requests', 'Finance', 'People & HR', 'Marketing', 'Operations', 'Sales', 'Customer support'}
    assert all(t['brief'] and t['title'] and isinstance(t['applications'], list) for t in tasks)
    assert sum(bool(t['applications']) for t in tasks) == 799  # One frozen task has an empty initial state.
    assert all(set(t) == {'id', 'title', 'brief', 'category', 'applications', 'source', 'version'} for t in tasks)
    assert all('assertions' not in t and 'initial_state' not in t for t in tasks)


def test_effort_variants_freeze_settings_and_reach_actual_gateway_payload(studio):
    calls = []
    def factory(ledger, model):
        return PaidGateway(ledger, model=model, transport=transport_for({'answer': 'Observed'}, calls))
    studio.gateway_factory = factory
    config = {'prompt': 'Use precise record selection.', 'max_turns': 3}
    job = studio.create(job_payload(studio, configuration=config), start=False)
    assert job['settings']['configuration'] == config
    assert job['task_hashes'] == {t: contract_hash(studio.tasks[t]) for t in studio.tasks}
    with pytest.raises(ValueError, match='different comparison'):
        studio.create(job_payload(studio, configuration={**config, 'max_turns': 4}), start=False)
    studio.execute(job['id'])
    assert studio.job(job['id'])['status'] == 'completed'
    generated = [p for operation, p in calls if operation == 'generateContent']
    assert [p['generationConfig']['thinkingConfig']['thinkingLevel'] for p in generated] == ['low', 'high']
    assert all('Use precise record selection.' in p['systemInstruction']['parts'][0]['text'] for p in generated)
    assert Decimal(studio.budget()['actual']) > 0  # Fake transport still exercises real reservation accounting.
    assert Decimal(studio.budget()['held']) == 0


@pytest.mark.parametrize('changes', [
    {'models': ['gemini-3.7-flash@max']}, {'models': ['oracle@high']},
    {'models': ['gemini-3.7-flash@high@low']},
    {'configuration': {'max_turns': True}}, {'configuration': {'max_turns': 0}},
    {'configuration': {'max_turns': 51}}, {'configuration': {'temperature': 1}},
    {'configuration': {'prompt': 'x' * 12001}},
    {'models': ['oracle'], 'configuration': {'prompt': 'Ignored instruction'}},
])
def test_invalid_reasoning_or_execution_settings_never_create_job(studio, changes):
    with pytest.raises(ValueError):
        studio.create(job_payload(studio, **changes), start=False)
    assert studio.jobs() == []


def setup_payload(**changes):
    return {'name': 'Precise selection', 'preset': PRESETS[0], 'prompt': 'Check record identity',
            'hypothesis': 'Entity checks reduce collateral writes', 'parents': 'baseline-1',
            'model': 'gpt-5.6-sol', 'efforts': ['low', 'high'], 'max_steps': 20, **changes}


def test_setup_drafts_are_distinct_immutable_records_and_honest_about_execution(studio):
    first = save_setup(studio, setup_payload())
    path = studio.directory / 'setups' / (first['id'] + '.json')
    original = path.read_bytes()
    second = save_setup(studio, setup_payload(prompt='Resolve names before writes'))
    assert first['id'] != second['id']
    assert path.read_bytes() == original
    assert first['configuration_sha256'] != second['configuration_sha256']
    assert first['prompt_sha256'] == hashlib.sha256(b'Check record identity').hexdigest()
    assert first['execution_status'] == second['execution_status'] == 'adapter_required'
    assert first['source_commit'] is None and first['runtime_snapshot_sha256'] is None
    assert studio.jobs() == []


@pytest.mark.parametrize('changes', [{'preset': 'invented'}, {'efforts': ['high', 'high']},
                                      {'max_steps': True}, {'id': 'overwrite-existing'}])
def test_invalid_setup_cannot_write_an_executable_or_replace_a_draft(studio, changes):
    with pytest.raises(ValueError):
        save_setup(studio, setup_payload(**changes))
    assert not (studio.directory / 'setups').exists()


def test_outcome_report_separates_infrastructure_scope_and_observed_actions():
    task = {'info': {'assertions': [{'field': 'phone', 'value': '123'}]}}
    results = [{'task': 'sales.task', 'model': model, 'passed': False, 'termination': termination,
                'checks': [{'type': 'field_equals', 'passed': True}, {'type': 'allowed_changes_only', 'passed': False}],
                'unexpected_changes': [{'service': 'gmail', 'path': 'messages[0].label_ids', 'before': ['INBOX'], 'after': ['TRASH']}]} for model, termination in [('api', 'completed'), ('infra', 'infra:harness_crash')]]
    events = [{'id': 1, 'type': 'node_started', 'task': 'sales.task', 'model': 'api', 'node': 'tool-1',
               'label': 'api_fetch', 'arguments': {'method': 'PATCH', 'url': 'https://example.salesforce.com/contact', 'body': '{"Phone":"123"}'}},
              {'id': 2, 'type': 'node_finished', 'task': 'sales.task', 'model': 'api', 'node': 'tool-1', 'status': 'completed'}]
    report = outcome_report({'id': 'run', 'results': results}, events, {'sales.task': task})
    scope, infra = report['attempts']
    assert scope['title'] == 'Requested work changed more than allowed'
    assert scope['scope_respected'] is False
    assert scope['requirements'] == [{'title': 'Phone should be 123', 'passed': True, 'check_index': 0}]
    assert scope['actions'][0]['status'] == 'observed'
    assert scope['actions'][0]['event_id'] == 1
    assert scope['causal_claim'] is None
    assert infra['title'] == 'Execution could not be evaluated'
    assert infra['infrastructure'] is True
    assert 'valid quality measurement' in infra['summary']


def ready_for_analysis(studio):
    job = studio.create(job_payload(studio), start=False)
    studio.emit(job['id'], 'node_started', model=job['settings']['models'][0], task=list(studio.tasks)[0], node='tool-1', label='api_search', arguments={'query': 'contacts'})
    studio.emit(job['id'], 'node_finished', model=job['settings']['models'][0], task=list(studio.tasks)[0], node='tool-1', output='found', status='completed')
    job['status'] = 'completed'
    studio.save(job)
    return job


def valid_analysis():
    return {'summary': 'A search was observed.', 'findings': [{'title': 'Discovery', 'explanation': 'Searched for contacts.', 'kind': 'fact', 'event_ids': [2]}],
            'next_experiment': 'Repeat with ambiguous contacts.', 'limitations': 'No completion evidence in this isolated trace.'}


def test_analysis_uses_blinded_citations_real_budget_and_single_dispatch(studio):
    job = ready_for_analysis(studio)
    calls = []
    studio.gateway_factory = lambda ledger, model: PaidGateway(ledger, model=model, transport=transport_for(valid_analysis(), calls))
    report = analysis.review(studio, job['id'])
    assert report['status'] == 'completed'
    assert report['findings'][0]['event_ids'] == [2]
    generated = [p for op, p in calls if op == 'generateContent']
    assert len(generated) == 1
    assert generated[0]['generationConfig']['thinkingConfig']['thinkingLevel'] == 'medium'
    payload = json.loads(generated[0]['contents'][0]['parts'][0]['text'])
    assert {e['model'] for e in payload['events']} == {'Approach 1'}
    assert 'assertions' not in payload and 'initial_state' not in payload
    assert 'not a replacement' in report['basis'] or 'interpretation' in report['basis']
    assert Decimal(studio.budget()['actual']) > 0 and Decimal(studio.budget()['held']) == 0
    assert analysis.review(studio, job['id']) == report
    assert len(calls) == 2


@pytest.mark.parametrize('bad', [
    {'summary': 12},
    {'findings': [{'title': 'Claim', 'explanation': 'Unsupported', 'kind': 'fact', 'event_ids': [999]}]},
    {'findings': [{'title': 'Claim', 'explanation': 'Unsupported', 'kind': 'fact', 'event_ids': [True]}]},
    {'findings': [{'title': 'Claim', 'explanation': 'Unsupported', 'kind': 'causal', 'event_ids': [2]}]},
])
def test_analysis_rejects_invalid_schema_or_citations_without_retry(studio, bad):
    job = ready_for_analysis(studio)
    calls = []
    studio.gateway_factory = lambda ledger, model: PaidGateway(ledger, model=model, transport=transport_for({**valid_analysis(), **bad}, calls))
    result = analysis.review(studio, job['id'])
    assert result['status'] == 'failed'
    assert (studio.directory / job['id'] / 'analysis-response.json').exists()
    assert analysis.review(studio, job['id']) == result
    assert len(calls) == 2


def test_analysis_does_not_dispatch_when_shared_budget_cannot_admit(studio):
    job = ready_for_analysis(studio)
    studio.ledger.reserve('other-work', Decimal('300'), scope_id='other-work')
    calls = []
    studio.gateway_factory = lambda ledger, model: PaidGateway(ledger, model=model, transport=transport_for(valid_analysis(), calls))
    result = analysis.review(studio, job['id'])
    assert result['status'] == 'failed'
    assert [op for op, _ in calls] == ['countTokens']
    assert Decimal(studio.budget()['held']) == 300


def test_analysis_rejects_running_jobs_before_reserving_or_dispatch(studio):
    job = studio.create(job_payload(studio), start=False)
    with pytest.raises(ValueError, match='finish'):
        analysis.review(studio, job['id'])
    assert not (studio.directory / job['id'] / 'analysis.claimed').exists()
    assert Decimal(studio.budget()['held']) == 0


def test_interrupted_analysis_claim_is_never_automatically_replayed(studio):
    job = ready_for_analysis(studio)
    claim = studio.directory / job['id'] / 'analysis.claimed'
    claim.write_text('previous-dispatch-input-hash')
    with pytest.raises(ValueError, match='already dispatched'):
        analysis.review(studio, job['id'])
    assert claim.read_text() == 'previous-dispatch-input-hash'
    assert not (studio.directory / job['id'] / 'analysis.json').exists()
