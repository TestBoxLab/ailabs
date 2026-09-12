"""Voice routes use the same person gate as lab changes, before provider access."""
import json
from unittest.mock import Mock
import pytest
from tests.test_studio_app import request, server_for
from wb_studio.app import ROOT, Studio
from wb_world.episode import load_suite

@pytest.fixture
def studio(tmp_path):
    s = Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1],
               gateway_factory=lambda *a, **k: pytest.fail('paid dispatch'))
    s.voice = Mock()
    s.voice.start.return_value = {'id': 'voice1', 'model': 'gpt-live-1'}
    s.voice.status.return_value = {'id': 'voice1', 'status': 'active'}
    s.voice.context.return_value = {'id': 'voice1'}
    s.voice.close.return_value = {'id': 'voice1', 'status': 'closing'}
    return s

def test_session_start_uses_authenticated_person_not_payload_name(studio):
    key = studio.genesis.access.add('Lucas', 'admin')['key']
    with server_for(studio) as port:
        headers = {'Content-Type':'application/json','X-Person-Key':key}
        status, _, body = request(port,'POST','/api/genesis/voice/sessions',
            json.dumps({'sdp':'offer','by':'human:someone-else'}),headers)
    assert status == 201, body
    assert studio.voice.start.call_args.args[1] == 'human:lucas'

def test_session_reads_and_writes_require_person_key_once_people_exist(studio):
    studio.genesis.access.add('Lucas','admin')
    with server_for(studio) as port:
        for method, path in [('POST','/api/genesis/voice/sessions'),
            ('GET','/api/genesis/voice/sessions/voice1'),
            ('POST','/api/genesis/voice/sessions/voice1/close')]:
            status, _, _ = request(port,method,path,'{}' if method=='POST' else None,
                {'Content-Type':'application/json','X-Studio-Token':studio.token})
            assert status == 403
    studio.voice.start.assert_not_called()
    studio.voice.close.assert_not_called()
    studio.voice.status.assert_not_called()

def test_session_context_and_close_are_bound_to_caller(studio):
    key = studio.genesis.access.add('Lucas','admin')['key']
    with server_for(studio) as port:
        headers={'Content-Type':'application/json','X-Person-Key':key}
        status, _, _=request(port,'POST','/api/genesis/voice/sessions/voice1/context',
            json.dumps({'workspace':{'route':'#budget'}}),headers)
        assert status==200
        status, _, _=request(port,'POST','/api/genesis/voice/sessions/voice1/close','{}',headers)
        assert status==200
    assert studio.voice.context.call_args.args == ('voice1', {'workspace':{'route':'#budget'},'by':'human:lucas'}, 'human:lucas')
    studio.voice.close.assert_called_once_with('voice1','human:lucas')

def test_dictation_cannot_bypass_the_person_gate(studio,monkeypatch):
    studio.genesis.access.add('Lucas','admin')
    transcribe=Mock(side_effect=AssertionError('must not call provider'))
    monkeypatch.setattr('wb_studio.voice_stt.transcribe',transcribe)
    with server_for(studio) as port:
        status, _, _=request(port,'POST','/api/voice/stt','audio',
            {'Content-Type':'audio/webm','X-Studio-Token':studio.token,'X-Clip-Seconds':'1'})
    assert status==403
    transcribe.assert_not_called()


def test_detach_preserves_work_and_requires_authenticated_caller(studio):
    key = studio.genesis.access.add('Lucas', 'admin')['key']
    with server_for(studio) as port:
        status, _, _ = request(port, 'POST', '/api/genesis/voice/sessions/voice1/detach', '{}',
                               {'Content-Type': 'application/json', 'X-Studio-Token': studio.token})
        assert status == 403
        studio.voice.close.assert_not_called()
        status, _, _ = request(port, 'POST', '/api/genesis/voice/sessions/voice1/detach', '{}',
                               {'Content-Type': 'application/json', 'X-Person-Key': key})
        assert status == 200
    studio.voice.close.assert_called_once_with('voice1', 'human:lucas', reason='page_detached')
