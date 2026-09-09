"""Focused source and build lifecycle regressions; no network or model calls."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import zipfile
import pytest
from wb_studio.enterprise_deploy import DeploymentManager, extract_archive

LOCK = b'lockfileVersion: 9\n'
BLOB = hashlib.sha1(b'blob ' + str(len(LOCK)).encode() + b'\0' + LOCK).hexdigest()
COMMIT = 'a' * 40

def archive(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        z.writestr('repo/pnpm-lock.yaml', LOCK)
        for name, contents in (extra or {}).items(): z.writestr(name, contents)
    return output.getvalue()

def baseline(): return dict(commit=COMMIT, repository='https://github.com/TestBoxLab/monarch', lockfile={'git_blob': BLOB})

def test_pinned_archive_validates_lock_and_preserves_source(tmp_path):
    data = archive({'repo/monarch-enterprise/Dockerfile': 'FROM node:24-alpine'})
    digest = extract_archive(data, tmp_path / 'source', BLOB)
    assert (tmp_path / 'source/pnpm-lock.yaml').read_bytes() == LOCK
    assert (tmp_path / 'source/monarch-enterprise/Dockerfile').read_text() == 'FROM node:24-alpine'
    assert digest == hashlib.sha256(data).hexdigest()

@pytest.mark.parametrize('path', ['repo/../../escape', '/absolute/file', 'repo/C:/secret', 'repo/..\\escape', 'other/extra', 'repo/PNPM-lock.yaml'])
def test_unsafe_archive_rejected_before_any_source_write(tmp_path, path):
    with pytest.raises(ValueError): extract_archive(archive({path: 'bad'}), tmp_path / 'source', BLOB)
    assert not (tmp_path / 'source').exists()

def test_lockfile_mismatch_does_not_write(tmp_path):
    with pytest.raises(ValueError, match='lockfile does not match'):
        extract_archive(archive(), tmp_path / 'source', 'b' * 40)
    assert not (tmp_path / 'source').exists()

def test_update_retains_prior_revision_and_download_failure(tmp_path, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=archive())
    monkeypatch.setattr(subprocess, 'run', run)
    manager = DeploymentManager(tmp_path)
    first = manager.prepare(baseline())
    second = manager.prepare(baseline())
    assert first['id'] != second['id']
    assert manager.status(first['id']) == first
    assert calls[0] == ['gh', 'api', 'repos/TestBoxLab/monarch/zipball/' + COMMIT]
    assert first['launchable'] is False
    def fail(*args, **kwargs): raise subprocess.CalledProcessError(1, 'gh')
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError): manager.prepare(baseline())
    assert sorted(r['state'] for r in manager.status()) == ['source_failed', 'source_ready', 'source_ready']
    assert manager.status(first['id']) == first

def test_build_failure_retains_old_image_and_records_log(tmp_path, monkeypatch):
    manager = DeploymentManager(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=archive()))
    record = manager.prepare(baseline())
    def fail(args, **kwargs):
        if args[1] == 'build':
            kwargs['stdout'].write(b'missing upstream dependency')
            raise subprocess.CalledProcessError(1, args)
        return SimpleNamespace(stdout='29')
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError): manager.build(record['id'], ['backend'])
    saved = manager.status(record['id'])
    assert saved['state'] == 'build_failed' and saved['launchable'] is False
    assert (manager._path(record['id']) / 'backend.build.log').read_text() == 'missing upstream dependency'
    assert (manager._path(record['id']) / 'source/pnpm-lock.yaml').read_bytes() == LOCK

def test_smoke_probe_uses_digest_no_network_or_mount_and_never_enables_launch(tmp_path, monkeypatch):
    from wb_results.evidence import write_json
    manager = DeploymentManager(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=archive()))
    record = manager.prepare(baseline())
    digest = 'sha256:' + 'd' * 64
    record.update(state='built', images={'backend': {'image_id': digest}})
    write_json(manager._path(record['id']) / 'deployment.json', record)
    commands = []
    def run(args, **kwargs):
        commands.append(args)
        value = json.dumps([{'Id': digest, 'Config': {'Labels': {'org.opencontainers.image.revision': COMMIT}}}]) if args[1] == 'image' else 'v24.0.0\n'
        return SimpleNamespace(stdout=value)
    monkeypatch.setattr(subprocess, 'run', run)
    result = manager.verify_images(record['id'])
    assert result['image_probes']['backend']['image_id'] == digest
    assert result['state'] == 'smoke_verified' and result['launchable'] is False
    assert commands[1][-2:] == [digest, '--version']
    assert commands[1][commands[1].index('--network') + 1] == 'none'
    assert '--read-only' in commands[1] and '--mount' not in commands[1] and '-v' not in commands[1]

def test_invalid_candidate_id_cannot_escape_manager_directory(tmp_path):
    with pytest.raises(ValueError, match='Invalid deployment ID'): DeploymentManager(tmp_path).status('../outside')
