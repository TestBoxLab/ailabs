import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from wb_results.evidence import write_json
from wb_studio.genesis import Genesis
from wb_studio import genesis_missions as m

@pytest.fixture
def g(tmp_path,monkeypatch):
    g=Genesis(SimpleNamespace(directory=tmp_path,ledger=Mock(),jobs=Mock(return_value=[]),job=Mock(),cancel=Mock()))
    g.autonomy.set({'cards':'act'}); g.watcher.notify=Mock()
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes',lambda:[{'id':'pinned','available':True}])
    write_json(g.path('turns','origin'),{'id':'origin','by':'human:Lucas','model':'pinned','thread':'thread1','workspace':{},'message':'Improve Monarch','status':'running','events':[]})
    g.context.turn='origin'
    return g

def start(g,**extra):
    return m.start_mission(g,{'objective':'Improve Monarch','acceptance':['Compare evidence'],'next_action':'Inspect failures',**extra})

def worker(g,c):
    p=m.worker_payload(g,g.read('cards',c['id']))
    c=g.read('cards',c['id']); c['work']={'status':'working','turn':'worker'}; write_json(g.path('cards',c['id']),c)
    t=dict(p,id='worker',status='running',events=[]); write_json(g.path('turns','worker'),t); g.context.turn='worker'
    return t

def checkpoint(g,c,**p):
    return m.checkpoint_mission(g,dict(card=c['id'],revision=g.read('cards',c['id'])['revision'],summary='Observed failures',**p))

def test_start_durable_idempotent(g):
    c=start(g); assert start(g)['id']==c['id']
    s=Genesis(g.studio).read('cards',c['id'])
    assert s['work']['status']=='queued'
    assert (s['mission']['owner'],s['mission']['model'],s['mission']['max_turns'])==('human:Lucas','pinned',8)

def test_explicit_continuation_once(g):
    c=start(g); t=worker(g,c); checkpoint(g,c,status='continue',next_action='Build')
    m.ON_TURN(g,dict(t,status='completed')); before=g.read('cards',c['id']); m.ON_TURN(g,dict(t,status='completed'))
    assert g.read('cards',c['id'])==before
    assert before['work']['status']=='queued' and before['mission']['turn_count']==1

def test_plain_answer_blocks(g):
    c=start(g); t=worker(g,c); m.ON_TURN(g,dict(t,status='completed'))
    assert g.read('cards',c['id'])['mission']['status']=='blocked'

def test_stale_and_foreign_checkpoint(g):
    c=start(g); worker(g,c)
    with pytest.raises(ValueError,match='changed'): m.checkpoint_mission(g,dict(card=c['id'],revision=0,summary='x',status='complete'))
    t=g.read('turns','worker'); t['by']='human:Other'; write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='owner'): checkpoint(g,c,status='complete')

def child(g,c):
    x=g.card({'title':'Experiment','body':'candidate','parent':c['id']}); x['job']='run1'; write_json(g.path('cards',x['id']),x)
    return x

def test_stop_cancels_and_survives_late_callback(g):
    c=start(g); t=worker(g,c); child(g,c); g.studio.job.return_value={'status':'running'}; g.context.turn='origin'
    m.control_mission(g,dict(card=c['id'],revision=g.read('cards',c['id'])['revision'],action='stop'))
    m.ON_TURN(g,dict(t,status='completed'))
    assert g.read('cards',c['id'])['mission']['status']=='stopped'; g.studio.cancel.assert_called_once_with('run1')

def test_steering_invalidates_old_worker(g):
    c=start(g); t=worker(g,c); g.context.turn='origin'
    m.control_mission(g,dict(card=c['id'],revision=g.read('cards',c['id'])['revision'],action='steer',instruction='Focus latency'))
    m.ON_TURN(g,dict(t,status='completed')); s=g.read('cards',c['id'])
    assert s['mission']['objective']=='Improve Monarch' and s['mission']['next_action']=='Focus latency'
    assert s['work']['status']=='queued'

def test_wait_wakes_once_without_paid_polling(g):
    c=start(g); t=worker(g,c); x=child(g,c); g.studio.job.return_value={'status':'running'}
    checkpoint(g,c,status='waiting',wait_for=x['id'],next_action='Analyze')
    m.ON_TURN(g,dict(t,status='completed')); m.reconcile(g)
    assert g.read('cards',c['id'])['mission']['status']=='waiting'
    g.studio.job.return_value={'status':'completed'}; m.reconcile(g); before=g.read('cards',c['id']); m.reconcile(g)
    assert g.read('cards',c['id'])==before and before['work']['status']=='queued'

