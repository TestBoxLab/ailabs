"""Offline contracts for hypothesis records: the schema, the population, coverage, the
settlement rules and the smallest plan. Nothing here touches a provider or the network."""
import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_hypotheses as H

A = {'kind': 'architecture', 'id': 'blueprint.a.v2'}
B = {'kind': 'architecture', 'id': 'blueprint.a.v1'}
TASKS = ['finance.t%02d' % i for i in range(1, 11)] + ['hr.t%02d' % i for i in range(1, 11)]
COVERED = TASKS[:10]


def task(identity, services=('gmail',)):
    return {'task': identity, 'answer': '',
            'prompt': [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'Do ' + identity}],
            'info': {'expected_changes': [{'service': s, 'op': 'added', 'path': s + '.x'} for s in services],
                     'allowed_changes': [], 'assertions': [], 'initial_state': {}, 'zapier_tools': []}}


CATALOG = {t: task(t, ('gmail', 'airtable') if t.startswith('hr.') else ('gmail',)) for t in TASKS}


def record(**changes):
    base = {'claim': 'Version 2 passes more tasks than version 1.',
            'population': {'filter': {'task_ids': list(TASKS)}},
            'comparison': {'a': dict(A), 'b': dict(B)}, 'measure': 'pass_rate',
            'direction': 'a_higher', 'minimum_effect': 0.2}
    base.update(changes)
    return base


def rows(arm, passed, tasks=COVERED, termination='completed', cost=1.0):
    return [{'task': t, 'model': arm, 'passed': i < passed, 'cost_usd': cost, 'flags': [],
             'termination': termination if i == 0 else 'completed', 'seconds': 1.0, 'tool_calls': 1,
             'tokens': {'prompt': 1000, 'cached': 0, 'cache_write': 0, 'output': 100},
             'checks': [{'type': 'field_equals', 'passed': i < passed}], 'unexpected_changes': [], 'output': ''}
            for i, t in enumerate(tasks)]


def job(identity, results, status='completed', bare=True, finished='2026-09-01T00:00:00+00:00'):
    arms = [{'id': A['id'], 'kind': 'version', 'name': 'V2'}, {'id': B['id'], 'kind': 'version', 'name': 'V1'}]
    if bare:
        arms.append({'id': 'bare', 'kind': 'native', 'version': 'without-monarch', 'name': 'Bare'})
    return {'id': identity, 'title': identity, 'status': status, 'created_at': finished, 'finished_at': finished,
            'task_hashes': {t: 'hash-' + t for t in COVERED},
            'settings': {'arms': arms, 'tasks': COVERED, 'models': [a['id'] for a in arms]},
            'results': results + (rows('bare', 2) if bare else [])}


def studio_for(jobs=(), tmp_path=None):
    listing = list(jobs)
    def one(identity):
        try:
            return next(j for j in listing if j['id'] == identity)
        except StopIteration:  # the Studio has no file for an unknown run
            raise FileNotFoundError(identity)
    return SimpleNamespace(directory=tmp_path, tasks=dict(CATALOG), jobs=lambda: list(listing), job=one,
                           events=lambda i, after=0: [], budget=lambda: {}, ledger=Mock(), create=Mock())


# --- the schema -------------------------------------------------------------------------

