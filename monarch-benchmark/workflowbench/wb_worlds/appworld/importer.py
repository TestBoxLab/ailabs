"""Identifier-only AppWorld imports. Source content stays outside the public checkout."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SUPPORTED_SPLITS = ('train', 'dev')


def outside_repository(path: str | Path) -> Path:
    path = Path(path).resolve()
    if path.is_relative_to(REPOSITORY_ROOT):
        raise ValueError('AppWorld content and evidence must live outside the public repository')
    return path


def appworld_root(root=None) -> Path:
    value = root or os.environ.get('APPWORLD_ROOT')
    if not value:
        raise ValueError('set APPWORLD_ROOT to the installed data root outside this repository')
    return outside_repository(value)


def source_call(operation: str, **arguments):
    """Keep the source's pydantic 1 environment separate from WorkflowBench."""
    python = os.environ.get('WB_APPWORLD_PYTHON')
    if not python or not Path(python).is_file():
        raise ValueError('set WB_APPWORLD_PYTHON to the isolated AppWorld Python interpreter')
    request = {'operation': operation, 'root': str(appworld_root(arguments.pop('root', None))), **arguments}
    result = subprocess.run([python, str(Path(__file__).with_name('source_worker.py'))],
        input=json.dumps(request), capture_output=True, text=True, encoding='utf-8',
        timeout=180, env={**os.environ, 'PYTHONUTF8':'1', 'PYTHONDONTWRITEBYTECODE':'1'})
    if result.returncode:
        raise RuntimeError(f'AppWorld source worker failed: {result.stderr[-4000:]}')
    marker = 'WORKFLOWBENCH_RESULT='
    lines = [line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise RuntimeError('AppWorld source worker did not produce exactly one result')
    return json.loads(lines[0])


def installed_version(root=None) -> str:
    return source_call('version', root=root)['version']


def _identifier(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError(f'invalid AppWorld task identifier: {value!r}')
    return value


def fingerprint(root: Path, task_id: str) -> str:
    """Pin the task, evaluator, reference, base data and published API documents."""
    roots = [root / 'data/tasks' / _identifier(task_id), root / 'data/base_dbs',
             root / 'data/api_docs', root / 'data/version.txt']
    digest = hashlib.sha256()
    for location in roots:
        paths = sorted(location.rglob('*')) if location.is_dir() else [location]
        for path in paths:
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b'\0')
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
    return digest.hexdigest()


def import_tasks(split: str, out: str | Path, limit: int | None = None, *,
                 root=None, reviewed_rules: dict | None = None, task_ids: list[str] | None = None, runtime_image: str | None = None) -> list[dict]:
    if split not in SUPPORTED_SPLITS:
        raise ValueError(f'AppWorld split {split!r} is refused: test_normal and test_challenge '
                         'do not publish reference solutions; use train or dev')
    if runtime_image is not None and not re.fullmatch(r'sha256:[0-9a-f]{64}', runtime_image):
        raise ValueError('AppWorld runtime_image must be an immutable Docker image digest')
    if limit is not None and limit < 1:
        raise ValueError('limit must be positive')
    root = appworld_root(root)
    ids = (root / 'data/datasets' / f'{split}.txt').read_text(encoding='utf-8').splitlines()
    ids = [_identifier(item.strip()) for item in ids if item.strip()]
    if task_ids is not None:
        if not task_ids or len(set(task_ids)) != len(task_ids) or not set(task_ids) <= set(ids):
            raise ValueError('requested AppWorld task identifiers must be distinct members of the selected split')
        ids = [_identifier(item) for item in task_ids]
    ids = ids[:limit]
    version = installed_version(root)
    tasks = []
    for task_id in ids:
        location = root / 'data/tasks' / task_id
        if not (location / 'ground_truth/solution.py').is_file():
            raise ValueError(f'AppWorld task {task_id} has no published reference solution')
        source_hash = fingerprint(root, task_id)
        info = {'world': {'package':'appworld', 'version':version,
                         'revision':(root / 'data/version.txt').read_text(encoding='utf-8').strip() if (root / 'data/version.txt').is_file() else version, 'split':split}}
        if reviewed_rules and task_id in reviewed_rules:
            rule = reviewed_rules[task_id]
            if not rule.get('approval_rule_reviewed'):
                raise ValueError(f'{task_id}: permitted changes need an explicit review record')
            info.update(copy.deepcopy(rule))
        task = {'task': f'appworld.{task_id}', 'prompt':'', 'info':info,
                'source_ref': {'task_id':task_id, 'split':split, 'content_sha256':source_hash}}
        if runtime_image:
            task['source_ref']['runtime_image'] = runtime_image
        from wb_world.episode import contract_hash
        task['contract_sha256'] = contract_hash(task)
        tasks.append(task)
    output = Path(out)
    # Build every manifest before touching output, then refuse overwriting history.
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'AppWorld import output is not empty: {output}')
    output.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        (output / f"{task['task']}.json").write_text(
            json.dumps(task, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    return tasks


def hydrate_task(task: dict, *, verify_runtime: bool = True) -> dict:
    """Call immediately before the competitor runs; keep the stored manifest hashed."""
    root = appworld_root()
    ref = task['source_ref']
    task_id = _identifier(ref['task_id'])
    world = task['info']['world']
    if verify_runtime and ref.get('runtime_image'):
        from .adapter import runtime_identity
        if runtime_identity()['image'] != ref['runtime_image']:
            raise ValueError('AppWorld runtime image changed; refusing the frozen task')
    if installed_version(root) != world['version']:
        raise ValueError('AppWorld installed source version changed; refusing the frozen task')
    if fingerprint(root, task_id) != ref['content_sha256']:
        raise ValueError('AppWorld source content changed; refusing the frozen task')
    specs = json.loads((root / 'data/tasks' / task_id / 'specs.json').read_text(encoding='utf-8'))
    result = copy.deepcopy(task)
    result['prompt'] = (specs['instruction'] + '\n\nTask-authorized context:\n' + json.dumps({
        'supervisor': specs.get('supervisor', specs.get('main_user')),
        'datetime': specs['datetime']}, ensure_ascii=False))
    result['prompt'] = [{'role':'system', 'content':'Use the published application APIs to fulfill the user request. Complete the task using the supervisor completion operation when finished.'}, {'role':'user', 'content':result['prompt']}]
    return result
