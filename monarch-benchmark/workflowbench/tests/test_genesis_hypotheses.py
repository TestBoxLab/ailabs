"""Offline contracts for hypothesis colours and the freshness rule in every Genesis turn."""
import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_harness as harness
from wb_studio.genesis import Genesis, hypothesis_outcome
from wb_studio.library import now_sao_paulo

CANDIDATE, PARENT = 'blueprint.a.v2', 'blueprint.a.v1'
GOAL = {'version': CANDIDATE, 'parent_version': PARENT, 'minimum_gain': 0.2, 'maximum_cost_ratio': 1.5, 'minimum_pass_rate': 0.5}


def card(goal=GOAL, job='run-1'):
    return {'id': 'card', 'job': job, 'proposal': {'tasks': ['t1', 't2', 't3', 't4'], 'goal': goal} if goal else {'tasks': ['t1']}}


def rows(model, passed, cost=1.0, termination='completed', suffix=''):
    return [{'task': 't' + str(i + 1), 'model': model + suffix, 'passed': i < passed, 'cost_usd': cost,
             'termination': termination if i == 0 else 'completed', 'flags': []} for i in range(4)]


def run(results, status='completed', bare=True):
    arms = [{'id': CANDIDATE, 'kind': 'version'}, {'id': PARENT, 'kind': 'version'}]
    if bare:
        arms.append({'id': 'bare', 'kind': 'native', 'version': 'without-monarch'})
    return {'id': 'run-1', 'status': status, 'settings': {'arms': arms, 'tasks': ['t1', 't2', 't3', 't4']},
            'results': results + (rows('bare', 2) if bare else [])}


@pytest.mark.parametrize('label,card_value,job_value,colour,outcome', [
    ('no run', card(job=None), None, 'white', 'Untested'),
    ('run not finished', card(), run(rows(CANDIDATE, 3) + rows(PARENT, 1), status='running'), 'white', 'Untested'),
    ('run record missing', card(), None, 'neutral', 'Invalid'),
    ('run failed', card(), run(rows(CANDIDATE, 3) + rows(PARENT, 1), status='failed'), 'neutral', 'Invalid'),
    ('no goal declared', card(goal=None), run(rows(CANDIDATE, 3) + rows(PARENT, 1)), 'neutral', 'Invalid'),
    ('infrastructure failure is never red', card(), run(rows(CANDIDATE, 0, termination='infra:provider') + rows(PARENT, 4)), 'neutral', 'Invalid'),
    ('Bare not shown', card(), run(rows(CANDIDATE, 3) + rows(PARENT, 1), bare=False), 'neutral', 'Invalid'),
    ('parent version absent from the run', card(), run(rows(CANDIDATE, 3)), 'neutral', 'Invalid'),
    ('goal met', card(), run(rows(CANDIDATE, 3) + rows(PARENT, 1)), 'green', 'Met goal'),
    ('goal met through model comparison arms', card(), run(rows(CANDIDATE, 3, suffix='--gpt') + rows(PARENT, 1, suffix='--gpt')), 'green', 'Met goal'),
    ('net negative', card(), run(rows(CANDIDATE, 1) + rows(PARENT, 3)), 'red', 'Net negative'),
    ('gain under the minimum', card(), run(rows(CANDIDATE, 2) + rows(PARENT, 2)), 'neutral', 'Inconclusive'),
    ('cost above the limit', card(), run(rows(CANDIDATE, 3, cost=2.0) + rows(PARENT, 1, cost=1.0)), 'neutral', 'Inconclusive'),
    ('cost unknown', card(), run(rows(CANDIDATE, 3, cost=None) + rows(PARENT, 1)), 'neutral', 'Inconclusive'),
    ('pass rate under the reliability floor', card(), run(rows(CANDIDATE, 1) + rows(PARENT, 0)), 'neutral', 'Inconclusive'),
])
def test_hypothesis_colour_follows_the_written_rules(label, card_value, job_value, colour, outcome):
    result = hypothesis_outcome(card_value, job_value)
    assert (result['colour'], result['label']) == (colour, outcome), label
    assert result['reason']


def test_green_needs_every_condition_at_once():
    good = run(rows(CANDIDATE, 3) + rows(PARENT, 1))
    assert hypothesis_outcome(card(), good)['colour'] == 'green'
    assert hypothesis_outcome(card(goal={**GOAL, 'minimum_gain': 0.6}), good)['label'] == 'Inconclusive'
    assert hypothesis_outcome(card(goal={**GOAL, 'maximum_cost_ratio': 0.5}), run(rows(CANDIDATE, 3, cost=1.0) + rows(PARENT, 1, cost=1.0)))['label'] == 'Inconclusive'
    assert hypothesis_outcome(card(goal={**GOAL, 'minimum_pass_rate': 1}), good)['label'] == 'Inconclusive'
    assert hypothesis_outcome(card(goal={'version': CANDIDATE, 'parent_version': PARENT, 'minimum_gain': 0.2}), good)['colour'] == 'green'


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_plugins.gate_launch', lambda g, c: (True, None))  # feature 022's Reviewer gate has its own tests
    studio = SimpleNamespace(directory=tmp_path, create=Mock(return_value={'id': 'run-1'}), jobs=Mock(return_value=[]),
                             job=Mock(), events=Mock(return_value=[]), ledger=Mock())
    return Genesis(studio)


