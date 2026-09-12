"""AppWorld adapter tests use only invented records and document shapes."""
import copy
import json
from pathlib import Path

import pytest

from wb_world.adapter import unsatisfied
from wb_worlds.appworld import adapter as mod


@pytest.fixture
def world_setup(tmp_path, monkeypatch):
    root = tmp_path / 'private'
    docs = root / 'data/api_docs/openapi'
    docs.mkdir(parents=True)
    for service in mod.SERVICES:
        (docs / f'{service}.json').write_text(json.dumps({'openapi':'3.1.0',
            'info':{'title':service, 'version':'test'}, 'paths':{
                f'/{service}/items': {'get':{'summary':'List items'}}}}))
    monkeypatch.setenv('APPWORLD_ROOT', str(root))
    monkeypatch.setenv('WB_APPWORLD_URL', 'http://localhost:38080')
    monkeypatch.setattr(mod, 'hydrate_task', lambda task, **kwargs: task)
    monkeypatch.setattr(mod, 'source_call', lambda operation, **kwargs:
                        {'admin':{}, 'simple_note':{'Note':[{'id':2}, {'id':1}]}})
    calls = []
    def request(url, path, payload=None):
        calls.append((path, payload))
        if path == '/initialize':
            experiment = payload['experiment_name']
            task_dir = root / 'experiments/outputs' / experiment / 'tasks/sample_1'
            (task_dir / 'version').mkdir(parents=True)
            (task_dir / 'version/code.txt').write_text('0.1.0')
            (task_dir / 'dbs').mkdir()
            (task_dir / 'dbs/simple_note.jsonl').write_text('own evidence')
        return {'output':'{"items": []}'}
    monkeypatch.setattr(mod, '_request', request)
    task = {'task':'appworld.sample_1', 'prompt':'Own request',
            'info':{'world':{'version':'0.1.3.post1'}},
            'source_ref':{'task_id':'sample_1', 'content_sha256':'own-content'}}
    return root, task, calls


def test_adapter_satisfies_shared_contract():
    assert unsatisfied(mod.AppWorldWorld) == []


def test_world_is_fresh_exclusive_and_cleanup_is_idempotent(world_setup):
    root, task, calls = world_setup
    world = mod.AppWorldWorld(task, 'attempt-one')
    with pytest.raises(RuntimeError, match='in use'):
        mod.AppWorldWorld(task, 'attempt-two')
    world.close()
    world.close()
    other = mod.AppWorldWorld(task, 'attempt-two')
    other.close()
    initializations = [payload for path, payload in calls if path == '/initialize']
    assert len({p['experiment_name'] for p in initializations}) == 2
    assert all(p['load_ground_truth'] is False for p in initializations)
    assert len([path for path, _ in calls if path == '/close']) == 2


def test_only_documented_operations_reach_execute(world_setup):
    root, task, calls = world_setup
    world = mod.AppWorldWorld(task, 'dispatch')
    try:
        assert json.loads(world.api_fetch('POST', '/evaluate'))['error']['code'] == 403
        assert json.loads(world.api_fetch('GET', '/admin/items'))['error']['code'] == 403
        assert json.loads(world.api_fetch('GET', '/simple_note/missing'))['error']['code'] == 404
        assert json.loads(world.api_fetch('GET', '/simple_note/items')) == {'items': []}
        executed = [payload['code'] for path, payload in calls if path == '/execute']
        assert len(executed) == 1
        assert '/simple_note/items' in executed[0]
        assert '/evaluate' not in json.dumps(world.interfaces().spec('simple_note', 'http://door'))
    finally:
        world.close()


def test_finish_persists_source_evidence_without_evaluating(world_setup, tmp_path):
    root, task, calls = world_setup
    world = mod.AppWorldWorld(task, 'evidence')
    world.artifacts_dir = tmp_path / 'evidence'
    try:
        assert world.snapshot() == world.snapshot0
        state = world.finish()
        assert (world.artifacts_dir / 'appworld-evidence.json').is_file()
        assert state == world.snapshot0
        assert '/evaluate' not in [path for path, _ in calls]
    finally:
        world.close()


def test_source_collateral_is_kept_beside_positive_result(world_setup, tmp_path, monkeypatch):
    root, task, calls = world_setup
    world = mod.AppWorldWorld(task, 'grade')
    world.artifacts_dir = tmp_path / 'evidence'
    before, after = world.snapshot0, world.finish()
    world.close()
    result = {'success':False, 'difficulty':2, 'num_tests':2,
        'passes':[{'requirement':'own positive', 'label':None}],
        'failures':[{'requirement':'own collateral', 'label':'no_op_pass', 'trace':'own trace'}]}
    monkeypatch.setattr(mod, 'source_call', lambda operation, **kwargs: copy.deepcopy(result))
    graded = mod.AppWorldWorld.positive_check(task, before, after, world.artifacts_dir)
    assert graded.passed is False
    assert graded.detail == result
    assert graded.side_effects == {'passed':False, 'passes':[], 'failures':result['failures']}
    evidence = next((root / 'experiments/outputs' / world.experiment / 'tasks/sample_1/dbs').glob('*'))
    evidence.write_text('tampered')
    with pytest.raises(ValueError, match='evidence.*changed'):
        mod.AppWorldWorld.positive_check(task, before, after, world.artifacts_dir)


