# AI Labs Studio — implementation plan, 9 September 2026

Status: plan for approval. It turns the three documents written today into
sequenced work: the UI/UX review (`AI-LABS-UIUX-REVIEW-2026-09-09.md`), the
design direction (`AI-LABS-STUDIO-DESIGN-DIRECTION-2026-09-09.md`) and the
benchmark landscape (`AI-LABS-BENCHMARK-LANDSCAPE-2026-09-09.md`). It also
absorbs the product vision from the Astra session of 8 and 9 September:
Genesis as a scientist with a research library and a hypothesis board, live
workstreams you can watch, plug-and-play components, a durable runtime, and
honest comparisons.

Each phase becomes one Spec Kit feature (012 to 018). Per the constitution,
this plan is the brainstorm output; `/speckit-specify` writes each spec, then
plan and tasks, then Superpowers executes with tests. The methodology in
`PLAN.md` §1 does not change anywhere in this plan.

## 1. Where the tree stands today

Working copy, branch `007-benchmark-foundations`, nothing pushed. Counts are
from this morning.

| Area | State | Evidence |
|---|---|---|
| Runs table, filters, expand, row click opens the run | Done | `workspace.js`; browser-verified today |
| Result side panel instead of modal | Done today | `workspace.css`, `workspace.js` |
| Copy slop pass, subtitles, wizard headings | Done today | 48 edits, `AI-LABS-UIUX-REVIEW` |
| Leaderboard: full 50-task runs only, server-pinned eligibility | Done | `leaderboard.py`, `test_studio_leaderboard.py` |
| Matched Bare pairing by model and thinking, server-derived | Done | `comparison_runner`, `matching_bare_ids` |
| Pause, Resume, Cancel with durable flag and worker gate | Done | `test_studio_pause.py`, `AI-LABS-RUN-CONTROLS` |
| Parallel failure cancels siblings; terminal runs never replay | Done | `test_studio_resilience.py` |
| Components registry (brain, action builder, judge) and runtime limits | Done | `components.py`, `runtime.py` |
| Product graph editor: source-only plugin, before/after diffs, research log | Done | `pg.js`, `AI-LABS-NODE-EDITOR` |
| Studio libraries list-first, name on first save, rename | Done | `studio-library.js` |
| Genesis: Codex bridge, cross-provider routing, board, approvals, chat | Done offline | `genesis*.py`, 243 tests, `AI-LABS-GENESIS-IMPLEMENTATION` |
| Genesis live provider acceptance | Pending | needs a US$ 4 synthetic check approved by Lucas; US$ 0.66 held |
| Live workstream cards with streaming and knowledge pulse | First version | `observatory.js` |
| Failure buckets with evidence links | First version | `failure_analysis.py` |
| Automatic narrative per finished run | Not started | decision taken today |
| Reports layer, chart kit, design tokens, research library | Not started | this plan |

Front-end weight and debt, measured today:

| Measure | Value |
|---|---:|
| CSS across six files | 140 KB |
| Hard-coded hex colours in CSS | 298 |
| `!important` rules | 30 |
| Inline-style workarounds for the CSP (`data-chart-style`) | 8 |
| JavaScript across eight files | 268 KB |
| Fonts | Segoe UI and Consolas, Windows only; other systems fall back |
| Ad hoc browser check scripts under `artifacts/` | 17 |
| Test files | 78 |

The colour and `!important` counts are the cost of six stylesheets layered
by load order, each overriding the previous. The design system phase exists
to end that.

## 2. Fixed constraints

- **Methodology is fixed.** Same request text for every competitor; nothing
  grades itself; pass means expected result present, nothing else changed,
  normal finish; frozen task hashes; paired comparisons only on identical
  sets with error bars; every figure carries its source line; cost complete
  and versioned; audience rules are code; config hash per run. Features add
  inputs and views, never rules.
- **Spending gate.** US$ 300 per week; Lucas approves paid rounds; every paid
  request reserved then settled. The automatic narrative is a paid request
  and obeys this.
- **No build step, strict CSP.** `script-src 'self'; style-src 'self'`. No
  CDN, no inline `style=""`, no injected `<style>`. Everything vendored under
  `wb_studio/static/vendor/` with its licence file.
