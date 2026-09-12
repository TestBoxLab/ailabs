"""Offline mission journey through real chat, watcher and harness persistence.

Responses and billing are fixtures. This demonstrates orchestration, not a real
architecture, provider request, benchmark execution, or scientific improvement.
"""
import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from tests.test_genesis_loop import FakeAdapter
from wb_results.evidence import write_json
from wb_studio import genesis_harness as harness
from wb_studio.genesis import Genesis


def test_conversation_watchers_wait_and_evidence_complete_one_mission(tmp_path, monkeypatch):
    FakeAdapter.script, FakeAdapter.made = [], []
    monkeypatch.setattr(harness, 'ADAPTERS', {key:FakeAdapter for key in ('anthropic','openai','openai_responses','gemini')})
    monkeypatch.setattr(harness.providers, 'cost_usd', Mock(return_value=0.01))
    monkeypatch.setattr(harness, 'model_routes', lambda:[{'id':'claude-opus-4-8','available':True}])
    # Chat creates and persists real turns. Execute their harness explicitly so no
    # daemon thread can race the assertions or call a provider after this test.
    monkeypatch.setattr(threading.Thread, 'start', lambda self:None)
    ledger=Mock()
    studio=SimpleNamespace(directory=tmp_path,ledger=ledger,events=lambda identity:[],
        runtime=SimpleNamespace(provider=lambda *args,**kwargs:nullcontext()))
    job_path=tmp_path/'fixture-run'/'job.json'
    studio.jobs=lambda:[json.loads(job_path.read_text())] if job_path.exists() else []
    studio.job=lambda identity:json.loads((tmp_path/identity/'job.json').read_text())
    g=Genesis(studio)
    monkeypatch.setattr(g,'allowance_allows',lambda amount:(True,None))
    monkeypatch.setattr(g.watcher,'refusal',lambda:None)
    monkeypatch.setenv('STUDIO_GENESIS_AUTO_RUNS','0')
    monkeypatch.setenv('STUDIO_GENESIS_AUTO_SOURCES','0')
    g.autonomy.set({'cards':'act'})

    def run(turn, calls, answer):
        FakeAdapter.script=[{'tool_calls':[{'id':f'call-{i}','name':name,'args':args}]} for i,(name,args) in enumerate(calls)] + [{'text':answer}]
        harness.start_turn(g,turn)
        saved=g.read('turns',turn['id'])
        assert saved['status']=='completed', saved.get('events')
        assert not FakeAdapter.script
        return saved

    origin=g.chat({'message':'Investigate Monarch and compare a candidate using stored evidence.',
                   'model':'claude-opus-4-8','effort':'high','by':'human:Lucas','maximum_usd':'10'})
    run(origin,[('start_mission',{'objective':'Compare a candidate with the baseline','acceptance':['Explain the recorded comparison'],
                                'next_action':'Inspect the stored failure evidence'})],'I recorded the mission.')
    card=next(c for c in g.listing('cards') if c.get('mission'))
    identity=card['id']
    assert card['mission']['origin_turn']==origin['id']
    assert card['mission']['status']=='queued'

    first=g.watcher.wake()
    card=g.read('cards',identity)
    run(first,[('checkpoint_mission',{'card':identity,'revision':card['revision'],'summary':'Selected the fixture comparison.',
                                     'status':'continue','next_action':'Wait for the recorded experiment'})], 'The next step is ready.')
    assert g.read('cards',identity)['mission']['status']=='queued'

    # The experiment is a persisted fixture child, not a launched benchmark.
    child=g.card({'title':'Fixture comparison','body':'Recorded baseline and candidate fixture','parent':identity,'stage':'research'})
    child['job']='fixture-run'; write_json(g.path('cards',child['id']),child)
    write_json(job_path,{'id':'fixture-run','title':'Fixture comparison','status':'running','results':[],
                         'settings':{'models':['oracle']}})
    second=g.watcher.wake()
    card=g.read('cards',identity)
    run(second,[('checkpoint_mission',{'card':identity,'revision':card['revision'],'summary':'Waiting for fixture-run.',
                                      'status':'waiting','wait_for':child['id'],'next_action':'Read the finished run and explain the evidence'})], 'Waiting for the comparison.')
    waiting=g.read('cards',identity)
    reservations=ledger.reserve.call_count
    turns=len(g.listing('turns'))
    for _ in range(3):
        assert g.watcher.wake() is None
    assert ledger.reserve.call_count==reservations and len(g.listing('turns'))==turns
    assert g.read('cards',identity)==waiting

    job=json.loads(job_path.read_text()); job['status']='completed'; write_json(job_path,job)
    final=g.watcher.wake()
    assert final['card']==identity
    assert g.watcher.wake() is None  # completion was consumed once; this worker owns the card
    card=g.read('cards',identity)
    saved=run(final,[('read_run',{'run':'fixture-run'}),
                     ('checkpoint_mission',{'card':identity,'revision':card['revision'],'summary':'The fixture has no scored attempts; no winner can be inferred.',
                                            'status':'complete'})], 'The fixture validates orchestration only; it establishes no performance result.')
    assert any(e.get('receipt')=={'ok':True,'run':'fixture-run'} for e in saved['events'])
    completed=g.read('cards',identity)
    assert completed['mission']['status']=='completed' and completed['stage']=='complete'
    assert completed['mission']['turn_count']==3
    assert g.read('cards',child['id'])['parent']==identity
    assert g.watcher.wake() is None
    for worker in (first,second,final):
        assert (worker['by'],worker['thread'],worker['model'],worker['effort'])==('human:Lucas',origin['thread'],'claude-opus-4-8','high')
    assert g.thread(origin['thread'])['turns'][-1]['id']==final['id']
    assert ledger.reserve_run.call_count==4
    assert len(FakeAdapter.made)==4
