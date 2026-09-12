"""Leaderboard contracts keep incomparable runs separate and incomplete evidence unranked."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from wb_studio.leaderboard import rank_records as leaderboard


def job(identity, *, arm='architecture-v1'):
    return {
        'id': identity, 'status': 'completed',
        'settings': {'tasks': ['task-a', 'task-b'], 'models': [arm],
                     'arms': [{'id': arm, 'name': arm, 'kind': 'version'}],
                     'track': 'agentic-request', 'configuration': {'max_turns': 10}, 'concurrency': 1},
        'task_hashes': {'task-a': 'task-a-sha', 'task-b': 'task-b-sha'},
        'component_manifest': {'brain': {'id': 'brain-v1', 'sha256': 'a' * 64},
                               'action_builder': {'id': 'tools-v1', 'sha256': 'b' * 64},
                               'judge': {'id': 'judge-v1', 'sha256': 'c' * 64}},
        'results': [
            {'model': arm, 'task': 'task-a', 'passed': True, 'termination': 'completed', 'cost_usd': .25},
            {'model': arm, 'task': 'task-b', 'passed': False, 'termination': 'completed', 'cost_usd': .75},
        ],
    }


def rank(jobs):
    return leaderboard(SimpleNamespace(jobs=lambda: jobs))


@pytest.mark.parametrize('change', ['task-hash', 'task-set', 'track', 'judge-hash', 'judge-id', 'assistance', 'world'])
def test_different_evaluation_contracts_never_share_a_cohort(change):
    first, second = job('first'), job('second')
    if change == 'task-hash':
        second['task_hashes']['task-b'] = 'revised-task-b-sha'
    elif change == 'task-set':
        second['settings']['tasks'][1] = 'task-c'
        second['task_hashes']['task-c'] = second['task_hashes'].pop('task-b')
        second['results'][1]['task'] = 'task-c'
    elif change == 'track':
        second['settings']['track'] = 'create-and-run'
    elif change == 'judge-hash':
        second['component_manifest']['judge']['sha256'] = 'd' * 64
    elif change == 'judge-id':
        second['component_manifest']['judge']['id'] = 'judge-v2'
    elif change == 'assistance':
        second['settings']['assistance'] = 'bounded-clarification'
    else:
        second['world_manifest'] = {'version': 'world-v2'}
    cohorts = rank([first, second])['cohorts']
    assert len(cohorts) == 2
    assert len({cohort['id'] for cohort in cohorts}) == 2
    assert {tuple(cohort['entries'][0]['runs']) for cohort in cohorts} == {('first',), ('second',)}
    assert all(len(cohort['entries']) == 1 and cohort['entries'][0]['attempts'] == 2 for cohort in cohorts)


def test_equivalent_contracts_and_repeated_runs_aggregate_once_despite_task_order():
    first, second = job('first'), job('second')
    second['settings']['tasks'].reverse()
    second['results'].reverse()
    second['task_hashes'] = dict(reversed(list(second['task_hashes'].items())))
    output = rank([first, second])
    assert len(output['cohorts']) == 1
    cohort = output['cohorts'][0]
    assert cohort['contract']['task_hashes'] == {'task-a': 'task-a-sha', 'task-b': 'task-b-sha'}
    assert cohort['task_count'] == 2
    assert len(cohort['entries']) == 1
    entry = cohort['entries'][0]
    assert entry['runs'] == ['first', 'second']
    assert (entry['attempts'], entry['passed'], entry['success_rate'], entry['cost_usd']) == (4, 2, .5, 2.0)


@pytest.mark.parametrize('change', ['configuration', 'brain-hash', 'action-builder-hash', 'concurrency', 'execution', 'runner'])
def test_same_architecture_with_changed_configuration_or_implementation_has_a_separate_group(change):
    first, second = job('first'), job('second')
    if change == 'configuration':
        second['settings']['configuration']['max_turns'] = 20
    elif change == 'brain-hash':
        second['component_manifest']['brain']['sha256'] = 'd' * 64
    elif change == 'action-builder-hash':
        second['component_manifest']['action_builder']['sha256'] = 'd' * 64
    elif change == 'concurrency':
        second['settings']['concurrency'] = 2
    elif change == 'execution':
        second['execution_manifests'] = {'architecture-v1': {'identity_sha256': 'new-execution'}}
    else:
        second['runner_manifests'] = {'architecture-v1': {'version': 'runner-v2'}}
    cohorts = rank([first, second])['cohorts']
    assert len(cohorts) == 1
    entries = cohorts[0]['entries']
    assert len(entries) == 2
    assert entries[0]['id'] != entries[1]['id']
    assert {tuple(entry['runs']) for entry in entries} == {('first',), ('second',)}
    assert all(entry['attempts'] == 2 and entry['name'] == 'architecture-v1' for entry in entries)


@pytest.mark.parametrize('status', ['queued', 'running', 'cancelling'])
def test_nonterminal_runs_are_excluded_even_with_complete_rows_without_mutating_jobs(status):
    complete, active = job('complete'), job('active')
    active['status'] = status
    jobs = [complete, active]
    original = deepcopy(jobs)
    entries = rank(jobs)['cohorts'][0]['entries']
    assert len(entries) == 1
    assert entries[0]['runs'] == ['complete']
    assert entries[0]['attempts'] == 2
    assert jobs == original


@pytest.mark.parametrize('incomplete', ['missing-row', 'duplicate-task', 'wrong-task', 'extra-row', 'missing-hash', 'empty-hashes'])
def test_exact_complete_task_coverage_is_required_without_mutating_jobs(incomplete):
    complete, partial = job('complete'), job('partial')
    if incomplete == 'missing-row':
        partial['results'].pop()
    elif incomplete == 'duplicate-task':
        partial['results'][1]['task'] = 'task-a'
    elif incomplete == 'wrong-task':
        partial['results'][1]['task'] = 'unselected-task'
    elif incomplete == 'extra-row':
        partial['results'].append(deepcopy(partial['results'][0]))
    elif incomplete == 'missing-hash':
        del partial['task_hashes']['task-b']
    else:
        partial['task_hashes'] = {}
    jobs = [complete, partial]
    original = deepcopy(jobs)
    output = rank(jobs)
    assert len(output['cohorts']) == 1
    entries = output['cohorts'][0]['entries']
    assert len(entries) == 1
    assert entries[0]['runs'] == ['complete']
    assert entries[0]['attempts'] == 2
    assert entries[0]['cost_usd'] == 1.0
    assert rank([partial]) == {'cohorts': []}
    assert jobs == original


@pytest.mark.parametrize('status', ['completed', 'failed', 'cancelled', 'interrupted'])
def test_terminal_run_infrastructure_failures_stay_in_denominator_and_never_count_as_passes(status):
    evidence = job('operational-result')
    evidence['status'] = status
    evidence['results'][1].update(passed=True, termination='infra:timeout')
    entry = rank([evidence])['cohorts'][0]['entries'][0]
    assert entry['attempts'] == 2
    assert entry['passed'] == 1
    assert entry['infrastructure'] == 1
    assert entry['success_rate'] == .5
    assert entry['runs'] == ['operational-result']


@pytest.mark.parametrize('cost, flags', [
    (None, []), (.75, ['billing=unknown']), (.75, ['cost_missing']),
    (-1, []), ('0.75', []), (float('nan'), []), (float('inf'), []),
])
def test_unknown_or_invalid_cost_stays_none_when_aggregated_with_known_costs(cost, flags):
    unknown, known = job('unknown'), job('known')
    unknown['results'][1].update(cost_usd=cost, flags=flags)
    for jobs in ([unknown, known], [known, unknown]):
        entry = rank(jobs)['cohorts'][0]['entries'][0]
        assert entry['cost_usd'] is None
        assert (entry['attempts'], entry['passed']) == (4, 2)
        assert set(entry['runs']) == {'unknown', 'known'}


def test_missing_cost_is_unknown_but_explicit_zero_is_a_known_free_attempt():
    free = job('free')
    for row in free['results']:
        row['cost_usd'] = 0
    entry = rank([free])['cohorts'][0]['entries'][0]
    assert entry['cost_usd'] == 0.0
    del free['results'][1]['cost_usd']
    assert rank([free])['cohorts'][0]['entries'][0]['cost_usd'] is None


def test_equal_success_fractions_share_rank_and_cost_does_not_break_ties():
    top = job('top', arm='A top')
    top['results'][1]['passed'] = True
    tie_one = job('tie-one', arm='B tied')
    tie_two_first = job('tie-two-first', arm='C tied')
    tie_two_second = job('tie-two-second', arm='C tied')
    tie_two_second['results'][0]['cost_usd'] = 99
    bottom = job('bottom', arm='D last')
    bottom['results'][0]['passed'] = False
    entries = rank([bottom, tie_two_second, top, tie_two_first, tie_one])['cohorts'][0]['entries']
    assert [(entry['name'], entry['rank'], entry['success_rate']) for entry in entries] == [
        ('A top', 1, 1.0), ('B tied', 2, .5), ('C tied', 2, .5), ('D last', 4, 0.0),
    ]
    assert entries[1]['attempts'] == 2
    assert entries[2]['attempts'] == 4
    assert entries[1]['cost_usd'] != entries[2]['cost_usd']


def test_historical_unpinned_judge_is_provisional_and_separate_from_pinned_results():
    pinned, historical = job('pinned'), job('historical')
    del historical['component_manifest']
    cohorts = rank([pinned, historical])['cohorts']
    assert len(cohorts) == 2
    provisional = next(cohort for cohort in cohorts if cohort['contract']['judge'] == 'historical-unpinned')
    assert provisional['entries'][0]['runs'] == ['historical']
    assert 'rankings are provisional' in provisional['note']


def test_complete_task_coverage_is_required_for_each_arm_without_reusing_other_arm_rows():
    evidence = job('comparison', arm='arm-a')
    evidence['settings']['arms'].append({'id': 'arm-b', 'name': 'arm-b', 'kind': 'version'})
    evidence['settings']['models'].append('arm-b')
    evidence['results'][1]['model'] = 'arm-b'
    assert rank([evidence]) == {'cohorts': []}

    evidence['results'].extend([
        {**evidence['results'][0], 'model': 'arm-b'},
        {**evidence['results'][1], 'model': 'arm-a'},
    ])
    entries = rank([evidence])['cohorts'][0]['entries']
    assert len(entries) == 2
    assert {entry['name'] for entry in entries} == {'arm-a', 'arm-b'}
    assert all(entry['attempts'] == 2 and entry['passed'] == 1 and entry['cost_usd'] == 1.0 for entry in entries)


def complete_benchmark():
    j=job('full')
    tasks=['task-'+str(i) for i in range(50)]
    j['settings']['tasks']=tasks
    j['task_hashes']={t:t+'-hash' for t in tasks}
    j['benchmark']={'id':'catalog-50','task_hashes':dict(j['task_hashes'])}
    j['results']=[{'model':'architecture-v1','task':t,'passed':i<30,'termination':'completed','cost_usd':.1} for i,t in enumerate(tasks)]
    return j

def test_public_leaderboard_excludes_single_task_pilot_and_accepts_full_benchmark():
    from wb_studio.leaderboard import leaderboard as public_board
    full=complete_benchmark()
    result=public_board(SimpleNamespace(jobs=lambda:[job('pilot'),full]))
    assert result['excluded_runs']==1
    entry=result['cohorts'][0]['entries'][0]
    assert entry['attempts']==50 and entry['success_rate']==.6 and entry['runs']==['full']

@pytest.mark.parametrize('change',['one-task','partial-arm','cancelled','duplicate','changed-task','unpinned'])
def test_public_leaderboard_rejects_incomplete_or_changed_benchmark(change):
    from wb_studio.leaderboard import leaderboard as public_board
    j=complete_benchmark()
    if change=='one-task': j['settings']['tasks']=j['settings']['tasks'][:1];j['results']=j['results'][:1]
    if change=='partial-arm': j['settings']['arms'].append({'id':'other','kind':'version','name':'Other'})
    if change=='cancelled': j['status']='cancelled'
    if change=='duplicate': j['results'][-1]=j['results'][0]
    if change=='changed-task': j['task_hashes']['task-0']='changed'
    if change=='unpinned': del j['benchmark']
    assert public_board(SimpleNamespace(jobs=lambda:[j]))['cohorts']==[]

def row(task, passed, model='a'):
    return {'model': model, 'task': task, 'passed': passed, 'termination': 'completed', 'cost_usd': .1}


def test_exclusion_reason_names_why_a_run_is_off_the_leaderboard_and_the_board_lists_it():
    from wb_studio.leaderboard import exclusion_reason, leaderboard as public_board
    assert exclusion_reason(complete_benchmark()) is None
    pilot = job('pilot')
    pilot['title'] = 'Pilot'
    assert exclusion_reason(pilot) == 'not the frozen 50-task benchmark'
    running = complete_benchmark(); running['status'] = 'running'
    assert exclusion_reason(running) == 'not finished'
    scripted = complete_benchmark(); scripted['settings']['arms'][0]['kind'] = 'scripted'
    assert exclusion_reason(scripted) == 'includes a scripted check'
    partial = complete_benchmark(); partial['results'].pop()
    assert exclusion_reason(partial) == 'incomplete attempts'
    changed = complete_benchmark(); changed['task_hashes']['task-0'] = 'changed'
    assert exclusion_reason(changed) == 'task set differs from the benchmark'
    unverdicted = complete_benchmark(); unverdicted['results'][0]['termination'] = 'running'
    assert exclusion_reason(unverdicted) == 'attempts without a verdict'
    result = public_board(SimpleNamespace(jobs=lambda: [pilot, complete_benchmark()]))
    assert result['excluded_runs'] == 1
    assert result['excluded'] == [{'id': 'pilot', 'title': 'Pilot', 'reason': 'not the frozen 50-task benchmark'}]


def test_pairings_count_wins_losses_ties_and_tasks_only_one_side_solved():
    from wb_studio.leaderboard import pairings
    groups = {'a': [row('t1', True), row('t2', False), row('t3', True), row('t4', False)],
              'b': [row('t1', False), row('t2', False), row('t3', True), row('t4', True), row('t4', False)]}
    assert pairings(groups) == [{'a': 'a', 'b': 'b', 'tasks': 4, 'wins': 1, 'losses': 1, 'ties': 2, 'unique_a': 1, 'unique_b': 1}]
    groups['a'].append({**row('t4', True), 'termination': 'infra:timeout'})
    assert pairings(groups)[0]['losses'] == 1
    assert pairings({'a': groups['a'], 'b': [row('t9', True)]}) == []


def test_uncertainty_is_over_attempts_without_repetitions_and_over_tasks_with_them():
    from wb_studio.leaderboard import uncertainty
    from wb_studio.measures import wilson
    single = uncertainty([row('t1', True), row('t2', False)])
    assert (single['unit'], single['tasks'], single['repetitions'], single['rate']) == ('attempts', 2, 1, .5)
    assert (single['low'], single['high']) == wilson(1, 2)
    repeated = uncertainty([row('t1', True), row('t1', True), row('t2', False), row('t2', True)])
    assert (repeated['unit'], repeated['tasks'], repeated['repetitions'], repeated['rate']) == ('tasks', 2, 2, .75)
    assert 0 <= repeated['low'] < .75 < repeated['high'] <= 1
    assert (repeated['low'], repeated['high']) != wilson(3, 4)
    one_task = uncertainty([row('t1', True), row('t1', False)])
    assert one_task['unit'] == 'tasks' and one_task['low'] is None and one_task['high'] is None
    assert uncertainty([]) == {'unit': 'attempts', 'tasks': 0, 'repetitions': 0, 'rate': None, 'low': None, 'high': None}


def test_cohorts_carry_task_aware_intervals_and_pairings():
    first, second = job('first', arm='arm-a'), job('second', arm='arm-a')
    entry = rank([first, second])['cohorts'][0]['entries'][0]
    assert entry['interval']['unit'] == 'tasks' and entry['interval']['repetitions'] == 2 and entry['interval']['rate'] == .5
    evidence = job('comparison', arm='arm-a')
    evidence['settings']['arms'].append({'id': 'arm-b', 'name': 'arm-b', 'kind': 'version'})
    evidence['settings']['models'].append('arm-b')
    evidence['results'].extend([{**evidence['results'][0], 'model': 'arm-b', 'passed': False}, {**evidence['results'][1], 'model': 'arm-b', 'passed': True}])
    cohort = rank([evidence])['cohorts'][0]
    assert all(e['interval']['unit'] == 'attempts' for e in cohort['entries'])
    [pair] = cohort['pairings']
    ids = {e['name']: e['id'] for e in cohort['entries']}
    assert {pair['a'], pair['b']} == {ids['arm-a'], ids['arm-b']}
    assert (pair['tasks'], pair['wins'], pair['losses'], pair['ties'], pair['unique_a'], pair['unique_b']) == (2, 1, 1, 0, 1, 1)


def test_report_data_uses_leaderboard_exclusion_reason(tmp_path):
    import json
    from wb_studio import report_data
    from wb_studio.leaderboard import exclusion_reason
    assert report_data.exclusion_reason is exclusion_reason

    pilot = job('pilot')
    pilot['title'] = 'Pilot'
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    (pilot_dir / "job.json").write_text(json.dumps(pilot), encoding="utf-8")
    (pilot_dir / "events.jsonl").write_text("", encoding="utf-8")

    mock_studio = SimpleNamespace(
        directory=tmp_path,
        jobs=lambda: [pilot],
        job=lambda identity: pilot,
        events=lambda identity: [],
        tasks={},
    )
    cohort_id = list(report_data.cohorts(mock_studio).keys())[0]
    rep = report_data.round_report(mock_studio, cohort_id)
    assert rep["excluded"] == [{"id": "pilot", "title": "Pilot", "reason": exclusion_reason(pilot)}]

    run_rep = report_data.run_report(mock_studio, "pilot")
    assert run_rep["exclusion_reason"] == exclusion_reason(pilot) == "not the frozen 50-task benchmark"
    assert run_rep["full_benchmark"] is False


