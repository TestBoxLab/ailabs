"""A memory that proves itself (feature 022, design section 10, points 1, 2, 3, 7, 10).

Five things, none of which calls a model by itself:

1. **Touches from tools.** A record read through a tool counts as a citation, not
   only a tag in the final answer, so probation and decay measure use. `ON_TURN`
   maps the turn's tool events: `read_run {id}` -> `[rec:run:<id>]`; every hit of
   `record_search` -> its own tag; `library_read {id}` -> `[rec:library:<id>]`;
   `save_research` -> `[rec:card:<id>]`. Nothing else is a touch.
2. **Consolidation as data.** The nightly turn answers with operations, not prose:
   `{"ops": [{"op": "add"|"replace"|"remove", "section"?, "text"?, "old"?, "new"?,
   "record": "kind:id"}], "contradictions": [...]}`. They are validated and applied
   in order, stopping at the first refusal (budget or injection scan); what applied
   and what was refused goes to the activity record as `consolidated`, and the
   contradictions onto the day's brief card.
3. **Nightly self-check.** `check_known` re-reads three random Known entries against
   their records; one whose record is gone is removed with history op `self-check`.
   A `human` tag always holds, and so does a `run` tag -- a run lives in the Studio's
   job store, so its absence is not proof the entry is wrong.
4. **Track record.** `track` computes `TRACK.md` from cards, turns and the activity
   record (hypotheses and outcomes, plans launched and their settled cost, the Brier
   score of Genesis's priors); `PROMPT` injects it after the core memory every turn.
5. **What was forgotten.** `what_changed` reads last night's promotions, drops, stale
   marks and removals out of the memory history, with the reason for each.
"""
from __future__ import annotations

import json
import os
import random
import re
import uuid
from collections import Counter
from decimal import Decimal

from wb_studio.genesis_reviewer import json_answer  # the same tolerant JSON reader both chambers use
from wb_studio.library import now_sao_paulo
from wb_studio.memory import ENTRY, TAG, tags

NIGHTLY_PURPOSE = 'Genesis nightly'
TRACK_BUDGET = 1500
TRACK_NAME = 'TRACK.md'
# The tool events that count as a touch, and where the record id is written in them.
TOOL_RECORDS = {'read_run': ('run', 'payload'), 'library_read': ('library', 'payload'), 'save_research': ('card', 'result')}
IDENTITY = re.compile(r'"id"\s*:\s*"([a-zA-Z0-9_.-]{1,120})"')
REASONS = {'promote': 'It was cited after it was added, so it moved from Recent to Known.',
           'drop': 'Seven days in Recent without a citation, so it went back to the record.',
           'stale': 'Not cited for thirty days, so it was marked stale.',
           'decay': 'Still not cited after the stale mark, so it left Known.',
           'revive': 'Cited again, so the stale mark was lifted.',
           'self-check': 'The record it cites is no longer in the Studio.',
           'remove': 'Removed by Genesis or by a person.'}


# ---- touches from tools -------------------------------------------------------------------
def touches(events) -> list:
    """The record tags a turn's tool calls named, in order, without duplicates."""
    found = []
    for event in events or []:
        action = event.get('action')
        if action == 'record_search':
            found += tags(str(event.get('result') or ''))
            continue
        rule = TOOL_RECORDS.get(action)
        if not rule:
            continue
        kind, field = rule
        match = IDENTITY.search(str(event.get(field) or ''))
        if match:
            found.append('[rec:' + kind + ':' + match[1] + ']')
    return list(dict.fromkeys(found))


