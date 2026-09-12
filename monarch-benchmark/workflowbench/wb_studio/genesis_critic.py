"""The weekly adversary (feature 023 §5.6, design of record
`docs/superpowers/specs/2026-09-11-genesis-engineer-loop-design.md`).

Once a week a **different** model than the one that writes reviews what the lab publishes, against
rubrics that live on disk as files a person can read and edit (`wb_studio/rubrics/`). It reads all
three of the things Lucas asked for:

- the **rendered pages**, through `tests/browser/shot.cjs`: a full-page picture, a crop, and a
  measured layout record — overflow, clipping, the smallest text, the lowest contrast, the tables;
- the **report prose and data**, through `report_data.run_report` on the newest finished run;
- the **Studio's own source**, through the lab code index, when it wants to name a location.

The measured layout record is the part that matters most. Sakana's reviewer failed because an LLM
judging an LLM has no gradient; here the figures rubric's numeric rules (F10 to F13) are decided by
the browser, not by the critic, and the critic's job on those is to say what to do about them.

Output: one enhancement card per finding, each naming the page and the rubric line it fails. A
finding that carries a valid spec is implemented through the engineer's Codex handoff, at most one
a week, so the week cannot turn into an agent farm.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from decimal import Decimal
from pathlib import Path

from wb_results.evidence import write_json
from wb_studio import genesis_engineer as engineer
from wb_studio.genesis_reviewer import json_answer
from wb_studio.library import now_sao_paulo

HOUR = 9                       # after the 08:00 engineer, on the digest day
PURPOSE = 'Genesis critic'
RUBRICS = ('prose', 'figures', 'accuracy')
DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
FINDINGS = 6                   # at most, per week
SHOT_SECONDS = 120
SERVER_SECONDS = 180
MESSAGE_LIMIT = 15_800
# The views worth a picture, and the one element on each worth a crop. A full page at 1440 will not
# show that a padding changed; a crop will.
VIEWS = (('runs', '#runs', '#history-rows'),
         ('leaderboard', '#leaderboard', '#reports-panel'),
         ('budget', '#budget', '#budget-content'))
# `analysis` first: reasoning before the verdict, or the verdict arrives and the reasoning becomes a
# justification of it. The name also sorts first, because at least one provider returns structured
# output with its keys sorted rather than in the order they were asked for.
OUTPUT = (
    'Write one JSON object and nothing else: {"findings": [ ... ]}, each finding with its fields in '
    'exactly this order:\n'
    '  "analysis": the evidence, quoted. A measured value from the record above ("lowest_contrast '
    '4.1 on 11px \'3 runs\'"), or the exact words you are objecting to, or the path:line you read. '
    'Then why that breaks the rule. This comes first because it is how you decide, not how you '
    'defend a decision you have already made.\n'
    '  "fix": what to do, specifically enough that someone could do it.\n'
    '  "rubric": the line id, like "figures:F10". Only ids that appear in the rubrics above.\n'
    '  "what": what is wrong, one sentence.\n'
    '  "where": the page, section or file.\n'
    '  "why_it_matters": what the reader loses. Not what a style guide says — what a person reading '
    'this page fails to learn, or learns wrongly.\n'
    '  "spec": null, or {"repo", "location", "commit", "change", "verify"} when the fix is mechanical '
    'and you have read the line.\n'
    '  "figure": "" or "[figure:<id>]" from a `figure` call, when the finding is about a number and a '
    'reader would see it faster drawn than described. One figure, or none — a figure that is not the '
    'point of the card is noise, and never a figure for a finding about prose.\n\n'
    'Worst first, at most ' + str(FINDINGS) + '.\n\n'
    'Write for someone who reads this in fifteen seconds. One sentence for "what". No preamble, no '
    'restating the rubric line you just cited, no closing summary. If "why_it_matters" needs a '
    'paragraph, you have not worked the finding out yet.\n\n'
    '**"findings": [] is a correct answer and a good week.** You are not required to find anything. A '
    'finding with no quote behind it, or one you would not raise to a colleague, is worse than an '
    'empty list: it teaches the lab to stop reading these. Do not fill the list to have something to '
    'say, and do not restate a rule as a finding — a rule is only broken when you can point at where.\n\n'
    'F10 to F13 are already decided by the measured record; if a number there is inside its limit, '
    'there is no finding, whatever the picture looks like. On everything else, the pictures and the '
    'text are your evidence and the rubric is the standard.')


def ceiling() -> Decimal:
    return Decimal(os.environ.get('STUDIO_GENESIS_CRITIC_USD', '2.00'))


def rubric(name: str) -> str:
    return (Path(__file__).parent / 'rubrics' / (name + '.md')).read_text(encoding='utf8')


def rubric_lines() -> set:
    """Every id a finding may cite, read from the files themselves, so a rubric a person edits is
    the one the card is checked against."""
    out = set()
    for name in RUBRICS:
        for line in rubric(name).splitlines():
            if line.startswith('## '):
                out.add(name + ':' + line[3:].split(' ', 1)[0].strip())
    return out


def same_family(writer, judge) -> bool:
    """Whether the critic would be marking its own family's homework. A judge scores its own
    family's output higher — the effect is measured and large enough to say out loud, so the turn
    is told when it applies rather than the lab quietly trusting a number."""
    if not writer or not judge:
        return False
    if writer['id'] == judge['id']:
        return True
    from wb_arms import providers
    try:
        a, b = providers.get(writer['id']), providers.get(judge['id'])
    except (KeyError, ValueError):
        return False
    left, right = (a.family or a.adapter), (b.family or b.adapter)
    return bool(left) and left == right


def due_today(studio, now=None) -> bool:
    now = now or now_sao_paulo()
    try:
        wanted = str(studio.genesis.access.settings().get('digest_day') or 'monday').lower()
    except Exception:
        wanted = 'monday'
    return DAYS[now.weekday()] == (wanted if wanted in DAYS else 'monday')


# -- the eyes ---------------------------------------------------------------------

def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_fixture(root: Path, port: int):
    """The same offline fixture Studio the browser suite uses: recorded runs, no money, no token."""
    uv = 'uv.exe' if os.name == 'nt' else 'uv'
    child = subprocess.Popen([uv, 'run', 'python', 'tests/browser/server.py', '--port', str(port)],
                             cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace')
    seen = ''
    import time
    deadline = time.monotonic() + SERVER_SECONDS
    while time.monotonic() < deadline:
        line = child.stdout.readline()
        if not line:
            break
        seen += line
        if 'READY' in line:
            return child
    child.kill()
    raise RuntimeError('The fixture Studio did not start: ' + seen[-400:])


def look(studio) -> dict:
    """A picture, a crop and a measured layout record for each view, in both themes for the first.
    Returns {'shots': [...], 'images': [paths], 'skipped': reason} — a missing browser is a reason,
    never a failure: the prose and accuracy half of the review still runs."""
    from wb_studio.app import ROOT
    out = {'shots': [], 'images': []}
    folder = Path(studio.directory) / 'genesis' / 'critic' / now_sao_paulo().date().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        port = free_port()
        server = start_fixture(ROOT, port)
    except (OSError, RuntimeError) as exc:
        return {**out, 'skipped': str(exc)[:300]}
    try:
        for view, hash_, selector in VIEWS:
            for theme in (('light', 'dark') if view == VIEWS[0][0] else ('light',)):
                args = ['node', str(ROOT / 'tests' / 'browser' / 'shot.cjs'),
                        '--base', f'http://127.0.0.1:{port}', '--view', view, '--hash', hash_,
                        '--theme', theme, '--out', str(folder)]
                if selector:
                    args += ['--selector', selector]
                code, said, err = engineer._run(args, ROOT, SHOT_SECONDS)
                line = next((l for l in reversed(said.splitlines()) if l.startswith('{')), None)
                if not line:
                    out['shots'].append({'view': view, 'theme': theme, 'error': (err or said or 'no output')[-300:]})
                    continue
                record = json.loads(line)
                out['shots'].append(record)
                out['images'] += [p for p in (record.get('crop'), record.get('image')) if p][:1]
    finally:
        server.kill()
    if not out['shots']:
        out['skipped'] = 'No view could be rendered.'
    return out


# -- what it reads besides the pictures ---------------------------------------------

def newest_report(studio) -> dict | None:
    """The report a reader would open: the newest finished run."""
    from wb_studio import report_data
    from wb_studio.genesis_watcher import TERMINAL
    for job in studio.jobs():
        if job.get('status') in TERMINAL:
            try:
                return report_data.run_report(studio, job['id'])
            except Exception:
                continue
    return None


def _short(value, limit) -> str:
    return json.dumps(value, indent=1, default=str)[:limit]


def message_for(studio, seen: dict, report: dict | None, same_model: bool) -> str:
    measured = [{k: s.get(k) for k in ('view', 'theme', 'layout', 'errors', 'error')} for s in seen.get('shots', [])]
    return ('Review what this lab publishes, as an adversary. You did not write any of it, and '
            'nothing here is yours to defend.\n\n'
            'The lab is an internal benchmark of a product against language models. Its readers are '
            'three or four people who decide what to build next from these pages. A finding is worth '
            'raising when it changes what one of them would conclude, or stops them believing '
            'something the evidence does not support. A finding that only makes a page tidier is not.\n\n'
            + ('Note: you are from the same model family as whatever wrote the prose you are about to '
               'read. A judge marks its own family up. Hold the prose findings to the quote rule '
               'harder than you otherwise would, and say in the finding that the two are the same '
               'family.\n\n' if same_model else '')
            + 'The rubrics are the standard. Cite the line id.\n\n'
            + '\n\n'.join('### ' + name + '\n' + rubric(name) for name in RUBRICS)[:6000]
            + '\n\n## What the browser measured\n'
              'These numbers come from the page itself, not from you. F10 to F13 are decided here; '
              'your job on them is to say what to do.\n'
            + _short(measured, 4500)
            + ('\n\n(No page could be rendered: ' + str(seen.get('skipped')) + '. Review the prose and '
               'the numbers only, and do not guess at the layout.)\n' if seen.get('skipped') else '')
            + '\n\n## The newest report a reader would open\n'
            + (_short(report, 4000) if report else 'There is no finished run to report on yet.')
            + '\n\nThe pictures attached are the full page and a crop of the same views. Use '
              'code_search and code_read with repo "lab" when you want to name a file and line.\n\n'
            + OUTPUT)[:MESSAGE_LIMIT]


# -- the turn and the cards ---------------------------------------------------------

FIGURE_TAG = re.compile(r'^\[figure:[a-zA-Z0-9]{1,40}\]$')


def check_finding(data: dict, allowed: set) -> dict:
    found = {key: str(data.get(key) or '').strip() for key in ('analysis', 'rubric', 'where', 'what', 'why_it_matters', 'fix')}
    tag = str(data.get('figure') or '').strip()
    found['figure'] = tag if FIGURE_TAG.fullmatch(tag) else ''
    if found['rubric'] not in allowed:
        raise ValueError('Cite a rubric line that exists, like figures:F10; ' + found['rubric'] + ' is not one.')
    if not found['what'] or not found['fix']:
        raise ValueError('A finding says what is wrong and what to do.')
    # The cheapest guard against a finding invented to fill a slot: it has to point at something.
    if len(found['analysis']) < 40:
        raise ValueError('A finding quotes its evidence — a measured value, the words objected to, or a path:line.')
    return found


def body_of(found: dict, built: dict | None) -> str:
    """A card someone reads in fifteen seconds: the claim, then a label column of facts, then the
    figure if there is one. Prose is capped because a finding that needs three paragraphs is a
    finding that has not been worked out."""
    return (found['what'].rstrip('.') + '.\n\n'
            + '| | |\n|---|---|\n'
            + '| Fails | ' + found['rubric'] + ' |\n'
            + '| Where | ' + found['where'][:120] + ' |\n'
            + '| Evidence | ' + found['analysis'][:300].replace('\n', ' ') + ' |\n'
            + '| Costs the reader | ' + found['why_it_matters'][:200].replace('\n', ' ') + ' |\n'
            + ('| Diff | ' + ('verify passed' if built.get('verified') else 'verify FAILED'
                              if built.get('verified') is False else 'written, not verified')
               + ' |\n' if built and built.get('changed') else '')
            + ('| Diff | not written: ' + str(built.get('skipped') or built.get('declined') or 'no change')[:160].replace('\n', ' ')
               + ' |\n' if built and not built.get('changed') else '')
            + '\n**Fix:** ' + found['fix']
            + (('\n\n' + found['figure']) if found.get('figure') else ''))[:6000]


def ON_TURN(genesis, turn):
    """The week's findings become one card each. At most one carries a diff."""
    if turn.get('purpose') != PURPOSE:
        return
    if turn.get('status') != 'completed':
        genesis.autonomy.record('critic', turn=turn['id'], status='failed',
                                reason=next((e.get('message') for e in reversed(turn.get('events') or [])
                                             if e.get('type') == 'failed'), 'The critic turn did not finish.'))
        return
    try:
        answer = json_answer(turn.get('answer'), 'The critic')
    except ValueError as exc:
        genesis.autonomy.record('critic', turn=turn['id'], status='refused', reason=str(exc))
        return
    allowed, made, fixes = rubric_lines(), [], int(os.environ.get('STUDIO_GENESIS_CRITIC_FIXES', '1'))
    for raw in (answer.get('findings') or [])[:FINDINGS]:
        if not isinstance(raw, dict):
            continue
        try:
            found = check_finding(raw, allowed)
        except ValueError as exc:
            genesis.autonomy.record('critic', turn=turn['id'], status='refused', reason=str(exc))
            continue
        built = None
        if fixes > 0 and isinstance(raw.get('spec'), dict):
            try:
                spec = engineer.check_spec({**raw['spec'], 'failure': found['what'],
                                            'analysis': found['analysis'] or found['why_it_matters']})
                if engineer.commit_of(genesis.studio, spec['repo']).startswith(spec['commit'][:7]):
                    built = engineer.implement(genesis, spec, turn['id'] + '-' + str(len(made)))
                    fixes -= 1
            except (ValueError, KeyError) as exc:
                built = {'skipped': 'The spec was refused: ' + str(exc)[:200]}
        card = genesis.card({'kind': 'enhancement', 'stage': 'review', 'auto': False, 'by': 'genesis:critic',
                             'title': (found['rubric'] + ' — ' + found['what'])[:140],
                             'body': body_of(found, built), 'evidence': []})
        with genesis.lock:
            record = genesis.read('cards', card['id'])
            record.update(finding=found, build=built, audience='internal')
            write_json(genesis.path('cards', card['id']), record)
        made.append(card['id'])
    genesis.autonomy.record('critic', turn=turn['id'], status='reviewed', findings=len(made), cards=made)