def test_completion_requires_terminal_child_and_successful_evidence(g):
    c=start(g); t=worker(g,c); child(g,c); g.studio.job.return_value={'status':'running'}
    with pytest.raises(ValueError,match='finished'): checkpoint(g,c,status='complete')
    g.studio.job.return_value={'status':'completed'}
    t['events']=[{'type':'tool_started','action':'read_run','payload':json.dumps({'run':'run1'})}]; write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='evidence'): checkpoint(g,c,status='complete')
    t['events'].append({'type':'tool_completed','action':'read_run','detail':json.dumps({'job':{'id':'run1','status':'completed'}})}); write_json(g.path('turns','worker'),t)
    checkpoint(g,c,status='complete'); m.ON_TURN(g,dict(t,status='completed'))
    assert g.read('cards',c['id'])['stage']=='complete'

def test_bound_pause_and_route(g,monkeypatch):
    c=start(g,max_turns=1); t=worker(g,c); checkpoint(g,c,status='continue',next_action='Next'); m.ON_TURN(g,dict(t,status='completed'))
    assert g.read('cards',c['id'])['mission']['status']=='blocked'
    g.context.turn='origin'
    with pytest.raises(ValueError,match='limit'): m.control_mission(g,dict(card=c['id'],revision=g.read('cards',c['id'])['revision'],action='resume'))
    g.autonomy.set({'paused':True})
    with pytest.raises(ValueError,match='paused'): m.worker_payload(g,g.read('cards',c['id']))
    g.autonomy.set({'paused':False}); monkeypatch.setattr('wb_studio.genesis_harness.model_routes',lambda:[])
    with pytest.raises(ValueError,match='model'): m.worker_payload(g,g.read('cards',c['id']))

def test_recovery_blocks_uncertain_worker(g):
    c=start(g); t=worker(g,c); t['status']='failed'; write_json(g.path('turns','worker'),t); m.reconcile(g)
    s=g.read('cards',c['id']); assert s['mission']['status']=='blocked' and s['work']['status']=='failed'
    assert s['mission']['turn_count']==1

def test_wait_for_approval_does_not_queue_more_work(g):
    c=start(g); t=worker(g,c)
    x=g.card({'title':'Await approval','body':'50 tasks','parent':c['id'],'stage':'approval'})
    checkpoint(g,c,status='waiting',wait_for=x['id'],next_action='Analyze approved experiment')
    m.ON_TURN(g,dict(t,status='completed'))
    before=g.read('cards',c['id'])
    for _ in range(3): m.reconcile(g)
    assert g.read('cards',c['id'])==before
    assert before['mission']['status']=='waiting'

@pytest.mark.parametrize('limit',[0,25,True,1.5])
def test_invalid_turn_bounds_refused_without_card(g,limit):
    with pytest.raises(ValueError,match='max_turns'): start(g,max_turns=limit)
    assert g.listing('cards')==[]

def test_maximum_turn_bound_accepted(g):
    assert start(g,max_turns=24)['mission']['max_turns']==24

def test_failed_evidence_does_not_allow_completion(g):
    c=start(g); t=worker(g,c); child(g,c); g.studio.job.return_value={'status':'completed'}
    t['events']=[{'type':'tool_started','action':'read_run','payload':json.dumps({'run':'run1'})},
                 {'type':'tool_completed','action':'read_run','detail':json.dumps({'error':'Unavailable'})}]
    write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='evidence'): checkpoint(g,c,status='complete')
    assert g.read('cards',c['id'])['mission']['status']=='working'

def test_stop_closes_unlaunched_child_before_late_review(g):
    c=start(g)
    x=g.card({'title':'Await reviewer','body':'candidate','parent':c['id'],'stage':'approval'})
    m.trusted_control(g,c,'stop')
    after=g.read('cards',x['id'])
    assert after['stage']=='complete' and after['work']['status']=='stopped' and not after['auto']

def test_worker_pins_effort_and_bounded_brief(g):
    t=g.read('turns','origin'); t.update(effort='high',message='Long user request '*800); write_json(g.path('turns','origin'),t)
    c=start(g,acceptance=['a'*1000]*12)
    p=m.worker_payload(g,c)
    assert p['effort']=='high' and len(p['message'])<16000
    assert c['kind']=='mission'

def test_uncommitted_build_cannot_continue(g):
    c=start(g); t=worker(g,c)
    t['events']=[{'type':'tool_completed','action':'edit_architecture','detail':json.dumps({'operation':{'operation':'add_node'},'saved':False})}]
    write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='save_architecture'): checkpoint(g,c,status='continue',next_action='Evaluate')
    t['events'].append({'type':'tool_completed','action':'save_architecture','detail':json.dumps({'id':'candidate','revision':1})})
    write_json(g.path('turns','worker'),t)
    assert checkpoint(g,c,status='continue',next_action='Evaluate')['mission']['checkpoint']=='continue'

