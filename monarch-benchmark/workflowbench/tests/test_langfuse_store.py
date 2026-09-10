"""Stored attempts reach telemetry without exporting private evidence or new cost."""
import json
import sqlite3

import pytest

from runner.schema import EpisodeRow
from wb_results.store import Store


@pytest.mark.parametrize('flags,known', [([], True), (['billing=unknown'], False), (['cost_missing'], False)])
def test_stored_attempt_has_safe_durable_summary_even_without_paid_dispatch(tmp_path, flags, known):
    path = tmp_path / 'results.sqlite3'
    store = Store(path)
    store.create_run('run', 'hash', 'suite', {})
    row = EpisodeRow(episode_id='attempt', run_id='run', task_id='task', arm='scripted',
                     contract_sha256='a' * 16, passed=False, assertions_passed=False,
                     invariant_passed=True, invariant_declared=True, cost_usd=0, flags=flags,
                     error='Bearer private-token', unexpected_changes=[{'secret': 'answer key'}])
    store.record_episode(row)
    store.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='telemetry_outbox'").fetchone()
        payload, = connection.execute('SELECT payload FROM telemetry_outbox').fetchone()
    value = json.loads(payload)
    assert value['kind'] == 'summary'
    assert ('cost_usd' in value) is known
    assert 'private-token' not in payload and 'answer key' not in payload
    reopened = Store(path)
    assert reopened.episodes()['rows'][0]['flags'] == flags
    reopened.close()
