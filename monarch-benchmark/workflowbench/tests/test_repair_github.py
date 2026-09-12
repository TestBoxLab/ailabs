"""GitHub credentials stay scoped and repository reads remain tied to a commit."""
import base64
from datetime import datetime, timedelta, timezone
import pytest
from wb_repair import github


@pytest.fixture
def app(monkeypatch):
    calls = []
    app = github.GitHubApp('app-id', '123', '/run/secrets/github.pem')
    monkeypatch.setattr(app, 'jwt', lambda: 'signed-app-jwt')
    def api(path, token, body=None):
        calls.append((path, token, body))
        if path.endswith('/access_tokens'):
            return {'token': 'installation-' + body['repositories'][0],
                    'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        if '/contents/' in path:
            return {'type': 'file', 'encoding': 'base64', 'size': 24, 'sha': 'blob-sha',
                    'content': base64.b64encode(b'Actual source at commit').decode()}
        if '/commits/' in path:
            return {'sha': 'a' * 40}
        return {'default_branch': 'main'}
    monkeypatch.setattr(github, 'api', api)
    return app, calls


def test_installation_tokens_are_repository_scoped_readonly_and_renewed(app):
    client, calls = app
    assert client.token('lab') == client.token('lab') == 'installation-ailabs'
    assert len(calls) == 1
    assert calls[0][2] == {'repositories': ['ailabs'], 'permissions': {'contents': 'read'}}
    assert client.token('monarch') == 'installation-monarch'
    assert calls[1][2]['repositories'] == ['monarch']
    client.tokens['lab'] = ('expired', 0)
    assert client.token('lab') == 'installation-ailabs' and len(calls) == 3
    with pytest.raises(ValueError, match='authorized'):
        client.token('other/private')
    assert len(calls) == 3


def test_head_resolution_and_paged_file_reads_name_exact_commit(app):
    client, calls = app
    head = client.read('lab')
    assert head['commit'] == 'a' * 40 and head['repository'] == 'TestBoxLab/ailabs'
    first = client.read('lab', head['commit'], 'src/main.py', limit=7)
    second = client.read('lab', head['commit'], 'src/main.py', offset=first['next_offset'])
    assert first['text'] + second['text'] == 'Actual source at commit'
    assert second['next_offset'] is None and second['commit'] == head['commit']
    assert calls[-1][0].endswith('/contents/src/main.py?ref=' + head['commit'])
    assert first['url'] == 'https://github.com/TestBoxLab/ailabs/blob/' + head['commit'] + '/src/main.py'
    assert first['audience'] == 'internal'


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'src/../.env', '.env', 'secrets/private.pem', 'a\\b'])
def test_unsafe_or_credential_paths_refuse_before_token_minting(app, path):
    client, calls = app
    with pytest.raises(ValueError):
        client.read('lab', 'a' * 40, path)
    assert calls == []


def test_unpinned_commit_and_binary_files_are_not_read_as_source(app, monkeypatch):
    client, calls = app
    with pytest.raises(ValueError, match='40-character'):
        client.read('lab', 'main', 'src/main.py')
    assert calls == []
    client.tokens['lab'] = ('cached', 10**12)
    monkeypatch.setattr(github, 'api', lambda *args: {'type': 'file', 'encoding': 'base64',
        'size': 4, 'content': base64.b64encode(b'a\x00bc').decode(), 'sha': 'blob'})
    with pytest.raises(ValueError, match='text source'):
        client.read('lab', 'a' * 40, 'image.bin')
