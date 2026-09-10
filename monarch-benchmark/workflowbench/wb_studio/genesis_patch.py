"""Monarch patch proposals (feature 022, design section 15 of the decisions, section 12 of the design).

A failure bucket that points at Monarch's behaviour becomes a card of kind `patch`: the failure and
its evidence, the suspected location as path and line at a named commit, a unified diff, the
reasoning, a suggested test, whether the diff applies, and the Reviewer's review. The Studio never
applies it and never runs Monarch's code: `code_diff_check` adds a detached worktree at the indexed
commit, asks `git apply --check`, and removes the worktree again.

The card is internal-only. Facts from the code never reach a public report.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from wb_studio import code_index
from wb_studio.genesis_reviewer import json_answer, request_review
from wb_results.evidence import write_json

PURPOSE = 'Genesis patch'
MESSAGE_LIMIT = 15_800  # `Genesis.chat` refuses a message over 16,000 characters
RUN_MARKER = re.compile(r'^Run: ([a-zA-Z0-9_-]{1,80})$', re.M)
COMMIT = re.compile(r'[0-9a-fA-F]{7,40}')
OUTPUT = ('Answer with one JSON object and nothing else: {"failure": "the bucket this addresses", '
          '"location": "path:line", "commit": "the commit you read", "diff": "a unified diff that '
          'applies at that commit", "reasoning": "why this is the cause", "test": "the test that '
          'would fail before and pass after"}.')


def cap() -> str:
    """The per-turn ceiling of one patch proposal."""
    return os.environ.get('STUDIO_GENESIS_PATCH_USD', '1.00')


def target_commit(studio) -> str:
    """The commit a patch is written against: the indexed one, else the checkout's HEAD."""
    status = code_index.code_status(studio)
    if status.get('indexed') and status.get('commit'):
        return str(status['commit'])
    return code_index.git(code_index.settings(studio)['repo'], 'rev-parse', 'HEAD').strip()


def same_commit(one, other) -> bool:
    one, other = str(one or '').strip(), str(other or '').strip()
    if not COMMIT.fullmatch(one) or not COMMIT.fullmatch(other):
        return False
    return one.startswith(other) or other.startswith(one)


# -- checking a diff without running anything -------------------------------------

def code_diff_check(studio, diff) -> dict:
    """Whether a unified diff applies at the commit the index names, and what git said.
    A detached worktree in a temporary directory, `git apply --check`, then the worktree is
    removed. Nothing in the Monarch checkout is written and no Monarch code is run."""
    text = str(diff or '')
    if not text.strip():
        raise ValueError('Give the unified diff to check, as diff.')
    if not text.endswith('\n'):
        text += '\n'
    repo = code_index.settings(studio)['repo']
    if not (repo / '.git').exists():
        return {'applies': False, 'output': 'There is no Monarch checkout at ' + str(repo) + '.',
                'commit': None, 'audience': 'internal'}
    try:
        commit = target_commit(studio)
    except RuntimeError as exc:
        return {'applies': False, 'output': str(exc), 'commit': None, 'audience': 'internal'}
    with tempfile.TemporaryDirectory(prefix='genesis-patch-') as tmp:
        work, patch = Path(tmp) / 'work', Path(tmp) / 'proposed.patch'
        patch.write_text(text, encoding='utf-8', newline='\n')
        try:
            code_index.git(repo, 'worktree', 'add', '--detach', str(work), commit)
        except (RuntimeError, OSError) as exc:
            return {'applies': False, 'output': str(exc), 'commit': commit, 'audience': 'internal'}
        try:
            output = code_index.git(work, 'apply', '--check', str(patch))
            applies, said = True, (output.strip() or 'The diff applies cleanly at ' + commit[:12] + '.')
        except (RuntimeError, OSError) as exc:
            applies, said = False, str(exc).strip() or 'git apply refused the diff.'
        finally:
            try:
                code_index.git(repo, 'worktree', 'remove', '--force', str(work))
            except (RuntimeError, OSError):
                pass  # the temporary directory goes either way; a stale entry is pruned by git
    return {'applies': applies, 'output': said, 'commit': commit, 'audience': 'internal'}


# -- proposing --------------------------------------------------------------------

def _short(value, limit) -> str:
    text = json.dumps(value, indent=1, default=str) if not isinstance(value, str) else value
    return text[:limit]


