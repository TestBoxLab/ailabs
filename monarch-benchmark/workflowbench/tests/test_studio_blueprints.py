"""Offline architectural publication, empirical difficulty and catalog contracts."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import threading

import pytest

from wb_studio import blueprints
from wb_studio.difficulty import difficulty
from wb_studio.runners import fireworks_catalog, runner_config
from wb_studio.app import ROOT
from wb_world.episode import contract_hash, load_suite


@pytest.fixture
def studio(tmp_path):
    return SimpleNamespace(directory=tmp_path, lock=threading.RLock())


def node(identity, kind, **config):
    return {'id': identity, 'type': kind, 'label': identity, 'x': 10, 'y': 20, 'config': config}


def graph(monarch=False):
    middle = node('worker', 'monarch' if monarch else 'agent', instructions='Read then act.',
                  runner={'provider': 'codex', 'model': 'gpt-test', 'effort': 'high'})
    return {'nodes': [node('input', 'input'), middle, node('output', 'output')],
            'edges': [{'from': 'input', 'to': 'worker'}, {'from': 'worker', 'to': 'output'}]}


def save(studio, **changes):
    return blueprints.save_draft(studio, {'id': 'design', 'name': 'Careful worker', 'graph': graph(), **changes})


def test_draft_compare_and_swap_prevents_lost_edits_and_copies_graph(studio):
    source = graph()
    first = save(studio, graph=source)
    source['nodes'][1]['label'] = 'Mutated caller data'
    assert first['graph']['nodes'][1]['label'] == 'worker'
    second = save(studio, revision=1, name='Changed name')
    assert second['revision'] == 2
    with pytest.raises(ValueError, match='another editor'):
        save(studio, revision=1, name='Stale editor')
    stored = blueprints.listing(studio)[0]
    assert stored['name'] == 'Changed name' and stored['revision'] == 2


def test_publish_is_idempotent_and_versions_are_immutable(studio):
    draft = save(studio)
    first = blueprints.publish(studio, {'id': draft['id'], 'revision': 1})
    path = studio.directory / 'blueprints' / 'design' / 'v0001.json'
    original = path.read_bytes()
    assert blueprints.publish(studio, {'id': 'design', 'revision': 1}) == first
    draft = save(studio, revision=1, name='Second design')
    second = blueprints.publish(studio, {'id': 'design', 'revision': draft['revision']})
    assert path.read_bytes() == original
    assert first['version'] == 1 and second['version'] == 2 and second['parent_version'] == 1
    assert first['order'] == ['input', 'worker', 'output']
    assert first['execution_status'] == 'blocked'   # a native runner: valid, not yet servable
    expected = hashlib.sha256(json.dumps(first['graph'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert first['sha256'] == expected
    assert len(blueprints.listing(studio)[0]['versions']) == 2
    with pytest.raises(ValueError, match='latest edits'):
        blueprints.publish(studio, {'id': 'design', 'revision': 1})


def test_monarch_publication_pins_verified_baseline_without_mutating_draft(studio, monkeypatch):
    calls = []
    def default(studio, refresh=False):
        calls.append(refresh)
        return {'id': 'default-monarch-enterprise', 'commit': 'a' * 40, 'ref': 'main'}
    monkeypatch.setattr(blueprints, 'default_status', default)
    save(studio, graph=graph(monarch=True))
    first = blueprints.publish(studio, {'id': 'design', 'revision': 1})
    assert first['graph']['nodes'][1]['config']['baseline']['commit'] == 'a' * 40
    assert 'baseline' not in blueprints.listing(studio)[0]['graph']['nodes'][1]['config']
    assert blueprints.publish(studio, {'id': 'design', 'revision': 1}) == first
    assert calls == [True]


def test_unverifiable_monarch_baseline_cannot_publish_partial_version(studio, monkeypatch):
    save(studio, graph=graph(monarch=True))
    def unavailable(*args, **kwargs):
        raise ValueError('Cannot verify revision')
    monkeypatch.setattr(blueprints, 'default_status', unavailable)
    with pytest.raises(ValueError, match='verify'):
        blueprints.publish(studio, {'id': 'design', 'revision': 1})
    assert blueprints.listing(studio)[0]['versions'] == []


def test_disconnected_draft_is_allowed_but_cannot_publish(studio):
    source = graph()
    source['edges'].pop()
    save(studio, graph=source)
    with pytest.raises(ValueError, match='Connect this node'):
        blueprints.publish(studio, {'id': 'design', 'revision': 1})
    assert blueprints.listing(studio)[0]['versions'] == []


def test_cycle_cannot_be_saved_even_as_draft(studio):
    source = graph()
    source['edges'].append({'from': 'output', 'to': 'input'})
    with pytest.raises(ValueError, match='circular'):
        save(studio, graph=source)
    assert blueprints.listing(studio) == []


def test_product_graph_step_needs_a_version_reference():
    source = {'nodes': [node('input', 'input'), node('knowledge', 'product-graph', graph='catalog', version=2), node('output', 'output')],
              'edges': [{'from': 'input', 'to': 'knowledge'}, {'from': 'knowledge', 'to': 'output'}]}
    assert blueprints.validate_graph(source) == ['input', 'knowledge', 'output']
    for broken in ({}, {'graph': 'catalog'}, {'graph': 'catalog', 'version': 0}, {'graph': 'bad id!', 'version': 1}):
        missing = deepcopy(source)
        missing['nodes'][1]['config'] = broken
        with pytest.raises(ValueError, match='prepared product graph version'):
            blueprints.validate_graph(missing)


@pytest.mark.parametrize('mutation', ['duplicate-id', 'duplicate-edge', 'bad-position', 'missing-instructions', 'missing-runner'])
def test_strict_graph_rejects_invalid_node_or_edge_contract(mutation):
    source = graph()
    if mutation == 'duplicate-id': source['nodes'][1]['id'] = 'input'
    if mutation == 'duplicate-edge': source['edges'].append(source['edges'][0].copy())
    if mutation == 'bad-position': source['nodes'][1]['x'] = float('nan')
    if mutation == 'missing-instructions': source['nodes'][1]['config'].pop('instructions')
    if mutation == 'missing-runner': source['nodes'][1]['config'].pop('runner')
    with pytest.raises(ValueError):
        blueprints.validate_graph(source)


def difficulty_inputs():
    task = load_suite(ROOT / 'tasks')[0]
    return {task['task']: task}, task['task'], contract_hash(task)


def result(task, passed=True, **changes):
    return {'task': task, 'model': 'gemini@high', 'passed': passed, 'termination': 'completed', 'flags': [], **changes}


def test_difficulty_excludes_mismatched_hash_scripted_infra_and_incomplete_evidence():
    tasks, identity, digest = difficulty_inputs()
    jobs = [{'task_hashes': {identity: 'wrong'}, 'results': [result(identity)]},
            {'task_hashes': {identity: digest}, 'results': [result(identity, model='oracle'), result(identity, model='sloppy'),
                result(identity, termination='infra:harness_crash'), result(identity, flags=['evidence_incomplete']), result(identity, passed=1)]}]
    value = difficulty(tasks, jobs)[identity]
    assert value['level'] == 'unrated'
    assert value['attempts'] == value['failures'] == 0
    assert value['failure_rate'] is None and value['provisional'] is True


@pytest.mark.parametrize('n,failed,level,provisional', [(3, 1, 'easy', True), (3, 2, 'hard', True), (4, 2, 'medium', True), (5, 2, 'medium', False), (5, 0, 'easy', False), (5, 5, 'hard', False)])
def test_difficulty_thresholds_and_uncertainty_are_explicit(n, failed, level, provisional):
    tasks, identity, digest = difficulty_inputs()
    job = {'task_hashes': {identity: digest}, 'results': [result(identity, passed=i >= failed) for i in range(n)]}
    value = difficulty(tasks, [job])[identity]
    assert value['attempts'] == n and value['failures'] == failed
    assert value['level'] == level and value['provisional'] is provisional
    assert value['failure_rate'] == failed / n
    assert 0 <= value['interval'][0] <= value['failure_rate'] <= value['interval'][1] <= 1
    assert 'not independent tasks' in value['description']


def test_fireworks_paginates_public_and_account_catalogs_deduplicates_and_caches(studio, monkeypatch):
    monkeypatch.setenv('FIREWORKS_ACCOUNT_ID', 'private-account')
    calls = []
    def transport(account, token):
        calls.append((account, token))
        if (account, token) == ('fireworks', ''):
            return {'models': [{'name': 'accounts/fireworks/models/z', 'displayName': 'Zulu'}], 'nextPageToken': 'page-two'}
        if account == 'fireworks':
            return {'models': [{'name': 'accounts/fireworks/models/a', 'displayName': 'Alpha', 'baseModelDetails': {'supportsServerless': True}}]}
        return {'models': [{'name': 'accounts/private-account/models/p', 'displayName': 'Private'}, {'name': 'accounts/fireworks/models/z', 'displayName': 'Zulu'}]}
    value = fireworks_catalog(studio, transport=transport)
    assert value['status'] == 'loaded' and value['complete'] is True
    assert calls == [('fireworks', ''), ('fireworks', 'page-two'), ('private-account', '')]
    assert [m['name'] for m in value['models']] == ['Alpha', 'Private', 'Zulu']
    assert value['models'][0]['serverless'] is True
    assert fireworks_catalog(studio, transport=lambda *args: pytest.fail('Cache unexpectedly fetched')) == value


@pytest.mark.parametrize('failure', ['repeat', 'error'])
def test_fireworks_failure_never_returns_or_caches_partial_models(studio, monkeypatch, failure):
    monkeypatch.delenv('FIREWORKS_ACCOUNT_ID', raising=False)
    calls = []
    def transport(account, token):
        calls.append(token)
        if token and failure == 'error': raise RuntimeError('secret-provider-body')
        return {'models': [{'name': 'accounts/fireworks/models/partial'}], 'nextPageToken': 'repeat'}
    value = fireworks_catalog(studio, transport=transport)
    assert value['status'] == 'unavailable' and value['complete'] is False
    assert value['models'] == []
    assert 'secret-provider-body' not in json.dumps(value)
    assert calls == ['', 'repeat']
    assert not (studio.directory / 'fireworks-models.json').exists()


def test_unconfigured_fireworks_catalog_never_opens_network(studio, monkeypatch):
    monkeypatch.delenv('FIREWORKS_API_KEY', raising=False)
    monkeypatch.setattr('wb_studio.runners.build_opener', lambda *args: pytest.fail('Unexpected network'))
    value = fireworks_catalog(studio)
    assert value['status'] == 'credentials_required' and value['models'] == [] and value['complete'] is False


@pytest.mark.parametrize('provider', ['claude-code', 'codex', 'fireworks', 'gemini'])
def test_runner_profiles_preserve_provider_model_and_effort_without_claiming_execution(provider):
    assert runner_config({'provider': provider, 'model': ' model-id ', 'effort': 'high'}) == {'provider': provider, 'model': 'model-id', 'effort': 'high'}
    assert runner_config({'provider': provider, 'model': 'model-id'})['effort'] == 'default'


@pytest.mark.parametrize('value', [None, {'provider': 'invented', 'model': 'x'}, {'provider': 'codex', 'model': ''}, {'provider': 'codex', 'model': 'bad\nmodel'}, {'provider': 'codex', 'model': 'x', 'effort': 'unlimited'}])
def test_invalid_runner_profiles_are_rejected(value):
    with pytest.raises(ValueError):
        runner_config(value)