def test_status_scoped_to_originating_conversation(g):
    start(g)
    t=g.read('turns','origin'); t['thread']='other-thread'; write_json(g.path('turns','origin'),t)
    assert m.mission_status(g,{})=={'missions':[]}

def test_start_reports_disabled_cards(g):
    g.autonomy.set({'cards':'off'})
    c=start(g)
    assert 'Cards dial' in c['work']['reason']


def test_unsaved_edit_after_save_still_blocks(g):
    c=start(g); t=worker(g,c)
    t['events']=[{'type':'tool_completed','action':'save_architecture','detail':json.dumps({'id':'candidate','revision':1})},
                 {'type':'tool_completed','action':'edit_architecture','detail':json.dumps({'operation':{'operation':'set_prompt'},'saved':False})}]
    write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='save_architecture'): checkpoint(g,c,status='complete')


def test_other_child_cannot_be_wait_target(g):
    c=start(g); worker(g,c); x=g.card({'title':'Unrelated','body':'Other experiment'})
    with pytest.raises(ValueError,match='belonging'): checkpoint(g,c,status='waiting',wait_for=x['id'],next_action='Analyze')
    assert g.read('cards',c['id'])['mission'].get('wait_for') is None

def test_compact_success_receipt_allows_large_run_evidence(g):
    c=start(g); t=worker(g,c); child(g,c); g.studio.job.return_value={'status':'completed'}
    t['events']=[{'type':'tool_started','action':'read_run','payload':json.dumps({'run':'run1'})},
                 {'type':'tool_completed','action':'read_run','detail':'{"job":'+'x'*6000,
                  'receipt':{'ok':True,'run':'run1'}}]
    write_json(g.path('turns','worker'),t)
    assert checkpoint(g,c,status='complete')['mission']['checkpoint']=='complete'


def test_compact_success_receipt_preserves_large_saved_build(g):
    c=start(g); t=worker(g,c)
    t['events']=[{'type':'tool_completed','action':'edit_architecture','detail':'x'*6000,'receipt':{'ok':True,'provisional':True}},
                 {'type':'tool_completed','action':'save_architecture','detail':'x'*6000,'receipt':{'ok':True,'architecture':'candidate','revision':3}}]
    write_json(g.path('turns','worker'),t)
    assert checkpoint(g,c,status='continue',next_action='Evaluate')['mission']['checkpoint']=='continue'
    t['events'].append({'type':'tool_completed','action':'edit_architecture','detail':'x'*6000,'receipt':{'ok':True,'provisional':True}})
    write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='save_architecture'): checkpoint(g,c,status='complete')

@pytest.mark.parametrize('receipt',[{'ok':False,'run':'run1'},{'ok':True,'run':'another-run'}])
def test_failed_or_wrong_run_receipt_denies_completion(g,receipt):
    c=start(g); t=worker(g,c); child(g,c); g.studio.job.return_value={'status':'completed'}
    t['events']=[{'type':'tool_started','action':'read_run','payload':json.dumps({'run':'run1'})},
                 {'type':'tool_completed','action':'read_run','detail':'x'*6000,'receipt':receipt}]
    write_json(g.path('turns','worker'),t)
    with pytest.raises(ValueError,match='evidence'): checkpoint(g,c,status='complete')

def test_stop_cancels_child_worker_and_review_despite_missing_job(g):
    c=start(g); x=child(g,c)
    x.update(work={'status':'working','turn':'debrief-turn'},review={'status':'working','turn':'review-turn'})
    write_json(g.path('cards',x['id']),x)
    y=g.card({'title':'Second experiment','body':'candidate','parent':c['id']}); y['job']='run2'; write_json(g.path('cards',y['id']),y)
    g.studio.job.side_effect=lambda identity: (_ for _ in ()).throw(FileNotFoundError()) if identity=='run1' else {'status':'running'}
    g.stop_turn=Mock(side_effect=lambda identity: (_ for _ in ()).throw(FileNotFoundError()) if identity=='debrief-turn' else {})
    m.trusted_control(g,c,'stop')
    assert g.read('cards',c['id'])['mission']['status']=='stopped'
    assert {call.args[0] for call in g.stop_turn.call_args_list}=={'debrief-turn','review-turn'}
    g.studio.cancel.assert_called_once_with('run2')
    assert g.read('cards',y['id'])['work']['status']=='stopped'
    assert any(row['kind']=='mission-cancel-error' for row in g.autonomy.tail())
