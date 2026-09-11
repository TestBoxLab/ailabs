"""The daily engineer job (feature 023, design of record
`docs/superpowers/specs/2026-09-11-genesis-engineer-loop-design.md` §5.2 to §5.5).

At 08:00 São Paulo the job reads the runs it has not checked off, computes their failure
buckets with the Studio's own free machinery, and — when a bucket points at code rather than
at the task setup — asks Genesis for **one spec**: the failure, its evidence, a location at a
named commit, what to change and the command that must pass afterwards. The spec goes to a
Codex agent in a throwaway git worktree; the Studio then runs the verify command **itself**,
captures the diff, and files a card. Nothing is applied, merged or pushed.

Three things here are deliberately not the model's to decide, because a model could otherwise
spend or run whatever it liked:

- the **verify command** is matched against a small allowlist before anything executes;
- the **verdict** on that command is the Studio's, taken from its own exit status, never read
  back from what the agent says it ran;
- the **money** is reserved in the weekly ledger at a fixed ceiling before Codex starts and
  settled from the token usage Codex reports; usage that cannot be read leaves the ceiling
  held, which is the ledger's own rule for unverified billing.

Codex runs with `workspace-write` inside the worktree, so it can edit files and run commands
there. That is what a coding agent is. The dial `engineer` starts **off**.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

from wb_results.evidence import write_json
from wb_studio import code_index
from wb_studio.genesis import digest
from wb_studio.genesis_reviewer import json_answer

HOUR = 8                       # after the 04:00 code index and the 07:00 initiative
PURPOSE = 'Genesis spec'
TRIES = 3                      # a run whose spec turn keeps failing is left alone after this
CODEX_SECONDS = 900
VERIFY_SECONDS = 600
MESSAGE_LIMIT = 15_800         # `Genesis.chat` refuses a message over 16,000 characters
RUN_MARKER = re.compile(r'^Run: ([a-zA-Z0-9_-]{1,80})$', re.M)
BUCKET_MARKER = re.compile(r'^Bucket: ([\w.-]{1,80})$', re.M)  # so the card's signature matches what `already_open` looks for
# The only commands the Studio will run on a model's say-so. `uv run --directory` keeps the
# bench's environment; the browser suite is how a view is checked.
# The path must start at `tests/` and may not contain `..`. Without both, `[\w./-]` admitted
# `/etc/passwd`, `tests/../../../elsewhere`, `..` and even `--pdb` — and pytest executes conftest.py
# and every test module it collects, so a path outside the worktree is code execution on the lab's
# machine at a path a model chose. The allowlist exists to make that impossible, not unlikely.
VERIFY_ALLOWED = re.compile(
    r'^(uv run --directory monarch-benchmark/workflowbench python -m pytest (?!.*\.\.)tests/[\w./-]{1,110}(?: -q)?'
    r'|node tests/browser/suite\.cjs)$')
# A bucket that names the task, the data or the harness is not a defect in anyone's code.
SETUP_BUCKETS = ('setup', 'task-setup', 'harness', 'infrastructure', 'budget', 'cancelled')
# Reasoning first, then the conclusion: a schema that asks for the verdict first gets a verdict and
# a rationalisation of it. `analysis` also sorts first alphabetically, because at least one provider
# returns structured output with its keys sorted rather than in the order they were asked for.
OUTPUT = (
    'Write one JSON object and nothing else, with its fields in exactly this order:\n'
    '  "analysis": what you read, at path:line, and what it shows. Quote the line. This comes first '
    'because it is how you work the problem out, not a justification of an answer you already have.\n'
    '  "change": what to change, in sentences. No diff — an agent writes that from your words.\n'
    '  "commit": the commit you read, from code_status.\n'
    '  "failure": the bucket this addresses.\n'
    '  "found": true when you traced the failure to a place in the code; false when you did not.\n'
    '  "location": "path:line".\n'
    '  "repo": "monarch" or "lab".\n'
    '  "verify": the command that must fail before and pass after, or "" when no test can run. Either '
    '"uv run --directory monarch-benchmark/workflowbench python -m pytest tests/<path> -q", whose path '
    'starts at tests/ and holds no "..", or "node tests/browser/suite.cjs".\n\n'
    'If you cannot trace the failure to a line of code, answer {"analysis": "...", "found": false} '
    'and stop. That is a complete, correct answer and the lab records it as one. A location you are '
    'not sure of is worse than none: it sends an agent to edit the wrong file. Do not fill the '
    'fields in to have something to say.')


def ceiling(name: str, fallback: str) -> Decimal:
    return Decimal(os.environ.get(name, fallback))


# -- the checkoff -------------------------------------------------------------------

def _seen_path(genesis) -> Path:
    return genesis.root / 'engineer' / 'seen.json'


def seen(genesis) -> dict:
    """Run id to {fingerprint, tries}. Written by the job in code, never by a model, so a run is
    looked at again only when its own evidence changes (a regrade moves the fingerprint)."""
    try:
        return json.loads(_seen_path(genesis).read_text(encoding='utf8'))
    except (OSError, ValueError):
        return {}


def check_off(genesis, run: str, mark: str) -> None:
    """Settled: this run is not looked at again until its own evidence changes."""
    with genesis.lock:
        record = seen(genesis)
        record[str(run)] = {'fingerprint': mark, 'tries': int((record.get(str(run)) or {}).get('tries') or 0)}
        write_json(_seen_path(genesis), record)


def one_more_try(genesis, run: str) -> None:
    """A spec turn that failed or was refused. The run keeps its place in the queue for another day,
    which is what a transient fault deserves, and is left alone after TRIES of them."""
    with genesis.lock:
        record = seen(genesis)
        entry = record.get(str(run)) or {}
        record[str(run)] = {'fingerprint': entry.get('fingerprint'), 'tries': int(entry.get('tries') or 0) + 1}
        write_json(_seen_path(genesis), record)


def fingerprint(studio, job: dict) -> str:
    """The same key `record_analysis` files an analysis under: the run's results and events."""
    return digest({'run': job['id'], 'results': job.get('results', []), 'events': studio.events(job['id'])})


