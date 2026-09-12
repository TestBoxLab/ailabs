"""Native worktree repair execution using a local fake Codex, never a paid model."""
import hashlib
import json
import subprocess
import sys
import time
from decimal import Decimal
import pytest
from tests.test_genesis_engineer import repo, fake_codex, EDITS
from wb_studio import code_index, genesis_engineer
from wb_repair.executor import execute, protected_change
from wb_repair.grants import fingerprint
from wb_orchestrator.budget import BudgetLedger


def test_prepaid_native_executor_writes_patch_and_independently_verifies_it(repo, tmp_path, monkeypatch):
    for name in ('GENESIS_GITHUB_PRIVATE_KEY_FILE', 'GENESIS_REPAIR_FUNDING_KEY', 'GENESIS_REPAIR_ACTOR_KEYS', 'GENESIS_REPAIR_WORKER_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(genesis_engineer, 'codex_binary', lambda: fake_codex(tmp_path, EDITS + '\n(work / "asset.bin").write_bytes(bytes(range(256)))\n(work / "legacy.txt").write_bytes(bytes([255, 10]))\n'))
    verification = [sys.executable, '-c', 'from pathlib import Path; assert Path("thing.py").read_text().strip() == "VALUE = 2"']
    assert subprocess.run(verification, cwd=repo, capture_output=True).returncode != 0
    monkeypatch.setenv('GENESIS_REPAIR_REPO_LAB', str(repo))
    monkeypatch.setenv('GENESIS_REPAIR_VERIFY_LAB', json.dumps(verification))
    head = code_index.git(repo, 'rev-parse', 'HEAD').strip()
    spec = {'repo': 'lab', 'commit': head, 'change': 'Change VALUE to 2', 'verification': 'The value must be 2'}
    job = {'id': 'repair_' + 'a' * 32, 'actor': 'lucas', 'payload': spec}
    job['funding'] = {'job': job['id'], 'actor': 'lucas', 'spec_sha256': fingerprint(spec),
                      'reservation': 'funded-at-source', 'maximum_usd': '2.00', 'model': 'gpt-5.6-sol', 'effort': 'medium'}
    directory = tmp_path / 'execution'
    result = execute(job, directory)
    patch = (directory / 'artifacts/change.patch').read_bytes()
    assert result['status'] == 'awaiting_review' and result['verified'] is True
    assert b'-VALUE = 1' in patch and b'+VALUE = 2' in patch
    assert result['diff_sha256'] == hashlib.sha256(patch).hexdigest()
    applied = tmp_path / 'applied'
    subprocess.run(['git', '-c', 'core.autocrlf=false', 'clone', str(repo), str(applied)], check=True, capture_output=True)
    subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', str(directory / 'artifacts/change.patch')], cwd=applied, check=True, capture_output=True)
    assert (applied / 'asset.bin').read_bytes() == bytes(range(256))
    assert (applied / 'legacy.txt').read_bytes() == bytes([255, 10])
    assert (applied / 'thing.py').read_text().strip() == 'VALUE = 2'
    assert result['usage']['prompt_tokens'] == 1000 and result['usage']['output_tokens'] == 250
    assert result['reservation'] == 'funded-at-source'
    assert BudgetLedger(directory / 'budget.sqlite3', weekly_limit_usd='2').status().committed_usd == Decimal(result['cost_usd'])
    assert (repo / 'thing.py').read_text().strip() == 'VALUE = 1'
    assert code_index.git(repo, 'worktree', 'list').count('\n') == 1


def test_protected_benchmark_changes_cannot_be_offered_as_verified_repair():
    assert protected_change(['monarch-benchmark/workflowbench/wb_studio/static/genesis.js']) is None
    for path in ('monarch-benchmark/workflowbench/wb_worlds/simulator.py',
                 'monarch-benchmark/workflowbench/grader/check.py', '.env', 'data/seeds/task.json'):
        assert path in protected_change([path])
