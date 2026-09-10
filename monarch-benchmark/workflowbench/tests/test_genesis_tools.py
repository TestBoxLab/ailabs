"""Offline contracts for the read-only Studio tools Genesis reads its numbers from."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_tools as T

TASKS = ['finance.t%02d' % i for i in range(1, 7)]
SETUP, BARE = 'blueprint.a.v2', 'claude-code@medium'


def task(identity, services=('gmail',)):
    return {'task': identity, 'answer': '',
            'prompt': [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'Do ' + identity}],
            'info': {'expected_changes': [{'service': s, 'op': 'added', 'path': s + '.x'} for s in services],
                     'allowed_changes': [], 'assertions': [{'field': 'Phone', 'value': '123'}],
                     'initial_state': {}, 'zapier_tools': []}}


CATALOG = {t: task(t, ('gmail', 'airtable') if int(t[-2:]) > 3 else ('gmail',)) for t in TASKS}


def rows(arm, passed, tasks=TASKS, termination='completed'):
    return [{'task': t, 'model': arm, 'passed': i < passed, 'cost_usd': 1.0, 'flags': [],
             'termination': termination, 'seconds': 1.0, 'tool_calls': 1,
             'tokens': {'prompt': 1000, 'cached': 0, 'cache_write': 0, 'output': 100},
             'checks': [{'type': 'field_equals', 'passed': i < passed}], 'unexpected_changes': [], 'output': ''}
            for i, t in enumerate(tasks)]


def job(identity, results, tasks=TASKS, hashes=None):
    return {'id': identity, 'title': 'Run ' + identity, 'status': 'completed',
            'created_at': '2026-09-01T00:00:00+00:00', 'finished_at': '2026-09-01T00:00:00+00:00',
            'task_hashes': hashes or {t: 'hash-' + t for t in tasks},
            'settings': {'arms': [{'id': SETUP, 'kind': 'version', 'name': 'V2'},
                                  {'id': BARE, 'kind': 'native', 'version': 'without-monarch', 'name': 'Bare'}],
                         'tasks': list(tasks), 'models': [SETUP, BARE], 'track': 'agentic-request'},
            'results': results}


def studio_for(jobs, tmp_path, events=(), catalog=None):
    listing = list(jobs)
    def one(identity):
        try:
            return next(j for j in listing if j['id'] == identity)
        except StopIteration:  # the Studio has no file for an unknown run
            raise FileNotFoundError(identity)
    return SimpleNamespace(directory=tmp_path, tasks=dict(catalog or CATALOG), jobs=lambda: list(listing),
                           job=one, events=lambda i, after=0: list(events), budget=lambda: {}, ledger=Mock())


def genesis_for(jobs, tmp_path, events=(), catalog=None):
    return SimpleNamespace(studio=studio_for(jobs, tmp_path, events, catalog),
                           read=Mock(side_effect=FileNotFoundError))


@pytest.fixture
def genesis(tmp_path):
    return genesis_for([job('run-1', rows(SETUP, 5) + rows(BARE, 2))], tmp_path)


def test_every_tool_result_carries_its_run_tag_and_names_the_internal_audience(genesis, tmp_path):
    for action in ('measures', 'compare', 'failure_buckets', 'report'):
        found = T.TOOLS[action](genesis, {'run': 'run-1'})
        assert found['tags'] == ['[rec:run:run-1]'], action
        assert found['audience'] == 'internal', action
    assert T.TOOLS['task_catalog'](genesis, {})['tags'] == ['[rec:task-catalog]']


def test_a_tool_without_a_run_says_so_as_a_sentence(genesis):
    with pytest.raises(ValueError, match='Name the run'):
        T.TOOLS['measures'](genesis, {})
    with pytest.raises(ValueError, match='No run is called nope'):
        T.TOOLS['measures'](genesis, {'run': 'nope'})
    with pytest.raises(ValueError, match='group_by is setup, task or category'):
        T.TOOLS['measures'](genesis, {'run': 'run-1', 'group_by': 'weather'})


@pytest.mark.parametrize('group,first', [('setup', SETUP), ('task', 'finance.t01'), ('category', 'Finance')])
def test_measures_groups_carry_passed_attempts_rate_and_the_interval(genesis, group, first):
    found = T.TOOLS['measures'](genesis, {'run': 'run-1', 'group_by': group})
    assert found['measures']['setups'][SETUP]['pass']['rate'] == 5 / 6
    head = found['groups'][0]
    assert head['group'] == first
    assert head['attempts'] and head['low'] is not None and head['high'] is not None
    assert sum(g['attempts'] for g in found['groups']) == 12


def test_compare_against_the_baseline_returns_the_paired_test_and_the_overlap(genesis):
    found = T.TOOLS['compare'](genesis, {'run': 'run-1'})
    assert found['comparable'] and found['baseline'] == BARE
    paired = next(s for s in found['setups'] if s['setup'] == SETUP)['paired']
    assert paired['comparable'] and (paired['wins'], paired['losses']) == (3, 0)
    assert paired['p_value'] is not None and found['overlap']


def test_compare_on_identical_tasks_pairs_and_on_different_tasks_says_so_in_words(tmp_path):
    same = job('run-2', rows(SETUP, 2) + rows(BARE, 1))
    other_tasks = ['hr.t01', 'hr.t02']
    listing = [job('run-1', rows(SETUP, 5) + rows(BARE, 2)), same,
               job('run-3', rows(SETUP, 1, other_tasks) + rows(BARE, 0, other_tasks), other_tasks)]
    genesis = genesis_for(listing, tmp_path, catalog=dict(CATALOG) | {t: task(t) for t in other_tasks})
    paired = next(s for s in T.TOOLS['compare'](genesis, {'run': 'run-1', 'against': 'run-2'})['setups']
                  if s['setup'] == SETUP)['paired']
    assert paired['comparable'] and paired['tasks'] == 6
    differing = next(s for s in T.TOOLS['compare'](genesis, {'run': 'run-1', 'against': 'run-3'})['setups']
                     if s['setup'] == SETUP)['paired']
    assert differing['comparable'] is False and differing['reason'] == 'task sets differ'
    assert differing['delta'] is None


def test_compare_with_no_shared_setup_says_which_setups_each_run_has(tmp_path):
    listing = [job('run-1', rows(SETUP, 5) + rows(BARE, 2)), job('run-4', rows('other-arm', 1))]
    found = T.TOOLS['compare'](genesis_for(listing, tmp_path), {'run': 'run-1', 'against': 'run-4'})
    assert found['comparable'] is False
    assert 'share no setup' in found['reason'] and 'other-arm' in found['reason']


def test_failure_buckets_keep_counts_denominators_and_one_evidence_event(tmp_path):
    events = [{'id': 1, 'type': 'node_finished', 'status': 'error', 'task': 'finance.t01', 'model': SETUP},
              {'id': 2, 'type': 'attempt_finished', 'task': 'finance.t01', 'model': SETUP}]
    genesis = genesis_for([job('run-1', rows(SETUP, 0, ['finance.t01']))], tmp_path, events)
    found = T.TOOLS['failure_buckets'](genesis, {'run': 'run-1'})
    unmet = next(b for b in found['buckets'] if b['id'] == 'requirement_unmet')
    assert (unmet['count'], unmet['percent_failed'], unmet['evidence_event']) == (1, 100.0, 1)
    assert found['summary']['failed_attempts'] == 1
    assert 'All recorded failed attempts' in found['denominators']['percent_failed']
    assert found['limitations']


def test_report_is_the_internal_report_as_data_without_the_narrative(genesis):
    found = T.TOOLS['report'](genesis, {'run': 'run-1'})
    assert 'narrative' not in found and 'model_findings' not in found
    assert found['grade']['grade'] and found['verdict'] and found['baseline'] == BARE
    assert found['setups'][SETUP]['pass']['passed'] == 5
    assert found['method']['task_count'] == 6 and found['caveats']


def test_task_catalog_carries_the_fields_a_filter_reads(genesis):
    found = T.TOOLS['task_catalog'](genesis, {})
    assert found['count'] == len(TASKS)
    assert set(found['tasks'][0]) == {'id', 'tier', 'tier_source', 'domain', 'category', 'hash', 'applications'}
    narrowed = T.TOOLS['task_catalog'](genesis, {'filter': {'applications': {'min': 2}}})
    assert [t['id'] for t in narrowed['tasks']] == TASKS[3:]
    with pytest.raises(ValueError, match='does not know colour'):
        T.TOOLS['task_catalog'](genesis, {'filter': {'colour': 'red'}})


def test_the_protocol_names_every_tool_and_forbids_counting_by_hand():
    assert T.PROTOCOL.startswith('Never add up events by hand.')
    assert all(name in T.PROTOCOL for name in T.TOOLS)
