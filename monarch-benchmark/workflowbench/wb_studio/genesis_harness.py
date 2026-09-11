"""Genesis turns: one in-process loop over the benchmark's provider adapters (deep dive of 10 Sep 2026, M1 to M4).

Until 10 September a turn was a Codex CLI subprocess talking through a loopback proxy to one
untyped tool; the model guessed argument shapes, narrated between calls and died at a hard
request count with its work unsaved. Now a turn is a loop in this process over the same four
adapters the benchmark competitors use (`wb_arms.api_loop`), with one typed tool per lab action
(`genesis_schemas`), the protocol as the system prompt with SOUL.md as its first block, every
request reserved in the weekly ledger for an output cap the turn can still pay, tool results
and the provider's reasoning kept in the record, and a landing before the request cap: the
model is told when two requests remain, and a turn that still runs out saves what it had to
the card before it fails.

`model_routes`, `build_prompt`, `start_turn`, `summary`, `freshness` and `GenesisRefused` are
the seams the rest of the Studio and the tests use; they keep their names.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from decimal import Decimal
from pathlib import Path

from wb_arms import providers
import traceback
from wb_arms.api_loop import NORMAL_STOPS, InfraError, _json_messages, canonical_json
from wb_orchestrator.budget import BudgetExceeded
from wb_studio.gateways import ADAPTERS, EFFORTS, _money, ceiling_cost, resolve_effort
from wb_studio.library import now_sao_paulo
from wb_studio.memory import CREDENTIAL
from wb_studio import genesis_plugins
from wb_studio.genesis_schemas import shaped, tool_defs

OUTPUT_CAP = 16000        # output tokens one request may produce at most
IMAGE_TOKENS = 2000       # what one screenshot costs, near enough, at the sizes the browser suite takes
IMAGE_DATA = re.compile(r'[A-Za-z0-9+/]{1500,}={0,2}')  # a base64 run in a serialised message: billed by tile, not by length
OUTPUT_FLOOR = 1024       # below this an answer cannot finish; the request is refused instead
THINKING_ALLOWANCE = {'gemini': 65535}  # Gemini bills thinking as output; the most its thinking_budget accepts, allowed when the turn can pay
REQUEST_LIMIT = 24        # provider requests in one turn
LANDING = 2               # requests left when the model is told to answer
TURN_SECONDS = 900        # a turn ends after this, whatever it is doing
REQUEST_TIMEOUT = 180     # one provider request
RESULT_CHARS = 60_000     # a tool result sent to the model is cut here, with a marker
DETAIL_CHARS = 6_000      # what the turn record keeps of a tool result, beyond the short summary
DELTA_CHARS = 400         # text deltas are written to the record in pieces at least this long
HARNESS = 'loop'


class GenesisRefused(ValueError):
    """The lab's own refusal of a request, written to be shown to a person."""


class Stopped(Exception):
    """A person stopped the turn; `stop_turn` already recorded the failure."""


class Stopper:
    """What `genesis.active` holds for a running turn. `poll` and `kill` keep the shape the card
    routes call on the old subprocess: None while running, 0 once stopped."""

    def __init__(self):
        self.stopped = threading.Event()

    def poll(self):
        return 0 if self.stopped.is_set() else None

    def kill(self):
        self.stopped.set()


def summary(value, limit=240):
    """A short, credential-free rendering of a tool payload or result for the turn's record."""
    text = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    text = CREDENTIAL.sub('[redacted]', text)
    return text if len(text) <= limit else text[:limit] + '...'


def request_bounds(provider, input_tokens, remaining):
    """(output cap, thinking budget, ceiling) for one request against what is left of the turn's allowance.

    The output cap is what the remainder can pay for after the input, at most OUTPUT_CAP; Gemini's
    thinking gets what is left after that, up to its allowance, so a cheap step is never refused
    for thinking it cannot afford (R11). A request that cannot afford OUTPUT_FLOOR is refused in words."""
    rate_in = Decimal(str(max(provider.price_in, provider.price_cache_write or 0)))
    price_out = Decimal(str(provider.price_out))
    remaining = Decimal(remaining)
    input_cost = _money(Decimal(input_tokens) * rate_in / 1_000_000)
    room = OUTPUT_CAP + THINKING_ALLOWANCE.get(provider.adapter, 0) if price_out <= 0 else int((remaining - input_cost) * 1_000_000 / price_out)
    if room < OUTPUT_FLOOR:
        floor = ceiling_cost(provider, input_tokens, OUTPUT_FLOOR)
        raise GenesisRefused(f"The turn's allowance is spent: ${remaining:.2f} left; one more request on {provider.key} needs at least ${floor:.2f}. Raise the per-turn cap or choose a cheaper model.")
    max_output = min(OUTPUT_CAP, room)
    thinking = min(THINKING_ALLOWANCE.get(provider.adapter, 0), room - max_output)
    return max_output, thinking, ceiling_cost(provider, input_tokens, max_output + thinking)


