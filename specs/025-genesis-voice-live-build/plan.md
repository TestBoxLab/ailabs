# Implementation Plan: Genesis voice and live build

**Branch**: `genesis-loop` | **Date**: 11 September 2026 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/025-genesis-voice-live-build/spec.md`

## Summary

User Story 6 and FR-044 to FR-059: Genesis builds the working artifact where a person can
watch it, and the watching costs nothing extra. The approach has one idea behind it —
**the build is the turn's own record** — and everything else follows from it.

Genesis calls `edit_architecture` once per step. The call is recorded the way every tool
call already is, as `tool_started` / `tool_completed` on the turn, and nothing else is
written. The lab reconstructs the graph by replaying those events, so:

- an operation is not a durable write, and a reload before the commit leaves nothing behind
  (FR-056, SC-022);
- delivering the same operation twice cannot double it, because the build is a pure
  function of what the record holds (FR-047);
- no per-turn state lives in the Studio process for two turns to race over.

The open editor is already receiving those events on the SSE turn stream it opened for the
conversation. It applies each one as provisional state. No second connection, no new event
kind, no new route for the build itself.

The commit is the existing `save_architecture`, which now accepts no `graph` and saves what
the turn built — one revision, however many operations it took.

## Technical Context

**Language/Version**: Python 3.13 under `uv`; hand-written ES2020 served as-is (no build step)

**Primary Dependencies**: none added

**Storage**: the turn record under `out/studio/turns/`; drafts under `out/studio/blueprints/`

**Testing**: `pytest` (`tests/test_genesis_build.py`, `tests/test_genesis_stream_contract.py`),
`node tests/browser/suite.cjs` for the rendered page

**Target Platform**: the Studio, local and on Railway

**Constraints**: CSP `style-src 'self'; script-src 'self'` — no inline style, no external
resource; component CSS uses design tokens only (`tests/test_static_csp.py` enforces both)

## Decisions as built

The ten decisions of 11 September stand, with two amended by what the code turned out to
say. Both amendments are in this plan rather than silently in the code.

| # | As proposed | As built |
|---|---|---|
| D3 | Following defaults on; the `show` tool's description is corrected first | Built. The description was wrong in four places, not one — including `PROTOCOL`, the text actually injected into the prompt — and all four are corrected. |
| D4/D5 | The server refuses a commit while an editor holds unsaved edits | Built. The server had no way to know, so the editor reports its own dirty state to `POST /api/studio/editor` on transitions; state not renewed for 15 minutes is a closed tab, not a person mid-sentence. |
| D6/D7 | "One ordinary save commits the operations" | **Amended.** `save_architecture` required `graph`, so this was impossible as written. `graph` is now optional; passing one is unchanged. |
| D8 | Per-operation validation | Built with the lab's own `blueprints.problems(strict=False)`. The strict list, which a half-built graph must fail, stays where it was: the editor's debounced validate, and again at save and publish. |
| D9/D10 | Editing is free, and has its own dial | **Amended.** Editing is not free: an operation only exists inside a turn, which reserves US$ 2.00 before its first request and about US$ 0.31 per request after, against a hard wall of 24 requests. The dial is built and ships on; the cost is the turn's, unchanged. |

`edit` is the one autonomy dial that defaults on, and the comment at
`wb_studio/genesis_autonomy.py:26` says why it is not an exception to the rule that every
dial defaults off: building spends nothing of its own, writes nothing outside the turn, and
cannot publish. Off, Genesis cannot touch an architecture at all — stricter than what
shipped before the dial existed.

## What landed

| Requirement | Where |
|---|---|
| FR-044, FR-047 | `static/genesis.js` `applyBuildEvents` — applied off the existing stream, once per turn and event id |
| FR-045 | `static/graph.js` `provisional`; `graph.css` `.bp-node.provisional` — a dashed rule, not a colour, because the meaning colours belong to results |
| FR-048 | `static/graph.js` `promptFieldIsBusy` / `releaseHeldOperations` — only the field the operation writes to is held; everything else already survives, because `renderInspector(true)` restores value and cursor |
| FR-049 | `wb_studio/genesis_build.py` `refuse_while_editing`; `POST /api/studio/editor` |
| FR-055 | one `commit()` per operation, so the existing Undo discards provisional work |
| FR-056, FR-057 | `wb_studio/genesis_build.py`; `blueprints.apply_operation` |
| FR-058 | `wb_studio/genesis_autonomy.py` `edit`; the control under Settings › Genesis |
| FR-059 | `wb_studio/genesis_show.py` docstring, `PROTOCOL` and receipt; `genesis_schemas.py` |
| D3's address | `#studio/<id>` in `genesis_show.PREFIXES`, both routers, `openStudioItem` |

Two defects were found by building rather than by reading, and are fixed:

- An operation that arrived before the editor finished mounting was dropped silently. The
  library renders its empty state while the drafts are still loading, so this was a real
  one-in-three race, caught by the browser check. Operations now wait and are drained when
  the editor opens.
- A terminal `done` frame discarded any step still buffered from the last animation frame,
  because `closeGenesisStream()` empties the queue. It flushes first now.

## What is not built, and why

- **The 100-node stress case.** `blueprints.problems` refuses anything over 80 nodes or 240
  connections. Raising that cap is a change to what the lab will publish, not a rendering
  question, and it needs its own decision.
- **Motion.** `renderNodes` replaces the canvas wholesale, so there is nothing for a
  transition to animate, and both evidence tools run under `reducedMotion: 'reduce'`.
  Giving nodes identity across renders is the prerequisite and is a separate change.
- **"Workspace" as a name.** It is already `static/workspace.js` and the largest sheet in
  the Studio. The spec's use of the word should be renamed before any code adopts it.
- **The remaining user stories.** Stories 1 to 5 of this spec — voice, the checked
  interface previews, remembering, the track record — are untouched here.

## Constitution check

- **§II, TDD and evidence.** 26 unit assertions and one browser check; the browser check
  delivers the operations by hand, which is what keeps it free of a paid turn.
- **§III, a human approves paid rounds.** Untouched. Nothing here launches anything, and
  `propose_experiment` and the ledger are not on this path.
- **§IV, the methodology does not change through features.** No task, competitor, approval
  rule or price moved.
- **Pre-registration and upstream integrity.** No AutomationBench file is touched.

## GPT-Live-1 connection continuation, 11 September

Lucas selected GPT-Live-1. The additional connection slice uses WebRTC media and
an authenticated server sideband, backed by the existing Genesis tool harness.
It adds `websockets>=15`, same-origin lifecycle routes, a persistent voice control
and structural workspace context shared with typed turns. The explicit GPT-Live
connection is the scoped exception to the earlier no-external-resource constraint;
API keys remain server-side. See [tasks](tasks.md) and the
[implementation evidence](implementation-2026-09-11.md) for verified behavior and
remaining live-service gates. This continuation does not mark the complete voice
truth, memory, source-preview or calibration design implemented.
