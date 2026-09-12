"""Genesis builds an architecture a step at a time (feature 025, FR-044 to FR-058).

The claims worth a test are the ones a screenshot cannot settle: that an operation writes
nothing, that however many operations there were the save makes one revision, that a
problem does not throw the build away, and that a person's unsaved edits outrank a model's
commit.
"""
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wb_results.evidence import write_json
from wb_studio import blueprints, genesis_build
from wb_studio.genesis import Genesis, stamp
from wb_studio.genesis_show import check_route


@pytest.fixture
def genesis(tmp_path):
    studio = SimpleNamespace(directory=tmp_path, lock=threading.RLock(), ledger=Mock(), editors={},
                             jobs=Mock(return_value=[]), events=Mock(return_value=[]), create=Mock())
    studio.job = Mock(side_effect=FileNotFoundError)
    return Genesis(studio)


def turn(genesis, identity='t1'):
    write_json(genesis.path('turns', identity), {'id': identity, 'status': 'running', 'events': [], 'answer': '',
                                                 'message': 'Build me one', 'created_at': stamp()})
    return identity


def step(genesis, identity, payload):
    """One operation, recorded the way the harness records every tool call."""
    result = genesis.tool('edit_architecture', payload, identity)
    genesis.event(identity, 'tool_completed', action='edit_architecture', result='', detail=json.dumps(result))
    return result


def worker(genesis, identity):
    step(genesis, identity, {'operation': 'add_node', 'node': {'id': 'input', 'type': 'input', 'label': 'Task input'}})
    step(genesis, identity, {'operation': 'add_node', 'node': {'id': 'worker', 'type': 'agent', 'label': 'Worker'}})
    step(genesis, identity, {'operation': 'add_node', 'node': {'id': 'out', 'type': 'output', 'label': 'Result Output'}})
    step(genesis, identity, {'operation': 'connect', 'from': 'input', 'to': 'worker'})
    step(genesis, identity, {'operation': 'connect', 'from': 'worker', 'to': 'out'})
    step(genesis, identity, {'operation': 'set_prompt', 'node': 'worker', 'text': 'Read the request and act on it.'})


# ---- the build is the turn's own record -------------------------------------------------
def test_the_build_is_read_back_from_the_turn_and_written_nowhere_else(genesis, tmp_path):
    identity = turn(genesis)
    worker(genesis, identity)
    graph, _, _, steps = genesis_build.build(genesis, identity)
    assert steps == 6
    assert [n['id'] for n in graph['nodes']] == ['input', 'worker', 'out']
    assert graph['edges'] == [{'from': 'input', 'to': 'worker'}, {'from': 'worker', 'to': 'out'}]
    assert [n for n in graph['nodes'] if n['id'] == 'worker'][0]['config']['instructions'].startswith('Read the request')
    # FR-056: an operation is not a durable write. Nothing has been saved yet.
    assert not list((tmp_path / 'blueprints').glob('*/draft.json'))


def test_reading_the_build_twice_gives_the_same_graph(genesis):
    # FR-047: the build is a pure function of the operations recorded so far, so a
    # reconnection that re-reads them lands where an uninterrupted delivery would have.
    identity = turn(genesis)
    worker(genesis, identity)
    first, *_ = genesis_build.build(genesis, identity)
    second, *_ = genesis_build.build(genesis, identity)
    assert first == second


def test_one_save_commits_the_whole_build_as_one_revision(genesis, tmp_path):
    identity = turn(genesis)
    worker(genesis, identity)
    saved = genesis.tool('save_architecture', {'name': 'Six operations, one revision'}, identity)
    assert saved['revision'] == 1                       # SC-022: not one per operation
    assert len(saved['graph']['nodes']) == 3
    assert len(list((tmp_path / 'blueprints').glob('*/draft.json'))) == 1


def test_a_save_with_nothing_built_says_so(genesis):
    with pytest.raises(ValueError, match='nothing to save'):
        genesis.tool('save_architecture', {'name': 'Empty'}, turn(genesis))


def test_a_whole_graph_still_saves_the_old_way(genesis):
    graph = {'nodes': [{'id': 'input', 'type': 'input', 'label': 'In', 'x': 0, 'y': 0, 'config': {}}], 'edges': []}
    saved = genesis.tool('save_architecture', {'name': 'Handed over whole', 'graph': graph}, turn(genesis))
    assert saved['revision'] == 1 and len(saved['graph']['nodes']) == 1


def test_a_second_turn_builds_on_the_saved_draft(genesis):
    first = turn(genesis, 't1')
    worker(genesis, first)
    saved = genesis.tool('save_architecture', {'name': 'Carried forward'}, first)
    second = turn(genesis, 't2')
    step(genesis, second, {'operation': 'add_node', 'node': {'id': 'second', 'type': 'agent', 'label': 'Reviewer'},
                           'id': saved['id'], 'revision': saved['revision']})
    graph, identity, revision, _ = genesis_build.build(genesis, second)
    assert identity == saved['id'] and revision == saved['revision']
    assert [n['id'] for n in graph['nodes']] == ['input', 'worker', 'out', 'second']


