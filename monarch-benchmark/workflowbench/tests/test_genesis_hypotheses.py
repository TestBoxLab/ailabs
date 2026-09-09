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
def genesis(tmp_path):
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


def test_every_turn_records_a_prompt_with_the_date_and_the_recency_rule(tmp_path, monkeypatch):
    sent = []

    class Process:
        def __init__(self, command, **kwargs):
            self.returncode = 0
        def communicate(self, input=None, timeout=None):
            sent.append(input)
            return '', ''
        def poll(self):
            return self.returncode

    monkeypatch.setattr(harness.subprocess, 'Popen', Process)
    events = []
    genesis = SimpleNamespace(root=tmp_path, active={}, studio=SimpleNamespace(ledger=Mock(), runtime=SimpleNamespace(provider=lambda *a, **kw: nullcontext())),
                              event=lambda identity, kind, **data: events.append({'kind': kind, **data}), read=Mock(side_effect=FileNotFoundError))
    before = now_sao_paulo()
    harness.start_turn(genesis, {'id': 'fresh', 'maximum_usd': '1', 'model': 'gpt-5.6-sol', 'message': 'What changed in agent evaluation this quarter?'})
    recorded = (tmp_path / 'sessions' / 'fresh' / 'prompt.txt').read_text(encoding='utf8')
    assert recorded == sent[0]
    assert recorded.startswith('# Genesis scientist protocol')
    assert before.strftime('%Y-%m-%d') in recorded or now_sao_paulo().strftime('%Y-%m-%d') in recorded
    assert 'America/Sao_Paulo' in recorded
    assert 'Prefer sources from the last six months; keep foundational and contradicting work.' in recorded
    assert recorded.rstrip().endswith('What changed in agent evaluation this quarter?')
    assert events[-1]['kind'] == 'completed'
    genesis.studio.ledger.finish_run.assert_called_once_with('genesis-fresh')
