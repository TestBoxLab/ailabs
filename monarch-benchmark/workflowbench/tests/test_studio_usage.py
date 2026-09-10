from types import SimpleNamespace
from wb_studio.usage import usage_report

def report(result,arm=None):
    job={'id':'run','title':'Comparison','created_at':'2026-09-08T01:00:00+00:00','settings':{'arms':[arm] if arm else []},'results':[result]}
    return usage_report(SimpleNamespace(jobs=lambda:[job],budget=lambda:{'available':'5'}))

def test_tokens_count_cached_input_once_and_use_sao_paulo_day():
    result={'model':'claude-opus-5@high','task':'task','tokens':{'prompt':100,'cached':60,'output':20},'cost_usd':.4}
    row=report(result)['rows'][0]
    assert row['tokens']==120 and row['input']==100 and row['output']==20
    assert row['model']=='claude-opus-5' and row['day']=='2026-09-07'
    assert row['cost']==.4

def test_missing_usage_and_unknown_billing_are_not_zero():
    row=report({'model':'m','task':'t','cost_usd':0,'flags':['billing=unknown']})['rows'][0]
    assert row['tokens'] is None and row['cost'] is None

def test_comparison_uses_bound_model_instead_of_architecture_name():
    row=report({'model':'architecture--model','task':'t','tokens':{'prompt':0,'output':0},'cost_usd':0}, {'id':'architecture--model','kind':'version','runner_override':{'model':'gpt-5.6-sol','effort':'high'}})['rows'][0]
    assert row['model']=='gpt-5.6-sol' and row['tokens']==0 and row['cost']==0

def test_unattributed_enterprise_usage_does_not_invent_a_model():
    row=report({'model':'enterprise','task':'t','cost_usd':1},{'id':'enterprise','kind':'enterprise'})['rows'][0]
    assert row['model']=='Mixed / unattributed models' and row['attribution']=='mixed'


def test_ledger_lines_read_the_week_as_a_person_audits_it(tmp_path):
    from datetime import datetime, timezone
    from wb_orchestrator.budget import BudgetLedger
    from wb_studio.usage import ledger_lines
    now=datetime(2026,9,9,12,tzinfo=timezone.utc)
    ledger=BudgetLedger(tmp_path/'budget.sqlite3')
    ledger.reserve_run('run-1','2.00',now=now,metadata={'source':'studio','operator':'lucas'})
    ledger.reserve('req-1','0.50',scope_id='run-1',now=now,metadata={})
    ledger.settle('req-1','0.10',now=now)
    ledger.reserve('genesis-x','0.25',scope_id='genesis',now=now,metadata={'purpose':'Genesis','model':'m'})
    studio=SimpleNamespace(ledger=ledger,jobs=lambda:[{'id':'run-1','title':'Two tasks'}],budget=lambda:{'available':'297.65'})
    out=ledger_lines(studio,now=now)
    assert out['week_start']=='2026-09-07'
    run=next(l for l in out['lines'] if l['kind']=='run')
    assert run['what']=='Two tasks' and run['who']=='lucas' and run['maximum_usd']=='2.00' and run['actual_usd']=='0.10' and run['requests']==1 and run['state']=='open' and run['run']=='run-1'
    req=next(l for l in out['lines'] if l['kind']=='request')
    assert req['what']=='Genesis' and req['who']=='Genesis' and req['actual_usd'] is None and req['state']=='open'
