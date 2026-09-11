"""Monarch patch proposals, offline: a real temporary git repository stands in for the Monarch
checkout, every model turn is a fake `genesis.chat`, and no Monarch code is ever run."""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_studio import code_index, genesis_patch as patch
from wb_studio.genesis import Genesis
from wb_results.evidence import write_json

FILE = 'monarch-enterprise/apps/backend/src/graphs/graphs.service.ts'
BEFORE = "export class GraphsService {\n  load() { return 1; }\n}\n"


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   text=True, encoding='utf-8', capture_output=True, check=True)


def diff_for(new_line):
    return ('diff --git a/' + FILE + ' b/' + FILE + '\n'
            '--- a/' + FILE + '\n+++ b/' + FILE + '\n'
            '@@ -1,3 +1,3 @@\n export class GraphsService {\n'
            '-  load() { return 1; }\n+  ' + new_line + '\n }\n')


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / 'monarch'
    (repo / FILE).parent.mkdir(parents=True)
    (repo / FILE).write_text(BEFORE, encoding='utf-8', newline='\n')
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'first')
    return repo


@pytest.fixture
def genesis(tmp_path, repo, monkeypatch):
    monkeypatch.setattr('wb_studio.genesis_harness.model_routes', lambda: [{'id': 'cheap', 'available': True}])
    out = tmp_path / 'genesis' / 'code-index'
    monkeypatch.setattr(code_index, 'settings',
                        lambda studio, which='monarch': {'repo': repo, 'ref': 'main', 'out': out, 'build': None,
                                                         'target': code_index.target(which)})
    studio = SimpleNamespace(directory=tmp_path, create=Mock(), jobs=Mock(return_value=[]), job=Mock(),
                             events=Mock(return_value=[]), ledger=Mock())
    studio.genesis = Genesis(studio)
    studio.genesis.chat = Mock(side_effect=[{'id': 'p1'}, {'id': 'r1'}, {'id': 'r2'}])
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True, capture_output=True,
                          check=True).stdout.strip()
    out.mkdir(parents=True)
    write_json(out / 'index.json', {'commit': head, 'ref': 'main', 'tracked_files': 1, 'repo': str(repo)})
    studio.genesis.head = head
    return studio.genesis


BUCKETS = {'run': 'run-7', 'summary': 'Half the attempts stop at the graph endpoint.',
           'denominators': {'attempts': 40}, 'classification_policy': 'recorded events only',
           'buckets': [{'id': 'graph-500', 'label': 'Graph endpoint answered 500', 'count': 18, 'percent_failed': 60.0},
                       {'id': 'timeout', 'label': 'The attempt ran out of turns', 'count': 4, 'percent_failed': 13.3}],
           'limitations': []}


def with_tools(genesis):
    genesis.tool = Mock(side_effect=lambda action, payload: {
        'failure_buckets': BUCKETS,
        'read_run': {'job': {'id': 'run-7', 'title': 'Nightly'}, 'events': [{'id': 4, 'task': 'finance.1', 'text': '500 from /graphs/:id'}]},
    }[action])
    return genesis


def answer(genesis, **changes):
    data = {'failure': 'Graph endpoint answered 500', 'location': FILE + ':2', 'commit': genesis.head,
            'diff': diff_for('load() { return 2; }'), 'reasoning': 'load never guards a missing graph.',
            'test': 'graphs.service.spec.ts: a missing graph answers 404.'}
    data.update(changes)
    return json.dumps(data)


def finished(turn_id, answer_text, status='completed', run='run-7'):
    return {'id': turn_id, 'purpose': patch.PURPOSE, 'status': status, 'answer': answer_text,
            'message': 'Run: ' + run + '\nPropose one patch.', 'card': None,
            'events': [{'type': 'failed', 'message': 'The allowance is spent.'}] if status == 'failed' else []}


# -- the diff check ---------------------------------------------------------------

def test_code_diff_check_says_whether_a_diff_applies_on_a_real_checkout(genesis):
    good = patch.code_diff_check(genesis.studio, diff_for('load() { return 2; }'))
    assert good['applies'] is True and good['commit'] == genesis.head and good['audience'] == 'internal'
    assert 'applies cleanly' in good['output']

    stale = diff_for('load() { return 3; }').replace('-  load() { return 1; }', '-  load() { return 99; }')
    bad = patch.code_diff_check(genesis.studio, stale)
    assert bad['applies'] is False and 'patch does not apply' in bad['output'].lower()

    # the temporary worktree is gone and the checkout is untouched
    listed = subprocess.run(['git', '-C', str(code_index.settings(genesis.studio)['repo']), 'worktree', 'list'],
                            text=True, capture_output=True, check=True).stdout
    assert listed.count('\n') == 1
    assert (code_index.settings(genesis.studio)['repo'] / FILE).read_text(encoding='utf-8') == BEFORE
    with pytest.raises(ValueError, match='unified diff'):
        patch.code_diff_check(genesis.studio, '  ')


# -- proposing --------------------------------------------------------------------