def _evidence(genesis, run, task=None) -> dict:
    """The failure buckets of a run and the recorded events behind them, read through the tools
    that already compute them; nothing here counts attempts by hand."""
    buckets = genesis.tool('failure_buckets', {'run': run})
    payload = {'id': run, 'limit': 20}
    if task:
        payload['task'] = task
    read = genesis.tool('read_run', payload)
    return {'buckets': buckets, 'job': read.get('job'), 'events': read.get('events') or []}


def propose_patch(genesis, run, task=None) -> dict:
    """Start one turn that reads Monarch's code and answers a patch for this run's worst failure."""
    if not run:
        raise ValueError('Name the run whose failure this patch addresses, as run.')
    found = _evidence(genesis, str(run), task)
    buckets = found['buckets'].get('buckets') or []
    if not buckets:
        raise ValueError('Run ' + str(run) + ' has no failure buckets, so there is nothing to patch.')
    worst = max(buckets, key=lambda b: b.get('count') or 0)
    status = code_index.code_status(genesis.studio)
    if not status.get('indexed'):
        raise ValueError('The Monarch code index has not been built yet, so a patch cannot name a commit.')
    route = genesis.config.route_for('patch')
    if not route:
        raise ValueError('No model route is available for patch proposals.')
    message = ('Run: ' + str(run) + '\nPropose one patch to Monarch for the failure below.\n\n'
               'Failure bucket: ' + str(worst.get('label')) + ' (' + str(worst.get('count')) + ' of '
               + str((found['buckets'].get('denominators') or {}).get('attempts', 'the attempts')) + ' attempts, '
               + str(worst.get('percent_failed')) + '% of the failures).\n'
               'Every bucket:\n' + _short([{k: b.get(k) for k in ('id', 'label', 'count', 'percent_failed')} for b in buckets], 2000) + '\n\n'
               'Recorded events behind it:\n' + _short(found['events'], 5000) + '\n\n'
               'Monarch code status:\n' + _short({k: status.get(k) for k in ('commit', 'ref', 'build', 'repo', 'tracked_files', 'monarch_md')}, 3000) + '\n\n'
               'Use code_search, code_explain and code_read to find the suspected location. Write the diff '
               'against commit ' + str(status['commit']) + ', the commit above, and name that commit in your '
               'answer. Nothing you write is applied or run: the Studio only checks that the diff applies.\n\n'
               + OUTPUT)[:MESSAGE_LIMIT]
    turn = genesis.chat({'message': message, 'model': route['id'], 'maximum_usd': cap(), 'purpose': PURPOSE})
    genesis.autonomy.record('patch-requested', turn=turn['id'], run=str(run), task=task,
                            bucket=worst.get('id'), commit=status['commit'])
    return {'run': str(run), 'turn': turn['id'], 'bucket': worst.get('id'), 'commit': status['commit'],
            'note': 'The patch model is reading the code. The proposal arrives as a card of kind patch.',
            'audience': 'internal'}


def _body(data, check) -> str:
    return ('Failure: ' + str(data.get('failure') or '') + '\n'
            'Location: ' + str(data.get('location') or '') + ' at commit ' + str(data.get('commit') or '') + '\n'
            'Applies: ' + ('yes' if check['applies'] else 'no') + '. ' + check['output'] + '\n\n'
            'Reasoning:\n' + str(data.get('reasoning') or '') + '\n\n'
            'Suggested test:\n' + str(data.get('test') or '') + '\n\n'
            'Internal only: facts from Monarch\'s code never reach a public report.')[:20000]


def _stamp(genesis, card_id, patch) -> None:
    """The patch object and the internal-only marker onto the card's file.
    ponytail: `Genesis.card` rebuilds a record from known keys, so these two would be dropped by
    an edit; the receipt owes one line adding `patch` and `audience` to the fields it keeps."""
    with genesis.lock:
        card = genesis.read('cards', card_id)
        card.update(patch=patch, audience='internal')
        write_json(genesis.path('cards', card_id), card)