@pytest.mark.parametrize('goal', [
    'not an object', {}, {'version': CANDIDATE, 'parent_version': CANDIDATE, 'minimum_gain': 0.2},
    {'version': CANDIDATE, 'parent_version': PARENT}, {'version': CANDIDATE, 'parent_version': PARENT, 'minimum_gain': 0},
    {'version': CANDIDATE, 'parent_version': PARENT, 'minimum_gain': True},
    {'version': CANDIDATE, 'parent_version': PARENT, 'minimum_gain': '0.2'},
    {'version': CANDIDATE, 'parent_version': PARENT, 'minimum_gain': 1.5},
    {**GOAL, 'maximum_cost_ratio': 0}, {**GOAL, 'minimum_pass_rate': 1.5}, {**GOAL, 'minimum_pass_rate': 'high'},
])
def test_goal_is_validated_before_the_proposal_is_saved(genesis, goal):
    with pytest.raises(ValueError, match='goal'):
        genesis.card({'id': 'bad-goal', 'title': 'Bad goal', 'stage': 'approval', 'proposal': {'tasks': ['t1'], 'goal': goal}})
    assert genesis.listing('cards') == []


def test_goal_is_part_of_the_frozen_proposal(genesis):
    without = genesis.card({'id': 'plain', 'title': 'Plain', 'stage': 'approval', 'proposal': {'tasks': ['t1']}})
    with_goal = genesis.card({'id': 'goal', 'title': 'Goal', 'stage': 'approval', 'proposal': {'tasks': ['t1'], 'goal': GOAL}})
    assert with_goal['proposal']['goal'] == GOAL
    assert with_goal['proposal_digest'] != without['proposal_digest']
    approved = genesis.approve('goal', {'revision': with_goal['revision'], 'digest': with_goal['proposal_digest']})
    assert genesis.studio.create.call_args.args[0]['goal'] == GOAL
    with pytest.raises(ValueError, match='cannot be edited'):
        genesis.card({**approved, 'proposal': {**approved['proposal'], 'goal': {**GOAL, 'minimum_gain': 0.01}}})


def test_state_exposes_the_outcome_of_every_card(genesis, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [])
    genesis.card({'id': 'idea', 'title': 'Idea', 'stage': 'hypothesis'})
    saved = genesis.card({'id': 'tested', 'title': 'Tested', 'stage': 'approval', 'proposal': {'tasks': ['t1'], 'goal': GOAL}})
    genesis.approve('tested', {'revision': saved['revision'], 'digest': saved['proposal_digest']})
    genesis.studio.job.return_value = run(rows(CANDIDATE, 3) + rows(PARENT, 1))
    outcomes = {c['id']: c['outcome'] for c in genesis.state()['cards']}
    assert (outcomes['idea']['colour'], outcomes['idea']['label']) == ('white', 'Untested')
    assert (outcomes['tested']['colour'], outcomes['tested']['label']) == ('green', 'Met goal')
    genesis.studio.job.side_effect = FileNotFoundError('gone')
    assert {c['id']: c['outcome']['label'] for c in genesis.state()['cards']} == {'idea': 'Untested', 'tested': 'Invalid'}


def test_freshness_names_the_sao_paulo_clock_and_the_recency_rule():
    fixed = datetime(2026, 9, 9, 14, 5, tzinfo=timezone(timedelta(hours=-3)))
    text = harness.freshness(fixed)
    assert '2026-09-09 14:05' in text and 'America/Sao_Paulo' in text
    assert 'Prefer sources from the last six months; keep foundational and contradicting work.' in text
    assert now_sao_paulo().utcoffset() == timedelta(hours=-3)


def test_every_turn_records_a_prompt_with_the_date_and_the_recency_rule(tmp_path):
    genesis = SimpleNamespace(root=tmp_path, read=Mock(side_effect=FileNotFoundError))
    before = now_sao_paulo()
    system, brief = harness.build_prompt(genesis, {'id': 'fresh', 'message': 'What changed in agent evaluation this quarter?'})
    assert system.startswith('# Genesis scientist protocol')
    assert before.strftime('%Y-%m-%d') in brief or now_sao_paulo().strftime('%Y-%m-%d') in brief
    assert 'America/Sao_Paulo' in brief
    assert 'Prefer sources from the last six months; keep foundational and contradicting work.' in brief
    assert brief.rstrip().endswith('What changed in agent evaluation this quarter?')


