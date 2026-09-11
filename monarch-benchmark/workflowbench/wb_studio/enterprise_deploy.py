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