@pytest.mark.parametrize('label,changes,match', [
    ('claim missing', {'claim': ''}, 'claim'),
    ('claim too long', {'claim': 'x' * 301}, '300 characters'),
    ('claim on two lines', {'claim': 'One.\nTwo.'}, 'one line'),
    ('unknown measure', {'measure': 'vibes'}, 'measure is one of'),
    ('unknown direction', {'direction': 'up'}, 'a_higher or a_lower'),
    ('minimum effect zero', {'minimum_effect': 0}, 'above 0'),
    ('minimum effect not a number', {'minimum_effect': '0.2'}, 'above 0'),
    ('cost ratio at one', {'measure': 'cost_per_pass', 'minimum_effect': 0.2}, 'ratio above 1'),
    ('prior out of range', {'prior': 1.5}, 'probability between 0 and 1'),
    ('population empty', {'population': {}}, 'names a task set or at least one filter'),
    ('population not an object', {'population': 'everything'}, 'names a task set'),
    ('unknown filter field', {'population': {'filter': {'colour': 'red'}}}, 'does not know colour'),
    ('applications not a range', {'population': {'filter': {'applications': 3}}}, 'min, max'),
    ('applications min above max', {'population': {'filter': {'applications': {'min': 4, 'max': 2}}}}, 'at most'),
    ('task_ids not a list', {'population': {'filter': {'task_ids': 'finance.t01'}}}, 'list of task ids'),
    ('comparison missing a side', {'comparison': {'a': dict(A)}}, 'is {a, b}'),
    ('setup without a kind', {'comparison': {'a': {'id': 'x'}, 'b': dict(B)}}, "kind is architecture"),
    ('setup without an id', {'comparison': {'a': {'kind': 'bare'}, 'b': dict(B)}}, 'names the id'),
    ('setup with an unknown field', {'comparison': {'a': {**A, 'effort': 'high'}, 'b': dict(B)}}, 'does not know effort'),
    ('the two sides are the same', {'comparison': {'a': dict(A), 'b': dict(A)}}, 'two different setups'),
])
def test_the_schema_refuses_each_bad_field_with_a_sentence(label, changes, match):
    with pytest.raises(ValueError, match=match) as raised:
        H.check_hypothesis(record(**changes))
    assert str(raised.value).endswith('.'), label


def test_a_good_record_is_normalised_and_the_parent_goal_is_one_of_its_shapes():
    out = H.check_hypothesis(record(prior=0.7, minimum_effect=1))
    assert out['minimum_effect'] == 1.0 and out['prior'] == 0.7
    assert out['population'] == {'task_set': None, 'filter': {'task_ids': sorted(TASKS)}}
    parent = H.check_hypothesis(record(comparison={'a': {'kind': 'monarch', 'id': 'v2'},
                                                   'b': {'kind': 'monarch', 'id': 'v1'}}))
    assert parent['comparison'] == {'a': {'kind': 'monarch', 'id': 'v2'}, 'b': {'kind': 'monarch', 'id': 'v1'}}


# --- the population ---------------------------------------------------------------------

def test_population_reads_the_catalog_fields_and_names_a_task_it_cannot_find(tmp_path):
    studio = studio_for(tmp_path=tmp_path)
    assert H.population_tasks(studio, record()) == sorted(TASKS)
    assert H.population_tasks(studio, record(population={'filter': {'domain': 'hr'}})) == sorted(t for t in TASKS if t.startswith('hr.'))
    assert H.population_tasks(studio, record(population={'filter': {'category': 'Finance'}})) == sorted(t for t in TASKS if t.startswith('finance.'))
    two_apps = H.population_tasks(studio, record(population={'filter': {'applications': {'min': 2}}}))
    assert two_apps == sorted(t for t in TASKS if t.startswith('hr.'))
    with pytest.raises(ValueError, match='no task called nope.task'):
        H.population_tasks(studio, record(population={'filter': {'task_ids': ['nope.task']}}))
    # No task records a tier, so the tier is the tercile of the difficulty score over the whole catalog
    # (hr tasks change two services, finance one), and the row says it was computed.
    assert H.population_tasks(studio, record(population={'filter': {'tier': 'medium'}})) == sorted(t for t in TASKS if t.startswith('hr.'))
    assert H.population_tasks(studio, record(population={'filter': {'tier': 'simple'}})) == sorted(t for t in TASKS if t.startswith('finance.'))
    assert {r['tier_source'] for r in H.catalog_rows(studio, None, {'tier': 'medium'})} == {'computed'}
    flat = studio_for(tmp_path=tmp_path); flat.tasks = {t: task(t) for t in TASKS}
    with pytest.raises(ValueError, match='records a tier, and the catalog cannot be split'):
        H.population_tasks(flat, record(population={'filter': {'tier': 'complex'}}))
    with pytest.raises(ValueError, match='No task set is called'):
        H.population_tasks(studio, record(population={'task_set': 'not-a-set'}))


def test_the_catalog_row_carries_the_hash_and_the_applications(tmp_path):
    from wb_world.episode import contract_hash
    row = next(r for r in H.catalog_rows(studio_for(tmp_path=tmp_path)) if r['id'] == 'hr.t01')
    assert row['hash'] == contract_hash(CATALOG['hr.t01'])
    assert row['applications'] == ['airtable', 'gmail'] and row['category'] == 'People & HR' and row['domain'] == 'hr'