- **Public by default.** Reports render for the public audience; the internal
  view is a filter, not a different report.
- **Square, light and dark from tokens, no slop.** Recorded preferences from
  Lucas: square geometry, technical and scientific character, CLI vibes,
  green means better than Bare and red means worse, one name per concept,
  no three-item subtitles, no explanatory paragraph under headings.

## 3. Design system

### 3.1 Candidates and verdicts

| Candidate | Licence | No build | CSP-safe | Square | Dark | Verdict |
|---|---|---|---|---|---|---|
| Radix Colors | MIT | Yes, plain CSS files | Yes | n/a | `.dark` class, same variable names | **Adopt** for colour |
| IBM Plex Sans, Mono, Serif | OFL 1.1 | Yes, woff2 | Yes | n/a | n/a | **Adopt** for type |
| Lucide icons | ISC (Feather parts MIT) | Yes, SVG sprite | Yes | Joins can be squared in CSS | n/a | **Adopt** for icons |
| Tufte CSS | MIT | Yes | Yes | n/a | Needs tokens | **Borrow** the sidenote and figure rules for reports |
| IBM Carbon | Apache 2.0 | Web Components via bundle | Shadow DOM styles are allowed | Yes, by principle | Yes | **Reference only**: patterns for dense tables and square controls; the bundle is heavy and reads as IBM |
| Vercel Geist fonts | OFL 1.1 | Yes | Yes | n/a | n/a | Runner-up for type; reads as "made with Geist" |
| Basecoat UI | MIT | Compiled CSS | Yes if vendored | Radius variable | `[data-theme=dark]` | Decline: utility-class markup and a shadcn look we would fight |
| Open Props UI | MIT | Yes | Yes | Tokens | `light-dark()` | Decline: a second opinion on every component |
| Terminal UI kits (scanlines, CRT) | Various | Yes | Yes | Yes | Dark only | Decline: costume, not character |

### 3.2 The composition

A small system assembled from primitives, owned by us, in four files:

1. `vendor/radix-colors/` — `sage.css`, `sage-dark.css`, `green.css`,
   `green-dark.css`, `red.css`, `red-dark.css`, `amber.css`,
   `amber-dark.css`, plus the family scales listed below. About 20 KB.
2. `vendor/plex/` — Plex Sans 400/500/600, Plex Mono 400/500, Plex Serif
   400/400i/600, latin subsets, woff2. About 250 KB, loaded with
   `font-display: swap`.
3. `vendor/lucide/sprite.svg` — only the icons we use, roughly thirty,
   with `stroke-linejoin: miter; stroke-linecap: square` set in CSS so the
   icons share the square geometry.
4. `THIRD_PARTY_LICENSES.md` at the repo root listing all three.

Radix Colors give us the discipline the current CSS lacks: a 12-step scale
where steps 1 and 2 are backgrounds, 3 to 5 component states, 6 to 8
borders, 9 and 10 solid fills, 11 and 12 text, with text steps guaranteed to
meet contrast on the scale's own background. Dark mode is the same variable
names under a `.dark` class, so component CSS never branches on theme. Sage
keeps the warm ivory-and-ink character the Studio already has. Green stays
the single accent and keeps its meaning of "better".

Plex is one family with three voices: Sans for the tool, Mono for numbers,
identifiers and hashes with tabular figures, Serif for report prose. It has
a laboratory character without imitating a vendor.

### 3.3 Token sheet

`static/tokens.css` maps Radix steps to semantic names. Component CSS uses
only these names.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | sage-1 | sage-1 | page |
| `--bg-2` | sage-2 | sage-2 | panels, table heads |
| `--surface` | white | sage-3 | cards, dialogs, inputs |
| `--surface-2` | sage-3 | sage-4 | hover, nested cards |
| `--line` | sage-6 | sage-6 | hairlines |
| `--line-strong` | sage-8 | sage-8 | focus, active borders |
| `--ink` | sage-12 | sage-12 | text |
| `--muted` | sage-11 | sage-11 | secondary text |
| `--accent` | green-9 | green-9 | primary action, "better" |
| `--accent-text` | green-11 | green-11 | accent text on bg |
| `--fail` | red-9 / red-11 | same | failed, "worse" |
| `--warn` | amber-9 / amber-11 | same | pausing, caveats |
| `--radius` | 0 | 0 | everything |
| `--space-1..8` | 4, 8, 12, 16, 24, 32, 48, 64 px | same | spacing |
| `--text-1..7` | 12, 13, 14, 16, 20, 24, 32 px | same | type scale |
| `--font-ui`, `--font-mono`, `--font-prose` | Plex Sans, Mono, Serif | same | type |

