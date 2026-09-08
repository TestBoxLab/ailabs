import pytest
from wb_studio.app import Studio,ROOT
from wb_world.episode import load_suite

def fixture_studio(tmp_path):
    return Studio(tmp_path,tasks=load_suite(ROOT/'tasks')[:1],gateway_factory=lambda *a,**k:pytest.fail('No provider dispatch allowed'))

def test_without_monarch_selection_is_frozen_in_run_settings(tmp_path):
    s=fixture_studio(tmp_path)
    j=s.create({'models':['oracle'],'tasks':list(s.tasks),'architectures':['without-monarch']},start=False)
    assert j['settings']['architectures']==['without-monarch']
    assert s.job(j['id'])['settings']==j['settings']

@pytest.mark.parametrize('architecture',[[],['default-monarch-enterprise'],['without-monarch','default-monarch-enterprise'],['bridge-v2-v9.12']])
def test_unimplemented_comparison_cannot_dispatch_or_create_job(tmp_path,architecture):
    s=fixture_studio(tmp_path)
    with pytest.raises(ValueError,match='cannot launch yet'):
        s.create({'models':['oracle'],'tasks':list(s.tasks),'architectures':architecture})
    assert s.jobs()==[]

def test_unsupported_runner_for_a_version_is_refused_with_the_registry_reason(tmp_path):
    s=fixture_studio(tmp_path)
    with pytest.raises(ValueError,match='native-isolation-v1'):
        s.create({'models':['claude-code'],'tasks':list(s.tasks),'architectures':['without-monarch']})
    assert s.jobs()==[]

def test_omitted_architectures_default_to_without_monarch(tmp_path):
    s=fixture_studio(tmp_path)
    j=s.create({'models':['oracle'],'tasks':list(s.tasks)},start=False)
    assert j['settings']['architectures']==['without-monarch']

def test_scripted_controls_are_rejected_on_production_launch(tmp_path):
    s=fixture_studio(tmp_path);s.gateway_factory=None
    for model in ['oracle','sloppy']:
        with pytest.raises(ValueError,match='internal tests'):
            s.create({'models':[model],'tasks':list(s.tasks)})
    assert s.jobs()==[]