# --- rows and coverage ------------------------------------------------------------------

def test_setup_rows_follow_the_arm_kind_and_the_model_expansion():
    expanded = {'id': 'run-x', 'settings': {'arms': [
        {'id': A['id'] + '--gpt@low', 'kind': 'version', 'runner_override': {'model': 'gpt'}},
        {'id': A['id'] + '--gemini@low', 'kind': 'version', 'runner_override': {'model': 'gemini'}}]},
        'results': rows(A['id'] + '--gpt@low', 3) + rows(A['id'] + '--gemini@low', 1)}
    assert len(H.setup_rows(expanded, A)) == 20
    assert {r['model'] for r in H.setup_rows(expanded, {**A, 'model': 'gpt'})} == {A['id'] + '--gpt@low'}
    assert H.setup_rows(expanded, {'kind': 'bare', 'id': A['id']}) == []


def test_coverage_finds_a_run_with_both_setups_and_ignores_one_without(tmp_path):
    both = job('run-both', rows(A['id'], 6) + rows(B['id'], 0))
    only_a = job('run-one', rows(A['id'], 6), finished='2026-08-01T00:00:00+00:00')
    unfinished = {**job('run-queued', rows(A['id'], 6) + rows(B['id'], 0)), 'id': 'run-queued', 'status': 'running'}
    found = H.coverage(studio_for([both, only_a, unfinished], tmp_path), record())
    assert [c['run'] for c in found] == ['run-both']
    assert found[0]['tasks'] == sorted(COVERED)
    assert (found[0]['a_attempts'], found[0]['b_attempts'], found[0]['same_tasks']) == (10, 10, True)


# --- the settlement ---------------------------------------------------------------------

@pytest.mark.parametrize('label,jobs,outcome', [
    ('nothing covers it', [], 'untested'),
    ('a covering run did not finish normally',
     [job('run-1', rows(A['id'], 6) + rows(B['id'], 0), status='failed')], 'invalid'),
    ('an attempt stopped on an infrastructure failure',
     [job('run-1', rows(A['id'], 6, termination='infra:provider') + rows(B['id'], 0))], 'invalid'),
    ('Bare was not shown alongside',
     [job('run-1', rows(A['id'], 6) + rows(B['id'], 0), bare=False)], 'invalid'),
    ('the effect is there and the runs separate the sides',
     [job('run-1', rows(A['id'], 6) + rows(B['id'], 0))], 'supported'),
    ('the effect runs the other way',
     [job('run-1', rows(A['id'], 0) + rows(B['id'], 6))], 'not_supported'),
    ('the effect is under the minimum',
     [job('run-1', rows(A['id'], 3) + rows(B['id'], 2))], 'inconclusive'),
])
def test_settle_yields_every_outcome_under_its_written_rule(label, jobs, outcome, tmp_path):
    found = H.settle(studio_for(jobs, tmp_path), record())
    assert found['outcome'] == outcome, label
    assert found['reason'] and found['reason'].endswith(('.', ')'))
    assert found['tags'] == (['[rec:run:run-1]'] if jobs else [])


def test_a_supported_settlement_carries_both_sides_the_paired_test_and_the_certainty(tmp_path):
    found = H.settle(studio_for([job('run-1', rows(A['id'], 6) + rows(B['id'], 0))], tmp_path), record())
    assert found['sides']['a']['value'] == 0.6 and found['sides']['b']['value'] == 0.0
    assert found['sides']['a']['low'] is not None and found['sides']['a']['high'] is not None
    assert found['paired']['comparable'] and found['paired']['wins'] == 6 and found['paired']['losses'] == 0
    assert found['certainty']['word'] == 'probably'
    assert math.isclose(found['effect'], 0.6)


def test_runs_pool_only_on_a_shared_task_set_and_the_rest_are_listed(tmp_path):
    newer = job('run-new', rows(A['id'], 6) + rows(B['id'], 0), finished='2026-09-02T00:00:00+00:00')
    older = job('run-old', rows(A['id'], 0) + rows(B['id'], 6), finished='2026-09-01T00:00:00+00:00')
    older['task_hashes'] = {t: 'other-' + t for t in COVERED}
    found = H.settle(studio_for([newer, older], tmp_path), record())
    assert found['tags'] == ['[rec:run:run-new]']
    assert [o['run'] for o in found['others']] == ['run-old']
    assert found['outcome'] == 'supported'
    pooled = H.settle(studio_for([newer, job('run-twin', rows(A['id'], 6) + rows(B['id'], 0),
                                             finished='2026-08-30T00:00:00+00:00')], tmp_path), record())
    assert sorted(pooled['tags']) == ['[rec:run:run-new]', '[rec:run:run-twin]'] and pooled['others'] == []


