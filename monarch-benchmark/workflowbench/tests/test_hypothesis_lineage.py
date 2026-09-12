"""A variant reaches the held-out slate once, and only after it won on development.

Feature 024, FR-022. The held-out slate is the lab's one uncontaminated measurement: a
variant that can be retried against it until it passes is not a confirmation, it is a
search over the confirmation set, and the slate is spent the moment that happens.

So a lineage — a record and everything descended from it — gets exactly one held-out
attempt. Not one per record: re-wording a claim, nudging the minimum effect or forking a
variant would otherwise mint a fresh ticket to the same slate.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import genesis_hypotheses as H


def record(**changes):
    base = {'claim': 'x helps', 'population': {'task_set': 'dev-50'}, 'measure': 'pass_rate',
            'direction': 'a_higher', 'minimum_effect': 0.2,
            'comparison': {'a': {'kind': 'architecture', 'id': 'v2', 'model': 'glm-5.3'},
                           'b': {'kind': 'architecture', 'id': 'v1', 'model': 'glm-5.3'}}}
    return {**base, **changes}


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    from wb_studio.genesis import Genesis
    studio = SimpleNamespace(directory=tmp_path, jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    return Genesis(studio)


# --- the record carries slate, repetitions and a lineage -------------------------------

def test_a_record_defaults_to_the_development_slate():
    assert H.check_hypothesis(record())['slate'] == 'development'


def test_a_record_may_name_the_held_out_slate():
    assert H.check_hypothesis(record(slate='held-out'))['slate'] == 'held-out'


def test_any_other_slate_is_refused():
    for bad in ('production', 'dev', '', 'HELD-OUT', 1):
        with pytest.raises(ValueError, match='(?i)slate'):
            H.check_hypothesis(record(slate=bad))


def test_repetitions_are_a_whole_number_above_zero():
    assert H.check_hypothesis(record())['repetitions'] == 1
    assert H.check_hypothesis(record(repetitions=3))['repetitions'] == 3
    for bad in (0, -1, 1.5, '3'):
        with pytest.raises(ValueError, match='(?i)repetition'):
            H.check_hypothesis(record(repetitions=bad))


def test_a_root_record_is_its_own_lineage():
    out = H.check_hypothesis(record(id='exp-1'))
    assert out['lineage'] == 'exp-1'


def test_a_descendant_keeps_its_parent_s_lineage():
    out = H.check_hypothesis(record(id='exp-2', parent='exp-1', lineage='exp-1'))
    assert out['lineage'] == 'exp-1'


# --- the once-only rule ----------------------------------------------------------------

def write(genesis, identity, *, lineage, slate, outcome=None):
    card = {'id': identity, 'title': identity, 'stage': 'hypothesis', 'kind': 'hypothesis',
            'hypothesis': H.check_hypothesis(record(id=identity, lineage=lineage, slate=slate))}
    if outcome:
        card['settlement'] = {'outcome': outcome}
    genesis.card(card)
    return card


def test_a_lineage_with_no_development_win_may_not_reach_held_out(genesis):
    write(genesis, 'exp-1', lineage='L', slate='development')
    ok, why = H.may_confirm(genesis, 'L')
    assert ok is False and 'supported' in why.lower()


def test_a_supported_development_result_opens_the_held_out_slate(genesis):
    write(genesis, 'exp-1', lineage='L', slate='development', outcome='supported')
    ok, why = H.may_confirm(genesis, 'L')
    assert ok is True and why is None


def test_a_lineage_that_already_reached_held_out_is_refused(genesis):
    write(genesis, 'exp-1', lineage='L', slate='development', outcome='supported')
    write(genesis, 'exp-2', lineage='L', slate='held-out', outcome='supported')
    ok, why = H.may_confirm(genesis, 'L')
    assert ok is False and 'once' in why.lower() and 'exp-2' in why


def test_a_refused_held_out_attempt_still_spends_the_lineage(genesis):
    """Not supported is a result. Retrying it is the search this rule exists to stop."""
    write(genesis, 'exp-1', lineage='L', slate='development', outcome='supported')
    write(genesis, 'exp-2', lineage='L', slate='held-out', outcome='not-supported')
    ok, why = H.may_confirm(genesis, 'L')
    assert ok is False and 'once' in why.lower()


def test_a_descendant_of_a_spent_lineage_is_refused_too(genesis):
    """Re-wording the claim must not mint a fresh ticket to the same slate."""
    write(genesis, 'exp-1', lineage='L', slate='development', outcome='supported')
    write(genesis, 'exp-2', lineage='L', slate='held-out', outcome='not-supported')
    write(genesis, 'exp-3', lineage='L', slate='development', outcome='supported')
    ok, _ = H.may_confirm(genesis, 'L')
    assert ok is False


def test_a_different_lineage_is_unaffected(genesis):
    write(genesis, 'exp-1', lineage='L', slate='development', outcome='supported')
    write(genesis, 'exp-2', lineage='L', slate='held-out', outcome='supported')
    write(genesis, 'exp-9', lineage='M', slate='development', outcome='supported')
    assert H.may_confirm(genesis, 'M')[0] is True
