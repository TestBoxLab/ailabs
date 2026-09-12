"""Scoped GitHub App reads. Secrets never enter job payloads or model results."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from . import REPOSITORIES


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def api(path, token, body=None):
    request = Request('https://api.github.com' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'AILabs-Genesis-Recovery',
                 'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('GitHub response is too large; use a narrower path.')
            return json.loads(raw)
    except HTTPError as exc:
        raise ValueError('GitHub refused the request (HTTP ' + str(exc.code) + ').') from None
    except (URLError, TimeoutError):
        raise ValueError('GitHub is unavailable; repository state is unknown.') from None


def _encoded(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


class GitHubApp:
    def __init__(self, issuer, installation, key_file):
        self.issuer, self.installation, self.key_file = issuer, installation, key_file
        self.tokens = {}
        self.lock = threading.Lock()

    @classmethod
    def environment(cls):
        return cls(os.environ.get('GENESIS_GITHUB_APP_ID'),
                   os.environ.get('GENESIS_GITHUB_INSTALLATION_ID'),
                   os.environ.get('GENESIS_GITHUB_PRIVATE_KEY_FILE'))

    def jwt(self):
        if not self.issuer or not re.fullmatch(r'[0-9]+', str(self.installation or '')) or not self.key_file:
            raise ValueError('The recovery service GitHub App is not configured.')
        now = int(time.time())
        message = _encoded(b'{"alg":"RS256","typ":"JWT"}') + '.' + _encoded(json.dumps(
            {'iat': now - 60, 'exp': now + 540, 'iss': self.issuer}, separators=(',', ':')).encode())
        try:
            signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', self.key_file],
                input=message.encode(), capture_output=True, timeout=10, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            raise ValueError('The recovery service could not sign its GitHub App token.') from None
        return message + '.' + _encoded(signed)

    def token(self, repo):
        if repo not in REPOSITORIES:
            raise ValueError('Repository is not authorized.')
        with self.lock:
            saved = self.tokens.get(repo)
            if saved and saved[1] > time.time() + 60:
                return saved[0]
            jwt = self.jwt()
            response = api('/app/installations/' + str(self.installation) + '/access_tokens', jwt,
                {'repositories': [REPOSITORIES[repo].split('/')[1]], 'permissions': {'contents': 'read'}})
            token = response.get('token')
            if not isinstance(token, str) or not token:
                raise ValueError('GitHub did not return an installation token.')
            expires = datetime.fromisoformat(response['expires_at'].replace('Z', '+00:00')).timestamp()
            self.tokens[repo] = (token, expires)
            return token

    def read(self, repo, commit=None, path=None, offset=0, limit=20000):
        if repo not in REPOSITORIES:
            raise ValueError('Repository is not authorized.')
        root = '/repos/' + REPOSITORIES[repo]
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
            raise ValueError('offset must be nonnegative and limit must be 1 to 24000.')
        if commit is None:
            token = self.token(repo)
            metadata = api(root, token)
            head = api(root + '/commits/' + quote(metadata['default_branch'], safe=''), token)
            return {'repo': repo, 'repository': REPOSITORIES[repo], 'commit': head['sha'],
                    'default_branch': metadata['default_branch'], 'audience': 'internal'}
        if not re.fullmatch(r'[0-9a-f]{40}', str(commit)):
            raise ValueError('Read code at a full 40-character commit.')
        path = str(path or '')
        if len(path) > 1500 or '\\' in path or path.startswith('/') or any(
                part in ('.', '..') for part in path.split('/')):
            raise ValueError('Provide a repository-relative source path.')
        if any(part.lower().startswith('.env') or part.lower() in ('credentials.json', 'id_rsa', 'id_ed25519')
               or part.lower().endswith(('.pem', '.key', '.p12', '.pfx')) for part in path.split('/')):
            raise ValueError('Credential files are not source context.')
        token = self.token(repo)
        value = api(root + '/contents/' + quote(path, safe='/') + '?ref=' + commit, token)
        common = {'repo': repo, 'repository': REPOSITORIES[repo], 'commit': commit, 'path': path, 'audience': 'internal'}
        if isinstance(value, list):
            return {**common, 'entries': [{k: entry.get(k) for k in ('name', 'path', 'type', 'sha', 'size')}
                                        for entry in value], 'possibly_truncated': len(value) >= 1000}
        if value.get('type') != 'file' or value.get('encoding') != 'base64' or value.get('size', 0) > 1_000_000:
            raise ValueError('Only text source files up to 1 MB are readable.')
        try:
            raw = base64.b64decode(value['content'])
            text = raw.decode('utf-8')
            if len(raw) > 1_000_000 or '\x00' in text:
                raise ValueError('Only text source files up to 1 MB are readable.')
        except (UnicodeError, KeyError):
            raise ValueError('GitHub did not return a readable text source file.') from None
        return {**common, 'blob': value['sha'], 'text': text[offset:offset + limit], 'offset': offset,
                'next_offset': offset + limit if offset + limit < len(text) else None,
                'url': 'https://github.com/' + REPOSITORIES[repo] + '/blob/' + commit + '/' + quote(path, safe='/')}
