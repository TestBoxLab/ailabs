"""AppWorld's published HTTP operations, with private source evidence and grading.

The upstream environment server has one global world. A cross-process lock holds
it for the entire attempt; a unique experiment preserves each attempt's evidence.
Only documented application operations become fixed requester calls. Competitors
never receive the environment server's execute, evaluator, or filesystem surface.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import tempfile
import subprocess
from datetime import datetime, timezone

from wb_world.adapter import PositiveResult, canonical
from .importer import appworld_root, hydrate_task, source_call, outside_repository, fingerprint

SERVICES = ('amazon', 'api_docs', 'file_system', 'gmail', 'phone', 'simple_note',
            'splitwise', 'spotify', 'supervisor', 'todoist', 'venmo')
METHODS = ('get', 'post', 'put', 'patch', 'delete')
DEFAULT_URL = 'http://127.0.0.1:18080'


def _request(url, path, payload=None):
    request = urllib.request.Request(url + path, method='POST' if payload is not None else 'GET',
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def runtime_identity():
    """Bind metadata to the actual local container serving the configured port."""
    url = os.environ.get('WB_APPWORLD_URL', DEFAULT_URL).rstrip('/')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('AppWorld image verification requires a local loopback Docker server')
    container = os.environ.get('WB_APPWORLD_CONTAINER', 'wb-appworld-pinned-v2')
    result = subprocess.run(['docker', 'inspect', '--type', 'container', container],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    if result.returncode:
        raise ValueError('AppWorld runtime container cannot be inspected; set WB_APPWORLD_CONTAINER')
    item, = json.loads(result.stdout)
    port = str(parsed.port or 80)
    bindings = item.get('NetworkSettings', {}).get('Ports', {}).get('8000/tcp') or []
    if not item.get('State', {}).get('Running') or not any(
            binding.get('HostIp') == '127.0.0.1' and binding.get('HostPort') == port
            for binding in bindings):
        raise ValueError('AppWorld inspected container does not own the configured loopback server port')
    identity = _request(url, '/workflowbench-runtime')
    return {**identity, 'image':item['Image'], 'container':item['Name'].lstrip('/'), 'url':url}


def _published_operation(operation, method):
    """Describe this JSON façade's transport while preserving source field schemas."""
    operation = copy.deepcopy(operation)
    body = operation.get('requestBody', {}).get('content', {})
    form = body.pop('application/x-www-form-urlencoded', None)
    if form is not None:
        body['application/json'] = form
        operation['description'] = operation.get('description', '') + (
            '\nThis façade accepts these fields as JSON; the source requester sends the original form-encoded request.')
    if operation.pop('security', None):
        token = {'type':'string', 'description':'Access token returned by this application login operation.'}
        if method in ('get', 'delete'):
            operation.setdefault('parameters', []).append({'name':'access_token', 'in':'query',
                'required':True, 'schema':token})
        else:
            request = operation.setdefault('requestBody', {})
            request['required'] = True
            schema = request.setdefault('content', {}).setdefault('application/json', {}).setdefault('schema', {'type':'object'})
            schema.setdefault('properties', {})['access_token'] = token
            if 'access_token' not in schema.setdefault('required', []):
                schema['required'].append('access_token')
        operation['description'] = operation.get('description', '') + (
            '\nPass access_token as a documented input; the source requester converts it to its original bearer header.')
    if method == 'delete' and operation.get('requestBody'):
        content = operation['requestBody'].get('content', {})
        schema = content.get('application/json', {}).get('schema', {})
        if schema.get('type', 'object') != 'object' or any(key in schema for key in ('$ref', 'allOf', 'oneOf', 'anyOf')):
            raise ValueError('AppWorld DELETE transport requires an inline object input schema')
        parameters = operation.setdefault('parameters', [])
        required = schema.get('required', [])
        for name, field in schema.get('properties', {}).items():
            if any(parameter.get('in') == 'query' and parameter.get('name') == name for parameter in parameters):
                raise ValueError('AppWorld DELETE body/query input names conflict')
            parameters.append({'name':name, 'in':'query', 'required':name in required, 'schema':field})
        operation.pop('requestBody')
        operation['description'] = operation.get('description', '') + (
            '\nThis facade accepts DELETE inputs as query parameters; the source requester preserves their original request arguments.')
    return operation