# -- picking the work ---------------------------------------------------------------

def candidates(studio, genesis) -> list:
    """Finished runs, newest first, that this job has not already settled."""
    from wb_studio.genesis_watcher import TERMINAL, scripted_only
    record = seen(genesis)
    out = []
    for job in studio.jobs():
        if job.get('status') not in TERMINAL or scripted_only(job):
            continue
        entry = record.get(job['id']) or {}
        if entry.get('tries', 0) >= TRIES:
            continue
        if entry.get('fingerprint') and entry['fingerprint'] == fingerprint(studio, job):
            continue
        out.append(job)
    return out


def worst_bucket(genesis, run: str) -> tuple[dict | None, dict]:
    """The failure bucket with the most attempts behind it, and every bucket beside it. Free:
    the Studio computed these before any model was asked anything."""
    found = genesis.tool('failure_buckets', {'run': str(run)})
    buckets = [b for b in (found.get('buckets') or []) if b.get('count')]
    actionable = [b for b in buckets if not any(word in str(b.get('id') or '').lower() for word in SETUP_BUCKETS)]
    return (max(actionable, key=lambda b: b['count']) if actionable else None), found


def signature(run: str, bucket: dict) -> str:
    return str(bucket.get('id') or bucket.get('label') or 'bucket') + '@' + str(run)


def already_open(genesis, mark: str) -> bool:
    return any(c.get('spec', {}).get('signature') == mark for c in genesis.listing('cards') if isinstance(c.get('spec'), dict))


# -- the spec -----------------------------------------------------------------------

class NoCause(ValueError):
    """The model said it could not trace the failure. A complete answer, not a bad one."""


def check_spec(data: dict) -> dict:
    """The spec as a record, or the sentence that says what is wrong with it."""
    spec = {key: str(data.get(key) or '').strip() for key in ('failure', 'location', 'commit', 'change', 'analysis', 'verify')}
    if data.get('found') is False:
        raise NoCause('The spec model traced no cause: ' + (spec['analysis'][:300] or 'it gave no reading.'))
    spec['repo'] = code_index.target(data.get('repo'))
    if not spec['failure'] or not spec['change']:
        raise ValueError('The spec names the failure it addresses and what to change.')
    if len(spec['analysis']) < 40:
        raise ValueError('The analysis quotes what you read at that line and says what it shows.')
    if not re.fullmatch(r'[\w./-]{1,200}:\d{1,7}', spec['location']):
        raise ValueError('The location is a path and a line, like wb_studio/reports.py:42.')
    if not re.fullmatch(r'[0-9a-fA-F]{7,40}', spec['commit']):
        raise ValueError('Name the commit you read, as commit.')
    if spec['verify'] and not VERIFY_ALLOWED.fullmatch(spec['verify']):
        raise ValueError('verify is one of: "uv run --directory monarch-benchmark/workflowbench python -m pytest '
                         'tests/<path> -q", where the path starts at tests/ and contains no "..", or '
                         '"node tests/browser/suite.cjs", or empty when no test can run.')
    return spec


