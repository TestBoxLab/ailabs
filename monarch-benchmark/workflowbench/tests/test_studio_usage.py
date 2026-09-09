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
