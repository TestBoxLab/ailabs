"""Read-only task-attempt usage, with conservative model attribution."""
from datetime import datetime
from zoneinfo import ZoneInfo
import math
from wb_studio.execution import load_version

def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def ledger_lines(studio, now=None):
    """The week's ledger as a person audits it: one line per run envelope or standalone
    request, newest first, with who asked, what for, the ceiling and what settled."""
    ledger=studio.ledger; status=ledger.status(now=now); week=status.week_start
    titles={j['id']:j['title'] for j in studio.jobs()}
    children={}
    for r in ledger.reservations(): children.setdefault(r.scope_id,[]).append(r)
    def purpose(meta, scope):
        if scope in titles: return titles[scope]
        return meta.get('purpose') or meta.get('harness') or meta.get('source') or scope
    def who(meta, scope):
        if meta.get('operator'): return meta['operator']
        by=str(meta.get('by') or '')
        if by=='person': return 'Studio user'
        if by.startswith('human:'): return by.split(':',1)[1] or 'Studio user'
        if by=='genesis' or scope.startswith('genesis-') or str(meta.get('purpose','')).startswith('Genesis'): return 'Genesis'
        return 'Studio'
    def allowance(meta, scope):
        """Which weekly allowance this line draws on.

        Separate from `who`, which names the requester for a reader. A person's
        Genesis turn is shown as theirs and still spends Genesis's research
        allowance; deciding the second from the first hid every such turn from the
        gate meant to bound it (feature 024, FR-005).
        """
        if scope.startswith('genesis-') or str(meta.get('purpose') or '').startswith('Genesis') or str(meta.get('by') or '')=='genesis':
            return 'genesis'
        if purpose(meta, scope)=='post-run-analysis': return 'analysis'
        return 'rounds'
    lines=[]
    for env in ledger.run_reservations():
        if env.week_start!=week: continue
        meta=env.metadata; kids=children.pop(env.scope_id,[])
        settled=[k for k in kids if k.actual_microusd is not None]
        lines.append({'kind':'run','id':env.scope_id,'what':purpose(meta,env.scope_id),'who':who(meta,env.scope_id),
                      'allowance':allowance(meta,env.scope_id),
                      'created_at':env.created_at,'closed_at':env.closed_at,'maximum_usd':_cents(env.maximum_usd),
                      'actual_usd':_cents(_usd_sum(settled)) if settled else None,'requests':len(kids),'settled':len(settled),
                      'state':'closed' if env.closed_at else 'open','run':env.scope_id if env.scope_id in titles else None})
    for scope,kids in children.items():
        for r in kids:
            if r.week_start!=week: continue
            meta=r.metadata
            lines.append({'kind':'request','id':r.reservation_id,'what':purpose(meta,scope),'who':who(meta,scope),
                          'allowance':allowance(meta,scope),
                          'created_at':r.created_at,'closed_at':r.settled_at,'maximum_usd':_cents(r.maximum_usd),
                          'actual_usd':None if r.actual_usd is None else _cents(r.actual_usd),'requests':1,'settled':int(r.actual_usd is not None),
                          # A hold a person released holds nothing; reading it as Reserved for
                          # ever is what `wb budget release` exists to end (feature 024 US4).
                          'state':'settled' if r.settled_at else 'released' if meta.get('hold_released') else 'open','run':None})
    lines.sort(key=lambda l:l['created_at'],reverse=True)
    return {'week_start':week,'lines':lines,'budget':studio.budget()}

def _cents(value):
    return f'{value:.2f}'

def _usd_sum(rows):
    from decimal import Decimal
    return sum((r.actual_usd for r in rows),Decimal('0'))

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