def ON_TURN(genesis, turn):
    """A finished patch turn becomes a patch card in review, with the Reviewer asked. A diff written
    against another commit is refused in words and no card is written."""
    if turn.get('purpose') != PURPOSE:
        return
    found = RUN_MARKER.search(str(turn.get('message') or ''))
    run = found[1] if found else None
    if turn.get('status') != 'completed':
        reason = next((e.get('message') for e in reversed(turn.get('events') or []) if e.get('type') == 'failed'),
                      'The patch turn did not finish.')
        genesis.autonomy.record('patch', turn=turn['id'], run=run, status='failed', reason=reason)
        return
    try:
        data = json_answer(turn.get('answer'), 'The patch model')
    except ValueError as exc:
        genesis.autonomy.record('patch', turn=turn['id'], run=run, status='failed', reason=str(exc))
        return
    diff = str(data.get('diff') or '')
    if not diff.strip():
        genesis.autonomy.record('patch', turn=turn['id'], run=run, status='failed',
                                reason='The patch model answered no diff.')
        return
    wanted = target_commit(genesis.studio)
    if not same_commit(data.get('commit'), wanted):
        reason = ('The patch names commit ' + (str(data.get('commit') or '') or 'nothing')
                  + ', but the code index is at ' + wanted + '. A diff written against another commit is not '
                  'proposed; read the code again at the indexed commit.')
        genesis.autonomy.record('patch', turn=turn['id'], run=run, status='refused', reason=reason)
        return
    check = code_diff_check(genesis.studio, diff)
    card = genesis.card({'kind': 'patch', 'stage': 'review', 'auto': False, 'by': 'genesis',
                         'title': ('Patch: ' + str(data.get('failure') or 'a Monarch failure'))[:140],
                         'body': _body(data, check),
                         'evidence': [{'kind': 'run', 'id': run}] if run else []})
    try:
        review = request_review(genesis, card['id'], 'patch')
    except (ValueError, OSError) as exc:
        review = {'note': str(exc)}
    _stamp(genesis, card['id'], {'diff': diff, 'commit': wanted, 'run': run,
                                 'location': str(data.get('location') or ''), 'test': str(data.get('test') or ''),
                                 'reasoning': str(data.get('reasoning') or ''), 'failure': str(data.get('failure') or ''),
                                 'applies': check['applies'], 'output': check['output'], 'turn': turn['id']})
    genesis.autonomy.record('patch', card=card['id'], turn=turn['id'], run=run, status='proposed',
                            applies=check['applies'], commit=wanted, location=str(data.get('location') or ''),
                            review=review.get('turn'))


# -- reading and exporting --------------------------------------------------------

def _card(genesis, identity):
    if not identity:
        raise ValueError('Name the card by its id.')
    try:
        return genesis.read('cards', str(identity))
    except (ValueError, FileNotFoundError, OSError):
        raise ValueError('No research card is called ' + str(identity) + '.') from None


def read_patch(genesis, card_id) -> dict:
    card = _card(genesis, card_id)
    patch = card.get('patch')
    if not patch:
        raise ValueError('Card ' + str(card['id']) + ' carries no patch.')
    return {'card': card['id'], 'title': card['title'], 'stage': card['stage'], **patch,
            'review': card.get('review'), 'audience': 'internal'}


def export_patch(genesis, card) -> str:
    """The card's patch as the text of a `.patch` file, `git format-patch` shaped: the subject and
    the reasoning above the `---`, the diff below it."""
    record = _card(genesis, card if isinstance(card, str) else (card or {}).get('id'))
    patch = record.get('patch')
    if not patch:
        raise ValueError('Card ' + str(record['id']) + ' carries no patch.')
    diff = patch['diff'] if patch['diff'].endswith('\n') else patch['diff'] + '\n'
    return ('Subject: [PATCH] ' + record['title'] + '\n\n'
            + str(patch.get('reasoning') or '') + '\n\n'
            'Failure: ' + str(patch.get('failure') or '') + '\n'
            'Location: ' + str(patch.get('location') or '') + '\n'
            'Against commit: ' + str(patch.get('commit') or '') + '\n'
            'Suggested test: ' + str(patch.get('test') or '') + '\n'
            'Proposed by Genesis, never applied by the Studio. Internal only.\n'
            '---\n' + diff)


TOOLS = {'propose_patch': lambda genesis, payload: propose_patch(genesis, payload.get('run'), payload.get('task')),
         'code_diff_check': lambda genesis, payload: code_diff_check(genesis.studio, payload.get('diff')),
         'read_patch': lambda genesis, payload: read_patch(genesis, payload.get('card'))}

PROTOCOL = (
    'When a failure bucket points at Monarch\'s own behaviour, call propose_patch {run, task?}: one turn '
    'reads the code at the indexed commit and answers a failure, a location as path and line, a unified '
    'diff, its reasoning and a test, which the Studio checks with code_diff_check and files as a patch card '
    'for the Reviewer; the Studio never applies a patch and never runs Monarch\'s code. Everything the code '
    'tools and patch cards carry is internal: a fact from Monarch\'s code never reaches a public report.'
)
