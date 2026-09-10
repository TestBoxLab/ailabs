"""Build immutable official Enterprise images in an isolated source tree.

Image verification is not a serving-runtime verification. Candidates stay blocked
until stock auth/queue services and the no-spend Enterprise probe are configured.
No source, host secret, grader or Docker socket is mounted into a candidate.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import uuid
import zipfile
from wb_results.evidence import write_json
from .architectures import REPOSITORY, SHA, resolve_default

TARGETS = {'auth': ('monarch-auth/Dockerfile', 'builder'), 'backend': ('monarch-enterprise/Dockerfile', 'backend-production'),
           'orchestrator': ('monarch-enterprise/Dockerfile', 'orchestrator-production'),
           'web': ('monarch-enterprise/Dockerfile', 'web-production'),
           'fdapi': ('feature-discovery/api/Dockerfile', 'runtime')}
BLOCKERS = ['Stock auth vault and engine queues need an isolated deployment recipe.',
            'FD dispatch needs a trusted broker isolated from evaluated workloads.',
            'Session, frozen knowledge-base and trace verification must pass before activation.']

def now(): return datetime.now(timezone.utc).isoformat()

def extract_archive(data, destination, expected_lockfile):
    """Validate the whole archive before writing; preserve the exact pinned lockfile."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries, roots, seen = [], set(), set()
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename:
                raise ValueError('Unsafe source archive path')
            if stat.S_ISLNK(item.external_attr >> 16): raise ValueError('Source archive contains a symbolic link')
            roots.add(path.parts[0])
            if len(path.parts) == 1 or item.is_dir(): continue
            relative = Path(*path.parts[1:])
            key = relative.as_posix().casefold()
            if key in seen: raise ValueError('Duplicate source archive path')
            seen.add(key)
            entries.append((relative, item))
        if len(roots) != 1: raise ValueError('Ambiguous source archive root')
        locks = [item for path, item in entries if path.as_posix() == 'pnpm-lock.yaml']
        if len(locks) != 1: raise ValueError('Missing source lockfile')
        lock = archive.read(locks[0])
        if hashlib.sha1(b'blob ' + str(len(lock)).encode() + b'\0' + lock).hexdigest() != expected_lockfile:
            raise ValueError('Source lockfile does not match frozen GitHub revision')
        destination.mkdir(parents=True, exist_ok=False)
        for relative, item in entries:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
    return hashlib.sha256(data).hexdigest()

def serialized(operation):
    def run(manager, identifier, *args, **kwargs):
        lock = manager._path(identifier) / 'operation.lock'
        try:
            handle = lock.open('x')
        except FileExistsError:
            raise ValueError('A candidate operation is already running. If its process exited, inspect its logs before clearing operation.lock.') from None
        try:
            handle.write(str(__import__('os').getpid()))
            handle.close()
            return operation(manager, identifier, *args, **kwargs)
        finally:
            handle.close()
            lock.unlink(missing_ok=True)
    return run