def commit_of(studio, which: str) -> str:
    status = code_index.code_status(studio, {'repo': which})
    if status.get('indexed') and status.get('commit'):
        return str(status['commit'])
    return code_index.git(code_index.settings(studio, which)['repo'], 'rev-parse', 'HEAD').strip()


# -- the Codex handoff --------------------------------------------------------------

def codex_binary() -> str | None:
    import shutil
    return os.environ.get('STUDIO_CODEX_BIN') or shutil.which('codex')


def usage_of(lines: list[str]) -> dict | None:
    """The token usage Codex reports, taken from its JSONL without assuming where it sits.
    Any object carrying input and output counts will do; a total wins over a per-turn record."""
    best = total = None

    def walk(node, key=None):
        nonlocal best, total
        if isinstance(node, dict):
            if 'input_tokens' in node and 'output_tokens' in node:
                if key == 'total_token_usage':
                    total = node
                else:
                    best = node
            for name, value in node.items():
                walk(value, name)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for line in lines:
        try:
            walk(json.loads(line))
        except ValueError:
            continue
    found = total or best
    if not found:
        return None
    numbers = {key: int(found.get(key) or 0) for key in
               ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens', 'reasoning_output_tokens')}
    if numbers['input_tokens'] <= 0:
        return None
    # Reasoning is billed as output; adding it can only overstate the cost, which is the safe
    # direction for a budget gate.
    return {'prompt_tokens': numbers['input_tokens'], 'cached_tokens': numbers['cached_input_tokens'],
            'cache_write_tokens': numbers['cache_write_input_tokens'],
            'output_tokens': numbers['output_tokens'] + numbers['reasoning_output_tokens']}


def _run(args, cwd, timeout) -> tuple[int, str, str]:
    try:
        done = subprocess.run(args, cwd=str(cwd), text=True, encoding='utf-8', errors='replace',
                              capture_output=True, timeout=timeout)
        return done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        return 124, '', f'It ran past {timeout} seconds and was stopped.'


def prompt_for(spec: dict) -> str:
    """What the agent is told. A person reads the diff afterwards, so the bar is a diff a reviewer
    can take in at a glance — not a refactor, not a tidy-up, not a second opinion on the spec."""
    return ('Make exactly this change and nothing else.\n\n'
            'Failure: ' + spec['failure'] + '\n'
            'Location: ' + spec['location'] + '\n'
            'What the analysis found:\n' + spec['analysis'] + '\n\n'
            'What to change:\n' + spec['change'] + '\n\n'
            + ('The lab runs `' + spec['verify'] + '` itself after you stop, and its exit status is '
               'the verdict — not your account of it. Make it pass.\n' if spec['verify']
               else 'There is no test command for this change, so the diff is read by a person as it stands.\n')
            + '\nHow to work:\n'
              '- Read the surrounding code first and match it: its naming, its comment density, its idiom.\n'
              '- Smallest diff that does the job. No refactor, no rename, no reformatting, no tidying '
              'of code the change does not touch, no new files unless the change needs one.\n'
              '- No new dependency. Whatever you need is already here or can be done in a few lines.\n'
              '- Do not commit, do not push, do not touch git branches. Editing the files is the whole job.\n'
              '- A person reads this diff next. Write it for them.\n\n'
              'If the change as specified is wrong, or the location does not hold what the analysis says '
              'it does, **make no edit** and say why in your last message. An empty diff with a reason is '
              'a useful answer; a plausible edit to the wrong place costs someone an afternoon.')


def implement(genesis, spec: dict, turn_id: str) -> dict:
    """One Codex agent in a detached worktree at the spec's commit. Returns what the Studio saw:
    the diff, whether it applies, what the verify command said, and the cost."""
    studio = genesis.studio
    binary = codex_binary()
    if not binary:
        return {'skipped': 'No Codex executable was found; set STUDIO_CODEX_BIN or install it. '
                           'The spec is filed without a diff.'}
    repo = code_index.settings(studio, spec['repo'])['repo']
    if not (repo / '.git').exists():
        return {'skipped': 'There is no ' + spec['repo'] + ' checkout at ' + str(repo) + '.'}
    route = genesis.config.route_for('implement')
    if not route:
        return {'skipped': 'No model route is configured for the implement step.'}
    from wb_arms import providers
    provider = providers.get(route['id'])
    cap = ceiling('STUDIO_GENESIS_CODEX_USD', '1.00')
    ok, reason = genesis.allowance_allows(cap)
    if not ok:
        return {'skipped': reason}
    scope, request = 'genesis-codex-' + turn_id, 'genesis-codex-' + turn_id + '-1'
    studio.ledger.reserve_run(scope, cap, metadata={'purpose': 'Genesis implement', 'model': route['id'], 'by': 'genesis'})
    out = {'commit': spec['commit'], 'repo': spec['repo'], 'model': route['id'], 'cost_usd': None}
    try:
        studio.ledger.reserve(request, cap, scope_id=scope, scope_limit_usd=cap,
                              metadata={'purpose': 'Genesis implement', 'harness': 'codex', 'model': route['id']})
        studio.ledger.claim(request)
        settled = False
        with tempfile.TemporaryDirectory(prefix='genesis-engineer-') as tmp:
            work = Path(tmp) / 'work'
            try:
                code_index.git(repo, 'worktree', 'add', '--detach', str(work), spec['commit'])
            except (RuntimeError, OSError) as exc:
                studio.ledger.settle(request, Decimal('0'), outcome='cancelled'); settled = True
                return {**out, 'skipped': 'The worktree could not be made: ' + str(exc)[:200]}
            try:
                last = Path(tmp) / 'last-message.txt'
                args = [binary, 'exec', '--json', '--ephemeral', '-C', str(work), '-s', 'workspace-write',
                        '-m', provider.model_id, '-o', str(last)]
                effort = genesis.config.effort_for('implement')
                if effort:
                    args += ['-c', 'model_reasoning_effort=' + effort]
                code, stdout, stderr = _run(args + [prompt_for(spec)], work, CODEX_SECONDS)
                usage = usage_of(stdout.splitlines())
                if usage:
                    actual = Decimal(str(providers.cost_usd(provider, usage['prompt_tokens'], usage['cached_tokens'],
                                                            usage['output_tokens'], usage['cache_write_tokens'])))
                    studio.ledger.settle(request, actual, usage=usage, outcome='completed' if not code else 'error')
                    out['cost_usd'] = str(actual)
                else:  # unverified billing: the ledger's rule is that the ceiling stays held
                    studio.ledger.settle(request, None, outcome='error')
                    out['cost_note'] = 'Codex reported no token usage; the ceiling stays reserved.'
                settled = True
                if code:
                    out['agent_error'] = (stderr or stdout).strip()[-600:] or f'Codex exited {code}.'
                code_index.git(work, 'add', '-A')
                out['diff'] = code_index.git(work, 'diff', '--cached')[:60_000]
                out['changed'] = bool(out['diff'].strip())
                if out['changed'] and spec['verify']:
                    status, said, err = _run(spec['verify'].split(), work, VERIFY_SECONDS)
                    out['verified'] = status == 0
                    out['verify_output'] = ((said or '') + (err or '')).strip()[-2000:]
                elif out['changed']:
                    out['verified'] = None
                    out['verify_output'] = 'No test command was given, so nothing was run.'
                if not out['changed']:
                    # The agent was told it may decline. A hatch that leads nowhere is worse than
                    # none, so its reason is read back and shown on the card.
                    try:
                        out['declined'] = last.read_text(encoding='utf-8', errors='replace').strip()[-1500:]
                    except OSError:
                        out['declined'] = (stdout or '').strip()[-600:] or 'The agent edited nothing and said nothing.'
            finally:
                if not settled:
                    studio.ledger.settle(request, None, outcome='error')
                try:
                    code_index.git(repo, 'worktree', 'remove', '--force', str(work))
                except (RuntimeError, OSError):
                    pass  # the temporary directory goes either way; a stale entry is pruned by git
    finally:
        studio.ledger.finish_run(scope)
    return out


# -- the turn and the card ----------------------------------------------------------

def message_for(genesis, job, bucket, buckets) -> str:
    read = genesis.tool('read_run', {'run': job['id'], 'limit': 15})
    short = lambda value, n: json.dumps(value, indent=1, default=str)[:n]
    return ('Run: ' + job['id'] + '\nBucket: ' + str(bucket.get('id') or bucket.get('label'))
            + '\nWrite one spec for the failure below. You are not writing code: '
            'a Codex agent will make the change from what you write.\n\n'
            'Failure bucket: ' + str(bucket.get('label')) + ' (' + str(bucket.get('count')) + ' attempts, '
            + str(bucket.get('percent_failed')) + '% of the failures).\n'
            'Every bucket:\n' + short([{k: b.get(k) for k in ('id', 'label', 'count', 'percent_failed')} for b in buckets], 1500) + '\n\n'
            'Recorded events:\n' + short(read.get('events') or [], 4000) + '\n\n'
            'Work in this order.\n'
            '1. Read the events above and say, to yourself, what the attempts actually did.\n'
            '2. Decide where the cause lives: in Monarch, the product under test (repo "monarch"), '
            'or in the lab\'s own code — the bench, the Studio, its reports (repo "lab"). The bucket '
            'label is a symptom, not a location.\n'
            '3. Read that checkout with code_search, code_read and code_explain, passing repo. Do not '
            'name a line you have not opened.\n'
            '4. Take the commit from code_status on the same repo.\n\n'
            'Out of bounds, whatever the evidence says: the grader, the task prompts, the approval '
            'rules, the frozen task sets and the price table. The methodology is fixed and a change '
            'to it is a question for a person, not a fix. If that is where the cause is, answer '
            '"found": false and say so in the analysis.\n\n' + OUTPUT)[:MESSAGE_LIMIT]


def body_of(spec, built) -> str:
    verified = built.get('verified')
    said = ('not run' if verified is None else ('passed' if verified else 'FAILED')) if 'verified' in built else 'no change was made'
    return ('Failure: ' + spec['failure'] + '\n'
            'Where: ' + spec['location'] + ' in the ' + spec['repo'] + ' checkout at commit ' + spec['commit'] + '\n'
            'Verify: ' + (spec['verify'] or 'no test command') + ' — ' + said + '\n'
            + ('Cost: $' + str(built['cost_usd']) + '\n' if built.get('cost_usd') else '')
            + ('Not implemented: ' + built['skipped'] + '\n' if built.get('skipped') else '')
            + ('The agent stopped badly: ' + built['agent_error'] + '\n' if built.get('agent_error') else '')
            + ('\nThe agent made no edit and gave this reason:\n' + built['declined'] + '\n'
               if built.get('declined') else '')
            + '\nWhat to change:\n' + spec['change']
            + '\n\nWhat the code shows:\n' + spec['analysis']
            + ('\n\nWhat the verify command said:\n' + built['verify_output'] if built.get('verify_output') else '')
            + '\n\nNothing here has been applied. Internal only: facts from either code base never '
              'reach a public report.')[:20000]


def ON_TURN(genesis, turn):
    """A finished spec turn becomes a card: the spec, the diff Codex wrote, and the Studio's own
    verdict on the verify command."""
    if turn.get('purpose') != PURPOSE:
        return
    found = RUN_MARKER.search(str(turn.get('message') or ''))
    run = found[1] if found else None

    def refuse(status, reason):
        if run:
            one_more_try(genesis, run)
        genesis.autonomy.record('spec', turn=turn['id'], run=run, status=status, reason=reason)

    if turn.get('status') != 'completed':
        return refuse('failed', next((e.get('message') for e in reversed(turn.get('events') or []) if e.get('type') == 'failed'),
                                     'The spec turn did not finish.'))
    try:
        spec = check_spec(json_answer(turn.get('answer'), 'The spec model'))
    except NoCause as exc:
        # An honest "I could not find it" settles the run: asking the same model the same question
        # about the same evidence tomorrow buys nothing.
        if run:
            check_off(genesis, run, fingerprint(genesis.studio, genesis.studio.job(run)))
        genesis.autonomy.record('spec', turn=turn['id'], run=run, status='no-cause', reason=str(exc))
        return
    except ValueError as exc:
        return refuse('refused', str(exc))
    wanted = commit_of(genesis.studio, spec['repo'])
    if not (wanted.startswith(spec['commit']) or spec['commit'].startswith(wanted)):
        return refuse('refused', 'The spec names commit ' + spec['commit'] + ', but the ' + spec['repo']
                                 + ' index is at ' + wanted + '.')
    built = implement(genesis, spec, turn['id'])
    card = genesis.card({'kind': 'patch' if spec['repo'] == 'monarch' else 'fix', 'stage': 'review', 'auto': False,
                         'by': 'genesis', 'title': ('Fix: ' + spec['failure'])[:140], 'body': body_of(spec, built),
                         'evidence': [{'kind': 'run', 'id': run}] if run else []})
    with genesis.lock:  # the spec and the build are records of their own, beside the card's body
        record = genesis.read('cards', card['id'])
        named = BUCKET_MARKER.search(str(turn.get('message') or ''))
        record.update(spec={**spec, 'signature': signature(run or '', {'id': named[1] if named else spec['failure']}),
                            'turn': turn['id']},
                      build=built, audience='internal')
        write_json(genesis.path('cards', card['id']), record)
    if run:
        check_off(genesis, run, fingerprint(genesis.studio, genesis.studio.job(run)))
    genesis.autonomy.record('spec', card=card['id'], turn=turn['id'], run=run, status='proposed', repo=spec['repo'],
                            location=spec['location'], verified=built.get('verified'), changed=built.get('changed'),
                            cost_usd=built.get('cost_usd'), skipped=built.get('skipped'))


# -- the job ------------------------------------------------------------------------

def engineer(studio) -> dict:
    """One spec a day from the newest run the job has not settled, or a plain reason why not.
    Reading the runs and their buckets spends nothing; only the spec turn does.

    ponytail: one spec per job run, not a daily quota. A person who wants another runs the job
    again from the schedule; two Codex worktrees at once buys nothing here.
    """
    genesis = studio.genesis
    summary = {'run': None, 'card': None, 'reason': None, 'looked_at': 0}
    dials = genesis.autonomy.read()
    if dials['paused']:
        summary['reason'] = 'Genesis is paused; a person has to turn it back on.'
        return summary
    if dials.get('engineer') != 'propose':
        summary['reason'] = 'The Engineer dial is off: Genesis does not write fixes.'
        return summary
    spent = genesis.watcher.today_usd()
    cap = ceiling('STUDIO_GENESIS_ENGINEER_USD', '3.00')
    if spent + cap > genesis.watcher.cap_usd:
        summary['reason'] = f"Today's Genesis allowance cannot cover ${cap:.2f} more."
        return summary
    # The day is one gate, the week is the other; the sweep passes both before it writes.
    ok, reason = genesis.allowance_allows(cap)
    if not ok:
        summary['reason'] = reason
        return summary
    jobs = candidates(studio, genesis)
    summary['looked_at'] = len(jobs)
    for job in jobs:
        mark = fingerprint(studio, job)
        try:
            bucket, buckets = worst_bucket(genesis, job['id'])
        except (ValueError, KeyError, FileNotFoundError) as exc:
            genesis.autonomy.record('spec', run=job['id'], status='skipped', reason=str(exc)[:200])
            check_off(genesis, job['id'], mark)
            continue
        if not bucket:
            check_off(genesis, job['id'], mark)  # nothing in this run points at code
            continue
        if already_open(genesis, signature(job['id'], bucket)):
            check_off(genesis, job['id'], mark)
            continue
        route = genesis.config.route_for('reading')
        if not route:
            summary['reason'] = 'No model route is available.'
            return summary
        if any(t.get('purpose') == PURPOSE and t.get('status') == 'running' for t in genesis.listing('turns')):
            summary['reason'] = 'A spec is already being written.'
            return summary
        # The run is settled by ON_TURN, not here: a turn that fails is worth one more day.
        turn = genesis.chat({'message': message_for(genesis, job, bucket, buckets.get('buckets') or []),
                             'model': route['id'], 'maximum_usd': str(cap), 'purpose': PURPOSE})
        genesis.autonomy.record('spec-requested', turn=turn['id'], run=job['id'], bucket=bucket.get('id'))
        summary.update(run=job['id'], turn=turn['id'], bucket=bucket.get('id'))
        return summary
    summary['reason'] = summary['reason'] or 'No run is waiting: every finished run has been looked at.'
    return summary


DAILY = ('genesis-engineer', HOUR, engineer)
