"""Durable accepted repairs. Interrupted execution is never silently replayed."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Conflict(ValueError):
    pass


class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, request_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, worker TEXT, heartbeat REAL,
                created REAL NOT NULL, updated REAL NOT NULL, result TEXT,
                UNIQUE(actor, request_key))""")
            db.execute("""CREATE TABLE IF NOT EXISTS funding (
                job TEXT PRIMARY KEY, reservation TEXT UNIQUE NOT NULL,
                expires INTEGER NOT NULL, claims TEXT NOT NULL)""")
            db.execute('CREATE TABLE IF NOT EXISTS patches (job TEXT PRIMARY KEY, sha256 TEXT NOT NULL, content BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS worker_requests (id TEXT PRIMARY KEY, response TEXT NOT NULL)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def record(row):
        if row is None:
            raise KeyError('Repair job not found.')
        out = dict(row)
        out['payload'] = json.loads(out['payload'])
        out['result'] = json.loads(out['result']) if out['result'] else None
        out.pop('fingerprint')
        out.pop('request_key')
        out.pop('worker')
        return out

    def submit(self, actor, request_key, payload):
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 120:
            raise ValueError('An authenticated actor is required.')
        if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 160:
            raise ValueError('A request key of 1 to 160 characters is required.')
        if not isinstance(payload, dict):
            raise ValueError('A repair specification is required.')
        content = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(content.encode()) > 64000:
            raise ValueError('The repair specification exceeds 64000 bytes.')
        fingerprint = hashlib.sha256(content.encode()).hexdigest()
        now = time.time()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM jobs WHERE actor=? AND request_key=?', (actor, request_key)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise Conflict('This request key already identifies a different repair.')
                return self.record(old)
            identity = 'repair_' + uuid.uuid4().hex
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (identity, actor, request_key, fingerprint, content, 'queued', None, None, now, now, None))
            return self.record(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())

    def read(self, identity, actor):
        with self.connection() as db:
            return self.record(db.execute('SELECT * FROM jobs WHERE id=? AND actor=?', (identity, actor)).fetchone())

    def recent(self, actor, limit=50):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM jobs WHERE actor=? ORDER BY created DESC,id DESC LIMIT ?', (actor, limit)).fetchall()
            return [{k: v for k, v in self.record(row).items() if k != 'result'} for row in rows]

    def put_patch(self, identity, worker, content, sha256):
        if not isinstance(content, bytes) or not 1 <= len(content) <= 8_000_000:
            raise ValueError('Patch must contain 1 to 8000000 bytes.')
        if hashlib.sha256(content).hexdigest() != sha256:
            raise ValueError('Patch does not match its SHA-256 receipt.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT worker,state FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None or row['worker'] != worker:
                raise Conflict('This worker does not own the repair.')
            previous = db.execute('SELECT sha256,content FROM patches WHERE job=?', (identity,)).fetchone()
            if previous:
                if previous['sha256'] == sha256 and previous['content'] == content:
                    return
                raise Conflict('The accepted patch cannot be replaced.')
            if row['state'] != 'running':
                raise Conflict('Only a running repair may upload its patch.')
            db.execute('INSERT INTO patches VALUES (?,?,?)', (identity, sha256, content))

    def patch(self, identity, actor):
        with self.connection() as db:
            row = db.execute('SELECT p.content,p.sha256 FROM patches p JOIN jobs j ON j.id=p.job WHERE j.id=? AND j.actor=?', (identity, actor)).fetchone()
            if row is None:
                raise KeyError('Patch not found.')
            return bytes(row['content']), row['sha256']

    def authorize(self, identity, actor, claims):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=? AND actor=?', (identity, actor)).fetchone()
            if row is None:
                raise KeyError('Repair job not found.')
            old = db.execute('SELECT claims FROM funding WHERE job=?', (identity,)).fetchone()
            if old:
                original = json.loads(old['claims'])
                if {k: v for k, v in original.items() if k != 'expires'} != {k: v for k, v in claims.items() if k != 'expires'}:
                    raise Conflict('This repair already has a different funding authorization.')
                return original
            if row['state'] != 'queued':
                raise Conflict('A running or finished repair cannot receive new funding.')
            try:
                db.execute('INSERT INTO funding VALUES (?,?,?,?)',
                    (identity, claims['reservation'], claims['expires'], json.dumps(claims)))
            except sqlite3.IntegrityError:
                raise Conflict('This reservation already funds another repair.') from None
            return claims

    def funding(self, identity):
        with self.connection() as db:
            row = db.execute('SELECT claims FROM funding WHERE job=?', (identity,)).fetchone()
            return json.loads(row['claims']) if row else None

    def claim(self, worker, *, funded_only=False, request_key=None):
        if not worker:
            raise ValueError('A unique worker identity is required.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if request_key:
                previous = db.execute('SELECT response FROM worker_requests WHERE id=?', (request_key,)).fetchone()
                if previous:
                    return json.loads(previous['response'])
            query = "SELECT * FROM jobs WHERE state='queued'"
            args = ()
            if funded_only:
                query += ' AND id IN (SELECT job FROM funding WHERE expires>?)'
                args = (time.time(),)
            row = db.execute(query + ' ORDER BY created,id LIMIT 1', args).fetchone()
            if row is None:
                if request_key:
                    db.execute('INSERT INTO worker_requests VALUES (?,?)', (request_key, 'null'))
                return None
            now = time.time()
            db.execute("UPDATE jobs SET state='running',worker=?,heartbeat=?,updated=? WHERE id=?",
                       (worker, now, now, row['id']))
            result = self.record(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())
            if request_key:
                funded = db.execute('SELECT claims FROM funding WHERE job=?', (row['id'],)).fetchone()
                result.update(claim_token=worker, funding=json.loads(funded['claims']) if funded else None)
                db.execute('INSERT INTO worker_requests VALUES (?,?)', (request_key, json.dumps(result)))
            return result

    def heartbeat(self, identity, worker):
        with self.connection() as db:
            now = time.time()
            changed = db.execute("UPDATE jobs SET heartbeat=?,updated=? WHERE id=? AND worker=? AND state='running'",
                                 (now, now, identity, worker)).rowcount
            if changed != 1:
                raise Conflict('This worker no longer owns a running repair.')

    def finish(self, identity, worker, state, result):
        if state not in ('awaiting_review', 'failed', 'interrupted'):
            raise ValueError('Execution ends awaiting_review, failed, or interrupted; it does not prove publication.')
        encoded = json.dumps(result, allow_nan=False)
        if len(encoded.encode()) > 2_000_000:
            raise ValueError('Persist large repair artifacts separately; result exceeds 2 MB.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT state,result,worker FROM jobs WHERE id=?', (identity,)).fetchone()
            if previous and previous['worker'] == worker and previous['state'] == state and previous['result'] == encoded:
                return
            if previous is None or previous['worker'] != worker or previous['state'] != 'running':
                raise Conflict('This worker no longer owns a running repair.')
            if state == 'awaiting_review':
                patch = db.execute('SELECT sha256 FROM patches WHERE job=?', (identity,)).fetchone()
                if not patch or result.get('diff_sha256') != patch['sha256']:
                    raise ValueError('Review requires the complete patch matching its receipt.')
            changed = db.execute("UPDATE jobs SET state=?,result=?,updated=? WHERE id=? AND worker=? AND state='running'",
                                 (state, encoded, time.time(), identity, worker)).rowcount
            if changed != 1:
                raise Conflict('This worker no longer owns a running repair.')

    def mark_interrupted(self, identity, worker, reason):
        """Only after supervisor evidence of worker exit. A timeout is not proof of exit."""
        self.finish(identity, worker, 'interrupted', {'reason': str(reason), 'replay': False})