class DeploymentManager:
    def __init__(self, directory):
        self.root = Path(directory) / 'enterprise-deployments'
        self.root.mkdir(parents=True, exist_ok=True)
    def _path(self, identifier):
        if not re.fullmatch(r'[0-9a-f]{40}-[0-9a-f]{12}', identifier): raise ValueError('Invalid deployment ID')
        return self.root / identifier
    def status(self, identifier=None):
        if identifier: return json.loads((self._path(identifier) / 'deployment.json').read_text(encoding='utf-8'))
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(self.root.glob('*/deployment.json'), reverse=True)]
    def prepare(self, baseline=None):
        baseline = baseline or resolve_default()
        commit, blob = baseline.get('commit', ''), baseline.get('lockfile', {}).get('git_blob', '')
        if baseline.get('repository') != 'https://github.com/' + REPOSITORY or not SHA.fullmatch(commit) or not SHA.fullmatch(blob):
            raise ValueError('Verified official source revision and lockfile required')
        identifier = commit + '-' + uuid.uuid4().hex[:12]
        directory = self._path(identifier)
        directory.mkdir()
        record = dict(id=identifier, commit=commit, lockfile_git_blob=blob, repository=baseline['repository'],
                      created_at=now(), state='downloading', images={}, launchable=False, blockers=BLOCKERS.copy())
        write_json(directory / 'deployment.json', record)
        try:
            result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/zipball/{commit}'], capture_output=True, timeout=180, check=True)
            record['archive_sha256'] = extract_archive(result.stdout, directory / 'source', blob)
            record['state'] = 'source_ready'
        except Exception as error:
            record.update(state='source_failed', error=type(error).__name__)
            raise
        finally:
            record['updated_at'] = now()
            write_json(directory / 'deployment.json', record)
        return record
    @serialized
    def build(self, identifier, services=None):
        directory, record = self._path(identifier), self.status(identifier)
        services = list(services or TARGETS)
        if not services or any(name not in TARGETS for name in services): raise ValueError('Unknown build target')
        if record['state'] not in ('source_ready', 'build_failed', 'built', 'smoke_verified'): raise ValueError('Source not ready')
        subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True, check=True, timeout=20)
        try:
            for name in services:
                dockerfile, target = TARGETS[name]
                record.update(state='building', building=name, updated_at=now())
                write_json(directory / 'deployment.json', record)
                tag, iidfile = f'ailabs-enterprise-{name}:{identifier}', directory / (name + '.iid')
                with (directory / (name + '.build.log')).open('wb') as log:
                    subprocess.run(['docker', 'build', '--progress=plain', '--file', dockerfile, '--target', target,
                                    '--label', 'org.opencontainers.image.revision=' + record['commit'], '--tag', tag,
                                    '--iidfile', str(iidfile.resolve()), '.'], cwd=directory / 'source', stdout=log,
                                   stderr=subprocess.STDOUT, check=True, timeout=2400)
                digest = iidfile.read_text().strip()
                if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest): raise ValueError('Missing immutable image ID')
                record['images'][name] = dict(image_id=digest, tag=tag, target=target)
            record['state'] = 'built'
        except Exception as error:
            record.update(state='build_failed', error=type(error).__name__)
            raise
        finally:
            record.pop('building', None)
            record['updated_at'] = now()
            write_json(directory / 'deployment.json', record)
        return record
    @serialized
    def verify_images(self, identifier):
        directory, record = self._path(identifier), self.status(identifier)
        if not record['images']: raise ValueError('Build images before verification')
        probes = {}
        for name, image in record['images'].items():
            inspected = json.loads(subprocess.run(['docker', 'image', 'inspect', image['image_id']], capture_output=True,
                                                 text=True, check=True, timeout=20).stdout)[0]
            revision = (inspected.get('Config', {}).get('Labels') or {}).get('org.opencontainers.image.revision')
            if inspected['Id'] != image['image_id'] or revision != record['commit']: raise ValueError('Image source mismatch')
            result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                                     '--security-opt', 'no-new-privileges', '--pids-limit', '64', '--memory', '256m',
                                     '--cpus', '1', '--entrypoint', 'node', image['image_id'], '--version'],
                                    capture_output=True, text=True, check=True, timeout=30)
            probes[name] = dict(node_version=result.stdout.strip(), image_id=image['image_id'], verified_at=now())
        record.update(state='smoke_verified', image_probes=probes, launchable=False, updated_at=now())
        write_json(directory / 'deployment.json', record)
        return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('action', choices=['prepare', 'build', 'verify', 'status'])
    parser.add_argument('--id')
    parser.add_argument('--service', action='append', choices=list(TARGETS))
    args = parser.parse_args()
    manager = DeploymentManager(args.directory)
    if args.action in ('build', 'verify') and not args.id: parser.error('--id is required')
    result = {'prepare': lambda: manager.prepare(), 'build': lambda: manager.build(args.id, args.service),
              'verify': lambda: manager.verify_images(args.id), 'status': lambda: manager.status(args.id)}[args.action]()
    print(json.dumps(result, indent=2))