def freshness(now=None):
    """The clock and the recency rule every Genesis turn receives."""
    now = now or now_sao_paulo()
    return 'Current date and time: ' + now.strftime('%Y-%m-%d %H:%M') + ' (America/Sao_Paulo). Prefer sources from the last six months; keep foundational and contradicting work.'


def model_routes():
    """Every model route: available when its key is set. `harness_ready` is always true now that a
    turn needs nothing installed beyond this process."""
    return [{'id': p.key, 'name': p.model_id, 'provider': p.family or p.adapter, 'harness': HARNESS,
             'available': bool(providers.api_key(p)), 'keyed': bool(providers.api_key(p)), 'harness_ready': True,
             'verification': 'Live provider route not yet verified', 'efforts': list(EFFORTS[p.adapter]) or ['default']}
            for p in providers.REGISTRY.values()]


def build_prompt(genesis, turn):
    """(system, brief). System: the protocol, SOUL.md first among the memory files, LAB.md, MONARCH.md, the
    card's notes, the skills that apply and the plugin blocks, read once at the start of the turn so the
    prefix holds for caching. Brief: the clock, the thread's previous exchanges and the request."""
    protocol = (Path(__file__).with_name('GENESIS.md')).read_text(encoding='utf8') + genesis_plugins.protocol()
    history = []; parent_id = turn.get('parent'); seen = set(); history_size = 0
    while parent_id and parent_id not in seen and len(history) < 8:
        seen.add(parent_id)
        try:
            parent = genesis.read('turns', parent_id)
            exchange = {'user': parent['message'], 'genesis': parent['answer']}
            history_size += len(json.dumps(exchange))
            if history_size > 64000:
                break
            history.insert(0, exchange); parent_id = parent.get('parent')
        except (ValueError, FileNotFoundError):
            break
    memory = getattr(genesis, 'memory', None)
    soul = memory.soul_block().strip() if memory else ''
    core = memory.prompt_block(turn.get('card'), soul=False) if memory else ''
    skills = getattr(genesis, 'skills', None)
    if skills:
        kind = None
        if turn.get('card'):
            try:
                kind = genesis.read('cards', turn['card']).get('kind')
            except (ValueError, FileNotFoundError, OSError):
                kind = None
        core += skills.prompt_block(kind or turn.get('kind'))
    core += genesis_plugins.prompt(genesis, turn)
    system = (soul + '\n\n' if soul else '') + protocol + core
    brief = freshness() + '\n\nPrevious exchange:\n' + json.dumps(history) + '\n\nUser request:\n' + turn['message']
    return system, brief


def prompt_text(genesis, turn):
    """The whole prompt as one text, the way `sessions/<turn>/prompt.txt` records it."""
    system, brief = build_prompt(genesis, turn)
    return system + '\n\n' + brief


def run_tool(genesis, name, args):
    """One lab action for the model. A refusal comes back as a sentence it can act on (R1); anything
    else is a lab fault, named without its internals and written to the activity record."""
    try:
        return genesis.tool(name, args or {})
    except KeyError as exc:
        return {'error': 'Missing or wrong field ' + str(exc) + ' for ' + name + '.'}
    except (ValueError, FileNotFoundError) as exc:
        return {'error': str(exc) or type(exc).__name__}
    except Exception as exc:
        recorder = getattr(getattr(genesis, 'autonomy', None), 'record', None)
        if callable(recorder):
            recorder('tool-error', action=name, error=type(exc).__name__ + ': ' + str(exc)[:200])
        return {'error': 'Lab action ' + name + ' failed (' + type(exc).__name__ + '). It was recorded; try another way.'}


def _landing(requests_left):
    if requests_left == LANDING:
        return '\n\n[Lab: two requests remain in this turn. Write your answer with the next one, citing what you have; save your analysis to the card first if it belongs there.]'
    if requests_left == 1:
        return '\n\n[Lab: this is the last request of the turn. Answer now; no further tool call will be run.]'
    if requests_left == REQUEST_LIMIT // 2:
        return '\n\n[Lab: half of the turn\'s requests are spent. Converge: read what you still need in one request, then write.]'
    return ''