def test_propose_patch_sends_the_worst_bucket_its_evidence_and_the_commit(genesis):
    with_tools(genesis)
    out = patch.propose_patch(genesis, 'run-7')
    payload = genesis.chat.call_args.args[0]
    assert payload['purpose'] == 'Genesis patch' and payload['model'] == 'cheap' and payload['maximum_usd'] == '1.00'
    message = payload['message']
    assert len(message) <= 16000 and message.startswith('Run: run-7')
    assert 'Graph endpoint answered 500' in message and '18 of 40 attempts' in message
    assert '500 from /graphs/:id' in message and genesis.head in message
    assert 'code_search' in message and '"diff"' in message
    assert out['bucket'] == 'graph-500' and out['commit'] == genesis.head and out['audience'] == 'internal'
    assert genesis.autonomy.tail(3)[0]['kind'] == 'patch-requested'


def test_a_finished_patch_turn_becomes_a_reviewed_internal_card_carrying_the_diff(genesis):
    with_tools(genesis)
    patch.propose_patch(genesis, 'run-7')
    patch.ON_TURN(genesis, finished('p1', answer(genesis)))

    card = next(c for c in genesis.listing('cards') if c['kind'] == 'patch')
    assert card['stage'] == 'review' and card['auto'] is False and card['audience'] == 'internal'
    assert card['patch']['diff'] == diff_for('load() { return 2; }')
    assert card['patch']['commit'] == genesis.head and card['patch']['applies'] is True
    assert card['patch']['location'] == FILE + ':2' and card['patch']['run'] == 'run-7'
    assert 'load never guards a missing graph.' in card['body'] and 'Applies: yes' in card['body']
    assert 'a missing graph answers 404' in card['body']
    assert card['review']['status'] == 'pending' and card['review']['subject'] == 'patch'
    assert genesis.chat.call_count == 2  # the patch turn and the Reviewer's

    logged = genesis.autonomy.tail(10)[0]
    assert logged['kind'] == 'patch' and logged['status'] == 'proposed' and logged['applies'] is True

    read = patch.read_patch(genesis, card['id'])
    assert read['diff'] == card['patch']['diff'] and read['audience'] == 'internal'
    exported = patch.export_patch(genesis, card['id'])
    assert exported.startswith('Subject: [PATCH] Patch: Graph endpoint answered 500')
    assert 'never applied by the Studio' in exported and exported.endswith(card['patch']['diff'])
    assert '\n---\n' in exported


def test_a_diff_that_does_not_apply_is_still_proposed_and_says_so(genesis):
    with_tools(genesis)
    patch.propose_patch(genesis, 'run-7')
    stale = diff_for('load() { return 3; }').replace('-  load() { return 1; }', '-  load() { return 99; }')
    patch.ON_TURN(genesis, finished('p1', answer(genesis, diff=stale)))
    card = next(c for c in genesis.listing('cards') if c['kind'] == 'patch')
    assert card['patch']['applies'] is False and 'Applies: no' in card['body']


def test_a_patch_written_against_another_commit_is_refused_in_words(genesis):
    with_tools(genesis)
    patch.propose_patch(genesis, 'run-7')
    patch.ON_TURN(genesis, finished('p1', answer(genesis, commit='deadbee' * 5 + 'f' * 5)))
    assert [c for c in genesis.listing('cards') if c['kind'] == 'patch'] == []
    logged = genesis.autonomy.tail(5)[0]
    assert logged['kind'] == 'patch' and logged['status'] == 'refused'
    assert 'the code index is at ' + genesis.head in logged['reason']
    assert 'read the code again at the indexed commit' in logged['reason']
    assert genesis.chat.call_count == 1  # no card, so no review was asked for


def test_a_failed_turn_or_an_answer_without_a_diff_writes_no_card(genesis):
    with_tools(genesis)
    patch.ON_TURN(genesis, finished('p1', '', status='failed'))
    assert genesis.autonomy.tail(3)[0]['reason'] == 'The allowance is spent.'
    patch.ON_TURN(genesis, finished('p1', 'I could not find the cause.'))
    assert genesis.autonomy.tail(3)[0]['reason'] == 'The patch model did not answer with JSON.'
    patch.ON_TURN(genesis, finished('p1', answer(genesis, diff='  ')))
    assert genesis.autonomy.tail(3)[0]['reason'] == 'The patch model answered no diff.'
    assert [c for c in genesis.listing('cards') if c['kind'] == 'patch'] == []


def test_a_run_with_no_buckets_and_an_unindexed_checkout_are_refused_in_words(genesis, tmp_path, monkeypatch):
    genesis.tool = Mock(return_value={'buckets': []})
    with pytest.raises(ValueError, match='nothing to patch'):
        patch.propose_patch(genesis, 'run-7')
    with pytest.raises(ValueError, match='Name the run'):
        patch.propose_patch(genesis, None)
    with_tools(genesis)
    (tmp_path / 'genesis' / 'code-index' / 'index.json').unlink()
    with pytest.raises(ValueError, match='code index has not been built'):
        patch.propose_patch(genesis, 'run-7')


def test_the_tools_are_reachable_through_genesis_and_stay_internal(genesis):
    out = genesis.tool('code_diff_check', {'diff': diff_for('load() { return 2; }')})
    assert out['applies'] is True and out['audience'] == 'internal'
    assert genesis.tool('read_patch', {'card': 'nosuch'})['error'].startswith('No research card')
    assert 'propose_patch' in patch.TOOLS and 'never runs Monarch' in patch.PROTOCOL
