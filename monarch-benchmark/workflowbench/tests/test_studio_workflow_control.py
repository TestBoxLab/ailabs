import json
from decimal import Decimal
from threading import Event
from types import SimpleNamespace
import pytest
from wb_arms.api_loop import ArmResult
from wb_studio.app import LiveArm


def fixture_arm(track,answer):
    records=[];actions=[];seen=[]
    job={'settings':{'track':track,'arms':[{'id':'control','runner':{'provider':'offline','model':'offline','effort':'default'}}]}}
    def execute(name,args):
        actions.append((name,args,len(records)))
        return json.dumps({'value':'aGVsbG8='})
    def brain(gateway,**kwargs):
        seen.append(kwargs)
        if track=='create-and-run':
            blocked=kwargs['execute_tool']('api_fetch',{'method':'POST','url':'/write'})
            assert 'reads only' in blocked
        return ArmResult(final_text=answer,tool_calls=0)
    studio=SimpleNamespace(job=lambda _:job,emit=lambda *a,**k:None,budget=lambda:{},
                           gateway_for=lambda _:SimpleNamespace(describe=lambda:{}),
                           component=lambda identity,role:brain if role=='brain' else lambda ep:execute)
    ep=SimpleNamespace(_observe=lambda *a:None,task={'prompt':[{'content':'System'},{'content':'Task'}]},record_agent_event=records.append)
    return LiveArm(studio,'run','control','task',Event(),Decimal('1')),ep,records,actions,seen


def test_workflow_control_records_artifact_before_executing_actions():
    text=json.dumps({'steps':[{'id':'encode','tool':'base64_encode','arguments':{'text':'hello'},'after':[]}]})
    arm,ep,records,actions,seen=fixture_arm('create-and-run',text)
    result=arm.run(ep)
    assert result.termination=='completed'
    assert records[0]['type']=='workflow_artifact'
    assert actions==[('base64_encode',{'text':'hello'},1)]
    assert result.tool_calls==1
    assert 'Workflow artifact requirement' in seen[0]['system']


def test_workflow_control_cannot_finish_with_prose_instead_of_workflow():
    arm,ep,records,actions,_=fixture_arm('create-and-run','Done, everything is complete.')
    result=arm.run(ep)
    assert result.termination=='agent_error'
    assert actions==[]
    assert not any(r['type']=='workflow_artifact' for r in records)


def test_request_control_keeps_its_original_prompt_and_output():
    arm,ep,records,actions,seen=fixture_arm('agentic-request','Normal response')
    result=arm.run(ep)
    assert result.final_text=='Normal response'
    assert seen[0]['system']=='System'
    assert records==[] and actions==[]
