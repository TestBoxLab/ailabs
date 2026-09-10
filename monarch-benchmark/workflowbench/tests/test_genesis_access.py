"""Feature 022, lane B: people, keys, the envelope, and the front door that accepts a key."""
import json

import pytest

from wb_studio.genesis_access import Access


def test_people_keys_and_roles(tmp_path):
    access = Access(tmp_path)
    assert access.may_write(None) == (True, None)  # nobody listed yet: the token alone opens writes
    lucas = access.add('Lucas', 'admin', by='human:studio')
    assert lucas['name'] == 'lucas' and lucas['key'].startswith('ail_')
    assert access.people() == [{k: v for k, v in access._read()['people'][0].items() if k != 'key_hash'}]
    assert 'key_hash' not in json.dumps(access.people())
    assert access.person_for_key(lucas['key']) == {'name': 'lucas', 'role': 'admin'}
    assert access.person_for_key('ail_wrong') is None and access.person_for_key(None) is None
    sam = access.add('sam', 'member')
    ok, why = access.may_write(None)
    assert not ok and 'key' in why
    assert access.may_write(access.person_for_key(sam['key']), admin_only=True)[0] is False
    assert access.may_write(access.person_for_key(lucas['key']), admin_only=True) == (True, None)
    with pytest.raises(ValueError, match='already'):
        access.add('sam')
    assert access.remove('sam') == {'name': 'sam', 'removed': True}
    with pytest.raises(ValueError):
        access.remove('sam')


def test_envelope_and_settings(tmp_path):
    access = Access(tmp_path)
    assert access.settings()['envelope_usd'] == '20.00'
    access.set_settings({'envelope_usd': '12.5', 'brief_hour': 7})
    lines = [{'who': 'Genesis', 'maximum_usd': '2.00', 'actual_usd': None, 'state': 'open'},
             {'who': 'Genesis', 'maximum_usd': '2.00', 'actual_usd': '0.35', 'state': 'closed'},
             {'who': 'lucas', 'maximum_usd': '5.00', 'actual_usd': None, 'state': 'open'}]
    assert access.envelope(lines) == {'envelope_usd': '12.50', 'reserved_usd': '2.00', 'settled_usd': '0.35', 'left_usd': '10.15'}
    with pytest.raises(ValueError):
        access.set_settings({'envelope_usd': '900'})


def test_routes_accept_a_key_and_record_who_wrote(tmp_path, monkeypatch):
    from wb_studio.app import ROOT, Studio
    from wb_world.episode import load_suite
    from tests.test_studio_app import request, server_for
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    studio = Studio(tmp_path / 'studio', tasks=load_suite(ROOT / 'tasks')[:1], gateway_factory=lambda *a, **k: pytest.fail('paid dispatch'))
    with server_for(studio) as port:
        token = {'X-Studio-Token': studio.token, 'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        status, _, body = request(port, 'POST', '/api/genesis/people', json.dumps({'name': 'lucas', 'role': 'admin'}), token)
        assert status == 201; key = json.loads(body)['key']
        status, _, body = request(port, 'GET', '/api/genesis/people')
        assert status == 200 and json.loads(body)['people'][0]['name'] == 'lucas' and 'key' not in body
        # a write without a key is refused once someone is listed; the key opens it and names the person
        status, _, body = request(port, 'POST', '/api/genesis/cards', json.dumps({'title': 'A claim', 'body': 'x', 'stage': 'hypothesis'}), token)
        assert status == 403 and 'key' in json.loads(body)['error']
        with_key = {'X-Person-Key': key, 'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'application/json'}
        status, _, body = request(port, 'POST', '/api/genesis/cards', json.dumps({'title': 'A claim', 'body': 'x', 'stage': 'hypothesis'}), with_key)
        assert status == 201
        entry = studio.genesis.autonomy.tail(1)[0]
        assert entry['kind'] == 'card' and entry['by'] == 'human:lucas'
        status, _, body = request(port, 'GET', '/api/genesis/settings')
        assert status == 200 and json.loads(body)['envelope']['envelope_usd'] == '20.00' and json.loads(body)['channels']['slack_webhook'] is False
        status, _, body = request(port, 'GET', '/api/genesis/digest?week=2026-W37')
        assert status == 200 and json.loads(body)['week'] == '2026-W37'
