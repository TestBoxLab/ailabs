"""Read-only task-attempt usage, with conservative model attribution."""
from datetime import datetime
from zoneinfo import ZoneInfo
import math
from wb_studio.execution import load_version

def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def usage_report(studio):
    rows=[]
    for job in studio.jobs():
        arms={a['id']:a for a in job['settings'].get('arms',[])}
        for result in job.get('results',[]):
            arm=arms.get(result['model'],{})
            if arm.get('kind')=='scripted' or result['model'] in ('oracle','sloppy'): continue
            runner=arm.get('runner_override') or arm.get('runner')
            models=set()
            if runner: models.add(runner.get('model','Unattributed'))
            elif arm.get('kind')=='version':
                try:
                    version=load_version(studio,arm['blueprint'],arm['number'])
                    models={n.get('config',{}).get('runner',{}).get('model') for n in version['graph']['nodes'] if n['type']=='agent'}-{None}
                except (OSError,ValueError,KeyError): pass
            elif arm.get('kind') in ('runner','native') or not arm:
                models.add(result['model'].split('@')[0])
            label=next(iter(models)) if len(models)==1 else 'Mixed / unattributed models'
            tokens=result.get('tokens') or {}
            token_known=all(number(tokens.get(k)) for k in ('prompt','output'))
            cost=result.get('cost_usd')
            if not number(cost) or any(f in result.get('flags',[]) for f in ('billing=unknown','cost_missing')): cost=None
            try: day=datetime.fromisoformat(job['created_at']).astimezone(ZoneInfo('America/Sao_Paulo')).date().isoformat()
            except (ValueError,KeyError): day=None
            rows.append({'run':job['id'],'title':job['title'],'day':day,'model':label,'task':result['task'],
                         'tokens':tokens['prompt']+tokens['output'] if token_known else None,
                         'input':tokens.get('prompt') if token_known else None,'output':tokens.get('output') if token_known else None,
                         'cached':tokens.get('cached'),'cost':cost,'passed':result.get('passed'),
                         'attribution':'model' if len(models)==1 else 'mixed'})
    return {'rows':rows,'budget':studio.budget(),'timezone':'America/Sao_Paulo',
            'scope':'Task attempts only. Research and preparation spend is in the weekly ledger, not in these charts. Unknown usage is excluded.'}