# ---- validation, per operation ----------------------------------------------------------
def test_an_impossible_operation_is_refused_and_the_build_stands(genesis):
    identity = turn(genesis)
    worker(genesis, identity)
    with pytest.raises(ValueError, match='already has a step'):
        genesis.tool('edit_architecture', {'operation': 'add_node', 'node': {'id': 'worker', 'type': 'agent'}}, identity)
    with pytest.raises(ValueError, match='not in this build'):
        genesis.tool('edit_architecture', {'operation': 'connect', 'from': 'worker', 'to': 'nobody'}, identity)
    graph, _, _, steps = genesis_build.build(genesis, identity)
    assert steps == 6 and len(graph['nodes']) == 3      # FR-057: the rest of the build survives


def test_a_problem_is_reported_against_the_node_that_caused_it(genesis):
    identity = turn(genesis)
    step(genesis, identity, {'operation': 'add_node', 'node': {'id': 'a', 'type': 'agent', 'label': 'A'}})
    step(genesis, identity, {'operation': 'add_node', 'node': {'id': 'b', 'type': 'agent', 'label': 'B'}})
    step(genesis, identity, {'operation': 'connect', 'from': 'a', 'to': 'b'})
    result = step(genesis, identity, {'operation': 'connect', 'from': 'b', 'to': 'a'})
    assert result['problems'] and 'circular' in result['problems'][0]['message'].lower()
    assert result['saved'] is False


def test_an_operation_never_reports_a_save(genesis):
    identity = turn(genesis)
    result = step(genesis, identity, {'operation': 'add_node', 'node': {'id': 'input', 'type': 'input'}})
    assert result['saved'] is False and 'save_architecture' in result['note']
    assert result['nodes'] == 1 and result['steps'] == 1
    # The node comes back as the canvas will hold it, so the editor fills in no defaults of its own.
    assert result['operation']['node']['label'] and result['operation']['node']['x'] == 60


def test_an_unknown_operation_names_the_ones_that_exist(genesis):
    with pytest.raises(ValueError, match='add_node, connect, set_prompt'):
        genesis.tool('edit_architecture', {'operation': 'delete_everything'}, turn(genesis))


def test_building_needs_a_turn_to_build_in(genesis):
    with pytest.raises(ValueError, match='needs a turn'):
        genesis.tool('edit_architecture', {'operation': 'add_node', 'node': {'id': 'a', 'type': 'agent'}}, None)


# ---- a person's unsaved edits outrank a model's commit (FR-049) --------------------------
def test_a_commit_waits_while_an_editor_holds_unsaved_edits(genesis):
    identity = turn(genesis)
    worker(genesis, identity)
    saved = genesis.tool('save_architecture', {'name': 'Held'}, identity)
    second = turn(genesis, 't2')
    step(genesis, second, {'operation': 'add_node', 'node': {'id': 'later', 'type': 'agent', 'label': 'Later'},
                           'id': saved['id'], 'revision': saved['revision']})
    genesis.studio.editors['architecture'] = {'id': saved['id'], 'dirty': True, 'at': time.time()}
    with pytest.raises(ValueError, match='unsaved edits'):
        genesis.tool('save_architecture', {'name': 'Held'}, second)
    with pytest.raises(ValueError, match='unsaved edits'):
        genesis.tool('publish_architecture', {'id': saved['id'], 'revision': saved['revision']}, second)
    # The build is not lost for it: the turn still holds every operation.
    graph, *_ = genesis_build.build(genesis, second)
    assert [n['id'] for n in graph['nodes']][-1] == 'later'
    # And once they save or discard, the same commit goes through.
    genesis.studio.editors['architecture']['dirty'] = False
    assert genesis.tool('save_architecture', {'name': 'Held'}, second)['revision'] == 2


def test_an_editor_that_stopped_reporting_stops_blocking(genesis):
    genesis.studio.editors['architecture'] = {'id': 'x', 'dirty': True,
                                              'at': time.time() - genesis_build.STALE_SECONDS - 1}
    assert genesis_build.open_editor(genesis.studio, 'x') is False


def test_an_editor_on_another_architecture_does_not_block(genesis):
    genesis.studio.editors['architecture'] = {'id': 'other', 'dirty': True, 'at': time.time()}
    assert genesis_build.open_editor(genesis.studio, 'mine') is False


