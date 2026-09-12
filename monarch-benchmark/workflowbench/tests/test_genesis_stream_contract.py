"""Two invariants of the Genesis turn stream that a browser test would notice late.

Feature 025, decision D3 and the streaming contract. `genesis.js` is hand-written and
served as-is, so the check that a terminal event cannot strand a buffered one, and that
Follow now ships on, lives here rather than in a suite that needs a live turn to run.
"""
import re
from pathlib import Path

GENESIS_JS = Path(__file__).resolve().parents[1] / "wb_studio" / "static" / "genesis.js"


def source():
    return GENESIS_JS.read_text(encoding="utf-8")


def test_done_handler_flushes_before_closing_the_stream():
    # closeGenesisStream() empties genesisQueue, and the settled turn keeps the client's
    # own event list, so closing first drops every step that arrived since the last frame.
    text = re.sub(r"^\s*//.*$", "", source(), flags=re.M)  # comments name both calls
    done = text.index("addEventListener('done'")
    body = text[done:done + 600]
    assert "flush();" in body, "the done handler must flush the queue"
    assert body.index("flush();") < body.index("closeGenesisStream()"), \
        "flush() must run before closeGenesisStream(), or buffered steps are lost"


def test_follow_is_on_unless_this_browser_turned_it_off():
    # Absent means on; only an explicit '0' is off, so an existing browser that never
    # touched the checkbox follows and one that opted out stays opted out.
    body = re.search(r"function followOn\(\)\{(.*?)\}\n", source(), re.S).group(1)
    assert "!=='0'" in body, "followOn() must treat an absent setting as on"
    assert "==='1'" not in body, "an absent setting must not read as off"


def test_startfollow_runs_after_its_own_state_is_declared():
    # followBar() reads followArmed and followBroken; `let` keeps them in the temporal
    # dead zone until their line. Calling startFollow() above the block threw a
    # ReferenceError on every page in the Studio, swallowed only while followOn()'s
    # catch returned false.
    text = source()
    assert text.index("\nlet followArmed") < text.index("\nstartFollow();"), \
        "startFollow() must be called below `let followArmed,followBroken`"


def test_show_never_claims_it_cannot_move_the_screen():
    # The model reasons about its own tool from these sentences. Follow can move the page.
    studio = GENESIS_JS.resolve().parents[1]
    for name in ("genesis_show.py", "genesis_schemas.py"):
        text = (studio / name).read_text(encoding="utf-8")
        assert "moves nobody's screen" not in text
        assert "does NOT move anyone's screen" not in text
    from wb_studio import genesis_show
    assert "moved" not in genesis_show.show(None, {"route": "#budget"})


def test_an_operation_is_applied_once_per_turn_and_event():
    # FR-047: `Last-Event-ID` resumes a dropped connection, but a redelivery must still
    # apply each operation exactly once, and a turn's event ids are its own.
    text = re.sub(r"^\s*//.*$", "", source(), flags=re.M)
    block = text[text.index("function applyBuildEvents"):text.index("function streamGenesis")]
    assert "appliedOperations.has(key)" in block and "turn+'#'+e.id" in block
    assert "e.action!=='edit_architecture'" in block, "only build events are applied"
    assert "applyBuildEvents(id,arrived)" in text, "operations are applied from the stream the page already has"


def test_the_editor_holds_an_operation_that_targets_the_focused_prompt():
    # FR-048: their text is theirs until they leave the field. Everything else survives a
    # re-render because renderInspector(true) restores value and cursor.
    graph = (GENESIS_JS.parent / "graph.js").read_text(encoding="utf-8")
    graph = re.sub(r"^\s*//.*$", "", graph, flags=re.M)
    block = graph[graph.index("function promptFieldIsBusy"):graph.index("function applyOperation")]
    assert "'node-instructions'" in block and "heldOperations.push(value)" in block
    assert "'blur', releaseHeldOperations" in block.replace('"', "'")
    # An operation that arrives before the editor has mounted waits for it rather than
    # being dropped: the library renders its empty state while the drafts still load, and
    # a dropped operation is a build the reader is told about but never sees.
    held = graph[graph.index("window.applyArchitectureOperation = function"):graph.index("function applyOperation")]
    assert "pendingOperations.push(value)" in held and "pendingOperations.length < 200" in held
    assert "pendingOperations = []; for (const v of waiting)" in graph, "and the editor drains them when it opens"
    # FR-045: provisional work is marked, and a save is the only thing that clears it.
    assert "provisional = new Set()" in graph[graph.index("function markSaved"):graph.index("let toldEditorAt")]
    assert "provisional.has(n.id) ? ' provisional' : ''" in graph


def test_follow_guards_are_rearmable_and_fire_once_per_show():
    # {once:true} spent the wheel guard on the first scroll, and "Resume following"
    # then resumed with no guard; announceShow re-navigated on every repaint.
    text = re.sub(r"^\s*//.*$", "", source(), flags=re.M)
    block = text[text.index("function breakFollow"):text.index("let paintedSteps")]
    assert "once:true" not in block.replace(" ", ""), "gesture guards must stand, not fire once"
    assert "!followArmed||" in block, "follow() must refuse when no turn armed it"
    assert re.search(r"followed!==t\.id\+' '\+r\.route", block), "announceShow must follow once per show"
