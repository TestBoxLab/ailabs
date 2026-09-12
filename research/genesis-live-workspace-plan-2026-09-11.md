# Genesis live workspace and streaming interaction plan

## Product direction

Genesis should visibly work in the same workspace Lucas uses. A spoken or written request can open the relevant artifact, assemble its structure, fill its content, validate it, and leave a usable result. Conversation remains concise while the workspace carries the detail. The signature experience is watching a workflow take shape: steps appear in stable positions, connections resolve, prompts fill their actual fields, and each change acquires an explicit saved or validation state.

This expands the [Genesis research roadmap](genesis-harness-review-2026-09-11.md) and feature 025. It is a planning addition, not an implemented frontend or a claim of measured visual quality. The intended mode is **Operate**: Lucas is directing research and engineering, inspecting evidence, and preparing experiments. Visual ambition must help him understand the work and intervene precisely.

Preserve the actual Studio identity in `wb_studio/static/tokens.css`: warm paper and ink, IBM Plex Sans for controls, Newsreader for reading, IBM Plex Mono for machine data, square geometry, hairline rules, and restrained signal red. Retain light and dark themes and semantic result colors. The older root `DESIGN.md` describes different fonts, geometry and green action styling; it is historical evidence, not authority to replace the current tokens. No design-system repair is bundled into this plan.

## Decisions — 11 September 2026 (Lucas)

Taken after reading this plan against the code. The rest of this document is written to them; where an earlier paragraph disagreed, it has been corrected rather than left as an alternative.

| # | Question | Decision |
|---|---|---|
| D1 | Delivery order | Slice A, then slice B, as the table below states. The event and object foundation lands before the showcase. |
| D2 | Showcase object | The architecture blueprint `static/graph.js` already edits — `/api/blueprints` draft, validate, publish, versions and diff. Not the generated workflow artifact, not a Monarch recipe. |
| D3 | Presentation | Genesis opens the artifact for the request, and **Follow ships on by default**. This reverses the off-by-default choice recorded in feature 024 stage S5 (`genesis.js:120–127`). |
| D4 | Same-field conflict | The field Lucas has focus in is soft-locked. Genesis's write to it queues behind him and applies when he leaves it. |
| D5 | Dirty editor | While the open editor holds unsaved edits to a draft, Genesis's commit to that draft is refused with that reason and carded. His unsaved work is never invalidated by a revision bump he did not cause. |
| D6 | Build granularity | Incremental operations — add node, connect, set prompt — not one whole-graph save the reader never sees arriving. |
| D7 | Commit unit | Operations stream to the open editor as events and are applied as provisional state. One ordinary `save_architecture` commits them as a single revision. Operations are not durable before that commit. |
| D8 | Validation | Per operation, server-side, through the existing `/api/blueprints/validate`. |
| D9 | Edit authority | A new autonomy dial of its own, beside reading, cards, runs and engineer. |
| D10 | Dial default | On. An authorized draft edit touches no frozen task, no stored run, no configuration hash and no money. |

## Inspiration and what transfers

The following are primary-source interaction references inspected on 11 September 2026. They establish available patterns, not comparative proof that a product delivers better outcomes. Sources are documentation and indexed official disclosures; no hands-on product comparison or rendered Studio audit was completed.

