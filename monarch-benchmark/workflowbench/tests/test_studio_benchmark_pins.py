from wb_studio.app import Studio,ROOT
from wb_world.episode import load_task_file,contract_hash

def test_server_pins_full_reference_and_does_not_accept_client_eligibility(tmp_path):
    studio=Studio(tmp_path,tasks=[load_task_file(p) for p in sorted((ROOT/'corpus').rglob('*.json'))[:50]],gateway_factory=lambda *a,**k:None)
    tasks=list(studio.tasks)
    full=studio.create({'models':['oracle'],'tasks':tasks},start=False)
    assert full['benchmark']=={'id':'catalog-50','task_hashes':{t:contract_hash(studio.tasks[t]) for t in tasks}}
    pilot=studio.create({'models':['oracle'],'tasks':tasks[:1],'benchmark':full['benchmark']},start=False)
    assert 'benchmark' not in pilot
    assert studio.job(full['id'])['benchmark']==full['benchmark']