def _save_partial(genesis, turn, reason):
    """A turn that ran out on a card leaves its last text in the card's notes (M3), inside the budget."""
    card = turn.get('card'); memory = getattr(genesis, 'memory', None)
    if not card or not memory:
        return
    try:
        text = genesis.read('turns', turn['id']).get('answer') or ''
        if not text.strip():
            return
        note = memory.note_read(card) or ''
        addition = '\n\nTurn ' + turn['id'][:8] + ' stopped (' + reason[:160] + '). Last text:\n' + text.strip()[:1500]
        memory.note_write(card, (note.rstrip() + addition)[-3900:].strip())
    except Exception:
        pass  # notes are a courtesy; the failure reason is on the card and the turn


def start_turn(genesis, turn):
    identity = turn['id']; scope = 'genesis-' + identity; maximum = Decimal(turn['maximum_usd']); studio = genesis.studio
    provider = providers.get(turn['model'])
    stopper = Stopper(); genesis.active[identity] = stopper
    context = getattr(genesis, 'context', None)
    if context is not None:
        context.turn = identity  # tools called from this thread know their turn (S2)
    spent = Decimal('0'); last_reason = None; request_id = None; dispatched = settled = False
    defs = tool_defs(); tools = shaped(defs, provider.adapter)
    pending = []

    def on_text(text):
        pending.append(text)
        if sum(len(t) for t in pending) >= DELTA_CHARS:
            flush()

    def flush():
        if pending:
            genesis.event(identity, 'text_delta', text=''.join(pending)); pending.clear()

    try:
        adapter = ADAPTERS[provider.adapter](provider, tools, REQUEST_TIMEOUT)
        effort = resolve_effort(provider, turn.get('effort') or 'default')
        if effort is not None and hasattr(adapter, 'effort'):
            adapter.effort = effort
        adapter.on_text = on_text
        system, brief = build_prompt(genesis, turn)
        folder = genesis.root / 'sessions' / identity; folder.mkdir(parents=True, exist_ok=True)
        (folder / 'prompt.txt').write_text(system + '\n\n' + brief, encoding='utf8')  # the same text prompt_text() gives
        messages = adapter.start(system, brief, turn.get('images'))  # feature 023: the critic sees the pages it reviews
        genesis.event(identity, 'harness_started', harness=HARNESS, model=provider.model_id, tools=len(defs))
        deadline = time.monotonic() + TURN_SECONDS
        for number in range(1, REQUEST_LIMIT + 1):
            if stopper.stopped.is_set():
                raise Stopped()
            if time.monotonic() > deadline:
                raise GenesisRefused(f'Genesis ran past {TURN_SECONDS // 60} minutes in one turn')
            dispatched = settled = False
            # SDK objects (Gemini) serialise through model_dump. An image is billed by tile, not by
            # the length of its base64, so it is counted once instead of by its characters — left in,
            # a single screenshot would reserve the whole turn's allowance and refuse itself.
            body = canonical_json(_json_messages(messages))
            shots = len(turn.get('images') or [])  # they sit in the first user message, so every request carries them
            input_tokens = (len(system) + len(IMAGE_DATA.sub('', body)) + len(canonical_json(tools))) // 2 + 1024 + shots * IMAGE_TOKENS
            max_output, thinking, ceiling = request_bounds(provider, input_tokens, maximum - spent)
            adapter.max_output = max_output
            if provider.adapter == 'gemini':
                adapter.thinking_budget = thinking
            request_id = scope + '-' + str(number)
            studio.ledger.reserve(request_id, ceiling, scope_id=scope, scope_limit_usd=maximum,
                                  metadata={'purpose': 'Genesis', 'provider': provider.key, 'model': provider.model_id, 'harness': HARNESS})
            with studio.runtime.provider(provider.family or provider.adapter, timeout=REQUEST_TIMEOUT, tokens=input_tokens + max_output + thinking):
                studio.ledger.claim(request_id); dispatched = True
                genesis.event(identity, 'model_started', request=number, model=provider.model_id, max_output=max_output, ceiling_usd=str(ceiling))
                try:
                    result = adapter.turn(messages, timeout=REQUEST_TIMEOUT)
                except InfraError as exc:
                    raise GenesisRefused('Provider request failed (' + exc.kind + '); the charge, if any, stays reserved') from None
            flush()
            usage = {'prompt_tokens': result.get('prompt_tokens'), 'cached_tokens': result.get('cached_tokens'),
                     'cache_write_tokens': result.get('cache_write_tokens', 0), 'output_tokens': result.get('output_tokens')}
            if any(type(v) is not int or v < 0 for v in usage.values()):
                raise ValueError('Provider usage could not be verified')
            genesis.event(identity, 'provider_receipt', request=number, usage=usage, finish_reason=result.get('stop_reason'))
            actual = _money(str(providers.cost_usd(provider, usage['prompt_tokens'], usage['cached_tokens'], usage['output_tokens'], usage['cache_write_tokens'])))
            from wb_arms.reservations import usage_details
            studio.ledger.settle(request_id, actual, usage=usage_details(usage), outcome='completed'); settled = True; spent += actual
            genesis.event(identity, 'usage', usage=usage, cost_usd=str(actual), finish_reason=result.get('stop_reason'))
            if result.get('reasoning'):
                genesis.event(identity, 'reasoning', text=summary('\n'.join(result['reasoning']), 4000))
            calls = result.get('tool_calls') or []
            if not calls:
                text = result.get('text') or ''
                if text and not genesis.read('turns', identity).get('answer'):
                    genesis.event(identity, 'text_delta', text=text)  # an adapter that does not stream
                if not text.strip() or result.get('stop_reason') not in NORMAL_STOPS:
                    raise GenesisRefused('The model stopped without a complete answer' + (' (stop reason: ' + str(result['stop_reason']) + ')' if result.get('stop_reason') else ''))
                if stopper.stopped.is_set():
                    raise Stopped()
                genesis.event(identity, 'completed', message='Genesis finished this turn.')
                break
            landing = _landing(REQUEST_LIMIT - number)
            for call in calls:
                if call.get('parse_error'):
                    value = {'error': 'The tool call arguments were not a JSON object: ' + str(call['parse_error'])}
                    genesis.event(identity, 'tool_started', action=call.get('name'), payload='')
                else:
                    genesis.event(identity, 'tool_started', action=call['name'], payload=summary(call.get('args') or {}))
                    value = run_tool(genesis, call['name'], call.get('args') or {})
                text = json.dumps(value, ensure_ascii=False, default=str)
                if len(text) > RESULT_CHARS:
                    text = text[:RESULT_CHARS] + ' ...[cut by the lab at ' + f'{RESULT_CHARS:,}' + ' characters; ask for a smaller page]'
                genesis.event(identity, 'tool_completed', action=call.get('name'), result=summary(text), detail=summary(text, DETAIL_CHARS))
                adapter.append_tool_result(messages, call, text + landing)
                landing = ''
        else:
            raise GenesisRefused(f'Genesis reached its limit of {REQUEST_LIMIT} requests in one turn')
        memory = getattr(genesis, 'memory', None)
        if memory:
            from wb_studio.memory import tags
            try:
                memory.touch(tags(genesis.read('turns', identity)['answer']))
            except Exception:
                pass  # citation bookkeeping never fails a finished turn
    except Stopped:
        pass
    except Exception as exc:
        if dispatched and not settled:
            studio.ledger.settle(request_id, None, outcome='error')
        flush()
        if isinstance(exc, BudgetExceeded):
            last_reason = f"The ledger refused the request ({exc}): ${maximum - spent:.2f} left of the turn's ${maximum:.2f}."
        elif isinstance(exc, GenesisRefused) or str(exc) == 'Provider usage could not be verified':
            last_reason = str(exc)
        else:
            last_reason = 'The turn stopped on a lab fault (' + type(exc).__name__ + ': ' + str(exc)[:160] + ').'
            recorder = getattr(getattr(genesis, 'autonomy', None), 'record', None)
            if callable(recorder):
                recorder('turn-fault', turn=identity, error=type(exc).__name__ + ': ' + str(exc)[:200], trace=traceback.format_exc()[-1500:])
        genesis.event(identity, 'request_error', message='Request stopped. Any uncertain charge remains reserved.', error_type=type(exc).__name__, reason=last_reason)
        _save_partial(genesis, turn, last_reason)
        if not stopper.stopped.is_set():
            genesis.event(identity, 'failed', message='Genesis could not complete this turn. No experiment was launched.', error_type=type(exc).__name__, reason=last_reason)
    finally:
        if context is not None:
            context.turn = None
        genesis.active.pop(identity, None)
        studio.ledger.finish_run(scope)