| Reference | Documented pattern | Application to Genesis | Limit or caution |
|---|---|---|---|
| [n8n AI Workflow Builder](https://docs.n8n.io/advanced-ai/ai-workflow-builder) | Natural-language workflow creation, node selection/placement/configuration, build phases and refinement | Make the workflow the main live artifact, with stage feedback and unfinished configuration exposed in place | A generated graph still requires validation and credentials; creation does not establish execution success |
| [React Flow dynamic layout](https://reactflow.dev/examples/layout/dynamic-layouting) | Placeholder nodes, insertion on edges and animated automatic positioning | Stable provisional nodes and local layout transitions as Genesis adds dependencies | Updated 24 August 2026; this particular example is Pro-licensed and tree-oriented. It is inspiration, not code to copy or evidence that a tree layout fits arbitrary workflow graphs |
| [Claude Artifacts announcement](https://www.anthropic.com/news/artifacts) | A dedicated artifact window beside conversation for iteration | Keep conversation and the working artifact visible together, with persistent selection | Historical 2024 interaction reference; indexed official excerpt available, direct page fetch failed. No current feature-parity claim |
| [Linear agent interaction](https://linear.app/developers/agent-interaction) | Sessions and activity expose working, waiting, error and completion states | A persistent work status connected to concrete objects and recovery actions | Borrow the state vocabulary and legibility, not Linear's visual styling or raw reasoning display |
| [LangChain Agent Chat UI](https://docs.langchain.com/oss/python/langchain/ui) | Tool visualization, interrupts, state forking and generative UI | Rich tool-specific output and inspectable history instead of one long answer bubble | Framework reference; replacing Genesis's harness is unnecessary |
| [AG-UI events](https://docs.ag-ui.com/concepts/events) | Separate run, text, tool, state snapshot/delta and activity events | Use typed event families to drive the conversation, artifact and progress independently | Pin a version if adopted; some documented event families are drafts. Ordering, authorization and durable storage remain application responsibilities |
| [A2UI](https://a2ui.org/) | Agents describe components; the client renders from an approved catalog with its own styling | A Studio component registry for graphs, prompt diffs, evidence tables, plans and result plots | Docs identify v0.9.1 as current and v1.0 as candidate. A catalog limits executable UI generation but does not make data, links or actions automatically trustworthy |
| [AI SDK custom data](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data) | Custom data can accompany a message stream | Stream activity and object updates separately from prose | Indexed official documentation only; direct fetch failed on its markdown content type. This plan does not rely on a specific SDK signature |
| [W3C status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) and [interaction animation](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html) | Programmatically exposed status and a way to disable nonessential interaction motion | Announce meaningful phase changes without moving focus; provide reduced motion and pause-follow controls | Accessibility requirements inform acceptance; compliance is not established by a written plan |

**Synthesis:** combine n8n's visible construction, the artifact/conversation split, and typed streaming state. Let Genesis choose the appropriate Studio view through a constrained presentation contract. The visual result comes from precise choreography of real changes, not from allowing a model to invent arbitrary markup or replaying a theatrical animation after work has already finished.

## Existing implementation to extend

Source inspection shows an existing foundation:

- `static/genesis.js:202–239` already opens an SSE stream, batches arrivals with animation frames, supplies an event cursor, reports reconnecting, and supports pausing visible updates. This is not a polling-to-streaming rewrite. Extend its event payloads and rendering contract; verify terminal-event flushing and catch-up behavior before depending on them.
- `static/graph.js` already owns architecture nodes, connections, prompts/configuration, validation, revision state and undo history, over `/api/blueprints` — `draft`, `validate`, `publish`, `versions/<n>/diff`. Extend this editor's data model and interaction rules rather than rendering a second, incompatible workflow.
- `static/app.js` already projects execution events into workflow and model nodes. Use the same distinction between an editable definition and a recorded execution.
- **The mutation path already exists.** `genesis_schemas.py` exposes `save_architecture` and `publish_architecture`, which write the same blueprint drafts `graph.js` edits and carry a `revision`. `blueprints.py:132` already refuses a save whose revision has moved: *"This draft changed in another editor. Reload it before saving."* Slice B is not building a mutation layer; it is making an existing save visible while it happens, and adding the incremental operations of D6 in front of it.
- **Contextual presentation already exists, and is already opinionated.** `genesis.js:120–186` implements Follow: a checkbox, a status bar, arm-on-turn, break on any wheel/key/pointer/touch gesture, break on Escape, and a resume control. `announceShow` routes a `show` result through it. Two corrections follow from D3: the default in `followOn()` flips to on, and the WCAG 3.2.5 rationale written at `genesis.js:121–124` must be rewritten — the toggle still satisfies 3.2.5 as an available mechanism, but the comment currently argues for the opposite default. The `show` tool description at `genesis_schemas.py:101` says it "moves nobody's screen"; that is false today and must be corrected, or the model is reasoning about its own tool from a wrong premise.
- Feature 025 already describes a checked, private preview of Studio source changes. A live graph edit is an application-data operation; changing the Studio's renderer is a separate engineering operation. Both need rich presentation, but they have different commit and acceptance boundaries.

A workflow may mean an architecture, a generated executable workflow artifact, or a Monarch recipe. Per D2 the showcase object is the architecture blueprint, and nothing here extends to the other two. Every view and event must still carry its object kind and revision, so that a later surface cannot inherit this one's contract by accident. Do not silently translate the experimental Studio workflow runtime into a Monarch recipe or imply they are interchangeable.

## The workspace composition

Keep the navigation and page identity stable. Within the working area, use three coordinated regions, with the artifact dominant:

1. **Conversation:** short written turns, the warm voice controls, current request, and a compact activity summary. Routine activity collapses after completion, retaining an expandable evidence trail.
2. **Working artifact:** the graph, prompt, source table, experiment comparison or private interface preview appropriate to the request. A small tab strip retains related artifacts and their revisions.
3. **Inspector:** the selected node, field, evidence record or change. It opens on demand and includes exact content, validation and provenance.

At narrower widths, collapse the inspector first and then switch conversation/artifact with persistent tabs. Keep current work and stop controls visible. Do not shrink a three-column desktop layout until prompts become unreadable. Preserve keyboard graph navigation and a structured list alternative for touch and assistive technology.

Selection is shared explicitly: route, artifact ID/type/revision, selected nodes or field, and unsaved local changes accompany an authorized request. “Connect this to the reviewer” resolves against the selected graph and its current revision. If two possible reviewers exist, highlight them and request clarification before changing an edge.

When Lucas asks Genesis to build or show something, opening its artifact is part of the request. Per D3, “Follow Genesis” ships **on**: the camera tracks relevant changes without being asked each time. The existing guards stay exactly as they are and are what make that default defensible — follow arms only for the duration of a turn, any wheel, key, pointer or touch gesture breaks it for the rest of that turn, Escape breaks it, the status bar says so, and a control resumes it. Follow moves the scroll position, never focus. A hidden tab and a surface the reader is not on both degrade to the link. Background work may add an activity indicator but takes the camera only under the same rules.

## Signature workflow sequence

Illustrative request: “Create an experimental research workflow, connect the researcher to a reviewer, and insert concise prompts.” Exact node types and permitted actions come from the object's catalog; the example is not a new runtime schema.

| Moment | What Lucas sees | What makes it truthful |
|---|---|---|
| Request accepted | Conversation acknowledges briefly; artifact header names the target and shows “Preparing draft” | Receipt contains the request and target revision |
| Structure begins | Provisional nodes arrive at reserved positions with readable labels and a drafting indicator | A node is provisional until a complete, schema-valid operation exists; partial arguments cannot execute |
| Dependencies form | Connections draw between actual ports; affected nearby nodes settle into place | Endpoints and compatibility are validated; structural edges do not imply data has run through them |
| Prompts arrive | The selected node's real prompt field fills in coherent chunks; changed sections remain marked | Partial text is provisional state in the editor and nothing else; no revision exists yet. A field Lucas has focus in is soft-locked (D4) and the operation queues behind him |
| Validation runs | Local node/edge problems appear in place; the inspector explains the next repair | Each operation posts the in-flight graph to `/api/blueprints/validate` (D8). Validation status comes from that executed check, not the model's narration |
| Draft is saved | Provisional marks settle; header names the saved revision; concise change summary links to affected nodes | One `save_architecture` commits the whole build as a single revision (D7). Receipt identifies the persisted object and revision |
| Refinement | “Make the reviewer stricter” produces a field diff without rebuilding the entire graph | The server's existing revision check is the backstop; while the editor is dirty the commit is refused and carded (D5), so a concurrent human edit is never invalidated. Undo targets one coherent change |
| Execution, if authorized | Nodes separately show queued, running, completed, failed or skipped, with recorded outputs | Saving or previewing never launches a run; execution uses existing budget and authorization controls |

The focal moment is the transition from a readable emerging graph to an inspectable, saved artifact. Prompt text should land in the editor field Lucas will actually use, not only in chat. A failure should remain equally tangible: the specific edge, missing field or unavailable operation is visible and recoverable.

**What D7 costs, stated plainly.** Between the first operation and the commit, the build exists in one browser and in the turn's event log. Reloading the page mid-build loses the uncommitted work; the turn's events remain, so the record of what Genesis did survives, but the draft does not. This is the price of not introducing server-side pending state, and it is the correct price here because the build is seconds long and the operations are cheap to repeat. If a build ever becomes long enough that losing it matters, the answer is a server-side buffer, not a rescue path bolted onto this one.

## Loading and activity states

Use separate state dimensions rather than one universal spinner. A task can be running while a tool waits, the network reconnects, and the selected graph already has saved nodes.

| State | Presentation and action |
|---|---|
| Queued | Show what is queued and any known reason; cancel remains available |
| Reading/searching | Show actual source/task labels and completed counts when known; unknown totals remain indeterminate |
| Drafting | Local placeholders or draft text inside the eventual artifact; no invented output or percent complete |
| Applying | Mark the affected objects; unrelated views remain usable |
| Validating | Show the check being run and its eventual result; distinguish structural validity from measured performance |
| Waiting for input or existing approval | Name the exact missing decision and the concrete object it affects |
| Reconnecting | Preserve the last confirmed view, show its last update, and reconcile on recovery |
| Partial failure | Keep successful receipts and unfinished work; offer retry of the failed portion when safe |
| Cancelling | Show that cancellation was requested and any operation still in flight |
| Cancelled/completed | Show the confirmed outcome, retained changes, unresolved work and relevant next action |

Skeletons belong only where content is genuinely pending. Avoid blanking already useful data during refresh. Known totals can produce a fraction; estimates must be labeled as estimates. A heartbeat means the connection is alive, not that a tool is advancing. Do not expose hidden model reasoning as a progress feed: surface deliberate summaries, tool activity and evidence.

Pausing the view freezes presentation while events continue to be retained. Muting or interrupting speech stops audio. Stopping a research job requests execution cancellation. Breaking Follow stops the camera and stops nothing else. Undoing before the commit discards provisional state; undoing after it writes a new revision. These controls must be separately labeled and reconciled; none promises to reverse an external side effect.

## Motion and visual craft

Reserve motion for object continuity and meaningful changes. Newly materialized nodes reveal within the existing grid; new edges trace once; a completed edit gets a short local emphasis that settles into the normal surface. Animate positions from their previous coordinates after a coherent change batch. Preserve user-positioned nodes and avoid global re-layout on every streamed character.

Prompts stream in small readable chunks with an optional follow mode, preserving text selection and the caret. The graph need not jump merely because a long prompt becomes longer. A live execution may show a directional pulse on the active edge, but authoring a connection uses a different treatment. Completed graphs are still.

Proposed starting ranges, to tune with rendered evidence: 120–180 ms for local emphasis and 180–280 ms for position changes. These are design targets, not measured thresholds or imposed delays. Do not slow down real results to finish an animation. Reduced-motion mode removes travel and edge tracing while preserving instant state changes and textual cues. Announce phases through a restrained live region, not every token or node update.

The aesthetic remains architectural and precise: measured spacing, sharp type hierarchy, rich content and responsive motion. Avoid glow, confetti, constant shimmer, bouncing nodes, or a new ornamental agent avatar competing with the work.

## Streaming and mutation contract

Extend the existing per-turn SSE path and nothing else. Audio keeps its own realtime transport; visual updates do not require a second competing state channel. The stream at `/api/genesis/turns/<id>/events?after=<seen>` already carries ordered, identified `step` events and a terminal `done`, already batches arrivals into one flush per animation frame, already resumes through `Last-Event-ID`, already reports reconnecting, and already supports pausing the visible updates while events keep arriving.

D6 and D7 make the contract small. An operation is one more kind of `step` event: its target object and kind, the operation itself (add node, connect, set prompt), and the validation result the server computed for it. There is no second write channel, no pending-state protocol and no transaction manager, because an operation is not a write — it is a description of a change the editor applies to state it already holds. The only write is the `save_architecture` that commits, and that call already exists and already carries its expected revision.

What this deletes from an earlier draft of this plan, deliberately: the confirmed/pending overlay, per-command idempotency keys, compensating-revision undo, and gap detection with authoritative snapshot refetch. Each was solving a problem that a durable per-operation write would have created. Ordering comes from SSE. Resume comes from the cursor. Duplicate suppression is the editor ignoring an event id it has already applied — one comparison, not a protocol. Undo before the commit is `graph.js`'s existing client history; after the commit it is a new saved revision, with the existing `versions/<n>/diff` as the record.

What survives unchanged: a terminal event must not strand operations buffered in the current animation frame, closing the stream must flush them, and an unknown or stale event produces a bounded fallback rather than arbitrary DOM mutation. Do not put secrets or inaccessible benchmark records into an event because a renderer could display them.

A component registry maps trusted surface types to existing styled components: workflow graph, prompt editor/diff, research sources, hypothesis, experiment plan, measured chart, change preview and receipt. Genesis requests a surface and supplies typed data; the server and renderer enforce schema, capabilities and allowed actions. Adopt an AG-UI/A2UI adapter only if interoperability earns its cost. A full React migration or generic UI interpreter is not a prerequisite.

When Genesis needs a genuinely new frontend capability, use feature 025's isolated engineering and checked preview path. Ordinary streamed data never gains permission to inject scripts, rewrite CSS or bypass that path.

## Breadth beyond workflows

| Genesis capability | Appropriate live surface | Durable completion evidence |
|---|---|---|
| Literature research | Source rows arrive with retrieval state; claims link to passages | Saved sources and cited synthesis |
| Hypothesis formation | Editable hypothesis, assumptions and proposed test | Versioned proposal and review |
| Experiment preparation | Configuration diff, predicted outcome, cost/reservation state | Validated plan; no implied launch |
| Experiment execution | Runner lanes and node activity, progressively available measured results | Stored trajectories, final state and billing |
| Benchmark analysis | Chart/table updates from computed records with missing values explicit | Reproducible figures and evidence links |
| Memory correction | Old/new entry and provenance | Recorded adoption under current policy |
| Engineering | Changed files, checks and private preview | Checked diff and acceptance record |
| Workflow/architecture editing | Nodes, edges, prompts and inline diagnostics | Persisted object revision |

Every newly enabled Genesis mutation should declare its visual target, pending state, acknowledgment, error recovery and audit link as part of its capability contract. Unknown capabilities can fall back to a concise receipt and an artifact link until a dedicated renderer exists. This makes the frontend expandable without promising that every future tool will magically acquire a rich editor.

## Delivery sequence and acceptance

This work is folded into the main roadmap before the spoken-colleague milestone: voice and text must operate the same live workspace.

| Slice | Deliverable | Evidence needed |
|---|---|---|
| A. Event and object foundation | The operation event kind on the existing turn stream, its server-side validation call, the new autonomy dial, and the two corrections D3 forces in `genesis.js` and `genesis_schemas.py` | Replay/reconnect tests; a resumed stream applies each operation exactly once; the visible graph after a replay equals the graph after uninterrupted delivery |
| B. Workflow showcase | `graph.js` applies node, edge and prompt operations as provisional state; stable layout; the field soft-lock, the dirty-editor block, and one commit | One request visibly creates, connects, fills and saves a valid development blueprint; reload reproduces the saved revision |
| C. Shared artifact workspace | Conversation/artifact/inspector coordination, context selection, Follow behaviour at its new default and rich loading states | Lucas can inspect and edit while background work continues; a gesture breaks Follow and it stays broken for the turn |
| D. Wider R&D surfaces | Research, plans, measurements, memory and checked interface previews | Correct surface and state for each enabled capability; original evidence remains accessible |
| E. Voice integration and craft | Voice targets the same selected objects; interruption, reduced motion, performance and accessibility | Live scripted sessions, rendered desktop/narrow-width checks, keyboard and screen-reader checks |

Use deterministic fixture streams first; fixtures must be visibly marked and cannot populate real research records. Proposed initial stress cases: 5/25/100-node graphs, long prompts, 1,000 retained activity events, and bursts of 50 events before a frame. Set a rendering budget after measuring the actual supported device baseline. Optimize incremental updates, viewport rendering and bounded history before introducing a new framework.

Acceptance must include: disconnect during prompt insertion; reconnect after the commit; completion arriving before the next animation frame; duplicate delivery across a resume boundary; a commit refused because the revision moved; **an operation arriving for a field Lucas has focus in** (D4 — it queues, his text survives, it applies on blur); **a commit attempted while the editor is dirty** (D5 — refused with that reason, carded, his edits untouched); **a reload mid-build** (the uncommitted draft is gone, the turn's events still show what happened, and nothing claims a save that did not occur); cancellation after a completed write; failed validation on one operation while others succeed; an unknown operation kind; reduced motion; Follow broken by a gesture and resumed; and a long-running job while the person reads older content. No success indicator may be produced solely by assistant prose.

The first demonstration should leave a saved, inspectable development workflow and an exact change record. It must not alter frozen task sets, historical configurations or results, apply a Monarch change, or initiate paid execution. Existing authorization governs those actions; this plan adds no blanket approval requirement for ordinary authorized draft edits.

## Planning integration and limits

Feature 025 remains the planning home. The visual workspace is an expansion of its live-build story, with an additional story for visible application-data editing. Its restriction on *agent-authored server-code previews* does not prohibit implementing the reviewed backend event support needed by this feature. Static-only preview scope and publication decisions remain as documented.

Source updates and product versions should be checked again at implementation kickoff. Visual inspiration here is grounded in official descriptions and source code, not an independently scored usability study. The native browser inspection tool was unavailable during this research, so the plan makes no claim that animations were personally auditioned. The implementation must obtain fresh rendered evidence before acceptance.