Four surface levels exist in both themes, which is the guardrail that makes
a dark theme read as designed rather than inverted.

Model families get their own hue, and none of them may be green or red:

| Family | Radix scale | Note |
|---|---|---|
| Claude | orange | replaces the current rust |
| GPT | indigo | replaces the current green, which collided with "better" |
| Gemini | blue | unchanged |
| Kimi | plum | unchanged in spirit |
| GLM | brown | unchanged |
| Monarch | teal | the product under test |
| Bare and scripted controls | gray | baselines are neutral |

Charts use the same family scales for series, and the dataviz reference
palette for categories that are not models.

### 3.4 Component sheet and layering

`static/ui.css` replaces the shared parts of `style.css`, `workspace.css`,
`genesis.css`, `analytics.css` and `studio-library.css`: buttons, inputs,
selects, checkboxes, tables, tabs, dialogs, badges, toasts, panels, the top
bar, page headings, empty states, the side panel. View-specific rules stay
in their files but only use tokens. The files are ordered with CSS
`@layer tokens, base, components, views` so specificity stops depending on
load order and the 30 `!important` rules go away. The global
`*{border-radius:0!important}` hack becomes `--radius: 0`.

Personality moves, all cheap:

- Metadata lines in Plex Mono, small, uppercase with letter-spacing, the
  way a lab notebook labels a sample: `RUN 154ecb · 10 TASKS · 2 SETUPS`.
- Warp-style blocks for attempts and workstreams: a hairline frame, a mono
  header strip, the body below. One shape for every unit of work.
- Numbers always tabular, always mono, always right-aligned in tables.
- The top bar in ink with the brand in Plex Sans 600 and letter-spacing
  tightened; one accent button.
- Focus rings as a 2 px ink outline offset 2 px, never a glow.
- Motion only for observed events: the knowledge pulse, the live dot, the
  streaming cursor. Reduced motion collapses each to a state change.

### 3.5 Report reading layer

`static/report.css`, prose in Plex Serif at 17 px on a 68-character
measure, figures full-width with captions, sidenotes in the right margin
above 1100 px and inline below, borrowed from Tufte CSS with our tokens.
Print stylesheet included, since the official round report is also a file.

## 4. Phases

Estimates assume one engineer with Claude or Codex, and Carlos or Lucas
reviewing. Phases 1 and 2 can run in parallel. Everything else is sequential
on them.

### Phase 0 — Stabilise (feature: none, 2 days)

Goal: a clean floor before the design system lands.

- Fix the ghost page height under the run view and make the New run wizard
  a route instead of a non-modal `<dialog>`, with Escape and a Cancel
  action.
- Show the Bare warning only when Bare is checked.
- One vocabulary: **setup** for the thing compared, **track** for the kind
  of run. Sweep every label in HTML and JS; keep code identifiers.
- Consolidate the 17 ad hoc Playwright scripts into `tests/browser/` with
  one runner and one fixture server, so browser checks run from one
  command. Keep the offline control-check server as the fixture.
- Add `tests/test_static_csp.py`: fails if any static file contains
  `style="` or a `<style>` tag, or references an external URL.
- Add `THIRD_PARTY_LICENSES.md`.
- Decide the live provider acceptance: Lucas approves the US$ 4 synthetic
  check across GPT, Claude, Gemini and Kimi, or defers it. Reconcile the
  US$ 0.66 held from the Gemini probes against provider usage.

Acceptance: browser suite green from one command; CSP test green; no
`readableRunConfig` race under a 700 ms script delay; vocabulary grep finds
no "approach", "runner" or "purpose" in user-facing strings.

