# Builder polish pass (interaction design)

8 September 2026. Front-end only: `wb_studio/static/graph.js`, `graph.css`, `index.html`.
No server change, nothing spent, nothing published or pushed.

## Sources the checklist was drawn from

- Node editors: React Flow (connection radius snapping, `interactionWidth` on edges, keyboard
  focus/Enter/Escape/arrow-move, `nodrag` regions), n8n (hover toolbar, "+" on the output,
  double-click to add, right-click actions), Blender (drag-node-onto-link insertion, Ctrl-drag
  rewire, left-to-right convention), Unreal Blueprints (drag a wire into empty space to get a
  compatible-node menu, Shift+F10 context menus), Maya/Cinema 4D (highlight compatible ports,
  dim incompatible ones while dragging).
- Controls: Vercel Web Interface Guidelines (≥24 px hit targets, `:focus-visible`, keep the
  label during loading, don't pre-disable submit, every drag has a click/keyboard equivalent,
  `touch-action: manipulation`), NN/g error guidelines (error beside the field, jump to it),
  GitLab Pajamas / SaaS destructive-action patterns (undo over confirm for reversible removals,
  name what is removed), Green & Petre cognitive dimensions (viscosity, secondary notation).

## Defects found and fixed

| Defect | Root cause | Fix |
|---|---|---|
| Drop-target highlight never appeared while dragging a wire (visible in the earlier screenshot) | `viewport.setPointerCapture` makes `event.target` the viewport for every pointermove, so `event.target.closest('[data-node]')` was always null | hit-test with `document.elementFromPoint` |
| Dropping a palette step on a short wire did nothing | the hidden "+" button (opacity 0) still intercepted hit-testing at the wire midpoint | hidden affordances get `pointer-events:none`; they are `display:none` during a palette drag; the "+" moved above the port row |
| Clicking empty canvas kept the selection | the pan gesture never distinguished a click from a drag | 4 px threshold; a still pointer clears the selection |
| Every keystroke in the inspector became an undo step | `commit()` on each `input` event | `commitTyping(key)`: one entry per field, new entry after a field change or 1.5 s pause |
| Keyboard focus lost on every re-render | `innerHTML` rebuilds | focused step and focused wire are restored after render |
| Marquee assumed 100 px node height | constant | real element heights |
| Refusals arrived as toasts covering the versions list | `toast()` for validation and readiness refusals | status line beside the canvas; toasts only for server errors |
| Run button disabled with no reason a user can read | `disabled` hides tooltips | `aria-disabled` + title + click explains and scrolls to the versions |

## What the builder does now that it did not before

- Context menus everywhere (`#context-menu`, `role=menu`, arrow keys, type-ahead, Escape returns
  focus): right-click a step, a wire or the canvas; the "…" on a step's hover toolbar; Shift+F10 or
  the Menu key on a focused step; "New from template…" is the same component.
- Quick-add: release a wire on empty canvas, click "+" after a step, double-click the canvas, or use
  "Insert a step here…" on a wire. The new step is placed in free space, connected, selected, and
  its instructions field focused.
- Connections: drag from an output *or* an input port; valid targets highlighted, invalid ones
  dimmed with the refusal as tooltip; the preview snaps to the target port; the status line says
  "Release to connect A → B"; Escape cancels; auto-pan near the viewport edge during connect,
  drag and marquee; wires are focusable and deletable by keyboard; dropping a palette item on a
  wire inserts the step between; the inspector lists a step's connections with remove buttons and
  a "Send output to / Receive from" select for keyboard-only connecting.
- Hit targets: ports 16 px visible, 32 px effective; wire delete handle 28 px; hover toolbar 26×24.
- Validation: each problem is a link that selects the step, centres it and focuses the field that
  fixes it (`aria-invalid` on that field); the badge on the step does the same; Publish stays
  clickable and jumps to the first problem instead of being a mute disabled button.
- Feedback: hover toolbar (duplicate, remove, more) on each step; selected/dragging steps rise
  above their neighbours; Save/Publish/Prepare show "Saving…/Publishing…/Preparing…" with
  `aria-busy`; every removal says "Ctrl+Z restores"; a shortcuts dialog (`?`).
- Templates name their steps (Planner, Worker, Product fields, Product research) so menus,
  problem links and diffs are unambiguous.
- The separate "Prompt tweak" step type is gone (Lucas: instructions belong on the agent step).
  Removed from the palette, templates, quick-add, validation (`blueprints.KINDS`) and the runtime
  (`execution.RUNTIME_KINDS`, the system-prompt inheritance branch). The run-level "Additional
  instructions" in the launcher is unchanged.

## Evidence

`.impeccable/review/verify-builder-3.cjs` (Playwright, headless Edge, 1600×1000 and 390×844):
32 of 32 interaction checks pass, zero page or console errors, no horizontal overflow on mobile.
Checks cover: template menu by keyboard; highlight/dim/snap while connecting; refused drop
creates no edge and cleans up; drop on empty opens quick-add and connects the new step; reverse
drag from an input port; typing 11 characters adds exactly one undo entry; click on empty canvas
clears the selection; node context menu with disabled-with-reason items; problem link focuses the
field; palette drop on a wire inserts between; Shift+F10; `?`; the inspector connection select;
port hit padding; the run refusal in the status line with no toast. Screenshots
`.impeccable/review/builder3-*.png`. `tests/test_studio_app.py` + `test_studio_blueprints.py`:
55 passed.

## Not done

- No minimap (graphs are capped at 80 nodes; fit-to-view covers it).
- No alignment guides beyond the 20 px grid snap.
- The launch dialog was left as it was apart from `aria-describedby` on Start run.