def test_the_certainty_word_comes_from_the_reports_closed_set():
    words = [H._certainty({'wins': w, 'losses': l, 'p_value': p}, 'Bare')['word']
             for w, l, p in [(6, 0, 0.03), (5, 0, 0.06), (1, 0, None)]]
    assert words == ['probably', 'may', 'cannot tell']


# --- the smallest plan ------------------------------------------------------------------

@pytest.mark.parametrize('minimum,expected', [(0.5, 12), (0.75, 8), (1.0, 6)])
def test_the_task_count_is_sized_for_the_sign_test_that_settles_it(minimum, expected, tmp_path):
    """Feature 024 FR-021: this asserted n = ceil(4·p·(1−1p)/d²) floored at 10, the size
    for two INDEPENDENT proportions — while `settle` decides the same hypothesis with a
    paired sign test that drops ties. Six discordant pairs are the fewest that can reach
    p<0.05, and a declared minimum effect is the share of tasks expected to flip, so the
    size is ceil(6/d)."""
    plan = H.smallest_plan(studio_for(tmp_path=tmp_path), record(minimum_effect=minimum))
    assert plan['tasks'] == expected == len(plan['proposal']['tasks'])
    assert plan['tasks'] <= plan['population'] == len(TASKS)
    assert plan['power']['ok'] and plan['power']['expected_pairs'] >= 6


@pytest.mark.parametrize('minimum', [0.25, 0.1])
def test_a_population_too_small_for_the_effect_is_refused(minimum, tmp_path):
    """Twenty tasks cannot show a 25% difference: five discordant pairs, and six is the
    floor. It used to cap silently at the population and call that a plan."""
    plan = H.smallest_plan(studio_for(tmp_path=tmp_path), record(minimum_effect=minimum))
    assert plan['power']['ok'] is False
    assert 'cannot be settled' in plan['not_launchable']
    assert str(plan['power']['sufficient_tasks']) in plan['not_launchable']


def test_the_plan_is_a_launch_payload_with_a_ceiling_and_says_why_it_cannot_run(tmp_path):
    plan = H.smallest_plan(studio_for(tmp_path=tmp_path), record())
    proposal = plan['proposal']
    assert proposal['architectures'] == sorted([A['id'], B['id']]) and proposal['tasks'] == sorted(TASKS)
    assert proposal['goal'] == {'version': A['id'], 'parent_version': B['id'], 'minimum_gain': 0.2}
    assert float(proposal['maximum_usd']) > 0
    assert plan['tokens_per_attempt']['attempts'] == 0 and '60,000' in plan['tokens_per_attempt']['basis']
    assert any('Bare' in note for note in plan['notes'])
    # A 20% effect over 20 tasks reaches four discordant pairs, below the floor of six,
    # so the plan now refuses on power before it ever reaches the Studio's own refusal.
    assert plan['power']['ok'] is False and 'cannot be settled' in plan['not_launchable']


def test_the_plan_uses_a_covered_pass_rate_instead_of_one_half(tmp_path):
    studio = studio_for([job('run-1', rows(A['id'], 6) + rows(B['id'], 0))], tmp_path)
    plan = H.smallest_plan(studio, record(minimum_effect=0.5))
    assert plan['pass_rate_assumed'] == 0.0
    # The observed pass rate still informs the cost estimate; it no longer drives the
    # size, because the sign test's power comes from how many tasks disagree, not from p.
    assert plan['tasks'] == 12 and plan['power']['ok']
    assert plan['tokens_per_attempt']['attempts'] > 0


# --- the tools --------------------------------------------------------------------------

def genesis_for(jobs, tmp_path):
    from wb_studio.genesis import Genesis
    return Genesis(studio_for(jobs, tmp_path))