def test_a_brand_new_build_is_not_blocked_by_edits_to_something_else(genesis):
    """No browser can be holding open an architecture that does not exist yet. This used
    to refuse the save with a sentence about an architecture nobody had built, and keep
    refusing for the fifteen minutes the editor record stays fresh."""
    identity = turn(genesis)
    worker(genesis, identity)
    genesis.studio.editors['architecture'] = {'id': 'someone-elses-draft', 'dirty': True, 'at': time.time()}
    assert genesis_build.open_editor(genesis.studio, None) is False
    assert genesis.tool('save_architecture', {'name': 'Fresh'}, identity)['revision'] == 1


# ---- the turn record is the build, so it may not be summarised ---------------------------
def test_a_long_prompt_survives_the_turn_record_and_reaches_the_commit(genesis):
    """The harness cut tool results at DETAIL_CHARS for the turn record. For every other
    tool that shortens a log; for this one it deletes a build step, because the record is
    the only place the build exists."""
    from wb_studio import genesis_harness

    assert 'edit_architecture' in genesis_harness.VERBATIM_RESULT
    identity = turn(genesis)
    worker(genesis, identity)
    long_prompt = 'Follow the policy exactly. ' * 400          # ~10,800 characters
    assert len(long_prompt) > genesis_harness.DETAIL_CHARS
    result = genesis.tool('edit_architecture', {'operation': 'set_prompt', 'node': 'worker',
                                                'text': long_prompt}, identity)
    text = json.dumps(result, ensure_ascii=False, default=str)
    detail = text if 'edit_architecture' in genesis_harness.VERBATIM_RESULT \
        else genesis_harness.summary(text, genesis_harness.DETAIL_CHARS)
    genesis.event(identity, 'tool_completed', action='edit_architecture',
                  result=genesis_harness.summary(text), detail=detail)
    graph, *_ = genesis_build.build(genesis, identity)
    worker_node = next(n for n in graph['nodes'] if n['id'] == 'worker')
    assert worker_node['config']['instructions'] == long_prompt
    saved = genesis.tool('save_architecture', {'name': 'Long'}, identity)
    stored = json.loads((blueprints.paths(genesis.studio, saved['id']) / 'draft.json').read_text(encoding='utf-8'))
    kept = next(n for n in stored['graph']['nodes'] if n['id'] == 'worker')
    assert kept['config']['instructions'] == long_prompt, "the commit reported success without the prompt"


def test_a_step_that_cannot_be_read_back_refuses_the_save_instead_of_dropping_it(genesis):
    """Silently skipping it committed a graph short a step under a normal revision
    receipt, and told the model and the person the build was saved."""
    identity = turn(genesis)
    worker(genesis, identity)
    genesis.event(identity, 'tool_completed', action='edit_architecture', result='',
                  detail='{"operation": {"operation": "set_prompt", "node": "worker", "text": "tru')
    with pytest.raises(ValueError, match='cannot be read back'):
        genesis_build.build(genesis, identity)
    with pytest.raises(ValueError, match='cannot be read back'):
        genesis.tool('save_architecture', {'name': 'Broken'}, identity)


# ---- the dial (FR-058) ------------------------------------------------------------------
def test_editing_ships_on_and_off_refuses(genesis):
    assert genesis.autonomy.read()['edit'] == 'act'
    genesis.autonomy.set({'edit': 'off'})
    with pytest.raises(ValueError, match='Editing dial is off'):
        genesis.tool('edit_architecture', {'operation': 'add_node', 'node': {'id': 'a', 'type': 'agent'}}, turn(genesis))


def test_the_pause_stops_editing_like_everything_else(genesis):
    genesis.autonomy.set({'paused': True})
    with pytest.raises(ValueError, match='paused'):
        genesis.tool('edit_architecture', {'operation': 'add_node', 'node': {'id': 'a', 'type': 'agent'}}, turn(genesis))


def test_no_other_dial_changed_meaning(genesis):
    state = genesis.autonomy.read()
    assert [state[k] for k in ('cards', 'runs', 'initiative', 'engineer')] == ['off'] * 4


# ---- the architecture has an address (D3) ------------------------------------------------
def test_an_architecture_is_a_place_genesis_can_point_at():
    assert check_route('#studio/6022e89f') == '#studio/6022e89f'
    assert check_route('#studio') == '#studio'
    with pytest.raises(ValueError):
        check_route('#studio/../etc')


# ---- the tool the model is given ---------------------------------------------------------
def test_the_tool_offers_the_operations_the_lab_will_apply():
    from wb_studio.genesis_schemas import tool_defs
    defs = {d['name']: d for d in tool_defs()}
    assert defs['edit_architecture']['parameters']['properties']['operation']['enum'] == list(blueprints.OPERATIONS)
    # FR-056: one save commits the build, so a graph is no longer required to save.
    assert defs['save_architecture']['parameters']['required'] == ['name']
