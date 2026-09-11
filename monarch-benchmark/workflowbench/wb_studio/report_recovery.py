"""Startup-only reconciliation of report stages interrupted between durable writes.

Call after Genesis has failed recorded running turns, before background workers
start. Recovery retains drafts and evidence, never invokes a model, and never
replays a successful turn whose completion callback was interrupted.
"""
from __future__ import annotations

from pathlib import Path
import re

from wb_studio import genesis_reports as reports


def recover(genesis):
    """Fail stranded active reports and release capacity without settling requests."""
    if getattr(genesis, 'active', {}):
        raise ValueError('Report recovery runs only at startup, before any live worker starts.')
    recovered = []
    with genesis.lock:
        for path in Path(genesis.studio.directory).glob('*/report-work.json'):
            try:
                state = reports._read(path)
                if not isinstance(state, dict) or state.get('stage') not in reports.STAGES:
                    continue
                if (state.get('run') != path.parent.name or
                    not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(state.get('id') or ''))):
                    raise ValueError('The report work identity does not match its stored run.')
                entries = state['turns'].values()
                for entry in entries:
                    if not entry.get('started'):
                        continue
                    try:
                        child = genesis.read('turns', entry['id'])
                    except FileNotFoundError:
                        # chat persists the turn before starting its provider
                        # thread. At startup a missing record cannot have a live
                        # worker. Any unexpected ledger child hold still survives.
                        entry['started'] = False
                        continue
                    if child.get('status') == 'running':
                        raise ValueError('Run Genesis running-turn recovery before report recovery.')
                # Closing an envelope releases only its unallocated capacity.
                # Ledger requests, including claimed/unknown charges, are never
                # settled here and continue to reduce the remaining run budget.
                for entry in state['turns'].values():
                    genesis.studio.ledger.finish_run('genesis-' + entry['id'])
                reports._fail(genesis, state,
                    'The server restarted before this report stage committed its completion. '
                    'Retained work and billing are available; retry explicitly after inspecting them.')
                recovered.append(state['run'])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                genesis.autonomy.record('report-recovery-error', run=path.parent.name,
                                         error=type(exc).__name__,
                                         reason='Startup could not reconcile this retained report; inspect its work and billing.')
    return recovered