def test_task_values_false_completion_restricts_to_competitor_produced_output():
    from wb_studio.genesis_hypotheses import _task_values
    rows = [
        {"task": "t1", "model": "m", "passed": False, "termination": "agent_error", "output": "Please complete this task."},
        {"task": "t2", "model": "m", "passed": False, "termination": "completed", "output": "I am done."},
        {"task": "t3", "model": "m", "passed": True, "termination": "completed", "output": "Done."},
    ]
    values = _task_values(rows, [], "false_completion")
    assert values.get("t1") == 0.0
    assert values.get("t2") == 1.0
    assert "t3" not in values


def test_variant_test_defaults_to_development_slate():
    from wb_studio.genesis_hypotheses import check_hypothesis
    record = {
        'claim': 'Naming the record owner raises pass rate.',
        'population': {'filter': {'domain': 'finance'}},
        'comparison': {'a': {'kind': 'architecture', 'id': 'v2'},
                       'b': {'kind': 'architecture', 'id': 'v1'}},
        'measure': 'pass_rate',
        'direction': 'a_higher',
        'minimum_effect': 0.2,
    }
    checked = check_hypothesis(record)
    assert checked['slate'] == 'development'


def test_variant_test_accepts_held_out_slate_and_refuses_unknown():
    from wb_studio.genesis_hypotheses import check_hypothesis
    record = {
        'claim': 'Naming the record owner raises pass rate.',
        'population': {'filter': {'domain': 'finance'}},
        'comparison': {'a': {'kind': 'architecture', 'id': 'v2'},
                       'b': {'kind': 'architecture', 'id': 'v1'}},
        'measure': 'pass_rate',
        'direction': 'a_higher',
        'minimum_effect': 0.2,
        'slate': 'held-out',
    }
    assert check_hypothesis(record)['slate'] == 'held-out'

    with pytest.raises(ValueError, match='development or held-out'):
        check_hypothesis({**record, 'slate': 'validation'})


def test_smallest_plan_refuses_size_when_sign_test_cannot_reach_significance(tmp_path):
    from wb_studio.genesis_hypotheses import smallest_plan
    tasks = {'t%d' % i: {'task': 't%d' % i, 'info': {}} for i in range(10)}
    studio = SimpleNamespace(directory=tmp_path, tasks=tasks, jobs=lambda: [],
                             job=lambda identity: None, events=lambda i, after=0: [],
                             budget=lambda: {}, ledger=Mock(), create=Mock())
    record = {
        'claim': 'V2 beats V1.',
        'population': {'filter': {'task_ids': ['t%d' % i for i in range(10)]}},
        'comparison': {'a': {'kind': 'architecture', 'id': 'v2'},
                       'b': {'kind': 'architecture', 'id': 'v1'}},
        'measure': 'pass_rate',
        'direction': 'a_higher',
        'minimum_effect': 0.2,
    }
    plan = smallest_plan(studio, record)
    assert plan['power']['ok'] is False
    assert 'cannot be settled' in plan['not_launchable']


def test_smallest_plan_refuses_when_exceeding_envelope_remainder(tmp_path, monkeypatch):
    from wb_studio.genesis_hypotheses import smallest_plan
    from wb_studio.genesis_access import Envelope
    from decimal import Decimal

    tasks = {'t%d' % i: {'task': 't%d' % i, 'info': {}} for i in range(100)}
    studio = SimpleNamespace(directory=tmp_path, tasks=tasks, jobs=lambda: [],
                             job=lambda identity: None, events=lambda i, after=0: [],
                             budget=lambda: {}, ledger=None, create=Mock())
    # Envelope has $3.00 left
    env = Envelope(tmp_path / 'genesis')
    env.set(amount_usd='50.00', per_experiment_ceiling_usd='40.00', by='Lucas')
    monkeypatch.setattr(env, 'status', lambda ledger=None: {
        'week_start': '2026-09-07', 'amount_usd': '50.00', 'per_experiment_ceiling_usd': '40.00',
        'held_usd': '47.00', 'settled_usd': '0.00', 'available_usd': Decimal('3.00'),
        'left_usd': '3.00', 'is_set': True, 'set_by': 'human:lucas', 'set_at': '2026-09-11T00:00:00Z',
    })
    studio.envelope = env

    record = {
        'claim': 'V2 beats V1 on development slate.',
        'population': {'filter': {'task_ids': ['t%d' % i for i in range(50)]}},
        'comparison': {'a': {'kind': 'architecture', 'id': 'v2', 'model': 'gemini-3.7-flash'},
                       'b': {'kind': 'architecture', 'id': 'v1', 'model': 'gemini-3.7-flash'}},
        'measure': 'pass_rate',
        'direction': 'a_higher',
        'minimum_effect': 0.2,
    }
    plan = smallest_plan(studio, record)
    assert plan['power']['ok'] is True
    max_usd = Decimal(plan['proposal']['maximum_usd'])
    assert max_usd > Decimal('3.00')
    shortfall = max_usd - Decimal('3.00')
    expected_refusal = (
        f"refused: this experiment reserves up to ${max_usd:.2f}; "
        f"the research envelope has $3.00 left this week. "
        f"Short by ${shortfall:.2f}. It will not draw on the lab's weekly ceiling."
    )
    assert plan['not_launchable'] == expected_refusal