def test_missing_evidence_is_ungraded(world_setup):
    _, task, _ = world_setup
    with pytest.raises(FileNotFoundError, match='evidence'):
        mod.AppWorldWorld.positive_check(task, {}, {}, None)


def test_null_positive_failure_does_not_become_source_collateral(world_setup, tmp_path, monkeypatch):
    _, task, _ = world_setup
    world = mod.AppWorldWorld(task, 'source-null-labels')
    world.artifacts_dir = tmp_path / 'evidence'
    before, after = world.snapshot0, world.finish()
    world.close()
    source = {'success':False, 'difficulty':1, 'num_tests':2,
        'passes':[{'requirement':'No application rows changed', 'label':'no_op_pass'}],
        'failures':[{'requirement':'Requested answer exists', 'label':'no_op_fail',
                     'trace':'Answer missing'}]}
    monkeypatch.setattr(mod, 'source_call', lambda operation, **kwargs: copy.deepcopy(source))
    result = mod.AppWorldWorld.positive_check(task, before, after, world.artifacts_dir)
    assert result.passed is False
    assert result.detail == source
    assert result.side_effects == {'passed':True, 'passes':source['passes'], 'failures':[]}


def test_published_transport_uses_json_and_explicit_tokens_without_editing_source():
    source = {'paths':{'/simple_note/login':{'post':{'requestBody':{'content':{
        'application/x-www-form-urlencoded':{'schema':{'type':'object','properties':{
            'username':{'type':'string'}}}}}}}},
        '/simple_note/items':{'get':{'security':[{'Bearer':[]}]},
                              'post':{'security':[{'Bearer':[]}]}}}}
    original = copy.deepcopy(source)
    output = mod._Interfaces({'simple_note':source}).spec('simple_note','http://door')
    login = output['paths']['/login']['post']['requestBody']['content']
    assert set(login) == {'application/json'}
    assert login['application/json']['schema']['properties'] == {'username':{'type':'string'}}
    assert output['paths']['/items']['get']['parameters'][0]['name'] == 'access_token'
    assert output['paths']['/items']['get']['parameters'][0]['required'] is True
    write = output['paths']['/items']['post']
    assert write['requestBody']['content']['application/json']['schema']['required'] == ['access_token']
    assert 'security' not in write
    assert source == original


def test_runtime_identity_binds_digest_to_the_configured_server_port(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('WB_APPWORLD_URL', 'http://127.0.0.1:18080')
    container = {'Image':'sha256:' + 'a' * 64, 'Name':'/own-container',
        'State':{'Running':True}, 'NetworkSettings':{'Ports':{'8000/tcp':[
            {'HostIp':'127.0.0.1','HostPort':'18080'}]}}}
    monkeypatch.setattr(mod.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps([container])))
    monkeypatch.setattr(mod, '_request', lambda *args, **kwargs:
                        {'package':'appworld','version':'own-version','data_version':'own-data'})
    assert mod.runtime_identity()['image'] == container['Image']
    container['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort'] = '18081'
    with pytest.raises(ValueError, match='does not own'):
        mod.runtime_identity()


def test_delete_query_inputs_reach_source_requester_unchanged(world_setup, monkeypatch):
    import contextlib
    import io
    _, task, _ = world_setup
    source = {'security':[{'Bearer':[]}], 'requestBody':{'content':{'application/json':{
        'schema':{'type':'object', 'properties':{'item_id':{'type':'integer'}}, 'required':['item_id']}}}}}
    published = mod._Interfaces({'simple_note':{'paths':{'/simple_note/items':{'delete':source}}}}).spec('simple_note','http://door')
    operation = published['paths']['/items']['delete']
    assert 'requestBody' not in operation
    assert {(p['name'],p['in'],p['required']) for p in operation['parameters']} == {
        ('access_token','query',True), ('item_id','query',True)}
    assert source['requestBody']['content']['application/json']['schema']['properties'] == {'item_id':{'type':'integer'}}
    world = mod.AppWorldWorld(task,'delete-query-control')
    world._specs['simple_note']['paths']['/simple_note/items']['delete'] = source
    observed = []
    class Requester:
        client = object()
        def delete(self, path, data, client, raise_on_failure):
            observed.append((path, data, client, raise_on_failure))
            return {'deleted':data['item_id']}
    requester = Requester()
    original_request = mod._request
    def execute(url, path, payload=None):
        if path != '/execute':
            return original_request(url,path,payload)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(payload['code'], {'requester':requester})
        return {'output':output.getvalue()}
    monkeypatch.setattr(mod,'_request',execute)
    try:
        result = json.loads(world.api_fetch('DELETE','/simple_note/items',params=json.dumps({'item_id':7,'access_token':'own-token'})))
        assert result == {'deleted':7}
        assert observed == [('/simple_note/items', {'item_id':7,'access_token':'own-token'}, requester.client, False)]
    finally:
        world.close()
