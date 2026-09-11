"""Genesis builds an architecture a step at a time, and one save commits the build.

Feature 025, FR-056 and FR-057. Genesis used to change an architecture only by handing
over a whole graph, which meant a person saw nothing until it was already saved. Here it
adds a step, connects two steps and writes a prompt, one operation at a time, and the open
editor applies each one as provisional state off the turn stream it is already receiving.

**An operation is not a durable write.** Nothing in this module touches
`blueprints/<id>/draft.json`; the only record an operation leaves is the `tool_completed`
event the harness writes for every tool call. So the build lives exactly as long as the
turn does, a reload before the commit leaves no half-saved architecture behind (SC-022),
and the turn's record still shows what was done (FR-056).

That also settles delivering the same operation twice (FR-047). The build is a pure
function of the operations recorded so far, replayed from the turn's own events, so a
reconnection that re-reads them lands on exactly the graph an uninterrupted delivery would
have produced. There is no separate buffer to fall out of step with, and no per-turn state
in this process that two turns could race over.

The commit is the existing `save_architecture`, unchanged for a caller that passes a whole
graph. Called with no graph it saves what the turn built — one revision, however many
operations it took.
"""
from __future__ import annotations

import json
import time

from wb_studio import blueprints

# A browser that closed without a word stops mattering. Editor state that has not been
# renewed inside this window is a tab that is gone, not a person in the middle of a
# sentence — otherwise one crashed browser blocks every later commit forever.
STALE_SECONDS = 900

PROTOCOL = (
    'edit_architecture(operation, ...): build an architecture one step at a time, in front of '
    'the person. add_node needs node {id, type, label, config}; connect needs from and to; '
    'set_prompt needs node and text. Pass id on the first operation to build on a saved draft, '
    'or leave it out to start an empty one. Nothing is saved: the steps appear in the open '
    'editor as provisional work and vanish on reload. When the build is right, call '
    'save_architecture with a name and no graph — it commits every operation of this turn as '
    'one revision. Publishing stays a separate, deliberate act.'
)


def _recorded(genesis, turn):
    """Every operation this turn has completed, in order, and the draft it started from."""
    try:
        record = genesis.read('turns', turn)
    except (OSError, ValueError, KeyError):
        return [], None, 0
    operations, base, revision = [], None, 0
    for event in record.get('events') or []:
        if event.get('type') != 'tool_completed' or event.get('action') != 'edit_architecture':
            continue
        try:
            value = json.loads(event.get('detail') or event.get('result') or '')
        except ValueError:
            continue          # a result the record had to truncate is not an operation
        if not isinstance(value, dict) or not isinstance(value.get('operation'), dict):
            continue
        operations.append(value['operation'])
        if base is None and value.get('id'):
            base, revision = value['id'], value.get('revision') or 0
    return operations, base, revision


def build(genesis, turn, identity=None, revision=0):
    """The graph this turn has built: the named draft as it was saved, then every operation."""
    operations, base, base_revision = _recorded(genesis, turn)
    identity = identity or base
    graph = {'nodes': [], 'edges': []}
    if identity:
        file = blueprints.paths(genesis.studio, identity) / 'draft.json'
        try:
            record = json.loads(file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise ValueError(f"There is no saved architecture called '{identity}'. Leave id out to start a new one.")
        graph = record.get('graph') or graph
        revision = revision or record.get('revision') or 0
    for operation in operations:
        graph = blueprints.apply_operation(graph, operation)
    return graph, identity, revision or base_revision, len(operations)


def _allowed(genesis):
    """FR-058: editing has its own dial, and it obeys the pause like every other."""
    state = genesis.autonomy.read()
    if state.get('paused'):
        raise ValueError('Genesis is paused. A person turns it back on under Settings, Genesis.')
    if state.get('edit', 'act') == 'off':
        raise ValueError('The Editing dial is off, so Genesis cannot change an architecture. '
                         'A person turns it on under Settings, Genesis.')


def edit(genesis, turn, payload):
    """One build step, validated by the lab's own blueprint validation (FR-057)."""
    if not turn:
        raise ValueError('Building an architecture needs a turn to build in.')
    _allowed(genesis)
    operation = {key: payload[key] for key in ('operation', 'node', 'from', 'to', 'text') if key in payload}
    graph, identity, revision, done = build(genesis, turn, payload.get('id'), payload.get('revision') or 0)
    graph = blueprints.apply_operation(graph, operation)
    # The node as the canvas will hold it, defaults and all. The editor applies what comes
    # back rather than filling in its own, so there is one copy of those defaults.
    if operation['operation'] == 'add_node':
        operation = {**operation, 'node': graph['nodes'][-1]}
    # A problem is reported against the node or connection that caused it and the build
    # stands (FR-057): a half-built graph is meant to be invalid, and discarding the work
    # over it would make building a step at a time impossible. The strict checks that
    # publishing needs run in the editor and again at save and publish.
    found = blueprints.problems(graph, strict=False)
    return {'operation': operation, 'id': identity, 'revision': revision, 'steps': done + 1,
            'nodes': len(graph['nodes']), 'edges': len(graph['edges']), 'problems': found[:6],
            'saved': False,
            'note': 'Provisional. Nothing is saved until you call save_architecture, which commits this whole build as one revision.'}


def open_editor(studio, identity=None):
    """Whether a browser has this architecture open right now with unsaved edits (FR-049)."""
    record = getattr(studio, 'editors', {}).get('architecture')
    if not isinstance(record, dict) or not record.get('dirty'):
        return False
    if identity and record.get('id') and record['id'] != identity:
        return False
    return (time.time() - float(record.get('at') or 0)) < STALE_SECONDS


def commit(genesis, turn, payload):
    """`save_architecture`. With a graph it is the old behaviour; without one it saves the build."""
    payload = dict(payload or {})
    if not payload.get('graph'):
        graph, identity, revision, steps = build(genesis, turn, payload.get('id'), payload.get('revision') or 0)
        if not steps:
            raise ValueError('There is nothing to save. Build it with edit_architecture first, or pass a graph.')
        payload['graph'] = graph
        if identity:
            payload.setdefault('id', identity)
        payload.setdefault('revision', revision)
    refuse_while_editing(genesis.studio, payload.get('id'))
    return blueprints.save_draft(genesis.studio, payload)


def refuse_while_editing(studio, identity):
    """A person's unsaved edits outrank a model's commit, and the build is not lost for it."""
    if open_editor(studio, identity):
        raise ValueError('Someone has this architecture open with unsaved edits, so it cannot be committed now. '
                         'This turn keeps the build: ask them to save or discard, then save again.')
