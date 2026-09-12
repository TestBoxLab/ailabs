"""`wb experiment`: the hypothesis record from a terminal (feature 024, T083).

No new store. This is a surface over the record `wb_studio/genesis_hypotheses.py`
already validates, sizes and settles — today reachable only through Genesis's own tools,
which is why a person cannot check a proposal without asking the model to do it.

`propose` never spends: it sizes against the paired sign test that settles the
hypothesis, and refuses before any reservation when that test could not conclude at the
size asked for. `confirm` is the held-out gate: a lineage reaches that slate once, and
only after it won on development.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from wb_orchestrator.cli import cmd_experiment_confirm, cmd_experiment_propose


def args(**changes):
    base = dict(claim='naming the record owner raises pass rate', measure='pass_rate',
                direction='a_higher', minimum_effect=0.2, task_set='catalog-50',
                a='v2', b='v1', model='glm-5.3', repetitions=1, slate='development',
                id=None, parent=None, out=None, ledger=None)
    return SimpleNamespace(**{**base, **changes})


def test_a_proposal_reports_its_power_and_the_size_it_needs(capsys, tmp_path):
    assert cmd_experiment_propose(args(out=str(tmp_path))) == 0
    out = capsys.readouterr().out
    assert 'discordant' in out and 'sign test' in out.lower()
    assert 'tasks' in out


def test_a_size_the_sign_test_cannot_settle_is_refused_before_any_reservation(capsys, tmp_path):
    code = cmd_experiment_propose(args(out=str(tmp_path), minimum_effect=0.05, task_set='tier-simple'))
    err = capsys.readouterr().err
    assert code == 2
    assert 'cannot be settled' in err and 'tasks' in err


def test_the_refusal_names_a_sufficient_size(capsys, tmp_path):
    cmd_experiment_propose(args(out=str(tmp_path), minimum_effect=0.05, task_set='tier-simple'))
    err = capsys.readouterr().err
    import re
    assert re.search(r'\d+ tasks', err)


def test_a_proposal_defaults_to_the_development_slate(capsys, tmp_path):
    cmd_experiment_propose(args(out=str(tmp_path)))
    assert 'development' in capsys.readouterr().out


def test_confirm_refuses_a_lineage_nobody_recorded(capsys, tmp_path):
    code = cmd_experiment_confirm(SimpleNamespace(lineage='never-ran', out=str(tmp_path), ledger=None))
    err = capsys.readouterr().err
    assert code == 2 and 'never-ran' in err


def test_confirm_refuses_a_lineage_that_has_not_won_on_development(capsys, tmp_path):
    from wb_studio.app import Studio
    from wb_studio import genesis_hypotheses as H
    studio = Studio(tmp_path / 'studio', tasks={}, gateway_factory=lambda *a, **k: None)
    studio.genesis.card({'id': 'e1', 'title': 'e1', 'stage': 'hypothesis', 'kind': 'hypothesis',
                         'hypothesis': H.check_hypothesis({
                             'claim': 'x helps', 'population': {'task_set': 'catalog-50'},
                             'measure': 'pass_rate', 'direction': 'a_higher', 'minimum_effect': 0.2,
                             'slate': 'development', 'lineage': 'L',
                             'comparison': {'a': {'kind': 'architecture', 'id': 'v2'},
                                            'b': {'kind': 'architecture', 'id': 'v1'}}})})
    code = cmd_experiment_confirm(SimpleNamespace(lineage='L', out=str(tmp_path / 'studio'), ledger=None))
    assert code == 2 and 'supported' in capsys.readouterr().err.lower()


def test_confirm_names_the_prior_attempt_when_the_lineage_is_spent(capsys, tmp_path):
    from wb_studio.app import Studio
    from wb_studio import genesis_hypotheses as H
    studio = Studio(tmp_path / 'studio', tasks={}, gateway_factory=lambda *a, **k: None)
    g = studio.genesis
    for identity, slate, outcome in (('e1', 'development', 'supported'), ('e2', 'held-out', 'not-supported')):
        g.card({'id': identity, 'title': identity, 'stage': 'hypothesis', 'kind': 'hypothesis',
                'hypothesis': H.check_hypothesis({
                    'claim': 'x helps', 'population': {'task_set': 'dev-50'}, 'measure': 'pass_rate',
                    'direction': 'a_higher', 'minimum_effect': 0.2, 'slate': slate, 'lineage': 'L',
                    'comparison': {'a': {'kind': 'architecture', 'id': 'v2'},
                                   'b': {'kind': 'architecture', 'id': 'v1'}}}),
                'settlement': {'outcome': outcome}})
    code = cmd_experiment_confirm(SimpleNamespace(lineage='L', out=str(tmp_path / 'studio'), ledger=None))
    err = capsys.readouterr().err
    assert code == 2 and 'once' in err.lower() and 'e2' in err