def candidate_compose(record, postgres_image, localstack_image, password, session_secret):
    """A private no-provider candidate; no source mounts or shared databases."""
    backend_image = record['images']['backend']['image_id']
    environment = {'NODE_ENV': 'development', 'HOST': '0.0.0.0', 'PORT': '4174',
        'DATABASE_URL': 'postgresql://monarch_app:' + password + '@postgres:5432/feature_discovery',
        'BOOTSTRAP_DATABASE_URL': 'postgresql://fd_app:' + password + '@postgres:5432/feature_discovery',
        'SESSION_SECRET': session_secret, 'SEED_ADMIN_PASSWORD': password,
        'FD_API_URL': 'http://fdapi:3000', 'AWS_ENDPOINT_URL': 'http://localstack:4566',
        'AWS_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'test', 'AWS_SECRET_ACCESS_KEY': 'test',
        'ENGINE_RUN_QUEUE_URL': 'http://localstack:4566/000000000000/monarch-enterprise-engine-runs.fifo',
        'OTEL_RESOURCE_ATTRIBUTES': 'service.version=' + record['commit']}
    restricted = {'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'pids_limit': 256,
                  'mem_limit': '2g', 'cpus': 2}
    services = {
        'postgres': {'image': postgres_image, 'environment': {'POSTGRES_DB': 'feature_discovery',
            'POSTGRES_USER': 'fd_app', 'POSTGRES_PASSWORD': password},
            'volumes': ['candidate-db:/var/lib/postgresql/data'],
            'healthcheck': {'test': ['CMD', 'pg_isready', '-U', 'fd_app', '-d', 'feature_discovery'], 'interval': '2s', 'timeout': '3s', 'retries': 40}},
        'localstack': {'image': localstack_image, 'environment': {'SERVICES': 'sqs,s3,dynamodb,secretsmanager',
            'AWS_DEFAULT_REGION': 'us-east-1'}, 'mem_limit': '2g',
            'healthcheck': {'test': ['CMD', 'curl', '-sf', 'http://127.0.0.1:4566/_localstack/health'], 'interval': '3s', 'timeout': '5s', 'retries': 40}},
        'migrate': {**restricted, 'image': backend_image, 'environment': environment,
            'depends_on': {'postgres': {'condition': 'service_healthy'}},
            'command': ['sh', '-c', 'cd monarch-enterprise/apps/backend && pnpm db:bootstrap && pnpm db:migrate && pnpm db:seed']},
        'backend': {**restricted, 'image': backend_image, 'environment': environment,
            'depends_on': {'migrate': {'condition': 'service_completed_successfully'}},
            'healthcheck': {'test': ['CMD', 'node', '-e', "fetch('http://127.0.0.1:4174/api').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],
                            'interval': '3s', 'timeout': '5s', 'retries': 40}},
    }
    if 'fdapi' in record['images']:
        fd_environment = {'DATABASE_URL': 'postgresql://fd_app:' + password + '@postgres:5432/feature_discovery',
                          'HOST': '0.0.0.0', 'PORT': '3000', 'NODE_ENV': 'production'}
        services['fd-migrate'] = {**restricted, 'image': record['images']['fdapi']['image_id'],
            'environment': fd_environment, 'command': ['node', 'dist/migrate.js'],
            'depends_on': {'postgres': {'condition': 'service_healthy'}}}
        services['fdapi'] = {**restricted, 'image': record['images']['fdapi']['image_id'],
            'environment': fd_environment, 'depends_on': {'fd-migrate': {'condition': 'service_completed_successfully'}}}
    return {'name': 'ailabs-' + record['id'][-12:], 'services': services,
            'networks': {'default': {'internal': True}}, 'volumes': {'candidate-db': {}}}


@serialized
def start_candidate(manager, identifier):
    """Start isolated backend/DB/queues for no-spend verification; retain prior candidates."""
    import secrets
    directory, record = manager._path(identifier), manager.status(identifier)
    if 'backend' not in record['images']: raise ValueError('Build the stock backend first')
    if (directory / 'candidate.compose.json').exists(): raise ValueError('Candidate already configured; inspect or stop it before creating another')
    images = {}
    for name, reference in [('postgres', 'pgvector/pgvector:pg16'), ('localstack', 'localstack/localstack:4')]:
        subprocess.run(['docker', 'pull', reference], check=True, capture_output=True, timeout=300)
        images[name] = json.loads(subprocess.run(['docker', 'image', 'inspect', reference], capture_output=True,
                                  text=True, check=True, timeout=20).stdout)[0]['Id']
    compose = candidate_compose(record, images['postgres'], images['localstack'], secrets.token_hex(24), secrets.token_hex(32))
    path = directory / 'candidate.compose.json'
    write_json(path, compose)
    record.update(candidate={'project': compose['name'], 'state': 'starting', 'dependency_images': images}, updated_at=now())
    write_json(directory / 'deployment.json', record)
    try:
        with (directory / 'candidate.start.log').open('wb') as log:
            subprocess.run(['docker', 'compose', '-f', str(path.resolve()), 'up', '-d', '--wait', '--wait-timeout', '180', 'backend', 'localstack'],
                           stdout=log, stderr=subprocess.STDOUT, timeout=240, check=True)
        record['candidate']['state'] = 'backend_healthy'
        record['candidate']['backend_url'] = None
        record['candidate']['network_access'] = 'Internal only; gateway not configured'
    except Exception as error:
        record['candidate'].update(state='failed', error=type(error).__name__)
        raise
    finally:
        record['updated_at'] = now()
        write_json(directory / 'deployment.json', record)
    return record

# Adapter is trusted local infrastructure: forwards AWS calls only to the private
# LocalStack endpoint and invokes the exact stock auth handler. No Docker API.
AWS_ADAPTER = r'''
const http = require('http');
const {handler} = require('/app/monarch-auth/packages/server/dist/handler.js');
http.createServer(async (req,res)=>{
  if (/^\/2015-03-31\/functions\/(?:arn[^/]*|monarch-auth-api)\/invocations$/.test(req.url)) {
    let chunks=[], size=0;
    for await (const chunk of req) { size+=chunk.length; if(size>1048576){res.writeHead(413);res.end();return;} chunks.push(chunk); }
    try { const answer=await handler(JSON.parse(Buffer.concat(chunks).toString())); res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(answer)); }
    catch(e) { res.writeHead(200,{'Content-Type':'application/json','X-Amz-Function-Error':'Unhandled'});res.end(JSON.stringify({errorType:e.name,errorMessage:e.message})); }
    return;
  }
  const upstream=http.request({hostname:'localstack',port:4566,path:req.url,method:req.method,headers:{...req.headers,host:'localstack:4566'}}, reply=>{res.writeHead(reply.statusCode,reply.headers);reply.pipe(res);});
  upstream.on('error',()=>{res.writeHead(502);res.end('Local AWS service unavailable');});req.pipe(upstream);
}).listen(4566,'0.0.0.0');
'''

@serialized
def configure_services(manager, identifier):
    """Add stock FD, auth and orchestrator to the private candidate; provision queues."""
    directory, record = manager._path(identifier), manager.status(identifier)
    required = {'backend', 'auth', 'fdapi', 'orchestrator'}
    if not required.issubset(record['images']): raise ValueError('Build backend, auth, FD and orchestrator images first')
    path = directory / 'candidate.compose.json'
    old = json.loads(path.read_text())
    env = old['services']['backend']['environment']
    compose = candidate_compose(record, old['services']['postgres']['image'], old['services']['localstack']['image'],
                                env['SEED_ADMIN_PASSWORD'], env['SESSION_SECRET'])
    adapter = directory / 'aws-adapter'
    adapter.mkdir(exist_ok=True)
    (adapter / 'server.cjs').write_text(AWS_ADAPTER)
    (adapter / 'Dockerfile').write_text('FROM ' + record['images']['auth']['image_id'] + '\nCOPY server.cjs /server.cjs\nCMD ["node", "/server.cjs"]\n')
    iid = adapter / 'image.iid'
    with (adapter / 'build.log').open('wb') as log:
        subprocess.run(['docker','build','--iidfile',str(iid.resolve()),'.'],cwd=adapter,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    auth_environment = {'AWS_ENDPOINT_URL':'http://localstack:4566', 'AWS_REGION':'us-east-1',
                        'AWS_ACCESS_KEY_ID':'test','AWS_SECRET_ACCESS_KEY':'test',
                        'CREDENTIALS_TABLE':'monarch-auth-credentials','DATASTORES_TABLE':'monarch-auth-datastores',
                        'ACCOUNTS_TABLE':'monarch-auth-accounts'}
    compose['services']['aws'] = {'image':iid.read_text().strip(), 'environment':auth_environment,
        'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],'pids_limit':128,'mem_limit':'1g'}
    environment = compose['services']['backend']['environment']
    environment.update(AWS_ENDPOINT_URL='http://aws:4566', MONARCH_AUTH_FUNCTION_ARN='arn:aws:lambda:us-east-1:000000000000:function:monarch-auth-api',
                       ENGINE_HOST_SECRET=__import__('base64').b64encode(__import__('secrets').token_bytes(32)).decode())
    compose['services']['orchestrator'] = {'image':record['images']['orchestrator']['image_id'],
        'environment':{**environment,'ENGINE_API_URL':'http://backend:4174/api'},'cap_drop':['ALL'],
        'security_opt':['no-new-privileges:true'],'mem_limit':'2g','pids_limit':256,
        'depends_on':{'backend':{'condition':'service_healthy'}}}
    write_json(path,compose)
    prefix=['docker','compose','-f',str(path.resolve())]
    with (directory / 'candidate.services.log').open('wb') as log:
        subprocess.run(prefix+['up','-d','--wait','--wait-timeout','120'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        localstack=subprocess.run(prefix+['ps','-q','localstack'],capture_output=True,text=True,check=True,timeout=20).stdout.strip()
        for source in ('infra/localstack/init/ready.d/01-create-dynamodb.sh','monarch-enterprise/infra/localstack/init/ready.d/01-engine-runs.sh'):
            subprocess.run(['docker','cp',str((directory/'source'/source).resolve()),localstack+':/tmp/provision.sh'],check=True,capture_output=True,timeout=20)
            subprocess.run(['docker','exec',localstack,'bash','/tmp/provision.sh'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    record.update(candidate={**record.get('candidate',{}),'state':'services_started','aws_adapter_image':iid.read_text().strip()},updated_at=now())
    record['blockers']=['FD discovery dispatch and execution worker are not configured.', 'Frozen KB, trace collector, Bedrock credentials and billing verification are still required.']
    write_json(directory / 'deployment.json', record)
    return record