def test_the_settle_tool_writes_the_settlement_and_the_record_onto_the_card(tmp_path):
    genesis = genesis_for([job('run-1', rows(A['id'], 6) + rows(B['id'], 0))], tmp_path)
    card = genesis.card({'id': 'card-1', 'title': 'V2 passes more', 'stage': 'hypothesis', 'hypothesis': record()})
    found = H.TOOLS['hypothesis_settle'](genesis, {'card': 'card-1'})
    assert found['outcome'] == 'supported' and found['card_written'] is True
    saved = genesis.read('cards', 'card-1')
    assert saved['revision'] == card['revision'] + 1 == found['card_revision']
    assert saved['settlement']['outcome'] == 'supported'
    assert saved['hypothesis'] == H.check_hypothesis(record())


def test_a_dispatched_card_keeps_its_proposal_and_the_settlement_says_it_was_not_written(tmp_path):
    genesis = genesis_for([job('run-1', rows(A['id'], 6) + rows(B['id'], 0))], tmp_path)
    genesis.studio.create.return_value = {'id': 'run-1'}
    card = genesis.card({'id': 'card-2', 'title': 'V2 passes more', 'stage': 'approval',
                         'hypothesis': record(), 'proposal': {'tasks': list(COVERED), 'maximum_usd': '1'}})
    genesis._dispatch(card, by='test')  # the launch path itself, without the approval gates around it
    found = H.TOOLS['hypothesis_settle'](genesis, {'card': 'card-2'})
    assert found['outcome'] == 'supported' and found['card_written'] is False
    assert 'dispatched proposal' in found['card_reason']
    assert genesis.read('cards', 'card-2').get('settlement') is None


def test_the_tools_refuse_a_missing_card_or_record_with_a_sentence(tmp_path):
    genesis = genesis_for([], tmp_path)
    genesis.card({'id': 'plain', 'title': 'No record here', 'stage': 'hypothesis'})
    for action in ('hypothesis_settle', 'hypothesis_plan'):
        with pytest.raises(ValueError, match='No research card is called ghost'):
            H.TOOLS[action](genesis, {'card': 'ghost'})
        with pytest.raises(ValueError, match='carries no hypothesis record'):
            H.TOOLS[action](genesis, {'card': 'plain'})
        with pytest.raises(ValueError, match='Give the hypothesis record'):
            H.TOOLS[action](genesis, {})


def test_the_check_tool_takes_the_record_bare_or_wrapped_and_the_protocol_names_all_three(tmp_path):
    genesis = genesis_for([], tmp_path)
    assert H.TOOLS['hypothesis_check'](genesis, record()) == H.TOOLS['hypothesis_check'](genesis, {'record': record()})
    assert all(name in H.PROTOCOL for name in H.TOOLS)
    assert 'write none of them yourself' in H.PROTOCOL


def test_a_cost_claim_has_its_own_certainty_from_the_measure_not_the_pass_test(tmp_path):
    # Both sides pass the same tasks, so the pass test cannot separate them; costs differ on every task.
    cheap, dear = rows(A['id'], 5, cost=0.5), rows(B['id'], 5, cost=2.0)
    found = H.settle(studio_for([job('run-1', cheap + dear)], tmp_path),
                     record(claim='Version 2 costs less per passed task than version 1.', measure='cost_per_pass', direction='a_lower', minimum_effect=1.5))
    assert found['paired']['measure'] == 'cost_per_pass' and found['paired']['wins'] == 10 and found['paired']['losses'] == 0
    assert found['certainty']['word'] == 'probably' and 'costs less' in found['certainty']['sentence']
    assert found['outcome'] == 'supported'
    # The same costs claimed the other way lean against the claim.
    against = H.settle(studio_for([job('run-1', cheap + dear)], tmp_path),
                       record(claim='Version 2 costs more.', measure='cost_per_pass', direction='a_higher', minimum_effect=1.5))
    assert against['certainty']['word'] == 'cannot tell' and against['outcome'] == 'not_supported'
    # Equal costs everywhere: nothing to tell apart.
    same = H.settle(studio_for([job('run-1', rows(A['id'], 5, cost=1.0) + rows(B['id'], 5, cost=1.0))], tmp_path),
                    record(measure='cost_per_pass', direction='a_lower', minimum_effect=1.2))
    assert same['certainty']['word'] == 'cannot tell' and same['outcome'] == 'inconclusive'