def _digest_tree(path):
    return {p.relative_to(path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


class _Lock:
    def __init__(self, root, url):
        parsed = urllib.parse.urlsplit(url)
        host = '127.0.0.1' if parsed.hostname == 'localhost' else parsed.hostname
        url = f'{parsed.scheme}://{host}:{parsed.port or 80}'
        directory = Path(tempfile.gettempdir()) / 'workflowbench-appworld-locks'
        directory.mkdir(exist_ok=True)
        self.stream = (directory / (hashlib.sha256(url.encode()).hexdigest() + '.lock')).open('a+b')
        try:
            self.stream.seek(0)
            if not self.stream.read(1):
                self.stream.write(b'0')
                self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('AppWorld server is in use by another attempt') from None

    def close(self):
        if self.stream.closed:
            return
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream, fcntl.LOCK_UN)
        self.stream.close()


class AppWorldWorld:
    artifacts_dir = None
    snapshot0 = None
    tool_calls = ()
    events = ()

    def __init__(self, task, episode_id, frozen_time=None):
        self.task = hydrate_task(task)
        self.episode_id = episode_id
        self.task_id = task['source_ref']['task_id']
        self.root = appworld_root()
        self.url = os.environ.get('WB_APPWORLD_URL', DEFAULT_URL).rstrip('/')
        self.experiment = 'workflowbench-' + uuid.uuid4().hex
        self.output = self.root / 'experiments/outputs' / self.experiment / 'tasks' / self.task_id
        self._lock = _Lock(self.root, self.url)
        self._closed = False
        self._initialized = False
        self._journal = None
        self.tool_calls, self.events = [], []
        try:
            self._specs = {name:json.loads((self.root / 'data/api_docs/openapi' / f'{name}.json').read_text(encoding='utf-8')) for name in SERVICES}
            _request(self.url, '/initialize', {'task_id':self.task_id,
                'experiment_name':self.experiment, 'load_ground_truth':False,
                'raise_on_failure':False, 'parse_datetimes':False,
                'munchify_response':False})
            self._initialized = True
            self.snapshot0 = self.snapshot()
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def _observe(self, tool, arguments, function):
        event = {'sequence':len(self.events), 'kind':'tool', 'tool':tool,
                 'arguments':arguments, 'started_at':datetime.now(timezone.utc).isoformat()}
        self.tool_calls.append({'tool':tool, **arguments})
        self.events.append(event)
        if self._journal:
            self._journal.tool({**event, 'status':'running'})
        try:
            result = function()
            event.update(status='completed', result=result)
            return result
        except Exception as exc:
            event.update(status='error', error=str(exc))
            raise
        finally:
            event['finished_at'] = datetime.now(timezone.utc).isoformat()
            if self._journal:
                self._journal.tool(event, self.snapshot if event['status'] == 'completed' else None)

    def api_search(self, query, top_k=5):
        def search():
            words = re.findall(r'\w+', query.lower())
            hits = []
            for service, doc in self._specs.items():
                for path, operations in doc['paths'].items():
                    for method, operation in operations.items():
                        if method not in METHODS:
                            continue
                        score = sum(word in (path + json.dumps(operation)).lower() for word in words)
                        if score:
                            hits.append((score, {'service':service, 'method':method.upper(),
                                'path':path, 'operation':_published_operation(operation, method)}))
            hits.sort(key=lambda hit:-hit[0])
            return json.dumps([hit[1] for hit in hits[:top_k]])
        return self._observe('api_search', {'query':query, 'top_k':top_k}, search)

    def api_fetch(self, method, url, params=None, body=None):
        return self._observe('api_fetch', {'method':method, 'url':url, 'params':params, 'body':body},
                             lambda:self._call(method, url, params, body))

    def _call(self, method, url, params, body):
        method = method.lower()
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        if not path.startswith('/'):
            path = '/' + path
        service = path.strip('/').split('/')[0]
        if service not in SERVICES:
            return json.dumps({'error':{'code':403, 'message':'Only published application operations are permitted'}})
        if method not in METHODS or not any(method in operations and re.fullmatch(
                re.sub(r'\{[^}]+\}', r'[^/]+', template), path)
                for template, operations in self._specs[service]['paths'].items()):
            return json.dumps({'error':{'code':404, 'message':'Operation is not published'}})
        data = dict(urllib.parse.parse_qsl(parsed.query))
        for raw in (params, body):
            if raw:
                value = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(value, dict):
                    return json.dumps({'error':{'code':400, 'message':'Request data must be a JSON object'}})
                data.update(value)
        # repr of strings plus JSON decoding is a data literal, never executable user code.
        code = f'import json\nprint(json.dumps(requester.{method}({path!r}, data=json.loads({json.dumps(data)!r}), client=requester.client, raise_on_failure=False), default=str))'
        result = _request(self.url, '/execute', {'task_id':self.task_id, 'code':code})['output'].strip()
        try:
            json.loads(result)
            return result
        except (ValueError, TypeError):
            return json.dumps({'error':{'code':500, 'message':result}})

    def base64_encode(self, text):
        return self._observe('base64_encode', {'text':text}, lambda:base64.b64encode(text.encode()).decode())

    def snapshot(self):
        _request(self.url, '/save_state', {'task_id':self.task_id, 'state_id':'workflowbench-snapshot'})
        return canonical(source_call('snapshot', dbs=str(self.output / 'dbs')))

    def finish(self):
        snapshot = self.snapshot()
        if self.artifacts_dir:
            directory = Path(self.artifacts_dir)
            directory.mkdir(parents=True, exist_ok=True)
            evidence = {'task_id':self.task_id, 'experiment':self.experiment,
                'root':str(self.root), 'source_ref':copy.deepcopy(self.task['source_ref']),
                'files':_digest_tree(self.output / 'dbs'),
                'snapshot_sha256':hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()}
            (directory / 'appworld-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        return snapshot

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._initialized:
                _request(self.url, '/close', {'task_id':self.task_id})
        finally:
            self._lock.close()

    def attach_journal(self, directory):
        if self._journal or self.events:
            raise RuntimeError('attach the journal before any tool use and only once')
        from wb_results.evidence import AttemptJournal
        self._journal = AttemptJournal(outside_repository(directory), self.snapshot0)

    def record_agent_event(self, entry):
        if self._journal:
            self._journal.agent(entry)

    def interfaces(self):
        return _Interfaces(self._specs)

    @classmethod
    def service_names(cls):
        return list(SERVICES)

    @classmethod
    def runtime_identity(cls):
        return runtime_identity()

    @classmethod
    def prerequisites(cls):
        try:
            root = appworld_root()
            version = source_call('version')['version']
            if version != '0.1.3.post1':
                return ['AppWorld isolated source interpreter must use distribution 0.1.3.post1']
            if not (root / 'data/version.txt').is_file():
                return ['AppWorld installed data bundle is missing']
            runtime = runtime_identity()
            if runtime.get('version') != version:
                return ['AppWorld environment server and isolated source evaluator distribution versions differ']
            if runtime.get('data_version') != (root / 'data/version.txt').read_text(encoding='utf-8').strip():
                return ['AppWorld environment server and local data bundle versions differ']
            return []
        except Exception as exc:
            return [f'AppWorld needs its isolated Python, installed external data root and environment server: {exc}']

    @classmethod
    def positive_check(cls, task, snapshot0, snapshot1, artifacts=None):
        evidence_path = Path(artifacts) / 'appworld-evidence.json' if artifacts else None
        if evidence_path is None or not evidence_path.is_file():
            raise FileNotFoundError('AppWorld source evidence was not stored; attempt is ungraded')
        evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
        root = outside_repository(evidence['root'])
        if evidence['task_id'] != task['source_ref']['task_id'] or evidence['source_ref'] != task['source_ref']:
            raise ValueError('AppWorld source evidence belongs to a different frozen task')
        output = root / 'experiments/outputs' / evidence['experiment'] / 'tasks' / evidence['task_id']
        if not evidence['files'] or _digest_tree(output / 'dbs') != evidence['files']:
            raise ValueError('AppWorld source evidence changed after the attempt')
        if hashlib.sha256(json.dumps(snapshot1, sort_keys=True).encode()).hexdigest() != evidence['snapshot_sha256']:
            raise ValueError('AppWorld source evidence snapshot changed after the attempt')
        hydrate_task(task, verify_runtime=False)  # Offline: recheck source files/evaluator, not a live world.
        result = source_call('evaluate', root=str(root), task_id=evidence['task_id'], experiment=evidence['experiment'])
        passes = [row for row in result.get('passes', []) if row.get('label') == 'no_op_pass']
        failures = [row for row in result.get('failures', []) if row.get('label') == 'no_op_pass']
        return PositiveResult(bool(result.get('success')), result, 'AppWorld evaluate_task',
            {'passed':not failures, 'passes':passes, 'failures':failures})


class _Interfaces:
    def __init__(self, documents):
        self.documents = documents

    def services(self):
        return list(self.documents)

    def spec(self, service, public_url):
        document = copy.deepcopy(self.documents[service])
        document['servers'] = [{'url':f'{public_url}/{service}'}]
        # Native source paths already include the app prefix. Remove it only in
        # the front-door document, then put it back at routing time.
        prefix = f'/{service}'
        document['paths'] = {path[len(prefix):] if path.startswith(prefix + '/') else path:
                             {method:_published_operation(operation, method) if method in METHODS else operation
                              for method, operation in operations.items()}
                             for path, operations in document['paths'].items()}
        return document

    def rest_url(self, service, rest):
        return f'/{service}/{rest}'
