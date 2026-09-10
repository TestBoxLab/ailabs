"""Durable coordinator for trusted remote workers; SQLite stays on the coordinator.

Workers use HTTPS (loopback HTTP for development), receive one job's inputs, and
upload its evidence. An expired claim is interrupted, never silently reassigned.
The worker credential belongs to operators, never evaluated agents.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from datetime import datetime
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import sqlite3
import time
import uuid

from wb_results.evidence import write_json
from wb_studio.gateways import GatewayError

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def encode(value):
    if isinstance(value, datetime): return {'$datetime': value.isoformat()}
    if isinstance(value, Decimal): return {'$decimal': str(value)}
    if is_dataclass(value): return {'$record': type(value).__name__, 'fields': encode(asdict(value))}
    if isinstance(value, dict): return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {'$datetime'}: return datetime.fromisoformat(value['$datetime'])
        if set(value) == {'$decimal'}: return Decimal(value['$decimal'])
        if set(value) == {'$record', 'fields'}:
            from wb_orchestrator import budget
            if value['$record'] not in {'Reservation', 'BudgetStatus', 'RunReservation'}: raise ValueError('Unknown budget record')
            fields = decode(value['fields'])
            if value['$record'] == 'BudgetStatus': fields['overrun_ids'] = tuple(fields['overrun_ids'])
            return getattr(budget, value['$record'])(**fields)
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list): return [decode(v) for v in value]
    return value


def code_identity():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for package in ('wb_studio', 'wb_arms', 'wb_orchestrator', 'wb_world', 'wb_results', 'grader', 'runner'):
        for path in sorted((root / package).rglob('*.py')):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class Coordinator:
    def __init__(self, studio, *, lease_seconds=60):
        if not isinstance(lease_seconds, (int, float)) or lease_seconds <= 0: raise ValueError('Positive worker lease required')
        self.studio, self.lease_seconds = studio, lease_seconds
        self.path = studio.directory / 'workers.sqlite3'
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS worker_nodes(worker TEXT PRIMARY KEY, last_seen REAL NOT NULL, code_sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS claim_requests(worker TEXT NOT NULL, id TEXT NOT NULL,
                    response TEXT NOT NULL, PRIMARY KEY(worker,id));
                CREATE TABLE IF NOT EXISTS claims(job TEXT PRIMARY KEY, worker TEXT NOT NULL,
                    token TEXT NOT NULL, heartbeat REAL NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS admissions(id TEXT PRIMARY KEY, job TEXT NOT NULL,
                    provider TEXT NOT NULL, started REAL NOT NULL, released INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS messages(job TEXT NOT NULL, id TEXT NOT NULL,
                    response TEXT NOT NULL, PRIMARY KEY(job,id));
            ''')
            if 'tokens' not in {r['name'] for r in db.execute('PRAGMA table_info(admissions)')}:
                db.execute('ALTER TABLE admissions ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0')
            if 'fingerprint' not in {r['name'] for r in db.execute('PRAGMA table_info(messages)')}:
                db.execute('ALTER TABLE messages ADD COLUMN fingerprint TEXT')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally: db.close()

    def snapshot(self):
        self.reap()
        with self.studio.lock, self.transaction() as db:
            now = time.time()
            rows = db.execute('SELECT job,worker,heartbeat,state FROM claims ORDER BY heartbeat DESC').fetchall()
            allocated = sum(self.studio.job(r['job'])['settings'].get('concurrency', 1) for r in rows if r['state'] == 'active')
            nodes = [dict(r) for r in db.execute('SELECT worker,last_seen,code_sha256 FROM worker_nodes ORDER BY worker')]
            for node in nodes:
                node['connected'] = node['last_seen'] >= now - self.lease_seconds
                node['active_jobs'] = [r['job'] for r in rows if r['worker'] == node['worker'] and r['state'] == 'active']
            names = set(self.studio.runtime.limits) | {r[0] for r in db.execute('SELECT DISTINCT provider FROM admissions')}
            providers = []
            for name in sorted(names):
                limit = self.studio.runtime.limits.get(name, {})
                active = db.execute('SELECT count(*) FROM admissions WHERE provider=? AND released=0', (name,)).fetchone()[0]
                requests, tokens = db.execute('SELECT count(*),coalesce(sum(tokens),0) FROM admissions WHERE provider=? AND started>?', (name, now-60)).fetchone()
                providers.append({'provider': name, 'concurrency': limit.get('concurrency', 2), 'requests_per_minute': limit.get('requests_per_minute', 30),
                                  'tokens_per_minute': limit.get('tokens_per_minute'), 'active': active, 'recent_requests': requests, 'reserved_tokens_last_minute': tokens})
        return {'mode': 'coordinator-workers', 'workers': [dict(r) for r in rows], 'worker_nodes': nodes,
                'active_agents': allocated, 'allocated_agent_slots': allocated, 'agent_metric': 'allocated', 'providers': providers,
                'limits_note': 'Coordinator-wide admission caps. Agent slots show allocated run capacity; provider slots include unknown requests retained after worker loss.',
                'lease_seconds': self.lease_seconds, 'code_sha256': code_identity(),
                'recovery': 'Queued jobs survive coordinator restarts. Lost worker claims are interrupted; paid work is never automatically replayed.'}

    def _owned(self, db, job, token):
        row = db.execute('SELECT * FROM claims WHERE job=?', (job,)).fetchone()
        if not isinstance(token, str) or not row or not secrets.compare_digest(row['token'], token) or row['state'] != 'active':
            raise ValueError('Worker claim is no longer active')
        return row

    def reap(self):
        with self.studio.lock, self.transaction() as db:
            rows = db.execute("SELECT job FROM claims WHERE state='active' AND heartbeat<?", (time.time()-self.lease_seconds,)).fetchall()
            for row in rows:
                db.execute("UPDATE claims SET state='interrupted' WHERE job=?", (row['job'],))
                job = self.studio.job(row['job'])
                if job['status'] not in TERMINAL:
                    job.update(status='interrupted', error='Worker heartbeat lost. Recorded evidence and unknown billing are retained; this run will not replay.')
                    self.studio.save(job)
                    self.studio.emit(job['id'], 'interrupted', job=job)
                # No automatic release: worker or provider may still be running.
        return len(rows)

    def claim(self, worker, code_sha256, request_id):
        if not isinstance(worker, str) or not worker or len(worker)>100: raise ValueError('Invalid worker name')
        if not isinstance(request_id, str) or not request_id or len(request_id)>100: raise ValueError('Claim request ID required')
        if code_sha256 != code_identity(): raise ValueError('Worker code differs from coordinator; install the same revision')
        self.reap()
        with self.studio.lock, self.transaction() as db:
            db.execute('INSERT INTO worker_nodes VALUES(?,?,?) ON CONFLICT(worker) DO UPDATE SET last_seen=excluded.last_seen,code_sha256=excluded.code_sha256', (worker,time.time(),code_sha256))
            previous = db.execute('SELECT response FROM claim_requests WHERE worker=? AND id=?', (worker,request_id)).fetchone()
            if previous: return json.loads(previous[0])
            if db.execute("SELECT 1 FROM claims WHERE worker=? AND state='active'", (worker,)).fetchone(): return None
            active = db.execute("SELECT count(*) FROM claims WHERE state='active'").fetchone()[0]
            if active >= self.studio.runtime.max_runs: return None
            reserved = sum(j['settings'].get('concurrency', 1) for j in self.studio.jobs()
                           if db.execute("SELECT 1 FROM claims WHERE job=? AND state='active'", (j['id'],)).fetchone())
            for job in reversed(self.studio.jobs()):
                if job['status'] != 'queued' or job.get('pause_requested') or db.execute('SELECT 1 FROM claims WHERE job=?', (job['id'],)).fetchone(): continue
                if reserved + job['settings'].get('concurrency', 1) > self.studio.runtime.max_agents: continue
                # Enterprise front-door routing is worker-specific and must be configured there.
                token = secrets.token_urlsafe(32)
                db.execute('INSERT INTO claims VALUES(?,?,?,?,?)', (job['id'], worker, token, time.time(), 'active'))
                job['worker'] = worker
                self.studio.save(job)
                files = {}
                for arm in job['settings']['arms']:
                    if arm['kind'] == 'version':
                        from wb_studio.execution import load_version
                        version = load_version(self.studio, arm['blueprint'], arm['number'])
                        relative = f"blueprints/{arm['blueprint']}/v{arm['number']:04d}.json"
                        files[relative] = (self.studio.directory / relative).read_text(encoding='utf-8')
                        for node in version['graph']['nodes']:
                            if node['type'] == 'product-graph':
                                config = node['config']
                                relative = f"product-graphs/{config['graph']}/v{config['version']:04d}.json"
                                files[relative] = (self.studio.directory / relative).read_text(encoding='utf-8')
                response = {'job': job, 'token': token, 'tasks': [self.studio.tasks[t] for t in job['settings']['tasks']], 'files': files,
                            'lease_seconds': self.lease_seconds, 'runtime': self.studio.runtime.snapshot()}
                db.execute('INSERT INTO claim_requests VALUES(?,?,?)', (worker,request_id,json.dumps(response)))
                return response
        return None

    def dispatch(self, payload):
        operation = payload.get('operation')
        if operation == 'claim': return self.claim(payload.get('worker'), payload.get('code_sha256'), payload.get('request_id'))
        self.reap()
        identity, token = payload.get('job'), payload.get('claim_token', '')
        with self.studio.lock, self.transaction() as db:
            owner = db.execute('SELECT * FROM claims WHERE job=?', (identity,)).fetchone()
            if not owner or not isinstance(token, str) or not secrets.compare_digest(owner['token'], token):
                raise ValueError('Worker claim is no longer active')
            if operation == 'heartbeat':
                self._owned(db, identity, token)
                db.execute('UPDATE claims SET heartbeat=? WHERE job=?', (time.time(), identity))
                db.execute('UPDATE worker_nodes SET last_seen=? WHERE worker=?', (time.time(), owner['worker']))
                return {'cancelled': self.studio.job(identity)['status'] in ('cancelling', 'cancelled', 'interrupted')}
            request_id = payload.get('request_id')
            if not isinstance(request_id, str) or not request_id or len(request_id)>100: raise ValueError('Request ID required')
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            previous = db.execute('SELECT response,fingerprint FROM messages WHERE job=? AND id=?', (identity, request_id)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint: raise ValueError('Request ID reused with different content')
                if owner['state'] != 'active' and not (operation == 'complete' and owner['state'] == 'finished'):
                    raise ValueError('Worker claim is no longer active')
                return json.loads(previous['response'])
            self._owned(db, identity, token)
            result = self._dispatch_owned(db, identity, operation, payload)
            db.execute('INSERT INTO messages(job,id,response,fingerprint) VALUES(?,?,?,?)', (identity, request_id, json.dumps(result), fingerprint))
            return result

    def _save(self, identity, update, *, terminal=False):
        current = self.studio.job(identity)
        for key in ('id', 'settings', 'task_hashes', 'component_manifest', 'runner_manifests', 'execution_manifests', 'workflow_contract', 'benchmark'):
            if current.get(key) != update.get(key): raise ValueError('Worker attempted to change frozen run identity')
        if (update['status'] in TERMINAL) != terminal: raise ValueError('Terminal jobs require completed evidence upload')
        if current['status'] in ('cancelling', 'cancelled'):
            update['status'] = 'cancelled' if terminal else 'cancelling'
        update['worker'] = current['worker']
        self.studio.save(update)

    def _artifact_target(self, identity, name):
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative) or ':' in str(relative): raise ValueError('Invalid artifact path')
        if not relative.parts or relative.parts[0] not in {'evidence', 'results.sqlite3', 'execution.error.log'}: raise ValueError('Unsupported artifact')
        if relative.parts[0] != 'evidence' and len(relative.parts) != 1: raise ValueError('Invalid artifact path')
        root = (self.studio.directory / identity).resolve()
        target = (root / ('.worker-results.sqlite3' if str(relative) == 'results.sqlite3' else str(relative))).resolve()
        if not target.is_relative_to(root): raise ValueError('Artifact escapes job directory')
        return target

    def _dispatch_owned(self, db, identity, operation, payload):
        if operation == 'event':
            if payload['kind'] == 'finished': raise ValueError('Finish through the evidence completion operation')
            for event in self.studio.events(identity):
                if event.get('worker_request_id') == payload['request_id']: return event
            return self.studio.emit(identity, payload['kind'], **payload.get('data', {}), worker_request_id=payload['request_id'])
        if operation == 'begin_attempt':
            return self.studio.begin_attempt(identity)
        if operation == 'end_attempt':
            self.studio.end_attempt(identity)
            return {'ended': True}
        if operation == 'save':
            self._save(identity, payload['value'])
            return {'saved': True}
        if operation == 'budget':
            method, args, kwargs = payload['method'], decode(payload.get('args', [])), decode(payload.get('kwargs', {}))
            if method not in {'status', 'scope_committed', 'reservations', 'reserve', 'claim', 'settle', 'finish_run', 'run_reservation'}:
                raise ValueError('Unsupported ledger method')
            if method in {'reserve', 'claim'} and self.studio.job(identity)['status'] in {'cancelling', 'cancelled', 'interrupted'}:
                from wb_orchestrator.budget import ReservationConflict
                raise ReservationConflict('Run cancelled before dispatch')
            if 'now' in kwargs: raise ValueError('Coordinator timestamps budget operations')
            if method == 'reserve' and (kwargs.get('scope_id') != identity or kwargs.get('run_id',identity) != identity): raise ValueError('Reservation scope must match run')
            if method in {'scope_committed', 'finish_run', 'run_reservation'} and args != [identity]: raise ValueError('Wrong run scope')
            if method == 'reservations': kwargs['scope_id'] = identity
            if method in {'claim', 'settle'}:
                if not args or args[0] not in {r.reservation_id for r in self.studio.ledger.reservations(scope_id=identity)}:
                    raise ValueError('Reservation belongs to another run')
            return encode(getattr(self.studio.ledger, method)(*args, **kwargs))
        if operation == 'admit':
            if self.studio.job(identity)['status'] in ('cancelling', 'cancelled', 'interrupted'): return {'cancelled': True, 'admitted': False}
            provider = payload['provider']
            if not isinstance(provider, str) or not provider or len(provider)>100: raise ValueError('Invalid provider')
            limit = self.studio.runtime.limits.get(provider, {})
            tokens = payload.get('tokens', 0)
            if type(tokens) is not int or tokens < 0: raise ValueError('Token reservation must be a nonnegative integer')
            tpm = limit.get('tokens_per_minute')
            if tpm is not None and tokens > tpm:
                raise GatewayError('This request exceeds the configured token-per-minute capacity; reduce its context or raise the operator limit', kind='infra:rate_limit')
            now = time.time()
            active = db.execute('SELECT count(*) FROM admissions WHERE provider=? AND released=0', (provider,)).fetchone()[0]
            recent, used_tokens = db.execute('SELECT count(*),coalesce(sum(tokens),0) FROM admissions WHERE provider=? AND started>?', (provider,now-60)).fetchone()
            if active >= limit.get('concurrency',2) or recent >= limit.get('requests_per_minute',30) or (tpm is not None and used_tokens + tokens > tpm): return {'admitted': False}
            admission = uuid.uuid4().hex
            db.execute('INSERT INTO admissions(id,job,provider,started,tokens) VALUES(?,?,?,?,?)', (admission,identity,provider,now,tokens))
            return {'admitted': True, 'id': admission}
        if operation == 'release':
            db.execute('UPDATE admissions SET released=1 WHERE id=? AND job=?', (payload['id'],identity))
            return {'released': True}
        if operation == 'artifact':
            target = self._artifact_target(identity, payload['path'])
            data = base64.b64decode(payload['data'], validate=True)
            if len(data) > 262144: raise ValueError('Artifact chunk too large')
            if hashlib.sha256(data).hexdigest() != payload['sha256']: raise ValueError('Artifact hash mismatch')
            target.parent.mkdir(parents=True, exist_ok=True)
            offset = payload.get('offset', 0)
            if type(offset) is not int or offset < 0: raise ValueError('Invalid offset')
            mode = 'r+b' if target.exists() else 'w+b'
            with target.open(mode) as stream:
                stream.seek(0, 2)
                length = stream.tell()
                if length > offset:
                    stream.seek(offset)
                    if stream.read(len(data)) != data: raise ValueError('Artifact retry differs from stored bytes')
                    return {'written': len(data)}
                if length != offset: raise ValueError('Artifact offset mismatch')
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            return {'written': len(data)}
        if operation == 'complete':
            files = payload.get('files')
            if not isinstance(files, list) or not files: raise ValueError('Evidence inventory required')
            names = set()
            for item in files:
                target = self._artifact_target(identity, item['path'])
                if item['path'] in names: raise ValueError('Duplicate artifact')
                names.add(item['path'])
                if not target.is_file() or target.stat().st_size != item['size'] or hashlib.sha256(target.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError('Evidence upload is incomplete or changed')
            if 'results.sqlite3' not in names: raise ValueError('Results database required')
            # Store URIs are local to the worker; rebase only the database links.
            # Hashed evidence files and manifest-relative paths remain untouched.
            root = str(payload['worker_root']).replace('\\','/').rstrip('/')+'/'
            database = self.studio.directory / identity / 'results.sqlite3'
            shutil.copyfile(self._artifact_target(identity, 'results.sqlite3'), database)
            with sqlite3.connect(database) as result_db:
                for episode_id, kind, uri in result_db.execute('SELECT episode_id,kind,uri FROM artifacts').fetchall():
                    normalized = uri.replace('\\','/')
                    if not normalized.startswith(root): raise ValueError('Artifact URI is outside worker job')
                    relative = normalized[len(root):]
                    if relative not in names: raise ValueError('Result links to missing uploaded evidence')
                    result_db.execute('UPDATE artifacts SET uri=? WHERE episode_id=? AND kind=?',
                                      (str(self._artifact_target(identity, relative)), episode_id, kind))
            self._save(identity, payload['value'], terminal=True)
            job = self.studio.job(identity)
            if not any(e.get('worker_request_id') == payload['request_id'] for e in self.studio.events(identity)):
                self.studio.emit(identity, 'finished', job=job, budget=self.studio.budget(), worker_request_id=payload['request_id'])
            db.execute("UPDATE claims SET state='finished' WHERE job=?", (identity,))
            return {'finished': True}
        raise ValueError('Unknown worker operation')