# ---- consolidation as data ----------------------------------------------------------------
def apply_ops(memory, ops, now=None) -> dict:
    """Apply the night's operations in order, stopping at the first one the memory refuses."""
    applied, refused = [], None
    for op in ops or []:
        if not isinstance(op, dict):
            refused = {'op': str(op)[:80], 'reason': 'Each operation is an object with op and the fields that op needs.'}
            break
        name = op.get('op')
        try:
            if name == 'add':
                out = memory.add(op.get('text'), op.get('record'), op.get('section') or 'Recent', now=now)['entry']
            elif name == 'replace':
                out = memory.replace(op.get('old'), op.get('new'), op.get('record'), now=now)['entry']
            elif name == 'remove':
                out = memory.remove(op.get('old'), now=now)['removed']
            else:
                raise ValueError('The operation is add, replace or remove, not ' + str(name) + '.')
        except ValueError as exc:  # MemoryFull is a ValueError: the budget ends the night here
            refused = {'op': str(name), 'reason': str(exc)}
            break
        applied.append({'op': name, 'entry': out})
    return {'applied': applied, 'refused': refused}


def _brief_card(turn):
    """The day's brief card id, from the day the nightly message names."""
    match = re.search(r'\d{4}-\d{2}-\d{2}', str(turn.get('message') or ''))
    return 'brief-' + match[0] if match else None


def _write_contradictions(genesis, turn, contradictions):
    if not contradictions:
        return None
    identity = _brief_card(turn)
    if not identity:
        return 'The nightly turn did not name its day, so the contradictions have no brief card.'
    with genesis.lock:
        try:
            card = genesis.read('cards', identity)
            genesis.card({**card, 'brief': {**(card.get('brief') or {}), 'contradictions': contradictions}})
        except (ValueError, OSError) as exc:
            return 'The contradictions could not be written to card ' + identity + ': ' + str(exc)
    return None


def preview(genesis, ops) -> dict:
    """The night's operations applied to a copy of LAB.md: the text that would result, what applied, what was refused."""
    import shutil
    from wb_studio.memory import Memory
    root = genesis.memory.root.parent / 'memory-preview'
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)  # rmtree ignores errors; a locked leftover must not fail the night
    if genesis.memory.lab.exists():
        shutil.copy(genesis.memory.lab, root / 'LAB.md')
    copy = Memory(root)
    result = apply_ops(copy, ops)
    text = copy.lab.read_text(encoding='utf8') if copy.lab.exists() else ''
    shutil.rmtree(root, ignore_errors=True)
    return {**result, 'text': text}


def consolidate(genesis, turn) -> dict:
    """The nightly turn's answer, validated and applied to a copy: the result is LAB.next.md and a memory card in
    Plan that a person adopts or declines (A1, the Dreams pattern). LAB.md itself changes only on approval."""
    try:
        data = json_answer(turn.get('answer'), 'The nightly turn')
    except ValueError as exc:
        genesis.autonomy.record('consolidated', turn=turn['id'], applied=0, refused={'reason': str(exc)})
        return {'applied': [], 'refused': {'reason': str(exc)}}
    ops = data.get('ops') if isinstance(data.get('ops'), list) else []
    result = preview(genesis, ops)
    contradictions = [str(c).strip()[:300] for c in (data.get('contradictions') or []) if str(c).strip()][:12]
    note = _write_contradictions(genesis, turn, contradictions)
    accepted = ops[:len(result['applied'])]
    card = None
    if accepted:
        genesis.memory.next_path.write_text(result['text'], encoding='utf8', newline='\n')
        day = (_brief_card(turn) or 'brief-tonight')[6:]
        lines = ['- ' + a['op'] + ': ' + str(a['entry'])[:200] for a in result['applied']]
        if result['refused']:
            lines.append('- refused ' + str(result['refused'].get('op')) + ': ' + str(result['refused'].get('reason'))[:200])
        card = genesis.card({'title': 'Memory changes proposed for ' + day, 'kind': 'memory', 'stage': 'approval',
                             'body': 'The night proposes these changes to LAB.md; adopt them or decline with a reason.\n\n' + '\n'.join(lines),
                             'proposal': {'operation': 'memory', 'ops': accepted, 'day': day}, 'evidence': [{'kind': 'turn', 'id': turn['id']}], 'auto': False, 'by': 'genesis'})
    genesis.autonomy.record('consolidation-proposed', turn=turn['id'], card=card['id'] if card else None, applied=result['applied'], refused=result['refused'],
                            contradictions=contradictions or None, note=note)
    return {**result, 'card': card['id'] if card else None}


