"""One independent repair worker with a durable outbox and no silent execution replay."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from .github import NoRedirect


class Client:
    def __init__(self, root, key):
        parsed = urlsplit(root)
        local = parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        if (parsed.scheme != 'https' and not local) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use HTTPS for the recovery service, or loopback HTTP for local development.')
        if not isinstance(key, str) or len(key) < 32:
            raise ValueError('Configure a high-entropy worker key.')
        self.root, self.key = root.rstrip('/'), key

    def call(self, operation, payload):
        request = Request(self.root + '/workers/' + operation, data=json.dumps(payload).encode(),
                          headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            return json.loads(response.read(2_100_000))


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


def executor_environment(directory):
    # The independently deployed worker must not mount control-service secrets.
    # Only model-provider credentials and explicit worker runtime settings cross
    # the subprocess boundary; no GitHub App, actor, funding, or worker API keys.
    allowed = {'PATH', 'SystemRoot', 'SYSTEMROOT', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
               'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'OPENAI_API_KEY',
               'STUDIO_CODEX_BIN', 'CODEX_HOME', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
               'PLAYWRIGHT_BROWSERS_PATH', 'PLAYWRIGHT_MODULE', 'BROWSER_CHANNEL',
               'GENESIS_REPAIR_REPO_LAB', 'GENESIS_REPAIR_REPO_MONARCH',
               'GENESIS_REPAIR_VERIFY_LAB', 'GENESIS_REPAIR_VERIFY_MONARCH'}
    environment = {k: v for k, v in os.environ.items() if k in allowed}
    environment.update(GENESIS_REPAIR_JOB_DIR=str(directory), PYTHONUNBUFFERED='1')
    return environment


class Worker:
    def __init__(self, directory, client, *, command=None, heartbeat_seconds=5):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.command = command or [sys.executable, '-m', 'wb_repair.executor']
        self.heartbeat_seconds = heartbeat_seconds
        self.current = self.root / 'current.json'
        self.pending = self.root / 'claim.json'

    def once(self):
        if self.current.exists():
            record = json.loads(self.current.read_text(encoding='utf-8'))
        else:
            if not self.pending.exists():
                save(self.pending, {'request_key': uuid.uuid4().hex})
            request = json.loads(self.pending.read_text(encoding='utf-8'))
            job = self.client.call('claim', request)['job']
            if job is None:
                self.pending.unlink()
                return 'idle'
            if not re.fullmatch(r'repair_[0-9a-f]{32}', job['id']):
                raise ValueError('The service returned an invalid repair identity.')
            record = {'job': job, 'phase': 'accepted'}
            save(self.current, record)
            self.pending.unlink(missing_ok=True)
        job = record['job']
        if record['phase'] == 'dispatching':
            # The process may still exist after supervisor restart. Neither elapsed
            # time nor a stale heartbeat authorizes a second execution or settlement.
            return 'needs_attention'
        if record['phase'] == 'accepted':
            directory = self.root / job['id']
            directory.mkdir(exist_ok=True)
            save(directory / 'input.json', {k: v for k, v in job.items() if k != 'claim_token'})
            record['phase'] = 'dispatching'
            save(self.current, record)
            with (directory / 'input.json').open('rb') as source, (directory / 'executor.log').open('wb') as log:
                try:
                    process = subprocess.Popen(self.command, stdin=source, stdout=log, stderr=log,
                                               env=executor_environment(directory))
                except OSError:
                    result = {'job': job['id'], 'reservation': job['funding']['reservation'],
                              'status': 'failed', 'cost_usd': None, 'error': 'Executor could not start.'}
                else:
                    record['pid'] = process.pid
                    save(self.current, record)
                    while process.poll() is None:
                        try:
                            self.client.call('heartbeat', {'job': job['id'], 'claim_token': job['claim_token']})
                        except Exception:
                            pass  # Accepted work survives control-service connectivity loss.
                        try:
                            process.wait(timeout=self.heartbeat_seconds)
                        except subprocess.TimeoutExpired:
                            pass
                    result_path = directory / 'result.json'
                    try:
                        result = json.loads(result_path.read_text(encoding='utf-8')) if process.returncode == 0 else None
                    except (OSError, ValueError):
                        result = None
                    if not isinstance(result, dict) or result.get('job') != job['id'] or result.get('reservation') != job['funding']['reservation']:
                        result = {'job': job['id'], 'reservation': job['funding']['reservation'],
                                  'status': 'interrupted', 'cost_usd': None,
                                  'error': 'Executor exited without a matching final receipt.'}
            record.update(phase='uploading', result=result)
            save(self.current, record)
        if record['result'].get('changed'):
            patch = self.root / job['id'] / 'artifacts' / 'change.patch'
            if not patch.exists() or patch.stat().st_size > 8_000_000:
                raise ValueError('Complete patch is missing or exceeds the 8 MB upload limit; retain this job for review.')
            content = patch.read_bytes()
            if hashlib.sha256(content).hexdigest() != record['result'].get('diff_sha256'):
                raise ValueError('Complete patch no longer matches the executor receipt.')
            self.client.call('patch', {'job': job['id'], 'claim_token': job['claim_token'],
                             'sha256': record['result']['diff_sha256'], 'content': base64.b64encode(content).decode('ascii')})
        self.client.call('finish', {'job': job['id'], 'claim_token': job['claim_token'], 'result': record['result']})
        save(self.root / (job['id'] + '.receipt.json'), record['result'])
        self.current.unlink()
        return record['result']['status']


@contextmanager
def exclusive_worker(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'worker.lock').open('a+b') as lock:
        lock.seek(0)
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('Another worker owns this recovery directory.') from None
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    directory = os.environ.get('GENESIS_REPAIR_WORKER_DATA', '/data')
    with exclusive_worker(directory):
        worker = Worker(directory, Client(os.environ['GENESIS_REPAIR_URL'], os.environ['GENESIS_REPAIR_WORKER_KEY']))
        while True:
            try:
                state = worker.once()
            except Exception as exc:
                print('Repair worker reconnecting: ' + type(exc).__name__, flush=True)
                state = 'retry'
            if state == 'needs_attention':
                print('Repair execution status is uncertain; supervisor reconciliation is required.', flush=True)
                return
            time.sleep(5)


if __name__ == '__main__':
    main()
