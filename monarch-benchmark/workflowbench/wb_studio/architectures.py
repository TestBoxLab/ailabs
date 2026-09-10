"""Resolve and freeze the official Enterprise baseline; custom definitions remain inert drafts.

Resolution happens at an explicit refresh or a new stock run, never during
execution or resume: the resolved commit and lockfile blob are frozen into a
runtime manifest, and a later refresh writes a new baseline rather than moving
an old one. Resolution proves that a revision exists; it does not build,
launch or verify that any build serves requests.
"""
from datetime import datetime, timezone
import json
import re
import subprocess
from wb_arms import runtime_manifest as rm
from wb_results.evidence import write_json

REPOSITORY = 'TestBoxLab/monarch'
DIRECTORY = 'monarch-enterprise'
LOCKFILE = 'pnpm-lock.yaml'
SHA = re.compile('[0-9a-f]{40}')

def _gh(path):
    proc = subprocess.run(['gh','api',path],capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
    return json.loads(proc.stdout)

def resolve_default():
    try:
        commit = _gh(f'repos/{REPOSITORY}/commits/main')['sha']
        if not isinstance(commit,str) or not SHA.fullmatch(commit): raise ValueError()
        blob = _gh(f'repos/{REPOSITORY}/contents/{LOCKFILE}?ref={commit}')['sha']
        if not isinstance(blob,str) or not SHA.fullmatch(blob): raise ValueError()
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
        raise ValueError('Cannot verify the latest Monarch Enterprise revision on GitHub. Check GitHub access and try again.') from None
    verified_at = datetime.now(timezone.utc).isoformat()
    lockfile = {'path':LOCKFILE,'git_blob':blob}
    manifest = rm.freeze(rm.build('default-monarch-enterprise',
        source={'kind':'git','repository':'https://github.com/'+REPOSITORY,'directory':DIRECTORY,'ref':'main','commit':commit,
                'patch_sha256':None,'lockfile':lockfile,'image_digest':None},
        runtime={'entrypoint':None,'dependency_closure':[{'path':LOCKFILE,'git_blob':blob}],
                 'note':'No benchmark build recipe exists yet; upstream docker-compose mounts host paths and the Docker socket and must be reduced to the benchmark boundary first.'},
        evaluation={'track':'create-and-run','provider':'bedrock','model':'claude-opus-4-8','effort':'default',
                    'harness':'monarch-enterprise-operator','harness_version':commit,
                    'settings':{'note':'Stock defaults (ANTHROPIC_MODEL=claude-opus-4-8, OPERATOR_MAX_STEPS=40); the deployed environment decides, no per-run override exists.'}},
        readiness_record=rm.readiness('resolved','not_applicable','adapter_required',
            ['No pinned Enterprise build serves requests yet: adapter, required services and Bedrock billing are unverified.']),
        notes='Stock product identity. Experimental forks and historical reproductions are separate identities.'))
    return {'id':'default-monarch-enterprise','kind':'default','name':'Default Monarch Enterprise',
            'repository':'https://github.com/'+REPOSITORY,'directory':DIRECTORY,'ref':'main','commit':commit,'lockfile':lockfile,
            'url':f'https://github.com/{REPOSITORY}/tree/{commit}/{DIRECTORY}','verified_at':verified_at,
            'readiness':manifest['readiness'],'runtime_manifest':manifest}

def pinned(baseline):
    """The identity-bearing subset a published node carries: no timestamps, no readiness."""
    return {k:baseline.get(k) for k in ('id','kind','name','repository','directory','ref','commit','lockfile','url')}

def cached_default(studio):
    """The last frozen resolution, or None; never contacts GitHub."""
    path=studio.directory/'enterprise-baseline.json'
    if not path.exists(): return None
    value=json.loads(path.read_text(encoding='utf-8'))
    return value if 'runtime_manifest' in value else None

def default_status(studio,refresh=False):
    if not refresh:
        cached=cached_default(studio)
        if cached is not None: return cached
    value=resolve_default()
    write_json(studio.directory/'enterprise-baseline.json',value)
    return value

def normalize_architecture(studio,value):
    if not isinstance(value,dict): raise ValueError('Choose an architecture')
    if value.get('kind')=='default':
        return default_status(studio,refresh=True)
    if value.get('kind')!='custom': raise ValueError('Choose Default Monarch Enterprise or a custom architecture')
    name,definition=value.get('name'),value.get('definition')
    if not isinstance(name,str) or not name.strip() or len(name)>100: raise ValueError('Give your custom architecture a name (up to 100 characters)')
    if name.strip().casefold()=='default monarch enterprise': raise ValueError('Choose a distinct name for your custom architecture')
    if not isinstance(definition,str) or not definition.strip() or len(definition)>30000: raise ValueError('Describe your architecture in up to 30,000 characters')
    return {'kind':'custom','name':name.strip(),'definition':definition}


def sync_default(studio):
    """Resolve upstream main and retain source identity metadata per commit, without mutating deployments."""
    value = resolve_default()
    with studio.lock:
        previous = cached_default(studio)
        if previous and previous.get('commit') == value['commit']:
            return {'changed': False, 'message': 'Already up to date with GitHub main.', 'baseline': previous}
        history = studio.directory / 'enterprise-source-versions'
        history.mkdir(parents=True, exist_ok=True)
        for record in (previous, value):
            if record and SHA.fullmatch(record.get('commit', '')):
                target = history / (record['commit'] + '.json')
                if not target.exists():write_json(target, record)
        write_json(studio.directory / 'enterprise-baseline.json', value)
        return {'changed': True, 'message': 'Source synced to ' + value['commit'][:12] + '. Verify the deployed runtime before launching.', 'baseline': value}
