"""Versioned node architectures: editable drafts and immutable published definitions."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import math
import re
import uuid
from wb_arms import runtime_manifest as rm
from wb_results.evidence import write_json
from wb_studio.architectures import default_status, pinned
from wb_studio.runners import runner_config
from wb_studio.runtime_registry import blueprint_readiness, resolve_api_control

KINDS={'input','monarch','product-graph','agent','merge','workflow','output'}
MODES=('act','advise')
ID=re.compile(r'^[a-zA-Z0-9_-]{1,80}$')
FIELD_PATH=re.compile(r'[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*')

def node_problems(n,strict=True):
    """Every problem with one node, in the order a person would fix them."""
    found=[]
    if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not ID.fullmatch(n['id']):return [{'node':None,'message':'Node IDs must be unique'}]
    if not isinstance(n.get('type'),str) or n.get('type') not in KINDS:found.append('Unknown node type')
    if not isinstance(n.get('label'),str) or not 1<=len(n['label'])<=100:found.append('Every node needs a short name')
    for axis in ('x','y'):
        if type(n.get(axis)) not in (int,float) or not math.isfinite(n[axis]) or not 0<=n[axis]<=10000:found.append('Node positions must stay inside the canvas');break
    c=n.get('config',{})
    if not isinstance(c,dict) or len(json.dumps(c))>40000:return [{'node':n['id'],'message':m} for m in found+['Invalid node configuration']]
    if strict and isinstance(n.get('type'),str) and n.get('type') in KINDS:
        if n['type'] in ('agent','monarch'):
            try:runner_config(c.get('runner'))
            except ValueError as exc:found.append(str(exc))
            else:
                if n['type']=='agent' and c['runner']['provider'] not in ('claude-code','codex') and resolve_api_control(c['runner']) is None:found.append('Choose a rate-carded API control for this step (its provider and model must have a rate card in config/models)')
        if n['type']=='product-graph' and (not isinstance(c.get('graph'),str) or not ID.fullmatch(c['graph']) or type(c.get('version')) is not int or c['version']<1):found.append('Choose a prepared product graph version')
        if n['type']=='agent' and c.get('mode','act') not in MODES:found.append('Agent mode must be act or advise')
        if n['type']=='agent' and 'max_turns' in c and (type(c['max_turns']) is not int or not 1<=c['max_turns']<=50):found.append('Turn limit must be between 1 and 50')
        if n['type']=='agent' and (not isinstance(c.get('instructions',''),str) or not c.get('instructions','').strip()):found.append('Add instructions')
    return [{'node':n['id'],'message':m} for m in found]

def problems(graph,strict=True):
    """All problems of a graph: per node, then connections, then flow. Empty means publishable."""
    if not isinstance(graph,dict):return [{'node':None,'message':'Architecture must contain a node graph'}]
    nodes,edges=graph.get('nodes'),graph.get('edges')
    if not isinstance(nodes,list) or not 1<=len(nodes)<=80 or not isinstance(edges,list) or len(edges)>240:return [{'node':None,'message':'Use 1-80 nodes and at most 240 connections'}]
    found=[];ids=set()
    for n in nodes:
        found+=node_problems(n,strict)
        if isinstance(n,dict) and isinstance(n.get('id'),str):
            if n['id'] in ids:found.append({'node':n['id'],'message':'Node IDs must be unique'})
            ids.add(n['id'])
    if any(p['node'] is None for p in found):return found
    by_id={n['id']:n for n in nodes}
    outgoing={i:[] for i in ids};incoming={i:[] for i in ids};pairs=set()
    for e in edges:
        if not isinstance(e,dict) or not isinstance(e.get('from'),str) or not isinstance(e.get('to'),str) or e.get('from') not in ids or e.get('to') not in ids or e['from']==e['to']:found.append({'node':None,'message':'Connections must join two existing nodes'});continue
        if by_id[e['to']]['type']=='product-graph':found.append({'node':e['to'],'message':'Product graphs provide knowledge and cannot receive connections'})
        if by_id[e['from']]['type']=='product-graph' and by_id[e['to']]['type']!='agent':found.append({'node':e['from'],'message':'Connect product knowledge only to agents'})
        pair=(e['from'],e['to'])
        if pair in pairs:found.append({'node':e['to'],'message':'Duplicate connection'});continue
        pairs.add(pair);outgoing[e['from']].append(e['to']);incoming[e['to']].append(e['from'])
    degree={i:len(incoming[i]) for i in ids};ready=sorted(i for i in ids if not degree[i]);order=[]
    while ready:
        i=ready.pop(0);order.append(i)
        for target in outgoing[i]:
            degree[target]-=1
            if not degree[target]:ready.append(target)
    if len(order)!=len(ids):found.append({'node':None,'message':'This version supports forward flows. Remove the circular connection.'})
    if strict and not found:
        by_id={n['id']:n for n in nodes}
        starts=[i for i in ids if by_id[i]['type']=='input'];ends=[i for i in ids if by_id[i]['type']=='output']
        if len(starts)!=1 or len(ends)!=1:found.append({'node':None,'message':'Use one task input and one result output'})
        elif incoming[starts[0]] or outgoing[ends[0]]:found.append({'node':starts[0] if incoming[starts[0]] else ends[0],'message':'The input starts the flow and the output ends it'})
        else:
            def visit(root,links):
                reached={root};todo=[root]
                while todo:
                    for target in links[todo.pop()]:
                        if target not in reached:reached.add(target);todo.append(target)
                return reached
            forward=visit(starts[0],outgoing);backward=visit(ends[0],incoming)
            for i in sorted(ids):
                if (i not in forward and by_id[i]['type']!='product-graph') or i not in backward:found.append({'node':i,'message':'Connect this node between the task input and the result output'})
    return found

def validate_graph(graph,strict=True):
    """Raise the first problem; return the execution order."""
    found=problems(graph,strict)
    if found:
        first=found[0];label=None
        if first['node'] and isinstance(graph,dict):
            label=next((n.get('label') for n in graph.get('nodes',[]) if isinstance(n,dict) and n.get('id')==first['node']),None)
        raise ValueError((label+': ' if label and first['message'][0].isupper() and not first['message'].startswith(label) else '')+first['message'])
    ids=[n['id'] for n in graph['nodes']];incoming={i:[] for i in ids};outgoing={i:[] for i in ids}
    for e in graph['edges']:outgoing[e['from']].append(e['to']);incoming[e['to']].append(e['from'])
    degree={i:len(incoming[i]) for i in ids};ready=sorted(i for i in ids if not degree[i]);order=[]
    while ready:
        i=ready.pop(0);order.append(i)
        for target in outgoing[i]:
            degree[target]-=1
            if not degree[target]:ready.append(target)
    return order

def paths(studio,identity):
    if not isinstance(identity,str) or not ID.fullmatch(identity):raise ValueError('Invalid architecture ID')
    return studio.directory/'blueprints'/identity

def listing(studio):
    root=studio.directory/'blueprints';items=[]
    for folder in sorted(root.glob('*')):
        draft=folder/'draft.json'
        if draft.exists():
            record=json.loads(draft.read_text(encoding='utf-8'))
            record['versions']=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('v????.json'))]
            items.append(record)
    return items

def save_draft(studio,payload):
    identity=payload.get('id') or uuid.uuid4().hex
    folder=paths(studio,identity)
    name=payload.get('name','')
    if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Name your architecture in up to 100 characters')
    if name.strip().casefold()=='default monarch enterprise':raise ValueError('Give your variation its own name; the default baseline stays unchanged')
    track=payload.get('track','agentic-request')
    if track not in ('agentic-request','create-and-run'):raise ValueError('Choose agentic requests or workflow building')
    validate_graph(payload.get('graph'),strict=False)
    if len(json.dumps(payload))>120000:raise ValueError('Architecture definition is too large')
    with studio.lock:
        file=folder/'draft.json';old=json.loads(file.read_text(encoding='utf-8')) if file.exists() else None
        revision=old['revision'] if old else 0
        if payload.get('revision',0)!=revision:raise ValueError('This draft changed in another editor. Reload it before saving.')
        data={'id':identity,'track':track,'name':name.strip(),'graph':deepcopy(payload['graph']),'revision':revision+1,'status':'draft',
              'updated_at':datetime.now(timezone.utc).isoformat(),'notes':str(payload.get('notes',''))[:2000]}
        folder.mkdir(parents=True,exist_ok=True);write_json(file,data)
    return data

def publish(studio,payload):
    folder=paths(studio,payload.get('id'))
    with studio.lock:
        draft=json.loads((folder/'draft.json').read_text(encoding='utf-8'))
        if payload.get('revision')!=draft['revision']:raise ValueError('Save your latest edits before publishing')
        order=validate_graph(draft['graph'])
        if any(n['type']=='monarch' for n in draft['graph']['nodes']):
            raise ValueError('Monarch Enterprise is a separate reference implementation. Remove the legacy Monarch node and configure the reference under Runtime.')
        if any(n['type']=='workflow' for n in draft['graph']['nodes']):
            raise ValueError('Remove the legacy Run workflow node. Workflow architectures deliver their workflow through Result Output; the benchmark executes it.')
        previous=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('v????.json'))]
        if previous and previous[-1]['draft_revision']==draft['revision']:return previous[-1]
        baseline=pinned(default_status(studio,refresh=True)) if any(n['type']=='monarch' for n in draft['graph']['nodes']) else None
        graph=deepcopy(draft['graph'])
        for n in graph['nodes']:
            if n['type']=='monarch':n['config']['baseline']=baseline
        fingerprint=hashlib.sha256(json.dumps(graph,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        version={'id':draft['id'],'track':draft.get('track','agentic-request'),'name':draft['name'],'version':len(previous)+1,'draft_revision':draft['revision'],
                 'graph':graph,'sha256':fingerprint,'order':order,'notes':draft['notes'],
                 'published_at':datetime.now(timezone.utc).isoformat(),'parent_version':previous[-1]['version'] if previous else None}
        state=blueprint_readiness(studio,version)
        version['readiness']=state['readiness'];version['capabilities']=state['capabilities']
        version['execution_status']=state['readiness']['runtime'];version['execution_note']=' '.join(state['readiness']['reasons'])
        version['runtime_manifest']=version_manifest(version,baseline)
        if previous:version['diff']=diff_versions(previous[-1],version)
        write_json(folder/f'v{version["version"]:04d}.json',version)
    return version

def version_manifest(version,baseline):
    """Executable identity of a published definition: graph, prompts, runners and the pinned baseline."""
    nodes=version['graph']['nodes']
    prompts={n['id']:n['config'].get('instructions','') for n in nodes if n['type']=='agent'}
    runners=[{'node':n['id'],'type':n['type'],'runner':n['config'].get('runner')} for n in nodes if n['config'].get('runner')]
    graphs={n['id']:{'graph':n['config'].get('graph'),'version':n['config'].get('version')} for n in nodes if n['type']=='product-graph'}
    artifacts={'graph':{'status':'present','sha256':version['sha256']},'prompts':{'status':'present','sha256':rm.sha256_json(prompts)}}
    if graphs:artifacts['product_graphs']={'status':'present','sha256':rm.sha256_json(graphs),'versions':graphs}
    source={'kind':'local','repository':None,'directory':f"blueprints/{version['id']}/v{version['version']:04d}",'commit':None,'patch_sha256':None,'lockfile':None,'image_digest':None}
    if baseline:
        artifacts['enterprise_baseline']={'status':'present','sha256':rm.sha256_json(baseline)}
        if baseline.get('repository') and baseline.get('commit'):
            source={**source,'kind':'git','repository':baseline['repository'],'directory':baseline['directory'],'commit':baseline['commit'],'lockfile':baseline.get('lockfile')}
    return rm.build('blueprint',source=source,
        runtime={'entrypoint':'wb_studio.execution.ArchitectureArm','dependency_closure':[],'nodes':[{'id':n['id'],'type':n['type']} for n in nodes],'order':version['order']},
        evaluation={'track':version.get('track','agentic-request'),'provider':None,'model':None,'effort':'default','harness':'studio-node-runtime','harness_version':None,'settings':{'runners':runners}},
        artifacts=artifacts,readiness_record=version['readiness'],
        parent=f"v{version['parent_version']}" if version.get('parent_version') else None,
        notes=f"{version['name']} v{version['version']}: published definition; execution binds to this version hash, never to the draft.")

def _scalar(value):
    text=json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value
    return text if len(text)<=160 else text[:157]+'…'

def diff_versions(before,after):
    """A readable node-level diff between two versions of the same architecture."""
    a={n['id']:n for n in before['graph']['nodes']};b={n['id']:n for n in after['graph']['nodes']}
    added=[{'id':i,'label':b[i]['label'],'type':b[i]['type']} for i in b if i not in a]
    removed=[{'id':i,'label':a[i]['label'],'type':a[i]['type']} for i in a if i not in b]
    changed=[]
    for i in b:
        if i not in a:continue
        fields=[]
        for key in ('label','type'):
            if a[i].get(key)!=b[i].get(key):fields.append({'field':key,'before':_scalar(a[i].get(key)),'after':_scalar(b[i].get(key))})
        ca,cb=a[i].get('config',{}),b[i].get('config',{})
        for key in sorted(set(ca)|set(cb)):
            if key=='baseline':
                if (ca.get(key) or {}).get('commit')!=(cb.get(key) or {}).get('commit'):fields.append({'field':'baseline commit','before':_scalar((ca.get(key) or {}).get('commit')),'after':_scalar((cb.get(key) or {}).get('commit'))})
                continue
            if ca.get(key)!=cb.get(key):fields.append({'field':key,'before':_scalar(ca.get(key)),'after':_scalar(cb.get(key))})
        if fields:changed.append({'id':i,'label':b[i]['label'],'fields':fields})
    ea={(e['from'],e['to']) for e in before['graph']['edges']};eb={(e['from'],e['to']) for e in after['graph']['edges']}
    name=lambda i:(b.get(i) or a.get(i) or {}).get('label',i)
    return {'from':before['version'],'to':after['version'],'added':added,'removed':removed,'changed':changed,
            'edges_added':[{'from':name(x),'to':name(y)} for x,y in sorted(eb-ea)],'edges_removed':[{'from':name(x),'to':name(y)} for x,y in sorted(ea-eb)],
            'moved_only':[b[i]['label'] for i in b if i in a and (a[i].get('x'),a[i].get('y'))!=(b[i].get('x'),b[i].get('y')) and not any(c['id']==i for c in changed)],
            'identical':before['sha256']==after['sha256']}
