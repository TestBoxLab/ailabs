"""Native repair executor for a separately deployed worker, not the control server."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from .grants import fingerprint
from .server import specification


def protected_change(paths):
    prefixes = ('monarch-benchmark/workflowbench/vendor/', 'monarch-benchmark/workflowbench/wb_world/',
                'monarch-benchmark/workflowbench/wb_worlds/', 'monarch-benchmark/workflowbench/grader/',
                'monarch-benchmark/workflowbench/config/task_sets/', 'research/budget.sqlite3')
    refused = [path for path in paths if path.startswith(prefixes) or
               any(part in ('snapshots', 'seeds') or part.startswith('.env') for part in path.split('/'))]
    return 'Protected benchmark or credential paths changed: ' + ', '.join(refused) if refused else None


def execute(job, directory):
    # Load the existing native executor only inside the worker. The control API
    # remains usable if this import or the versioned worker image is broken.
    from wb_orchestrator.budget import BudgetLedger
    from wb_studio.genesis_engineer import implement
    spec = specification(job['payload'])
    grant = job['funding']
    if grant['job'] != job['id'] or grant['actor'] != job['actor'] or grant['spec_sha256'] != fingerprint(spec):
        raise ValueError('The funded job does not match its specification.')
    repo = os.environ.get('GENESIS_REPAIR_REPO_' + spec['repo'].upper())
    if not repo or not Path(repo).is_dir():
        raise ValueError('The worker repository mirror is not configured.')
    verify = json.loads(os.environ.get('GENESIS_REPAIR_VERIFY_' + spec['repo'].upper(), 'null'))
    if not isinstance(verify, list) or not verify or any(not isinstance(s, str) or not s for s in verify):
        raise ValueError('Configure an operator-owned verification command before executing repairs.')
    if any(name in os.environ for name in ('GENESIS_GITHUB_PRIVATE_KEY_FILE', 'GENESIS_REPAIR_FUNDING_KEY',
                                          'GENESIS_REPAIR_ACTOR_KEYS', 'GENESIS_REPAIR_WORKER_KEY')):
        raise ValueError('Control-service credentials must not be present in the executor environment.')
    root = Path(directory)
    maximum = Decimal(grant['maximum_usd'])
    # This ledger accounts only this already-funded job. It does not allocate a
    # second weekly allowance; its full capacity remains held at the issuer.
    ledger = BudgetLedger(root / 'budget.sqlite3', weekly_limit_usd=maximum)
    genesis = SimpleNamespace(studio=SimpleNamespace(ledger=ledger),
        config=SimpleNamespace(route_for=lambda _: {'id': grant['model']}, effort_for=lambda _: grant['effort']),
        allowance_allows=lambda amount: (amount <= maximum, 'The prepaid repair allowance is insufficient.'))
    prompt = ('Implement the requested change in this isolated worktree. Read the actual code first. '
              'Match existing conventions. Do not commit, push, deploy, change frozen benchmark worlds, '
              'task sets, seeds, assertions, graders, billing or authorization gates. '
              'The operator runs an independent verification command after you finish.\n\n'
              'Requested change:\n' + spec['change'] + '\n\nAcceptance criteria:\n' + spec['verification'])
    result = implement(genesis, {**spec, 'verify': ''}, job['id'], repo_path=repo, maximum_usd=maximum,
                       verification_args=verify, request_prompt=prompt, artifact_directory=root / 'artifacts', validate_changes=protected_change)
    status = 'awaiting_review' if result.get('changed') and result.get('verified') is True and not result.get('agent_error') else 'failed'
    return {**result, 'job': job['id'], 'reservation': grant['reservation'], 'status': status}


def main():
    job = json.loads(sys.stdin.read(100000))
    directory = Path(os.environ['GENESIS_REPAIR_JOB_DIR'])
    result = execute(job, directory)
    target = directory / 'result.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result), encoding='utf-8')
    temporary.replace(target)


if __name__ == '__main__':
    main()