# ---- the nightly self-check ---------------------------------------------------------------
def record_holds(genesis, kind, identity) -> bool:
    """Whether the record an entry cites is still there. What cannot be checked holds."""
    try:
        if kind == 'turn':
            return genesis.path('turns', identity).exists()
        if kind == 'card':
            return genesis.path('cards', identity).exists()
        if kind == 'analysis':
            return (genesis.root / 'analyses' / (identity + '.json')).exists()
        if kind == 'library':
            return genesis.library.path(identity).exists()
        if kind == 'code':
            return (genesis.root / 'code' / 'changes' / (identity + '.json')).exists()
    except Exception:
        return True  # an id this code cannot resolve is never grounds for forgetting
    return True      # human and run tags: nothing on Genesis's disk contradicts them


def check_known(genesis, sample=3, now=None) -> dict:
    """Re-read up to `sample` random Known entries against their records; drop what is gone."""
    memory = genesis.memory
    entries = list(memory.sections().get('Known') or [])
    checked, removed = [], []
    for entry in random.sample(entries, min(max(0, int(sample)), len(entries))):
        bare = entry[8:] if entry.startswith('(stale) ') else entry
        line = ENTRY.match(bare)
        if not line:
            continue
        kind, identity = TAG.match(line['tag']).groups()
        checked.append(entry)
        if record_holds(genesis, kind, identity):
            continue
        try:
            memory.remove(entry, now=now, op='self-check')
        except ValueError:
            continue
        removed.append({'entry': entry, 'reason': 'Its record ' + kind + ':' + identity + ' is no longer in the Studio.'})
    return {'known': len(entries), 'checked': len(checked), 'removed': removed}


# ---- the track record ---------------------------------------------------------------------
def _run_cost(genesis, job_id):
    from wb_studio.leaderboard import known_cost
    try:
        costs = [known_cost(row) for row in genesis.studio.job(job_id).get('results') or []]
        return sum(c for c in costs if c is not None)
    except Exception:
        return None


def track(genesis) -> str:
    """`TRACK.md`: what Genesis proposed, what settled, what it cost, and how well it predicts.

    Outcomes come from `card['settlement']['outcome']`; a hypothesis with no settlement is
    untested. The Brier score is the mean squared error of `card['hypothesis']['prior']`
    against the outcome (supported = 1, not supported = 0); every other outcome is excluded,
    and the count it rests on is printed beside it.
    """
    cards = genesis.listing('cards')
    hypotheses = [c for c in cards if c.get('kind') == 'hypothesis']
    outcome = lambda c: str((c.get('settlement') or {}).get('outcome') or 'untested')
    counts = Counter(outcome(c) for c in hypotheses)
    launched = [c for c in cards if c.get('job')]
    run_costs = [_run_cost(genesis, c['job']) for c in launched]
    known = [c for c in run_costs if c is not None]
    turns = sum(float(e.get('cost_usd') or 0) for t in genesis.listing('turns') for e in (t.get('events') or [])
                if e.get('type') == 'usage')

    scored = []
    for card in hypotheses:
        prior = (card.get('hypothesis') or {}).get('prior')
        result = outcome(card)
        if type(prior) in (int, float) and result in ('supported', 'not_supported'):
            scored.append((float(prior), 1.0 if result == 'supported' else 0.0))
    brier = sum((p - a) ** 2 for p, a in scored) / len(scored) if scored else None

    runs_line = f'${sum(known):.2f} settled in the runs' if known else 'no settled run cost yet'
    if known and len(known) < len(launched):
        runs_line += f' ({len(known)} of {len(launched)} runs priced)'
    lines = ['# Track record', '',
             'Computed by the Studio from the cards, the turns and the activity record. Genesis does not write this file.', '',
             (f"Hypotheses: {len(hypotheses)} proposed; {counts['supported']} supported, {counts['not_supported']} not supported, "
              f"{counts['inconclusive']} inconclusive, {counts['untested']} untested, {counts['invalid']} invalid."),
             f'Plans: {len(launched)} launched; {runs_line}; ${turns:.2f} settled in Genesis\'s own turns.']
    if brier is None:
        lines.append('Calibration: no settled hypothesis carries a prior yet, so there is no Brier score.')
    else:
        lines.append(f'Calibration: Brier score {brier:.2f} on the {len(scored)} settled hypotheses that carried a prior '
                     '(0 is perfect, 0.25 is a coin toss, above 0.25 is worse than guessing).')
    return ('\n'.join(lines) + '\n')[:TRACK_BUDGET]


