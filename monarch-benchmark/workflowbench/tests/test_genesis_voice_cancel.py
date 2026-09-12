"""Interrupting voice work prevents late model tool calls from running."""
from unittest.mock import Mock
from tests.test_genesis_loop import genesis, FakeAdapter, turn_record, harness

def test_stop_while_model_is_replying_prevents_returned_actions(genesis, monkeypatch):
    original = FakeAdapter.turn
    def stopped_response(adapter, *args, **kwargs):
        result = original(adapter, *args, **kwargs)
        genesis.stop_turn('t1')
        return result
    monkeypatch.setattr(FakeAdapter, 'turn', stopped_response)
    tool = Mock(return_value={'ok':True})
    monkeypatch.setattr(genesis, 'tool', tool)
    FakeAdapter.script = [{'tool_calls':[{'id':'c1','name':'save_research','args':{'title':'Late write'}}]}]
    harness.start_turn(genesis, turn_record(genesis))
    tool.assert_not_called()
    assert genesis.read('turns','t1')['status']=='failed'

def test_stop_in_first_action_prevents_second_action_in_same_response(genesis, monkeypatch):
    def stop_after_one(*args, **kwargs):
        genesis.stop_turn('t1')
        return {'ok':True}
    tool = Mock(side_effect=stop_after_one)
    monkeypatch.setattr(genesis, 'tool', tool)
    FakeAdapter.script = [{'tool_calls':[
        {'id':'c1','name':'save_research','args':{'title':'First'}},
        {'id':'c2','name':'save_research','args':{'title':'Second'}}]}]
    harness.start_turn(genesis, turn_record(genesis))
    assert tool.call_count == 1
    assert tool.call_args.args[1] == {'title':'First'}


def test_stop_before_worker_registration_survives_worker_start(genesis):
    turn = turn_record(genesis)
    genesis.stop_turn('t1')
    FakeAdapter.script = [{'text':'must not be requested'}]
    harness.start_turn(genesis, turn)
    assert FakeAdapter.script == [{'text':'must not be requested'}]
    assert genesis.read('turns','t1')['status'] == 'failed'
    genesis.studio.ledger.reserve.assert_not_called()


def test_voice_turn_retains_structured_facts_before_tool_detail_is_truncated(genesis, monkeypatch):
    from wb_results.evidence import write_json
    from wb_studio.measures import run_measures
    from wb_studio.genesis_voice import receipt_speech
    job = {'id':'run-1','status':'completed','settings':{'models':['candidate']},'results':[
        {'task':'a','model':'candidate','passed':True,'termination':'completed'},
        {'task':'b','model':'candidate','passed':False,'termination':'completed'}]}
    result = {'padding':'x' * 20000,'run':'run-1','status':'completed','measures':run_measures(job,[])}
    monkeypatch.setattr(genesis,'tool',Mock(return_value=result))
    FakeAdapter.script = [{'tool_calls':[{'id':'c1','name':'measures','args':{'run':'run-1'}}]},
                          {'text':'The comparison is recorded.'}]
    turn = turn_record(genesis)
    turn['input_mode']='voice'
    write_json(genesis.path('turns','t1'),turn)
    harness.start_turn(genesis,turn)
    saved=genesis.read('turns','t1')
    event=next(e for e in saved['events'] if e['type']=='tool_completed')
    assert len(event['detail']) < 10000
    assert '1 of 2 evaluated attempts' in ' '.join(event['voice_facts'])
    assert '1 of 2 evaluated attempts' in ' '.join(receipt_speech(saved))
    assert saved['status']=='completed'