### Phase 1 — Design system (feature 012, 3 days)

Goal: every screen draws from one token sheet in both themes.

- Vendor Radix Colors, Plex and the Lucide sprite; write `tokens.css`,
  `ui.css`, `report.css`; introduce `@layer`.
- Replace the 298 hard-coded colours with tokens, file by file, verifying
  each view in light and dark with the browser suite.
- Retire `style.css` overrides that `ui.css` now owns; delete the
  `!important` rules.
- Family colours applied to the chat picker, workstream headers, chart
  series and the results table.
- Icons through the sprite; remove the inline SVG paths from `index.html`
  and the JS templates.

Acceptance: zero hex colours outside `tokens.css` and the vendor folder;
zero `!important`; both themes pass a contrast check on text tokens; fonts
served locally; a screenshot set of every view in both themes committed
under `tests/browser/snapshots/` for review, not for pixel diffing.

### Phase 2 — Measures and chart kit (feature 013, 4 days)

Goal: the numbers the reports need, computed once on the server, and ten
charts drawn one way.

Backend, `wb_studio/measures.py`, pure functions over stored results and
events, with fixture tests:

| Measure | Definition | Source |
|---|---|---|
| Pass rate with 95 % Wilson interval | passed over recorded attempts | results |
| pass^k | share of tasks where all k repetitions passed, for k run | results by repetition |
| Objective share | checks passed over checks defined, per attempt, averaged | checks |
| Violations per attempt | unexpected changes count over attempts | unexpected_changes |
| False completion | final message claims done and verdict failed | output, verdict |
| Overlap | Jaccard of solved task sets per competitor pair | task matrix |
| Turns and tool calls per attempt | from events | events |
| Paired delta | per-task pass difference vs baseline on identical sets, with a sign test | results |
| Cost per attempt and per pass | from settled cost, unknown stays unknown | ledger receipts |

Chart kit, `static/charts.js`, SVG built by DOM APIs, styled by CSS classes
only (which retires the `data-chart-style` workaround), scales and ticks
from vendored `d3-scale` and `d3-array` (about 40 KB together, ISC):

1. Dot-and-whisker pass rate per competitor with ceiling and floor lines.
2. Paired table with green and red deltas, ties neutral.
3. Task matrix and consistency grid (tasks × competitors × repetitions).
4. Cost vs pass rate, log cost axis, Pareto line, thinking levels connected.
5. Failure categories with counts and denominators.
6. Time-to-finish strips per competitor.
7. Token waterfall per competitor: uncached input, cache writes, cache
   reads, output.
8. Trend per Monarch release over rounds.
9. Trace timeline per attempt, tool calls by node over time.
10. Architecture figure: the existing canvas rendered read-only with
    per-node cost and time badges.

Every chart takes the same options (title as a claim, source line, series
with family colours) and renders the same axes.

Acceptance: measures tested against three fixture runs including one with
repetitions and one with unknown billing; each chart has a fixture page in
`tests/browser/` rendered in both themes; the Budget charts move onto the
kit.

### Phase 3 — Reports (feature 014, 5 days)

Goal: Reports become the front door and read like a release post.

- Routes: `#reports`, `#report/<run>`, `#round/<task-set>`.
- Run report in eight sections: verdict with grade (Improvement,
  Regression, Tradeoff, Tie, Not comparable), three to five findings with
  one number and one evidence link each, hero figure, paired table, where
  it failed, what it cost, caveats, method.
- Round report for several runs on one frozen set: paired table across
  competitors, matrix, trend, and a Standings section that absorbs the
  Leaderboard page.
- Caveat generator, `wb_studio/caveats.py`: sentences from data only. Fork
  version and the public-set note on every public report; unrecorded
  attempts; mismatched thinking; missing Bare; price table version; config
  hash; whether repetitions were run.
- Automatic narrative: on the `finished` event the Studio reserves an
  analysis request in the ledger with a per-run ceiling from the plan
  (default US$ 0.50), runs the existing analysis, fills only the prose
  slots, and links every claim to an event. A run the ledger cannot cover
  shows "Analysis pending" with the shortfall. No manual button.