def write_track(genesis) -> dict:
    """`genesis/memory/TRACK.md`, written by the nightly job."""
    text = track(genesis)
    path = genesis.memory.root / TRACK_NAME
    path.write_text(text, encoding='utf8', newline='\n')
    return {'size': len(text), 'budget': TRACK_BUDGET}


def PROMPT(genesis, turn):
    memory = getattr(genesis, 'memory', None)
    if memory is None:
        return ''
    try:
        text = (memory.root / TRACK_NAME).read_text(encoding='utf8').strip()
    except OSError:
        return ''
    return '\n\nTrack record (TRACK.md, computed by the Studio):\n\n' + text if text else ''


# ---- what was forgotten -------------------------------------------------------------------
def what_changed(genesis, limit=50) -> list:
    """Last night's promotions, drops, stale marks and removals, newest first, with reasons."""
    out = []
    for row in reversed(genesis.memory.history_tail(300)):
        if row.get('op') not in REASONS:
            continue
        out.append({'op': row['op'], 'at': row.get('at'), 'record': row.get('record'),
                    'entry': row.get('before') or row.get('after'), 'reason': REASONS[row['op']]})
        if len(out) >= max(1, min(200, int(limit))):
            break
    return out


# ---- the weekly evaluation ------------------------------------------------------------------
EVAL_PURPOSE = 'Genesis memory eval'
EVAL_SEED = 12          # the fixed questions, seeded once from the store
EVAL_GENERATED = 8      # how many more are generated from the newest records each week
EVAL_MESSAGE = ('This is the weekly memory evaluation. Answer each question with the record tag that holds the '
                'answer, using record_search to find it. Answer with one JSON object and nothing else: '
                '{"answers": [{"question": "the question as written", "tag": "[rec:kind:id]"}]}. Leave a tag out '
                'only when the record is not there. The questions:\n')


def eval_cap() -> str:
    """The evaluation's per-turn ceiling. Per-step caps are not in `genesis/config.json` yet."""
    return os.environ.get('STUDIO_GENESIS_EVAL_USD', '0.50')


def week_of(now=None) -> str:
    now = now or now_sao_paulo()
    return now.strftime('%G-W%V')


def _question(row) -> str:
    title = str(row.get('title') or row.get('id'))[:120]
    return ('What did ' + title + ' find?') if row['kind'] == 'library' else ('Which run tested ' + title + '?')


def questions(genesis) -> list:
    """The fixed twelve, seeded from the store the first time, plus up to eight from the newest records."""
    path = genesis.memory.root / 'eval.json'
    try:
        fixed = json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError):
        fixed = []
    fixed = [q for q in fixed if isinstance(q, dict) and q.get('question') and q.get('answer_tag')]
    if not fixed:
        fixed = [{'question': _question(r), 'answer_tag': r['tag']} for r in genesis.memory.recent(EVAL_SEED)]
        if fixed:
            path.write_text(json.dumps(fixed, indent=1, ensure_ascii=False), encoding='utf8', newline='\n')
    known = {q['answer_tag'] for q in fixed}
    fresh = [{'question': _question(r), 'answer_tag': r['tag']} for r in genesis.memory.recent(EVAL_SEED + EVAL_GENERATED)
             if r['tag'] not in known][:EVAL_GENERATED]
    return fixed + fresh


