import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_arms.api_loop import ArmResult, EpisodeTimeout, InfraError
from wb_orchestrator.campaign_budget import CampaignBudget
from wb_orchestrator.prototype_campaign import (BudgetedCompetitor, PreflightError, build_manifest,
                                               main, validate_preflight, ROOT)


def test_manifest_is_keyless_deterministic_and_has_exact_approved_attempt_counts():
    first, second = build_manifest(), build_manifest()
    assert first == second
    assert first['attempts'] == 66
    assert [p['attempts'] for p in first['phases']] == [30, 36]
    assert first['reservation_estimate_usd'] == 792
    assert first['missing'] == ['personal_30_node_workflow']
    assert len({t['id'] for t in first['tasks']}) == 10
    assert all(len(t['file_sha256']) == 64 for t in first['tasks'])
    assert all(t['readiness']['negative_control'] == 'rejected' for t in first['tasks'])


def test_dry_plan_does_not_create_budget_or_construct_a_model_competitor(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr('wb_orchestrator.prototype_campaign.CampaignBudget', Mock(side_effect=AssertionError('ledger created')))
    assert main(['--budget', str(tmp_path/'budget.sqlite')]) == 0
    assert json.loads(capsys.readouterr().out)['attempts'] == 66
    assert not (tmp_path/'budget.sqlite').exists()


def test_missing_proof_prevents_execution_before_any_ledger_mutation(tmp_path):
    with pytest.raises(PreflightError):
        main(['--execute', '--budget', str(tmp_path/'budget.sqlite')])
    assert not (tmp_path/'budget.sqlite').exists()


def test_preflight_cannot_use_a_manifest_with_different_hashes(tmp_path):
    p = tmp_path/'proof.json'
    p.write_text(json.dumps({'manifest_sha256': 'wrong'}))
    with pytest.raises(PreflightError, match='manifest'):
        validate_preflight(p, build_manifest())


def competitor(tmp_path, result=None):
    budget = CampaignBudget(tmp_path/'budget.sqlite')
    complete = ArmResult(cost_usd=2, turn_log=[
        {'authoring_events': {'complete': True, 'events': []}},
    ])
    inner = SimpleNamespace(name='model', provider_key='monarch', run=Mock(return_value=result or complete))
    stop = Mock()
    return BudgetedCompetitor(inner, budget, authorize=lambda: None, stop=stop), inner, budget, stop


def test_reservation_precedes_dispatch_and_duplicate_id_never_dispatches_twice(tmp_path):
    wrapped, inner, budget, _ = competitor(tmp_path)
    def run(ep, deadline):
        assert budget.snapshot()['reserved_usd'] == 12
        return ArmResult(cost_usd=2, turn_log=[
            {'authoring_events': {'complete': True, 'events': []}},
        ])
    inner.run.side_effect = run
    ep = SimpleNamespace(episode_id='stable-attempt')
    wrapped.run(ep, time.monotonic()+1)
    assert budget.snapshot()['spent_usd'] == 2
    with pytest.raises(InfraError):
        wrapped.run(ep, time.monotonic()+1)
    assert inner.run.call_count == 1


def test_wrapper_preserves_model_metadata_used_by_stored_episode_rows(tmp_path):
    wrapped, inner, _, _ = competitor(tmp_path)
    inner.model_label = 'monarch@abc123+prototype'
    wrapped = BudgetedCompetitor(inner, CampaignBudget(tmp_path/'other.sqlite'),
                                 authorize=lambda: None, stop=Mock())
    assert wrapped.model_label == 'monarch@abc123+prototype'


def test_unknown_cost_stops_paid_work_and_does_not_treat_zero_as_free(tmp_path):
    wrapped, inner, budget, stop = competitor(tmp_path, ArmResult(cost_usd=0, flags=['cost_missing']))
    wrapped.run(SimpleNamespace(episode_id='a'), time.monotonic()+1)
    assert budget.snapshot()['unknown'] == ['a']
    stop.assert_called()
    with pytest.raises(InfraError):
        wrapped.run(SimpleNamespace(episode_id='b'), time.monotonic()+1)
    assert inner.run.call_count == 1


def test_timeout_cost_is_unknown_until_cancellation_and_billing_are_settled(tmp_path):
    wrapped, inner, budget, stop = competitor(tmp_path)
    exc = EpisodeTimeout('cancel requested')
    exc.partial = ArmResult(cost_usd=1)
    inner.run.side_effect = exc
    with pytest.raises(EpisodeTimeout):
        wrapped.run(SimpleNamespace(episode_id='a'), time.monotonic()+1)
    assert budget.snapshot()['unknown'] == ['a']
    stop.assert_called()


def test_incomplete_child_usage_with_partial_cost_remains_unknown(tmp_path):
    result = ArmResult(cost_usd=3, turn_log=[
        {'authoring_events': {'complete': True, 'events': [
            {'seq': 1, 'data': {'kind': 'section_model_usage', 'callId': 'child-1',
                                'usageComplete': True, 'costKnown': True}},
            {'seq': 2, 'data': {'kind': 'section_model_usage', 'callId': 'child-2',
                                'usageComplete': False, 'costKnown': False}},
        ]}},
        {'cost': {'authoring': {'model': {'cost_usd': 3}}}},
    ])
    wrapped, _, budget, stop = competitor(tmp_path, result)
    wrapped.run(SimpleNamespace(episode_id='partial'), time.monotonic()+1)
    assert budget.snapshot()['unknown'] == ['partial']
    stop.assert_called_once()


def test_complete_child_usage_allows_exactly_one_settlement(tmp_path):
    result = ArmResult(cost_usd=3, turn_log=[
        {'authoring_events': {'complete': True, 'events': [
            {'seq': 1, 'data': {'kind': 'section_model_usage', 'callId': 'child-1',
                                'usageComplete': True, 'costKnown': True}},
        ]}},
        {'cost': {'authoring': {'model': {'cost_usd': 3}}}},
    ])
    wrapped, inner, budget, _ = competitor(tmp_path, result)
    wrapped.run(SimpleNamespace(episode_id='complete'), time.monotonic()+1)
    assert budget.snapshot()['spent_usd'] == 3
    with pytest.raises(InfraError):
        wrapped.run(SimpleNamespace(episode_id='complete'), time.monotonic()+1)
    assert inner.run.call_count == 1


def test_preflight_is_rechecked_before_every_dispatch(tmp_path):
    wrapped, inner, budget, stop = competitor(tmp_path)
    wrapped.authorize = Mock(side_effect=PreflightError('proof withdrawn'))
    with pytest.raises(PreflightError):
        wrapped.run(SimpleNamespace(episode_id='a'), time.monotonic()+1)
    inner.run.assert_not_called()
    assert budget.snapshot()['committed_usd'] == 0


def proof_fixture(tmp_path, manifest):
    import hashlib
    # Synthetic qualified manifest is only for proof-validator unit tests.
    for task in manifest['tasks']:
        task['readiness']['status'] = 'qualified'
    sha = 'a' * 40
    proof = {'manifest_sha256': manifest['manifest_sha256'], 'preview_sha': sha,
             'preview_url': 'https://pr-123.monarch-dev.testbox.com', 'approved_by': 'unit-test-only',
             'campaign_id': 'unit-test', 'personal_30_node_workflow_not_included': True}
    def record(name, fields):
        raw = json.dumps({'verified': True, 'preview_sha': sha, **fields}).encode()
        p = tmp_path / f'{name}.json'
        p.write_bytes(raw)
        return {'path': p.name, 'sha256': hashlib.sha256(raw).hexdigest()}
    proof['models'] = record('models', {'kind': 'exact_model_inventory', 'all_roles_accounted_for': True,
                                      'models': {'test-role': {'model_id': 'unit-test-model', 'provider': 'test', 'effort': 'none'}}})
    proof['dollar_enforcement'] = record('dollars', {'kind': 'server_dollar_enforcement', 'campaign_limit_usd': 1000,
                                                   'development_limit_usd': 200, 'attempt_limit_usd': 12,
                                                   'inflight_calls_included': True, 'unknown_usage_blocks': True,
                                                   'enforced_before_model_calls': True})
    proof['cancellation'] = record('cancel', {'kind': 'settled_cancellation', 'all_child_calls_stopped': True, 'billing_final': True})
    proof['world'] = record('world', {'kind': 'dedicated_synthetic_world', 'per_attempt_reset': True, 'shared_accounts': False})
    proof['graders'] = {t['id']: record(t['id'], {'kind': 'task_grader_controls', 'task_sha256': t['file_sha256'],
                                               'positive_passed': True, 'negative_rejected': True, 'collateral_rejected': True})
                        for t in manifest['tasks']}
    path = tmp_path / 'proof.json'
    path.write_text(json.dumps(proof))
    return path, proof


def test_validated_attestations_are_bound_to_the_exact_evidence_bytes(tmp_path):
    manifest = build_manifest()
    path, proof = proof_fixture(tmp_path, manifest)
    assert validate_preflight(path, manifest) == proof
    (tmp_path / 'dollars.json').write_text('{}')
    with pytest.raises(PreflightError, match='hash differs'):
        validate_preflight(path, manifest)


@pytest.mark.parametrize('missing', ['models', 'dollar_enforcement', 'cancellation', 'world', 'graders'])
def test_each_paid_proof_requirement_is_mandatory(tmp_path, missing):
    manifest = build_manifest()
    path, proof = proof_fixture(tmp_path, manifest)
    del proof[missing]
    path.write_text(json.dumps(proof))
    with pytest.raises(PreflightError):
        validate_preflight(path, manifest)


def test_existing_orchestrator_applies_wrapper_before_any_competitor_prepare(tmp_path, monkeypatch):
    from wb_orchestrator import orchestrator as module
    from wb_results.store import Store
    from wb_world.episode import load_task_file
    task = load_task_file(ROOT/'tasks/simple.email_sf_contact_city_update.json')
    seen = []
    fake = SimpleNamespace(name='null', provider_key=None)
    monkeypatch.setattr(module, 'build_arm', lambda key: fake)
    store = Store(tmp_path/'results.sqlite')
    orchestrator = module.Orchestrator(store, tmp_path, ['null'], 1, tmp_path, tasks=[task])
    orchestrator.arm_wrapper = lambda inner: seen.append(inner) or inner
    monkeypatch.setattr(orchestrator, '_run_arm_group', lambda run_id, arm, work: seen.append(('dispatched', arm)))
    orchestrator.run('wrapper-test')
    assert seen == [fake, ('dispatched', fake)]
    store.close()


def test_external_attestation_cannot_override_a_locally_rejected_grader(tmp_path):
    manifest = build_manifest()
    path, proof = proof_fixture(tmp_path, manifest)
    manifest['tasks'][0]['readiness']['status'] = 'rejected'
    with pytest.raises(PreflightError, match='Local independent'):
        validate_preflight(path, manifest)