def critic(studio) -> dict:
    """One adversarial review a week, on the lab's digest day."""
    genesis, now = studio.genesis, now_sao_paulo()
    summary = {'day': now.date().isoformat(), 'turn': None, 'reason': None, 'views': 0}
    if genesis.autonomy.read()['paused']:
        summary['reason'] = 'Genesis is paused; a person has to turn it back on.'
        return summary
    if not due_today(studio, now):
        summary['reason'] = 'The review runs on the digest day; today is not it.'
        return summary
    from wb_studio.genesis_harness import model_routes
    routes = model_routes()
    route = genesis.config.route_for('critic', routes=routes)
    if not route:
        summary['reason'] = 'No model route is available.'
        return summary
    writer = genesis.config.route_for('reading', routes=routes)
    same = same_family(writer, route)
    seen = look(studio)
    summary['views'] = len(seen.get('shots') or [])
    turn = genesis.chat({'message': message_for(studio, seen, newest_report(studio), same),
                         'model': route['id'], 'maximum_usd': str(ceiling()), 'purpose': PURPOSE,
                         'images': seen.get('images')})
    genesis.autonomy.record('critic-requested', turn=turn['id'], model=route['id'], views=summary['views'],
                            images=len(seen.get('images') or []), same_model=same or None,
                            skipped=seen.get('skipped'))
    summary.update(turn=turn['id'], model=route['id'], same_model=same, skipped=seen.get('skipped'))
    return summary


DAILY = ('genesis-critic', HOUR, critic)