def ask_eval(genesis, now=None) -> dict:
    """One evaluation turn on the reading route. The questions are recorded before it starts."""
    from wb_studio.genesis_harness import model_routes
    asked = questions(genesis)
    if not asked:
        return {'asked': 0, 'turn': None, 'reason': 'The record holds nothing to ask about yet.'}
    route = genesis.config.route_for('reading', routes=model_routes())
    if not route:
        raise ValueError('No model route is available for the memory evaluation.')
    identity = uuid.uuid4().hex
    week = week_of(now)
    genesis.autonomy.record('memory-eval-requested', turn=identity, week=week, questions=asked)
    message = (EVAL_MESSAGE + json.dumps([q['question'] for q in asked], ensure_ascii=False))[:15000]
    genesis.chat({'id': identity, 'message': message, 'model': route['id'], 'maximum_usd': eval_cap(), 'purpose': EVAL_PURPOSE})
    return {'asked': len(asked), 'turn': identity, 'week': week}


def eval_path(genesis, week):
    return genesis.memory.root / ('eval-' + str(week) + '.json')


def trend(genesis) -> list:
    """Every scored week, oldest first: recall, wrong, unanswered and tokens per answer."""
    out = []
    for path in sorted(genesis.memory.root.glob('eval-*.json')):
        try:
            row = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        out.append({k: row.get(k) for k in ('week', 'asked', 'recall', 'wrong', 'unanswered', 'tokens_per_answer')})
    return out


def score_eval(genesis, turn, now=None) -> dict | None:
    """The evaluation turn's answers scored by exact tag match, written as the week's file."""
    entry = next((e for e in genesis.autonomy.tail(500) if e.get('kind') == 'memory-eval-requested' and e.get('turn') == turn['id']), None)
    if not entry:
        return None
    asked, week = entry.get('questions') or [], entry.get('week') or week_of(now)
    given = {}
    try:
        if turn.get('status') != 'completed':
            raise ValueError('The evaluation turn did not finish.')
        data = json_answer(turn.get('answer'), 'The memory evaluation')
        given = {str(a.get('question')): str(a.get('tag') or '').strip() for a in (data.get('answers') or []) if isinstance(a, dict)}
        problem = None
    except ValueError as exc:
        problem = str(exc)
    rows = []
    for question in asked:
        answer = given.get(question['question'], '')
        rows.append({'question': question['question'], 'expected': question['answer_tag'], 'given': answer or None,
                     'verdict': 'unanswered' if not answer else ('right' if answer == question['answer_tag'] else 'wrong')})
    counts = Counter(r['verdict'] for r in rows)
    tokens = sum(int(v or 0) for e in (turn.get('events') or []) if e.get('type') == 'usage'
                 for k, v in (e.get('usage') or {}).items() if k in ('prompt_tokens', 'output_tokens'))
    result = {'week': week, 'turn': turn['id'], 'at': (now or now_sao_paulo()).isoformat(timespec='seconds'),
              'asked': len(rows), 'right': counts['right'], 'wrong': counts['wrong'], 'unanswered': counts['unanswered'],
              'recall': round(counts['right'] / len(rows), 3) if rows else 0.0,
              'tokens_per_answer': round(tokens / len(rows)) if rows else 0, 'answers': rows, 'problem': problem}
    eval_path(genesis, week).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf8', newline='\n')
    result['trend'] = trend(genesis)
    eval_path(genesis, week).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf8', newline='\n')
    genesis.autonomy.record('memory-eval', turn=turn['id'], week=week, recall=result['recall'], wrong=result['wrong'],
                            unanswered=result['unanswered'], tokens_per_answer=result['tokens_per_answer'], reason=problem)
    return result