- Audience: the public rules from `audiences.yaml` filter competitors and
  prose; an internal toggle for Carlos and Lucas shows the rest with a
  visible "internal" mark.
- Export: the report page prints to PDF cleanly and can be saved as a
  single HTML file, which closes feature 006's intent.

Acceptance: a report for `Product graph e2e` reads verdict-first with no
repeated numbers; a claim without evidence renders as Unknown; the public
view hides a lab competitor in a fixture run; the ledger shows the analysis
reservation and settlement; Back and reload restore any report route.

### Phase 4 — Evidence and live views (feature 015, 4 days)

Goal: the run page investigates, the live page impresses without lying.

- Side panel tabs: Output, Checks, Trace, Timeline. Checks show expected
  versus observed with the record and field. Timeline is chart 9.
- Architecture figure above the trace with the executing node lit during
  live runs.
- Workstream blocks: one per active attempt, header strip in mono with
  competitor and task, streamed output body, the knowledge pulse once on
  delivery, the live cursor, progress as `3 / 10`. Finished blocks collapse
  to their verdict line. Reduced motion respected.
- Runs table gains turns and violations columns; Results table header reads
  "Actions taken".
- Leaderboard fairness completion: excluded runs listed with the reason;
  wins, losses, ties and unique tasks per pairing; task-aware uncertainty
  when repetitions exist.
- Settings: capacity and Monarch Enterprise stay; installed components and
  provider limits move under Advanced.
- Empty states with one action each: Reports, Runs, Genesis, Studio.
- Report-layer artifacts: the `<object>` placeholder from `snapshot.py`
  rendered as the record, empty check recipients fixed at the source, event
  links labelled by what they show.

Acceptance: an operator reaches the failing check and its event in two
clicks from the Runs table; the live fixture shows streaming, pulse and
collapse without page errors; no motion under reduced-motion.

### Phase 5 — Genesis research library and hypotheses (feature 016, 5 days)

Goal: Genesis reads the field, remembers what it read, and keeps an honest
record of what worked.

- Research library view under Genesis: a list with publication date,
  discovery date, authors, source type, topic and status. Status is only
  Saved or Analyzed. Expand a row to read the source, formatted, with
  Original and Genesis analysis as separate tabs; a full reader for long
  papers. Filters for both dates, topic and status. Unavailable full text
  is marked and can never show Analyzed.
- "Used in" as metadata: which architecture version used the technique,
  where, why, with links to the experiments; attached to the historical
  version and never removed by later versions.
- Freshness: the harness injects the current São Paulo date and time into
  every Genesis turn with the rule to prefer sources from the last six
  months while keeping foundational and contradicting work. A "new
  evidence since analysis" flag when a later source contradicts an analyzed
  one.
- Hypothesis record: green, white and red with written rules. Green means
  the predeclared goal against the parent version was met within cost and
  reliability limits, with Bare shown. Red means a net negative on that
  goal. White means untested. Inconclusive and invalid are neutral with
  their label; an infrastructure failure never turns a card red.
- Weekly research automation writes into the library: the source ledger in
  `research/search-log.jsonl` becomes library records; the digest links to
  them; the synthesis matrix and contradictions are views over the same
  records.
- Board polish with the kit: six columns keep their meaning; cards are
  blocks.

Acceptance: a saved abstract cannot be marked Analyzed; the date filter
narrows the list; a turn's recorded prompt contains the date and the
recency rule; a card turns green only through a recorded run that met its
goal; a Used-in link survives a newer version removing the technique.

### Phase 6 — Runtime closure (feature 017, 3 days)

Goal: runs work the same on one host and with workers, and every paid path
has live evidence.

- Live provider acceptance for the Genesis bridge once approved; record
  receipts; release or settle the held US$ 0.66 on evidence only.
- Pause, Resume and Cancel verified in workers mode against a real
  coordinator.
- Budget chip in the top bar showing the week's available amount, opening
  the ledger page; Budget leaves the main navigation.
- Concurrency limits visible when launching: agents at once bounded by
  provider limits, with the reason shown when the bound bites.
- A restart drill: kill the host mid-run with two attempts active, restart,
  confirm the run resumes at the task boundary and no attempt replays.

