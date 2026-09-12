"""`smallest_plan` must size for the paired sign test that settles the hypothesis.

Feature 024, FR-021 / R11. It computed n = ceil(4·p·(1−p)/d²) with a floor of ten tasks
— the textbook size for comparing two INDEPENDENT proportions. `settle` decides the
same hypothesis with `measures.paired` -> `measures.sign_test`, which pairs by task and
drops ties. Those are different statistics, and the floor of ten is below anything the
sign test can conclude.

The minimum effect a hypothesis declares is exactly the share of tasks a real difference
is expected to flip, so it is also the expected discordant-pair rate. Sizing follows
from it directly: enough tasks that the expected pairs reach the floor.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio.measures import minimum_discordant_pairs


def record(effect=0.2, measure='pass_rate'):
    return {'claim': 'x helps', 'population': {'task_set': 'corpus'}, 'measure': measure,
            'direction': 'a_higher', 'minimum_effect': effect,
            'comparison': {'a': {'kind': 'architecture', 'id': 'v2', 'model': 'glm-5.3'},
                           'b': {'kind': 'architecture', 'id': 'v1', 'model': 'glm-5.3'}}}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_hypotheses.population_tasks',
                        lambda s, r: [f't{i}' for i in range(200)])
    monkeypatch.setattr('wb_studio.genesis_hypotheses.coverage', lambda s, r: [])
    monkeypatch.setattr('wb_studio.runtime_registry.check_launch',
                        lambda studio, architectures, selected, track='agentic-request': [])
    return SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), job=Mock(),
                           events=Mock(return_value=[]), ledger=Mock())


def plan(studio, **kw):
    from wb_studio.genesis_hypotheses import smallest_plan
    return smallest_plan(studio, record(**kw))


def test_the_size_reaches_the_sign_test_s_floor(studio):
    """A 20% minimum effect flips about a fifth of the tasks, so six discordant pairs
    need thirty tasks — not the ten the old floor allowed."""
    out = plan(studio, effect=0.2)
    assert out['tasks'] >= minimum_discordant_pairs() / 0.2
    assert out['power']['expected_pairs'] >= minimum_discordant_pairs()
    assert out['power']['ok'] is True


def test_a_smaller_effect_needs_more_tasks(studio):
    assert plan(studio, effect=0.1)['tasks'] > plan(studio, effect=0.4)['tasks']


def test_the_old_floor_of_ten_is_gone(studio):
    """Ten tasks could never settle anything; it was the default the floor produced."""
    assert plan(studio, effect=0.9)['tasks'] > 6
    for effect in (0.1, 0.2, 0.3, 0.5, 0.9):
        out = plan(studio, effect=effect)
        assert out['power']['ok'], f"a plan at effect {effect} cannot be settled"


def test_the_plan_carries_its_power_for_the_record(studio):
    power = plan(studio, effect=0.2)['power']
    assert set(power) >= {'ok', 'expected_pairs', 'wins_needed', 'flip_rate', 'reason'}
    assert power['wins_needed'] <= power['expected_pairs']


def test_the_basis_says_which_test_it_sized_for(studio):
    out = plan(studio, effect=0.2)
    assert 'sign test' in out['basis'].lower()
    assert 'discordant' in out['basis'].lower()


def test_a_population_too_small_to_settle_is_refused_not_trimmed(studio, monkeypatch):
    """Silently capping at the population is how an unsettleable experiment got launched."""
    monkeypatch.setattr('wb_studio.genesis_hypotheses.population_tasks',
                        lambda s, r: [f't{i}' for i in range(10)])
    out = plan(studio, effect=0.2)
    assert out['power']['ok'] is False
    assert out.get('not_launchable') or 'cannot be settled' in out['power']['reason']
    assert str(out['power']['sufficient_tasks']) in out['power']['reason']


def test_a_ratio_measure_sizes_on_the_effect_above_one(studio):
    out = plan(studio, effect=1.25, measure='cost_per_pass')
    assert out['power']['flip_rate'] == pytest.approx(0.25)
