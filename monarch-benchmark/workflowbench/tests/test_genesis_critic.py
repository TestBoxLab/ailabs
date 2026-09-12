"""The weekly adversary (feature 023 §5.6): it runs on the digest day, on a route of its own, it
sees the pages, it may only cite a rubric line that exists on disk, and each finding becomes one
card. Offline: no browser is started and no model is asked anything."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_orchestrator.budget import BudgetLedger
from wb_studio import genesis_critic as critic
from wb_studio.genesis import Genesis

ROUTES = [{'id': 'glm-5.3', 'available': True}, {'id': 'claude-opus-5', 'available': True}]
SEEN = {'shots': [{'view': 'runs', 'theme': 'light', 'layout': {'overflow_px': 0}, 'errors': []}],
        'images': ['/tmp/runs-light-crop.png']}
FINDING = {'analysis': 'lowest_contrast records 4.1 on the 11px "3 runs" line; F12 wants 4.5 at that size.',
           'rubric': 'figures:F12', 'where': 'Runs, the week line', 'what': 'Contrast is 4.1 on 11px text',
           'why_it_matters': 'A reader on a bright screen cannot read the run count.',
           'fix': 'Take the muted ink one step darker in the light theme.'}


@pytest.fixture
def genesis(tmp_path, monkeypatch):
    (tmp_path / 'genesis').mkdir(exist_ok=True)
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: ROUTES)
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]),
                             events=Mock(return_value=[]), job=Mock(),
                             ledger=BudgetLedger(tmp_path / 'budget.sqlite3'), budget=Mock(return_value={}))
    made = Genesis(studio)
    studio.genesis = made
    return made


def turn(answer, status='completed'):
    return {'id': 'c1', 'status': status, 'purpose': critic.PURPOSE, 'message': 'review', 'answer': answer, 'events': []}


# -- the rubrics are the standard, and they live on disk -------------------------------

def test_every_rubric_id_is_read_from_the_file_a_person_edits():
    ids = critic.rubric_lines()
    assert {'prose:P5', 'figures:F10', 'figures:F12', 'accuracy:A6'} <= ids
    assert len(ids) >= 35 and all(':' in i for i in ids)
    assert 'Signs of AI writing' in critic.rubric('prose')
    assert 'overflow_px' in critic.rubric('figures')          # the numeric rules name the measured field


def test_a_finding_may_only_cite_a_rubric_line_that_exists():
    allowed = critic.rubric_lines()
    assert critic.check_finding(FINDING, allowed)['rubric'] == 'figures:F12'
    for bad, message in [({'rubric': 'figures:F99'}, 'rubric line that exists'),
                         ({'rubric': 'vibes'}, 'rubric line that exists'),
                         ({'fix': ''}, 'what to do'),
                         ({'analysis': 'it looks bad'}, 'quotes its evidence')]:
        with pytest.raises(ValueError, match=message):
            critic.check_finding({**FINDING, **bad}, allowed)


def test_the_critic_is_told_an_empty_week_is_a_good_answer():
    """A model asked for findings and given no way to return none will invent one to fill the slot."""
    assert '"findings": [] is a correct answer' in critic.OUTPUT
    assert 'Do not fill the list' in critic.OUTPUT
    fields = [line.strip().split('"')[1] for line in critic.OUTPUT.splitlines() if line.strip().startswith('"')]
    # The six judgement fields are alphabetical so a provider that sorts keys keeps the order;
    # `spec` and `figure` trail because they are outputs, not reasoning.
    assert fields[0] == 'analysis' and fields[:6] == sorted(fields[:6]) and fields[6:] == ['spec', 'figure']


def test_no_findings_files_no_cards_and_is_recorded_as_a_review(genesis):
    critic.ON_TURN(genesis, turn(json.dumps({'findings': []})))
    assert genesis.listing('cards') == []
    assert any(e.get('status') == 'reviewed' and e.get('findings') == 0 for e in genesis.autonomy.tail())


def test_a_judge_from_the_writers_own_family_is_named_as_one(genesis, monkeypatch):
    """Self-preference is measured and large; the turn is told when it applies."""
    assert critic.same_family({'id': 'glm-5.3'}, {'id': 'glm-5.3'}) is True
    assert critic.same_family({'id': 'claude-opus-4-8'}, {'id': 'claude-opus-5'}) is True   # same family, different id
    assert critic.same_family({'id': 'claude-opus-5'}, {'id': 'gemini-3.7-flash'}) is False
    assert critic.same_family(None, {'id': 'glm-5.3'}) is False


# -- when it runs ----------------------------------------------------------------------

def test_it_runs_on_the_digest_day_and_not_otherwise(genesis, monkeypatch):
    from datetime import datetime, timezone
    genesis.access.set_settings({'digest_day': 'wednesday'})
    monday = datetime(2026, 9, 14, 9, tzinfo=timezone.utc)
    wednesday = datetime(2026, 9, 16, 9, tzinfo=timezone.utc)
    assert critic.due_today(genesis.studio, monday) is False
    assert critic.due_today(genesis.studio, wednesday) is True
    monkeypatch.setattr(critic, 'now_sao_paulo', lambda: monday)
    monkeypatch.setattr(genesis, 'chat', Mock(side_effect=AssertionError('a turn was started')))
    assert 'digest day' in critic.critic(genesis.studio)['reason']


def test_pause_stops_it(genesis, monkeypatch):
    genesis.autonomy.set({'paused': True})
    monkeypatch.setattr(genesis, 'chat', Mock(side_effect=AssertionError('a turn was started')))
    assert 'paused' in critic.critic(genesis.studio)['reason']


def test_it_takes_its_own_route_and_says_when_it_is_the_writers(genesis, monkeypatch):
    monkeypatch.setattr(critic, 'due_today', lambda studio, now=None: True)
    monkeypatch.setattr(critic, 'look', lambda studio: SEEN)
    monkeypatch.setattr(critic, 'newest_report', lambda studio: None)
    monkeypatch.setattr(genesis, 'chat', Mock(return_value={'id': 'c1'}))
    genesis.config.set({'models': {'critic': 'claude-opus-5', 'reading': 'glm-5.3'}}, routes=ROUTES)
    summary = critic.critic(genesis.studio)
    assert summary['model'] == 'claude-opus-5' and summary['same_model'] is False
    payload = genesis.chat.call_args[0][0]
    assert payload['purpose'] == critic.PURPOSE and payload['images'] == SEEN['images']
    assert 'Signs of AI writing' not in payload['message'] or 'figures:F10' in payload['message']
    assert 'overflow_px' in payload['message']                # the measured record reaches the model

    genesis.config.set({'models': {'critic': 'glm-5.3'}}, routes=ROUTES)
    assert critic.critic(genesis.studio)['same_model'] is True
    assert 'same model family' in genesis.chat.call_args[0][0]['message']


def test_a_page_that_cannot_be_rendered_does_not_stop_the_review(genesis, monkeypatch):
    monkeypatch.setattr(critic, 'due_today', lambda studio, now=None: True)
    monkeypatch.setattr(critic, 'look', lambda studio: {'shots': [], 'images': [], 'skipped': 'Playwright not found.'})
    monkeypatch.setattr(critic, 'newest_report', lambda studio: None)
    monkeypatch.setattr(genesis, 'chat', Mock(return_value={'id': 'c1'}))
    summary = critic.critic(genesis.studio)
    assert summary['turn'] == 'c1' and summary['skipped'] == 'Playwright not found.'
    assert 'do not guess at the layout' in genesis.chat.call_args[0][0]['message']


# -- the cards -------------------------------------------------------------------------

def test_each_finding_becomes_one_card_that_names_the_rubric_line(genesis):
    critic.ON_TURN(genesis, turn(json.dumps({'findings': [FINDING, {**FINDING, 'rubric': 'prose:P5'}]})))
    cards = genesis.listing('cards')
    assert len(cards) == 2 and all(c['kind'] == 'enhancement' and c['stage'] == 'review' and not c['auto'] for c in cards)
    assert cards[0]['title'].startswith('figures:F12 — ') and cards[0]['audience'] == 'internal'
    assert cards[0]['body'].startswith('Contrast is 4.1 on 11px text.')          # the claim, first
    assert '| Fails | figures:F12 |' in cards[0]['body'] and '| Costs the reader |' in cards[0]['body']
    assert len(cards[0]['body']) < 900                                          # read in fifteen seconds
    assert cards[0]['finding']['fix'].startswith('Take the muted ink')


def test_an_invented_rubric_line_is_refused_and_files_no_card(genesis):
    critic.ON_TURN(genesis, turn(json.dumps({'findings': [{**FINDING, 'rubric': 'figures:F99'}]})))
    assert genesis.listing('cards') == []
    assert any(e.get('status') == 'refused' for e in genesis.autonomy.tail())


def test_at_most_one_finding_a_week_is_implemented(genesis, monkeypatch):
    monkeypatch.setattr(critic.engineer, 'commit_of', lambda studio, which: 'abc1234def')
    calls = []
    monkeypatch.setattr(critic.engineer, 'implement',
                        lambda g, spec, t: calls.append(spec) or {'diff': 'd', 'changed': True, 'verified': True})
    spec = {'repo': 'lab', 'location': 'wb_studio/ui.css:10', 'commit': 'abc1234',
            'change': 'Darken the muted ink.', 'verify': ''}
    critic.ON_TURN(genesis, turn(json.dumps({'findings': [{**FINDING, 'spec': spec},
                                                          {**FINDING, 'rubric': 'prose:P5', 'spec': spec}]})))
    assert len(calls) == 1                                   # the second finding is a card without a diff
    bodies = [c['body'] for c in genesis.listing('cards')]
    assert sum('| Diff | verify passed |' in b for b in bodies) == 1
    assert sum('| Diff |' in b for b in bodies) == 1                             # the other card has none


def test_a_finding_whose_spec_is_bad_still_becomes_a_card(genesis, monkeypatch):
    monkeypatch.setattr(critic.engineer, 'implement', Mock(side_effect=AssertionError('Codex was started')))
    critic.ON_TURN(genesis, turn(json.dumps({'findings': [{**FINDING, 'spec': {'repo': 'lab', 'location': 'nope'}}]})))
    card = genesis.listing('cards')[0]
    assert 'The spec was refused' in card['body'] and card['finding']['rubric'] == 'figures:F12'


def test_it_is_registered_weekly_and_as_a_plugin():
    from wb_studio import genesis_plugins, scheduler
    assert critic.DAILY == ('genesis-critic', 9, critic.critic)
    assert 'wb_studio.genesis_critic' in scheduler.MODULES
    assert critic.ON_TURN in [getattr(m, 'ON_TURN', None) for m in genesis_plugins.modules()]