Acceptance: receipts for four providers; the drill passes twice; the chip
matches `wb budget status`.

### Phase 7 — Product graph editor polish (feature 018, 2 days)

Goal: enrichment is readable at a glance.

- Before-and-after diff kept; add a per-version summary in words generated
  from the diff counts, not by a model.
- Per-product drilldown with the research events that produced each value.
- Research log formatted as blocks instead of raw JSON.
- Prepare dialog and version list on the kit.

Acceptance: a reviewer can name what changed between v1 and v2 without
opening JSON.

## 5. Sequence

| Week | Work |
|---|---|
| 1 | Phase 0; Phase 1 starts; Phase 2 backend starts in parallel |
| 2 | Phase 1 done; Phase 2 chart kit; Budget on the kit |
| 3 | Phase 3 reports, run report first, then round report and narrative |
| 4 | Phase 3 done; Phase 4 evidence and live views |
| 5 | Phase 5 research library and hypotheses |
| 6 | Phase 6 runtime closure; Phase 7 product graph polish; docs and handoff |

About 28 working days in total. Reports and the design system are the two
largest pieces and the ones people will see; the rest is what makes them
true.

## 6. Decisions assumed

Taken today: reports are public by default; the narrative is automatic and
ledger-charged. Still open, with the defaults this plan uses until Lucas
says otherwise:

1. Report voice: Plex Serif prose with Plex Sans UI.
2. Front door: Reports, latest round on top; Runs one click away.
3. First three charts: pass rate with intervals, the paired table, cost
   versus pass rate with the Pareto line.
4. Narrative model and ceiling: the analysis model already configured, at
   US$ 0.50 per run, set in the plan file so a round can raise it.

## 7. Risks

- **Stylesheet migration breaks views.** Mitigated by the browser suite
  from Phase 0 and by migrating one view at a time behind the layer order.
- **Genesis depends on the installed Codex binary and cross-provider
  routing not yet accepted live.** Phase 6 holds the acceptance; the
  library and board work in Phase 5 does not need it.
- **Automatic narrative spends money on every run.** The per-run ceiling
  and the weekly ledger bound it; smoke-scale runs can set the ceiling to
  zero in their plan file.
- **Pre-registration.** Any task, rule or snapshot change makes old rows
  non-regradable. Nothing in this plan edits tasks or rules; the `<object>`
  fix is presentation only.
- **Repetitions are rare in existing runs**, so pass^k and the consistency
  grid appear only when k is greater than one; the report says so rather
  than showing a trivial value.
- **Graphify is not installed on this machine**, so the code graph is not
  refreshed after these changes until it is.

## 8. Documents to update when each phase lands

`CLAUDE.md` "What lives where" for the new modules and the vendor folder;
`monarch-benchmark/PLAN.md` with the Studio as a frente and the decision
record; `specs/0NN/` for each feature; `THIRD_PARTY_LICENSES.md`; the
direction doc's visual section to point at `tokens.css` as the design of
record.

## Sources for the design system choice

- Radix Colors usage and scale: https://www.radix-ui.com/colors/docs/overview/usage and https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale
- IBM Plex licence (OFL 1.1): https://github.com/IBM/plex/blob/master/LICENSE.txt
- Carbon square geometry and Plex: https://www.designsystems.one/design-systems/carbon-design and https://github.com/carbon-design-system/carbon/issues/285
- Tufte CSS (MIT): https://github.com/edwardtufte/tufte-css
- Lucide licence (ISC): https://lucide.dev/license
- Geist font licence (OFL 1.1): https://github.com/vercel/geist-font/blob/main/LICENSE.txt
- Basecoat UI: https://basecoatui.com/installation/
- Open Props UI theme: https://open-props-ui.netlify.app/guide/getting-started/theme
- Linear's redesign and dark surfaces: https://linear.app/now/how-we-redesigned-the-linear-ui and https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/
- Vercel Geist breakdown: https://www.designsystems.one/design-systems/vercel-geist
- Warp block UI analysis: https://getdesign.md/warp/design-md
- "Technical Mono" trend: https://aigoodies.beehiiv.com/p/aesthetics-2026
