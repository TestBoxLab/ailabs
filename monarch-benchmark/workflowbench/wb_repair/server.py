"""Authenticated recovery endpoint, independently runnable with only Python stdlib."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .jobs import Conflict, JobStore


from . import REPOSITORIES


def specification(value):
    if not isinstance(value, dict):
        raise ValueError('Provide a spec object.')
    if set(value) - {'repo', 'commit', 'change', 'verification'}:
        raise ValueError('Unsupported specification fields.')
    if value.get('repo') not in REPOSITORIES:
        raise ValueError('repo must be lab or monarch.')
    if not re.fullmatch(r'[0-9a-f]{40}', str(value.get('commit') or '')):
        raise ValueError('commit must be the full 40-character source commit.')
    for key, limit in (('change', 16000), ('verification', 8000)):
        if not isinstance(value.get(key), str) or not 1 <= len(value[key].strip()) <= limit:
            raise ValueError(f'{key} must contain 1 to {limit} characters.')
    return {key: value[key] for key in ('repo', 'commit', 'change', 'verification')}


def handler(store, actor_hashes, revision='unknown', github=None, funding_secret=None, worker_hash=None):
    if not actor_hashes or any(not isinstance(actor, str) or not actor or
            not re.fullmatch(r'[0-9a-f]{64}', str(digest)) for actor, digest in actor_hashes.items()):
        raise ValueError('Configure actor names and SHA-256 access-key hashes before starting recovery.')
    if len(set(actor_hashes.values())) != len(actor_hashes):
        raise ValueError('Each actor needs a distinct access key.')

    class RecoveryHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Request paths and bodies may contain internal repair information.

        def respond(self, status, value):
            self.send_bytes(status, json.dumps(value, allow_nan=False).encode(), 'application/json; charset=utf-8')

        def send_bytes(self, status, body, content_type, filename=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header('Referrer-Policy', 'no-referrer')
            if filename:
                self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
            self.end_headers()
            self.wfile.write(body)

        def actor(self):
            authorization = self.headers.get('Authorization', '')
            if not authorization.startswith('Bearer '):
                return None
            digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
            return next((actor for actor, expected in actor_hashes.items()
                         if hmac.compare_digest(digest, expected)), None)

        def do_GET(self):
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/recovery.js': ('recovery.js', 'text/javascript; charset=utf-8'),
                      '/recovery.css': ('recovery.css', 'text/css; charset=utf-8'),
                      '/regular.woff2': ('regular.woff2', 'font/woff2'),
                      '/medium.woff2': ('medium.woff2', 'font/woff2')}
            if self.path in assets:
                name, content_type = assets[self.path]
                self.send_bytes(200, (Path(__file__).parent / 'static' / name).read_bytes(), content_type)
                return
            if self.path == '/health':
                self.respond(200, {'status': 'ready', 'service': 'genesis-repair', 'revision': revision, 'execution_enabled': bool(worker_hash and funding_secret)})
                return
            actor = self.actor()
            if actor is None:
                self.respond(401, {'error': 'An authorized recovery key is required.'})
                return
            if self.path == '/jobs':
                self.respond(200, {'jobs': store.recent(actor)})
                return
            patch = re.fullmatch(r'/jobs/(repair_[0-9a-f]{32})/patch', self.path)
            if patch:
                try:
                    content, digest = store.patch(patch[1], actor)
                    self.send_bytes(200, content, 'text/plain; charset=utf-8', patch[1] + '.patch')
                except KeyError:
                    self.respond(404, {'error': 'Not found.'})
                return
            parsed = urlsplit(self.path)
            repo = re.fullmatch(r'/repos/(lab|monarch)', parsed.path)
            if repo:
                if github is None:
                    self.respond(503, {'error': 'GitHub access is not configured.'})
                    return
                try:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if set(query) - {'commit', 'path', 'offset', 'limit'} or any(len(v) != 1 for v in query.values()):
                        raise ValueError('Unsupported or repeated repository query field.')
                    args = {k: v[0] for k, v in query.items()}
                    for key in ('offset', 'limit'):
                        if key in args:
                            args[key] = int(args[key])
                    self.respond(200, github.read(repo[1], **args))
                except ValueError as exc:
                    self.respond(400, {'error': str(exc)})
                return
            match = re.fullmatch(r'/jobs/(repair_[0-9a-f]{32})', self.path)
            if not match:
                self.respond(404, {'error': 'Not found.'})
                return
            try:
                self.respond(200, store.read(match[1], actor))
            except KeyError:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if self.path.startswith('/workers/'):
                self.worker_request()
                return
            actor = self.actor()
            if actor is None:
                self.respond(401, {'error': 'An authorized recovery key is required.'})
                return
            funding = re.fullmatch(r'/jobs/(repair_[0-9a-f]{32})/funding', self.path)
            if self.path != '/jobs' and not funding:
                self.respond(404, {'error': 'Not found.'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 1 <= size <= 64000:
                    self.respond(413, {'error': 'Provide a JSON body of at most 64000 bytes.'})
                    return
                if self.headers.get_content_type() != 'application/json':
                    self.respond(415, {'error': 'Use application/json.'})
                    return
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(size))
                if funding:
                    if not funding_secret:
                        self.respond(503, {'error': 'Funding transfer is not configured.'})
                        return
                    from .grants import verify
                    job = store.read(funding[1], actor)
                    if not isinstance(body, dict) or set(body) != {'grant'}:
                        raise ValueError('Provide only a signed funding grant.')
                    claims = verify(body['grant'], funding_secret, actor=actor, job=job['id'], spec=job['payload'])
                    accepted = store.authorize(job['id'], actor, claims)
                    self.respond(200, {'job': job['id'], 'funding': accepted, 'state': job['state']})
                    return
                if not isinstance(body, dict) or set(body) != {'spec'}:
                    raise ValueError('Provide only a spec object; identity comes from authentication.')
                job = store.submit(actor, self.headers.get('Idempotency-Key'), specification(body['spec']))
                self.respond(202, job)
            except KeyError:
                self.respond(404, {'error': 'Not found.'})
            except Conflict as exc:
                self.respond(409, {'error': str(exc)})
            except (ValueError, UnicodeError) as exc:
                self.respond(400, {'error': str(exc)})
            except TimeoutError:
                self.respond(408, {'error': 'The request body timed out.'})

        def worker_request(self):
            authorization = self.headers.get('Authorization', '')
            digest = hashlib.sha256(authorization[7:].encode()).hexdigest() if authorization.startswith('Bearer ') else ''
            if not worker_hash or not hmac.compare_digest(digest, worker_hash):
                self.respond(401, {'error': 'An authorized worker key is required.'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 1 <= size <= (10_700_000 if self.path == '/workers/patch' else 2_100_000):
                    self.respond(413, {'error': 'Worker payload too large.'})
                    return
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Provide a worker request object.')
                if self.path == '/workers/claim':
                    key = body.get('request_key')
                    if set(body) != {'request_key'} or not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', key):
                        raise ValueError('Provide one stable claim request key.')
                    job = store.claim(secrets.token_urlsafe(32), funded_only=True, request_key=key)
                    self.respond(200, {'job': job})
                    return
                if self.path not in ('/workers/heartbeat', '/workers/finish', '/workers/patch'):
                    self.respond(404, {'error': 'Not found.'})
                    return
                identity, token = body.get('job'), body.get('claim_token')
                if not isinstance(identity, str) or not isinstance(token, str):
                    raise ValueError('Provide the job and its claim token.')
                if self.path.endswith('/patch'):
                    try:
                        content = base64.b64decode(body.get('content', ''), validate=True)
                    except (binascii.Error, TypeError):
                        raise ValueError('Provide a base64 encoded patch.') from None
                    store.put_patch(identity, token, content, body.get('sha256'))
                elif self.path.endswith('/heartbeat'):
                    store.heartbeat(identity, token)
                else:
                    result = body.get('result')
                    funding = store.funding(identity)
                    if not isinstance(result, dict) or not funding or result.get('job') != identity or result.get('reservation') != funding['reservation']:
                        raise ValueError('Result must match the funded job and reservation.')
                    state = result.get('status')
                    if state == 'awaiting_review' and (result.get('verified') is not True or result.get('changed') is not True):
                        raise ValueError('Review requires an actual patch and passing verification.')
                    store.finish(identity, token, state, result)
                self.respond(200, {'accepted': True, 'job': identity})
            except Conflict as exc:
                self.respond(409, {'error': str(exc)})
            except (ValueError, UnicodeError) as exc:
                self.respond(400, {'error': str(exc)})
            except TimeoutError:
                self.respond(408, {'error': 'Worker request timed out.'})

    return RecoveryHandler


def main():
    from .github import GitHubApp
    root = Path(os.environ.get('GENESIS_REPAIR_DATA', '/data'))
    actors = json.loads(os.environ.get('GENESIS_REPAIR_KEY_HASHES', '{}'))
    server = ThreadingHTTPServer((os.environ.get('GENESIS_REPAIR_HOST', '127.0.0.1'),
                                  int(os.environ.get('PORT', '8780'))),
        handler(JobStore(root / 'jobs.sqlite3'), actors, os.environ.get('GENESIS_REPAIR_REVISION', 'unknown'), GitHubApp.environment(), os.environ.get('GENESIS_REPAIR_FUNDING_KEY'), os.environ.get('GENESIS_REPAIR_WORKER_KEY_HASH')))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
