"""Own synthetic records only; no AppWorld task or interface content is redistributed."""
import json
from pathlib import Path

import pytest

from wb_worlds.appworld import importer


def source(tmp_path, monkeypatch):
    root = tmp_path / 'private'
    data = root / 'data'
    (data / 'datasets').mkdir(parents=True)
    (data / 'datasets/dev.txt').write_text('sample_1\nsample_2\n')
    (data / 'datasets/train.txt').write_text('sample_1\n')
    (data / 'base_dbs').mkdir()
    (data / 'base_dbs/notes.db').write_bytes(b'own synthetic seed')
    (data / 'api_docs/openapi').mkdir(parents=True)
    (data / 'api_docs/openapi/notes.json').write_text('{}')
    for task_id in ('sample_1', 'sample_2'):
        task = data / 'tasks' / task_id
        (task / 'ground_truth').mkdir(parents=True)
        (task / 'ground_truth/solution.py').write_text('# own synthetic reference\n')
        (task / 'specs.json').write_text(json.dumps({'instruction':'Private source request',
            'supervisor': {'first_name': 'Test'}, 'datetime':'2023-01-01T00:00:00'}))
    monkeypatch.setenv('APPWORLD_ROOT', str(root))
    monkeypatch.setattr(importer, 'installed_version', lambda root=None: '0.1.3.post1')
    return root


@pytest.mark.parametrize('split', ['test_normal', 'test_challenge'])
def test_test_splits_are_refused_before_writing(tmp_path, split):
    with pytest.raises(ValueError, match='reference solutions'):
        importer.import_tasks(split, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('split', ['train', 'dev'])
def test_import_writes_only_identifiers_and_hashes(tmp_path, monkeypatch, split):
    source(tmp_path, monkeypatch)
    out = tmp_path / 'out'
    tasks = importer.import_tasks(split, out, limit=1)
    raw = next(out.glob('*.json')).read_text()
    assert 'Private source request' not in raw
    assert 'synthetic reference' not in raw
    assert tasks[0]['prompt'] == ''
    assert tasks[0]['source_ref']['task_id'] == 'sample_1'
    assert tasks[0]['info']['world']['version'] == '0.1.3.post1'
    hydrated = importer.hydrate_task(tasks[0])
    assert hydrated['prompt'][1]['content'].startswith('Private source request')
    assert hydrated['contract_sha256'] == tasks[0]['contract_sha256']
    assert tasks[0]['prompt'] == ''


def test_changed_source_is_refused_during_hydration(tmp_path, monkeypatch):
    root = source(tmp_path, monkeypatch)
    task = importer.import_tasks('dev', tmp_path / 'out', limit=1)[0]
    (root / 'data/tasks/sample_1/ground_truth/solution.py').write_text('# edited source')
    with pytest.raises(ValueError, match='source.*changed'):
        importer.hydrate_task(task)


def test_data_root_inside_public_repository_is_refused(monkeypatch):
    monkeypatch.setenv('APPWORLD_ROOT', str(importer.REPOSITORY_ROOT / 'private-data'))
    with pytest.raises(ValueError, match='outside'):
        importer.appworld_root()


def test_reviewed_no_change_rules_are_preserved(tmp_path, monkeypatch):
    source(tmp_path, monkeypatch)
    rules = {'sample_1': {'expected_changes': [], 'allowed_changes': [],
                          'approval_rule_reviewed': {'by': 'operator', 'basis': 'read-only'}}}
    task = importer.import_tasks('dev', tmp_path / 'out', limit=1, reviewed_rules=rules)[0]
    assert task['info']['expected_changes'] == []
    assert task['info']['approval_rule_reviewed']['basis'] == 'read-only'


def test_frozen_runtime_image_drift_refuses_execution_but_allows_offline_hydration(tmp_path, monkeypatch):
    source(tmp_path, monkeypatch)
    from wb_worlds.appworld import adapter
    original = 'sha256:' + 'a' * 64
    task = importer.import_tasks('dev', tmp_path / 'out', limit=1, runtime_image=original)[0]
    monkeypatch.setattr(adapter, 'runtime_identity', lambda: {'image':'sha256:' + 'b' * 64})
    with pytest.raises(ValueError, match='runtime image changed'):
        importer.hydrate_task(task)
    restored = importer.hydrate_task(task, verify_runtime=False)
    assert restored['source_ref']['runtime_image'] == original
    assert restored['prompt'][1]['content'].startswith('Private source request')