def eval_status(genesis) -> dict:
    """The last week scored and the trend, for the Memory tab and for Genesis."""
    line = trend(genesis)
    latest = None
    if line:
        try:
            latest = json.loads(eval_path(genesis, line[-1]['week']).read_text(encoding='utf8'))
        except (OSError, ValueError):
            latest = None
    return {'latest': latest, 'trend': line,
            'note': 'The evaluation runs on Sundays; recall is the share of questions answered with the right record tag.'}


def weekly(studio) -> dict:
    """`genesis-memory-eval`, 05:00, Sundays only: one turn, inside the weekly ledger."""
    genesis, now = studio.genesis, now_sao_paulo()
    summary = {'day': now.date().isoformat(), 'week': week_of(now), 'asked': 0, 'turn': None, 'reason': None, 'errors': []}
    if now.weekday() != 6:
        summary['reason'] = 'The memory evaluation runs on Sundays; today is not one.'
        return summary
    ceiling = Decimal(eval_cap())
    try:
        if Decimal(str(studio.ledger.status(now=now).available_usd)) < ceiling:
            summary['reason'] = f'The weekly ledger cannot cover ${ceiling:.2f} for the evaluation.'
            return summary
        summary.update(ask_eval(genesis, now))
    except Exception as exc:  # the job reports and finishes; it never takes the server down
        summary['errors'].append(f'{type(exc).__name__}: {exc}')
    return summary


DAILY = ('genesis-memory-eval', 5, weekly)


# ---- hybrid retrieval ------------------------------------------------------------------------
EMBED_BATCH = 64


def _client(provider):
    """The embeddings client for an OpenAI-compatible route. Replaced in tests."""
    import openai
    from wb_arms import providers
    return openai.OpenAI(api_key=providers.api_key(provider), base_url=provider.base_url, max_retries=0, timeout=60)


def embedding_price(provider):
    """The embedding list price per million tokens named in the route's model file, or None."""
    import yaml
    from wb_arms.providers import DEFAULT_MODELS_DIR
    path = DEFAULT_MODELS_DIR / (provider.key + '.yaml')
    try:
        data = yaml.safe_load(path.read_text(encoding='utf8')) or {}
    except (OSError, ValueError):
        return None
    price = (data.get('usd_per_million') or {}).get('embedding', data.get('embedding_usd_per_million'))
    return None if price is None else Decimal(str(price))


