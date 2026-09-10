"""Genesis plugins (feature 022): modules that add to Genesis without editing the shared files.

A module named here may offer:
- `TOOLS`: action name to `callable(genesis, payload)`; the action reaches the model through
  `lab_action` and is dispatched here after the built-in actions. A `ValueError` comes back to
  the model as a plain sentence, as the memory tools already do.
- `PROTOCOL`: a paragraph appended to `GENESIS.md` in every prompt, describing the tools.
- `PROMPT`: `callable(genesis, turn) -> str`, text added after the core memory of a turn.
- `ON_TURN`: `callable(genesis, turn)`, called once when a turn completes or fails, after the
  card bookkeeping; a plugin that raises is recorded in the activity log and never fails the turn.
- `GATE_LAUNCH` (or `review_gate`): `callable(card) -> (ok, reason)`, asked before any launch,
  by Genesis at smoke scale or by a person's approval; the first refusal wins, and a gate that
  raises refuses with its error, never lets a launch through.

A module that is not there yet is skipped, so lanes land independently.
"""
from __future__ import annotations

import importlib

MODULES = ('wb_studio.genesis_hypotheses', 'wb_studio.genesis_tools', 'wb_studio.genesis_ingest',
           'wb_studio.genesis_reviewer', 'wb_studio.genesis_ranking', 'wb_studio.genesis_memory_suite',
           'wb_studio.genesis_people', 'wb_studio.genesis_channels', 'wb_studio.genesis_patch')


def modules() -> list:
    out = []
    for name in MODULES:
        try:
            out.append(importlib.import_module(name))
        except ImportError:
            continue
    return out


def actions() -> list[str]:
    """Every plugin action name, in module order, without duplicates."""
    return list(dict.fromkeys(a for m in modules() for a in getattr(m, 'TOOLS', {})))


def dispatch(genesis, action: str, payload: dict) -> tuple[bool, object]:
    """(True, result) when a plugin owns the action, else (False, None)."""
    for module in modules():
        tool = getattr(module, 'TOOLS', {}).get(action)
        if tool is None:
            continue
        try:
            return True, tool(genesis, payload or {})
        except ValueError as exc:
            return True, {'error': str(exc)}
    return False, None


def protocol() -> str:
    parts = [str(getattr(m, 'PROTOCOL', '') or '').strip() for m in modules()]
    parts = [p for p in parts if p]
    return ('\n\n' + '\n\n'.join(parts)) if parts else ''


def prompt(genesis, turn: dict) -> str:
    out = ''
    for module in modules():
        fn = getattr(module, 'PROMPT', None)
        if callable(fn):
            out += str(fn(genesis, turn) or '')
    return out


def _record(genesis, kind: str, **data) -> None:
    recorder = getattr(getattr(genesis, 'autonomy', None), 'record', None)
    if callable(recorder):
        recorder(kind, **data)


def on_turn(genesis, turn: dict) -> None:
    for module in modules():
        fn = getattr(module, 'ON_TURN', None)
        if not callable(fn):
            continue
        try:
            fn(genesis, turn)
        except Exception as exc:  # a plugin never fails a finished turn; the record says what broke
            _record(genesis, 'plugin-error', card=turn.get('card'), turn=turn.get('id'), module=module.__name__, error=type(exc).__name__ + ': ' + str(exc)[:200])


def gate_launch(genesis, card: dict) -> tuple[bool, str | None]:
    """Whether every plugin gate lets this card launch, and the first plain reason when one does not."""
    for module in modules():
        fn = getattr(module, 'GATE_LAUNCH', None) or getattr(module, 'review_gate', None)
        if not callable(fn):
            continue
        try:
            ok, reason = fn(card)
        except Exception as exc:  # a broken gate refuses; it never waves a launch through
            _record(genesis, 'plugin-error', card=card.get('id'), module=module.__name__, error=type(exc).__name__ + ': ' + str(exc)[:200])
            return False, 'The launch gate in ' + module.__name__.rsplit('.', 1)[-1] + ' failed (' + type(exc).__name__ + '); a person has to look before this launches.'
        if not ok:
            return False, str(reason or 'A launch gate refused without a reason.')
    return True, None
