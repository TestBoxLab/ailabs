"""Architecture definitions preserve user freedom and immutable baseline revisions."""
from types import SimpleNamespace
import json
import pytest
from wb_studio.architectures import resolve_default
from wb_studio.setups import save_setup

def payload(architecture):
    return dict(name='An experiment',architecture=architecture,prompt='',hypothesis='',parents='',model='gpt-5.6-sol',efforts=['medium'],max_steps=50)

def test_default_saves_latest_revision_without_rewriting_prior_setup(tmp_path,monkeypatch):
    commits=iter(['a'*40,'b'*40])
    monkeypatch.setattr('wb_studio.architectures.resolve_default',lambda:dict(kind='default',name='Default Monarch Enterprise',repository='https://github.com/TestBoxLab/monarch',directory='monarch-enterprise',commit=next(commits)))
    studio=SimpleNamespace(directory=tmp_path)
    first=save_setup(studio,payload({'kind':'default','commit':'forged'}))
    second=save_setup(studio,payload({'kind':'default'}))
    assert first['source_commit']=='a'*40
    assert second['source_commit']=='b'*40
    assert json.loads((tmp_path/'setups'/(first['id']+'.json')).read_text())['source_commit']=='a'*40
    assert first['configuration_sha256']!=second['configuration_sha256']

def test_custom_architecture_accepts_arbitrary_definition_without_launching(tmp_path,monkeypatch):
    monkeypatch.setattr('wb_studio.architectures.resolve_default',lambda:pytest.fail('Custom definitions must not resolve or execute external code'))
    architecture={'kind':'custom','name':'My planner with two independent reviewers','definition':'Any architecture: planner -> workers -> verifier.\n{"arbitrary_component": "my implementation"}'}
    saved=save_setup(SimpleNamespace(directory=tmp_path),payload(architecture))
    assert saved['architecture']==architecture
    assert saved['source_commit'] is None
    assert saved['execution_status']=='adapter_required'
    assert saved['schema_version']=='ailabs-monarch-experiment-v2'

@pytest.mark.parametrize('architecture',[{'kind':'custom','name':'Default Monarch Enterprise','definition':'pretend official'},{'kind':'custom','name':'Mine','definition':''}])
def test_invalid_custom_definition_does_not_create_setup(tmp_path,architecture):
    with pytest.raises(ValueError):save_setup(SimpleNamespace(directory=tmp_path),payload(architecture))
    assert not list(tmp_path.rglob('*.json'))

def test_github_resolution_uses_official_repo_and_pins_commit_and_lockfile(monkeypatch):
    commands=[]
    def run(args,**kwargs):
        commands.append(args)
        assert kwargs['timeout']==20 and kwargs['check'] is True
        return SimpleNamespace(stdout=json.dumps({'sha':'c'*40 if len(commands)==1 else 'd'*40}))
    monkeypatch.setattr('wb_studio.architectures.subprocess.run',run)
    result=resolve_default()
    assert commands==[['gh','api','repos/TestBoxLab/monarch/commits/main'],['gh','api','repos/TestBoxLab/monarch/contents/pnpm-lock.yaml?ref='+'c'*40]]
    assert result['url']=='https://github.com/TestBoxLab/monarch/tree/'+'c'*40+'/monarch-enterprise'
    assert result['commit']=='c'*40 and result['lockfile']=={'path':'pnpm-lock.yaml','git_blob':'d'*40}
    manifest=result['runtime_manifest']
    assert manifest['frozen'] is True and manifest['source']['commit']=='c'*40
    assert (manifest['readiness']['source'],manifest['readiness']['runtime'])==('frozen','adapter_required')
    assert result['readiness']['launchable'] is False

def test_unverifiable_lockfile_fails_resolution_closed(monkeypatch):
    def run(args,**kwargs):
        return SimpleNamespace(stdout=json.dumps({'sha':'c'*40} if args[2].endswith('commits/main') else {'message':'Not Found'}))
    monkeypatch.setattr('wb_studio.architectures.subprocess.run',run)
    with pytest.raises(ValueError,match='Cannot verify'):resolve_default()

def test_cached_default_never_resolves_and_ignores_pre_manifest_baselines(tmp_path,monkeypatch):
    from wb_studio.architectures import cached_default,default_status
    monkeypatch.setattr('wb_studio.architectures.resolve_default',lambda:pytest.fail('cached read must not resolve'))
    studio=SimpleNamespace(directory=tmp_path)
    assert cached_default(studio) is None
    (tmp_path/'enterprise-baseline.json').write_text(json.dumps({'commit':'a'*40}),encoding='utf-8')
    assert cached_default(studio) is None
    with pytest.raises(BaseException):default_status(studio)