def embed(genesis, texts) -> list | None:
    """Vectors for these texts through the embedding step's route, reserved and settled in the
    ledger. `None` when no embedding route is configured or the adapter has no embeddings."""
    from wb_arms import providers
    from wb_studio.gateways import _money
    from wb_studio.genesis_harness import model_routes
    texts = [str(t or '') for t in (texts or [])]
    if not texts:
        return []
    route = genesis.config.route_for('embedding', routes=model_routes())
    if not route or not route.get('available'):
        return None
    provider = providers.get(route['id'])
    if provider.adapter not in ('openai', 'openai_responses'):
        return None  # only an OpenAI-compatible route offers client.embeddings.create
    price = embedding_price(provider)
    if price is None:
        raise ValueError('The model file for ' + provider.key + ' names no embedding price, so no embedding request '
                         'may be reserved. Name usd_per_million.embedding in the model file or choose another '
                         'embedding route on the configuration page.')
    tokens = sum(len(t) // 4 + 1 for t in texts)
    ceiling = _money(Decimal(tokens) * price / 1_000_000) or Decimal('0.01')
    # Embeddings are Genesis spend like any other and pass the same weekly gate.
    ok, reason = genesis.allowance_allows(ceiling)
    if not ok:
        raise ValueError(reason)
    request_id = 'genesis-embed-' + uuid.uuid4().hex[:16]
    ledger = genesis.studio.ledger
    ledger.reserve(request_id, ceiling, scope_id='genesis-embedding',
                   metadata={'purpose': 'Genesis embedding', 'provider': provider.key, 'model': provider.model_id})
    ledger.claim(request_id)
    try:
        result = _client(provider).embeddings.create(model=provider.model_id, input=texts)
    except Exception:
        ledger.settle(request_id, None, outcome='error')  # an uncertain charge stays held at its ceiling
        raise
    used = getattr(getattr(result, 'usage', None), 'prompt_tokens', None)
    known = type(used) is int and used >= 0
    ledger.settle(request_id, _money(Decimal(used) * price / 1_000_000) if known else None,
                  usage={'input': used, 'output': 0, 'cache_read': 0, 'cache_write': 0} if known else None,
                  outcome='completed')
    return [list(item.embedding) for item in result.data]


def index_vectors(genesis, limit=EMBED_BATCH) -> dict:
    """Embed the indexed records that have no vector yet. Off when there is no embedding route."""
    rows = genesis.memory.unvectored(limit)
    if not rows:
        return {'embedded': 0, 'reason': 'Every indexed record already has a vector.'}
    try:
        vectors = embed(genesis, [r['text'] for r in rows])
    except ValueError as exc:  # a route that names no embedding price is refused in words, never at night
        return {'embedded': 0, 'reason': str(exc)}
    if vectors is None:
        return {'embedded': 0, 'reason': 'No embedding route is configured; the record search stays FTS5 only.'}
    stored = genesis.memory.store_vectors([{'kind': r['kind'], 'id': r['id'], 'vector': v} for r, v in zip(rows, vectors)])
    return {'embedded': stored, **genesis.memory.vector_stats()}


def record_search(genesis, payload) -> list:
    """`record_search` with hybrid retrieval when an embedding route exists, FTS5 when it does not."""
    query, limit = payload.get('query'), payload.get('limit', 10)
    vector = None
    try:
        vectors = embed(genesis, [str(query or '')])
        vector = vectors[0] if vectors else None
    except Exception as exc:  # a refused or broken embedding never costs the search
        reason = str(exc)[:300]
        said = next((e for e in genesis.autonomy.tail(50) if e.get('kind') == 'embedding-refused'), None)
        if not said or said.get('reason') != reason:  # a standing refusal is recorded once, not once a search
            genesis.autonomy.record('embedding-refused', reason=reason)
    return genesis.memory.search(query, limit, mode='hybrid' if vector else 'fts', vector=vector)


def ON_TURN(genesis, turn):
    found = touches(turn.get('events'))
    if found:
        genesis.memory.touch(found)
    if turn.get('purpose') == NIGHTLY_PURPOSE and turn.get('status') == 'completed':
        consolidate(genesis, turn)
    if turn.get('purpose') == EVAL_PURPOSE:
        score_eval(genesis, turn)
    from wb_studio import genesis_skills
    genesis_skills.after_turn(genesis, turn)  # skills that write themselves (this module is the plugin that carries them)


TOOLS = {'memory_changes': lambda genesis, payload: what_changed(genesis, payload.get('limit', 50)),
         'memory_eval_status': lambda genesis, payload: eval_status(genesis)}

PROTOCOL = ('The Studio counts a record as cited when you read it with a tool, not only when you tag it in an '
            'answer, so read what you cite. Every night one turn returns memory operations as JSON, which the '
            'code applies inside the budget and stops at the first refusal; three Known entries are re-read '
            'against their records and dropped when the record is gone. memory_changes lists what memory '
            'promoted, dropped, marked stale or removed, with the reason for each. TRACK.md, in every prompt, '
            'is the Studio\'s count of what you proposed, what settled and how well your priors predicted it; '
            'you do not write it. Once a week the Studio asks you twenty questions whose answers are record tags '
            'and scores them by exact match; memory_eval_status shows the last score and the trend. record_search '
            'fuses words and meaning when an embedding route is configured, and every hit says why it matched.')
