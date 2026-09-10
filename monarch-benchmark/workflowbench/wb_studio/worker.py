"""Trusted remote Studio worker. Credentials and billing stay outside evaluated agents."""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

from wb_orchestrator import budget
from wb_results.evidence import write_json
from wb_studio.app import Studio
from wb_studio.components import Components
from wb_studio.coordinator import TERMINAL, code_identity, decode, encode
from wb_studio.gateways import GatewayError
from wb_studio.runtime import Runtime


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class WorkerClient:
    def __init__(self, url, token, *, job=None, claim_token=None, timeout=15):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}):
            raise ValueError('Workers require HTTPS, except loopback development')
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not token:
            raise ValueError('Use a plain coordinator URL and a worker credential')
        self.url, self.token = url.rstrip('/') + '/api/worker', token
        self.job, self.claim_token, self.timeout = job, claim_token, timeout
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, operation, *, request_id=None, **values):
        payload = {'operation': operation, 'request_id': request_id or uuid.uuid4().hex, **values}
        if self.job is not None:
            payload.update(job=self.job, claim_token=self.claim_token)
        data = json.dumps(payload).encode()
        # Retry transport failures with exactly the same identity. Server-side
        # claim semantics still refuse unknown paid dispatch rather than replay it.
        for attempt in range(3):
            request = urllib.request.Request(self.url, data=data, headers={
                'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as error:
                try:
                    detail = json.loads(error.read())
                except (ValueError, OSError):
                    detail = {'error': 'Coordinator rejected the worker request'}
                error_type = detail.get('error_type')
                if error_type == 'GatewayError':
                    raise GatewayError(detail.get('error', 'Coordinator rejected the request'), kind=detail.get('kind', 'infra:provider')) from None
                kind = {'BudgetExceeded': budget.BudgetExceeded,
                        'ReservationConflict': budget.ReservationConflict,
                        'BudgetConfigurationError': budget.BudgetConfigurationError}.get(error_type, ValueError)
                raise kind(detail.get('error', 'Coordinator rejected the worker request')) from None
            except (urllib.error.URLError, OSError):
                if attempt == 2:
                    raise OSError('Coordinator connection failed; dispatch status is unknown') from None
                time.sleep(.2)


class RemoteLedger:
    def __init__(self, client):
        self.client = client

    def __getattr__(self, method):
        if method not in {'status', 'scope_committed', 'reservations', 'reserve', 'claim', 'settle', 'finish_run', 'run_reservation'}:
            raise AttributeError(method)
        def invoke(*args, **kwargs):
            return decode(self.client.call('budget', method=method, args=encode(args), kwargs=encode(kwargs)))
        return invoke


class RemoteRuntime(Runtime):
    def __init__(self, client, concurrency, configuration):
        super().__init__(max_agents=concurrency, max_runs=1, provider_limits=configuration.get('providers', {}))
        self.client = client

    @contextmanager
    def provider(self, name, *, timeout=None, cancel=None, tokens=0):
        if type(tokens) is not int or tokens < 0:
            raise ValueError("Token reservation must be a nonnegative integer")
        deadline = time.monotonic() + (600 if timeout is None else timeout)
        admission = None
        while admission is None:
            if cancel is not None and cancel.is_set():
                raise GatewayError('Cancelled while waiting for provider capacity', kind='infra:cancelled')
            if time.monotonic() >= deadline:
                raise GatewayError('Provider capacity wait timed out; no request sent', kind='infra:timeout')
            response = self.client.call('admit', provider=name, tokens=tokens)
            if response.get('cancelled'):
                raise GatewayError('Run cancelled before dispatch', kind='infra:cancelled')
            if response['admitted']:
                admission = response['id']
            else:
                time.sleep(min(.1, max(0, deadline-time.monotonic())))
        try:
            if time.monotonic() >= deadline:
                raise GatewayError('Provider capacity wait timed out; no request sent', kind='infra:timeout')
            yield max(.001, deadline-time.monotonic())
        finally:
            self.client.call('release', id=admission)


class WorkerStudio(Studio):
    def __init__(self, directory, bundle, client):
        # Avoid Studio.__init__: workers never open a budget DB or recover jobs.
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.tasks = {task['task']: task for task in bundle['tasks']}
        self.client, self.ledger = client, RemoteLedger(client)
        self.gateway_factory = self.adapter_factory = None
        self.lock = threading.RLock()
        self.cancelled = {bundle['job']['id']: threading.Event()}
        self.components = Components()
        self.runtime = RemoteRuntime(client, bundle['job']['settings'].get('concurrency', 1), {})
        self.coordinator = None
        self.token = ''
        self.deferred_finish = None
        for name, content in bundle['files'].items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                raise ValueError('Invalid bundled input path')
            target = self.directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        (self.directory / bundle['job']['id']).mkdir(parents=True, exist_ok=True)
        write_json(self.directory / bundle['job']['id'] / 'job.json', bundle['job'])
        for role in bundle['job']['component_manifest']:
            self.components.resolve(bundle['job']['component_manifest'], role)

    def begin_attempt(self, identity):
        return self.client.call('begin_attempt')

    def end_attempt(self, identity):
        return self.client.call('end_attempt')

    def save(self, job):
        write_json(self.directory / job['id'] / 'job.json', job)
        if job['status'] not in TERMINAL:
            self.client.call('save', value=job)

    def schedule_narrative(self, identity):
        """A worker never spends on interpretation; it records why the report shows the analysis as pending.
        ponytail: the coordinator does not yet pick these up (Phase 6, runtime closure)."""
        from wb_results.evidence import write_json
        folder = self.directory / identity
        if not (folder / "analysis.json").exists():
            write_json(folder / "analysis.pending.json", {"reason": "Finished on a worker; the coordinator does not yet schedule the analysis of worker runs.", "ceiling_usd": "0"})

    def emit(self, identity, kind, **data):
        if kind == 'finished':
            self.deferred_finish = data
            return {'type': kind, **data}
        return self.client.call('event', kind=kind, data=data)

    def upload_and_complete(self, identity):
        root = self.directory / identity
        files = []
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if not (relative.startswith('evidence/') or relative in {'results.sqlite3', 'execution.error.log'}):
                continue
            data = path.read_bytes()
            files.append({'path': relative, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            for offset in range(0, max(1, len(data)), 262144):
                chunk = data[offset:offset+262144]
                self.client.call('artifact', path=relative, offset=offset,
                                 data=base64.b64encode(chunk).decode(), sha256=hashlib.sha256(chunk).hexdigest())
        return self.client.call('complete', files=files, value=self.job(identity), worker_root=str(root))


def run_once(url, token, *, worker=None, work_dir=None):
    worker = worker or f'{socket.gethostname()}-{os.getpid()}'
    client = WorkerClient(url, token)
    bundle = client.call('claim', worker=worker, code_sha256=code_identity())
    if bundle is None:
        return None
    identity = bundle['job']['id']
    client.job, client.claim_token = identity, bundle['token']
    directory = Path(tempfile.mkdtemp(prefix='studio-worker-', dir=work_dir))
    app = WorkerStudio(directory, bundle, client)
    stop = threading.Event()
    heartbeat_error = []

    def heartbeat():
        while not stop.wait(min(10, bundle['lease_seconds']/3)):
            try:
                if client.call('heartbeat')['cancelled']:
                    app.cancelled[identity].set()
            except Exception as error:
                heartbeat_error.append(error)
                app.cancelled[identity].set()
                return

    if client.call('heartbeat')['cancelled']:
        app.cancelled[identity].set()
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        app._load_env()
        app.execute(identity)
        if heartbeat_error:
            raise OSError('Worker lost coordinator ownership; local evidence retained')
        app.upload_and_complete(identity)
        return {'job': identity, 'status': app.job(identity)['status'], 'evidence_directory': str(directory)}
    finally:
        stop.set()
        thread.join(timeout=client.timeout+1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coordinator', default=os.getenv('STUDIO_COORDINATOR_URL'))
    parser.add_argument('--worker', default=f'{socket.gethostname()}-{os.getpid()}')
    parser.add_argument('--work-dir', default=os.getenv('STUDIO_WORKER_DATA_DIR'))
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    token = os.getenv('STUDIO_WORKER_TOKEN')
    if not args.coordinator or not token:
        parser.error('Set coordinator URL and STUDIO_WORKER_TOKEN')
    if args.work_dir:
        Path(args.work_dir).mkdir(parents=True, exist_ok=True)
    while True:
        result = run_once(args.coordinator, token, worker=args.worker, work_dir=args.work_dir)
        if result:
            print(json.dumps(result), flush=True)
        if args.once:
            return
        if result is None:
            time.sleep(2)


if __name__ == '__main__':
    main()