def test_smallest_plan_refuses_when_exceeding_per_experiment_ceiling(tmp_path):
    from wb_studio.genesis_hypotheses import smallest_plan
    from wb_studio.genesis_access import Envelope
    from decimal import Decimal

    tasks = {'t%d' % i: {'task': 't%d' % i, 'info': {}} for i in range(100)}
    studio = SimpleNamespace(directory=tmp_path, tasks=tasks, jobs=lambda: [],
                             job=lambda identity: None, events=lambda i, after=0: [],
                             budget=lambda: {}, ledger=None, create=Mock())
    env = Envelope(tmp_path / 'genesis')
    env.set(amount_usd='200.00', per_experiment_ceiling_usd='0.05', by='Lucas')
    studio.envelope = env

    record = {
        'claim': 'V2 beats V1 on development slate.',
        'population': {'filter': {'task_ids': ['t%d' % i for i in range(50)]}},
        'comparison': {'a': {'kind': 'architecture', 'id': 'v2', 'model': 'gemini-3.7-flash'},
                       'b': {'kind': 'architecture', 'id': 'v1', 'model': 'gemini-3.7-flash'}},
        'measure': 'pass_rate',
        'direction': 'a_higher',
        'minimum_effect': 0.2,
    }
    plan = smallest_plan(studio, record)
    assert plan['power']['ok'] is True
    max_usd = Decimal(plan['proposal']['maximum_usd'])
    assert max_usd > Decimal('0.05')
    shortfall = max_usd - Decimal('0.05')
    expected_refusal = (
        f"refused: this experiment reserves up to ${max_usd:.2f}; "
        f"the per-experiment ceiling is $0.05. Short by ${shortfall:.2f}."
    )
    assert plan['not_launchable'] == expected_refusal




# --- the proposal: what a held-out confirmation produces (FR-034) ---

def _lineage_genesis(cards):
    return SimpleNamespace(listing=lambda kind: cards if kind == 'cards' else [])


def _confirmed_card(slate='held-out', outcome='supported', identity='c2'):
    return {
        'id': identity, 'created_at': '2026-09-11T10:00:00Z', 'lineage': 'L1',
        'hypothesis': {'claim': 'Naming the record owner raises pass rate.',
                       'slate': slate, 'lineage': 'L1', 'repetitions': 3,
                       'comparison': {'a': {'kind': 'architecture', 'id': 'v2'},
                                      'b': {'kind': 'architecture', 'id': 'v1'}},
                       'measure': 'pass_rate', 'direction': 'a_higher',
                       'minimum_effect': 0.2},
        'settlement': {'outcome': outcome, 'effect': 0.3, 'certainty': 'probably',
                       'paired': {'wins': 8, 'losses': 1, 'pairs': 9, 'p_value': 0.02},
                       'tags': ['[rec:run:run-9]']},
    }


def test_a_proposal_comes_only_from_a_supported_held_out_confirmation():
    from wb_studio.genesis_hypotheses import proposal
    ok = proposal(_lineage_genesis([_confirmed_card()]), 'L1')
    assert ok['variant'] == 'v2' and ok['baseline'] == 'v1'
    assert ok['slate'] == 'held-out' and ok['repetitions'] == 3
    assert ok['paired_result']['p_value'] == 0.02
    assert '[rec:run:run-9]' in ok['evidence']
    # A written specification, not something anybody can execute.
    assert ok['kind'] == 'written-specification'
    assert 'v2' in ok['rationale'] and '8' in ok['rationale']


def test_a_development_result_alone_is_not_a_proposal():
    """FR-034. Development is where the search happens; it is contaminated by design."""
    from wb_studio.genesis_hypotheses import proposal
    out = proposal(_lineage_genesis([_confirmed_card(slate='development')]), 'L1')
    assert out['proposal'] is None
    assert 'held-out' in out['reason']


def test_a_held_out_result_that_did_not_hold_is_not_a_proposal():
    from wb_studio.genesis_hypotheses import proposal
    out = proposal(_lineage_genesis([_confirmed_card(outcome='not_supported')]), 'L1')
    assert out['proposal'] is None and 'not_supported' in out['reason']
