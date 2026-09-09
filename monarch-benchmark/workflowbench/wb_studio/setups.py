"""Immutable Monarch experiment drafts; never mutate or launch historical sources."""
import hashlib
import json
import uuid
from wb_results.evidence import write_json
PRESETS = ('graph-inline-v3','graph-inline-v6','graph-inline-v8','subtraction-first','typed-resolution','typed-obligation','typed-resource','plan-ensemble-v7')

def save_setup(studio,payload):
    allowed={'name','preset','prompt','hypothesis','parents','model','efforts','max_steps','architecture'}
    if set(payload)-allowed: raise ValueError('Unsupported setup field')
    for key,maximum in [('name',100),('prompt',12000),('hypothesis',2000),('parents',1000)]:
        if not isinstance(payload.get(key,''),str) or len(payload.get(key,''))>maximum: raise ValueError('Invalid '+key)
    if not payload.get('name','').strip() or ('architecture' not in payload and payload.get('preset') not in PRESETS): raise ValueError('Choose a name and an existing Monarch preset')
    if payload.get('model') not in ('gpt-5.6-sol','claude-opus','gemini-3.7-flash'): raise ValueError('Unsupported draft model')
    efforts=payload.get('efforts',[])
    if not isinstance(efforts,list) or not efforts or len(set(efforts))!=len(efforts) or any(e not in ('low','medium','high','xhigh','max') for e in efforts): raise ValueError('Choose valid reasoning levels')
    if type(payload.get('max_steps')) is not int or not 1<=payload['max_steps']<=50: raise ValueError('Step limit must be between 1 and 50')
    data={**payload,'schema_version':'ailabs-monarch-experiment-v1','id':uuid.uuid4().hex,'execution_status':'adapter_required',
          'source':'Monarch_Main/ATLAS/backend/scripts/dev/bench-monarch-v81-core.ts',
          'source_commit':None,'runtime_snapshot_sha256':None,
          'prompt_sha256':hashlib.sha256(payload.get('prompt','').encode()).hexdigest()}
    if 'architecture' in payload:
        from wb_studio.architectures import normalize_architecture
        data['architecture'] = normalize_architecture(studio,payload['architecture'])
        architecture = data['architecture']
        data['preset'] = architecture['name']
        data['source'] = architecture.get('repository')
        data['source_commit'] = architecture.get('commit')
        data['schema_version'] = 'ailabs-monarch-experiment-v2'
    data['configuration_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    folder=studio.directory/'setups';folder.mkdir(exist_ok=True)
    write_json(folder/(data['id']+'.json'),data)
    return data
