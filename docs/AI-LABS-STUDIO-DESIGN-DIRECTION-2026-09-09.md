# AI Labs Studio — design direction proposal, 9 September 2026

Status: proposal for discussion, no code. Companion to
`AI-LABS-UIUX-REVIEW-2026-09-09.md` (what is wrong today) and
`AI-LABS-ADVERSARIAL-REVIEW-2026-09-09.md` (reliability and decision support).
Written after a research pass over evaluation platforms, benchmark hubs, model
release posts and scientific publishing tools; sources at the end.

## The brief

Lucas wants the Studio to stop looking generic: a minimalist, scientific,
sleek interface; rich graph visualisations; scientific analysis; and
high-level outputs that read like a model release post, not a technical dump.

## Constraints the direction has to respect

- **Methodology is fixed** (`PLAN.md` §1): same request text for every
  competitor, nothing grades itself, paired comparisons only on identical task
  sets with error bars, every figure carries its source line, cost complete and
  versioned, audience rules are code. The report layer must make these rules
  visible, never bend them.
- **No build step, strict CSP.** The Studio is vanilla JS served by Python.
  `script-src 'self'; style-src 'self'` means no CDN scripts, no inline
  `style=""` attributes. Any library or font is vendored under `static/`. The
  existing charts already hand-build SVG for this reason.
- **The repo is public.** Fonts and libraries must be permissively licensed.
- **Two readers.** The operator investigating a run (evidence first) and the
  program reader deciding what the round means (findings first). Today the
  product serves only the first.

## What the research says

**Model release posts** (Anthropic's Opus 4.6 post is the template): a
headline claim with one number, then grouped bar charts per benchmark, one
comprehensive table with model columns, small multiples for specialised
domains, and dense footnotes on method (tool access, sample counts, which model
version was compared). Order: claims → evidence → method. Numbers are always
labelled on the mark, not read off an axis.

**Evaluation platforms** converge on the same three screens: an experiments
table, a comparison view against a chosen baseline with green/red deltas and
regression filters (LangSmith, Braintrust), and a per-sample transcript with
tabs for messages, scoring, metadata and a timeline (Inspect). Braintrust's
Summary layout grades a whole comparison as Improvement, Regression, Tradeoff
or Tie across score, latency, cost and errors. That grade is the one-word
answer a program reader wants.

**Benchmark hubs**: Epoch AI leads with state-of-the-art-over-time trends and
keeps caveats next to the chart; Artificial Analysis leads with trade-off
scatters (capability vs cost, vs speed) with a marked Pareto line and one
point per model. Both label points directly and colour by group, never by
value.

**Evaluation Cards** (arXiv 2606.09809, June 2026) give the pattern for
plain-language reporting: three fixed blocks per benchmark ("What it
measures", "Main caveat", "Intended for"), and automatically surfaced
reproducibility and comparability warnings written as sentences ("Scores
diverge across setups: temperature, shot count"). Our config hash, task set
hash and price-table version already carry the data for exactly those
sentences.

**Visual language**: the sleek minimal look of 2026 developer tools (Vercel
Geist, Linear) is near-white paper, near-black ink, a long neutral scale, one
rationed accent, mono numerals, hairline rules, no shadows, restraint as the
brand. Scientific publishing (Distill) adds a serif reading voice, figures
with captions, margin notes, and prose that carries the argument. The two
combine well: sans and mono for the tool, serif for the report.

**Benchmarks like ours** (reviewed in
`AI-LABS-BENCHMARK-LANDSCAPE-2026-09-09.md`): our corpus is Zapier's
AutomationBench, which Zapier and Artificial Analysis already publish with two
different headline metrics, so every public report needs a comparability
sentence. The field agrees on cost beside accuracy in the same table, caveats
next to the chart, strict pass as the headline with a softer second number,
and reliability across repetitions (pass^k, consistency grids). Five measures
come from that review and need no new grading: pass^k, objective share,
violations per attempt, false-completion rate, and success overlap between
competitors.

**Charting without a build step**: Observable Plot, Vega-Lite, ECharts and
uPlot all load from a script tag, but ECharts is about 1 MB of canvas that CSS
cannot theme, Vega-Lite injects inline styles that our CSP blocks, and Plot
pulls 40 D3 modules. For our ten chart types the right size is a small
in-house chart kit on vendored D3 primitives (scale, shape, axis, array),
styled entirely by CSS classes. For node graphs the Studio already owns a
canvas editor; render it read-only for figures instead of adding Cytoscape.

## The direction: a lab notebook that ends in a release post

Three layers, each with its own reading mode.

### 1. Reports (new; becomes the front door)

One page per run, and one per round (several runs on the same frozen task
set). Structure, in order:

1. **Verdict.** One paragraph, plain language, hard cap of 120 words. One
   Braintrust-style grade in the margin: Improvement, Regression, Tradeoff, Tie,
   or Not comparable.
2. **Key findings.** Three to five, each one sentence, each anchored to one
   number and one evidence link. Descending significance.
3. **Hero figure.** Pass rate per competitor with 95 % confidence intervals,
   dot-and-whisker, baseline in grey, the competitor under discussion in the
   accent. Source line under it.
4. **The table.** Competitors as columns, task categories as rows, cells
   "passed / total" with the paired delta versus baseline in green or red only
   when the sets are identical. Ties share the neutral colour.
5. **Where it failed.** Failure categories with counts and denominators, then
   the task matrix (tasks × competitors, pass/fail/agreement across
   repetitions), sortable by disagreement.
6. **What it cost.** Cost vs pass rate scatter with the Pareto line; token
   waterfall per competitor (uncached input, cache writes, cache reads,
   output).
7. **Caveats.** Generated from data, not written by a model: unrecorded
   attempts, mismatched thinking settings, missing Bare baseline, price table
   version, config hash. Sentences, not fields.
8. **Method.** Task set hash, seed, repetitions, judge version, run IDs.

The narrative slots (verdict, findings) are written by the analysis model
that already exists in `wb_studio/analysis.py`; every number in them is
inserted by code, and every claim must cite an event or a table cell. A claim
without evidence renders as "Unknown". This keeps "nothing grades itself".

For the weekly program, the round report adds a **trend figure**: pass rate
per Monarch release over rounds, Epoch-style, with the intervals.

### 2. Runs (existing; evidence)

Keep the table. Row click opens the run (done today). Per attempt, adopt the
Inspect tab set in the side panel: Output, Checks, Trace, Timeline. The
timeline is a small Gantt of tool calls by node over time. The architecture
graph appears read-only above the trace with per-node cost and time badges.

### 3. Studio (existing; authoring)

No change to the canvas. Architectures and product graphs merge under one
"Studio" section, which they already are.

### Information architecture

Reports · Runs · Studio · Genesis · Settings, with the weekly budget as a
chip in the top bar that opens the ledger. Leaderboard becomes the
"Standings" section of the round report; it is a report, not a workspace.

## Visual system

Design of record since 9 Sep: `wb_studio/static/tokens.css` (Radix sage and
green, IBM Plex Sans, Mono and Serif, Lucide icons), chosen in
`AI-LABS-IMPLEMENTATION-PLAN-2026-09-09.md` §3. The bullets below are the
proposal that led to it.

- **Type.** UI: Inter or Geist Sans (both open licence, vendorable). Numbers,
  IDs, hashes: Geist Mono or IBM Plex Mono with tabular figures everywhere a
  number appears in a table or chart. Report prose and headings: a serif
  (Source Serif 4 or Newsreader) so the report reads as writing, not as UI.
  Three families is the ceiling.
- **Colour.** Paper near-white, ink near-black, a twelve-step neutral scale,
  the current forest green kept as the single accent. Green and red mean
  passed and failed, nothing else. Chart series use a fixed categorical
  palette from the dataviz reference, validated for light and dark.
- **Surface.** Square corners (kept), 1 px hairlines, no shadows, 8 px grid,
  dense tables, wide margins on report pages (max 72 characters of prose).
- **Figures.** Every chart: title as a claim ("Opus passes 9 of 10, Monarch
  8 of 10"), direct labels on marks, no legend where labels suffice, gridlines
  only on the value axis, intervals drawn as thin whiskers, a one-line source
  under the figure with the run IDs. Same axis style across all ten charts.
- **Motion.** None, except the live pulse on running attempts.
- **Dark theme.** Tokens only; no hard-coded colours (the Budget panel bug
  came from one fallback value).

## What I would not do

- Not React, not a bundler, not Tailwind. The no-build setup is a feature
  here: one process, one directory, every file readable.
- Not ECharts or Vega. Canvas cannot be themed by CSS and both fight the CSP.
- Not a third node-graph library. The canvas editor already exists.
- Not more disclosure widgets. Reports show the hierarchy through headings and
  whitespace, not `<details>`.
- Not a model writing numbers. Prose slots only.

## Sequence, if approved

Per the constitution: brainstorm (this document plus the answers below),
then `/speckit-specify` for a feature "012 studio reports", plan, tasks, then
execution with tests.

1. **Spike (1 day).** Vendor D3 primitives and fonts, confirm CSP passes,
   build the dot-and-whisker chart and the table with real run data.
2. **Run report (2–3 days).** The eight-section page for a single run, with the
   narrative slots filled by the existing analysis and the caveat generator.
3. **Round report (2 days).** Several runs on one task set: the paired table,
   the task matrix, the trend figure, the grade.
4. **Evidence panel (1–2 days).** Output, Checks, Trace, Timeline tabs; the
   read-only architecture figure.
5. **Visual system (1–2 days).** Fonts, tokens, the ten-chart kit, dark theme
   parity, Reports as the front door.

## Decisions

Taken by Lucas on 9 September 2026:

- **Who reads it: everyone.** Reports render for the public audience by
  default, so the audience rules in `audiences.yaml` apply to every report:
  lab competitors and internal-only prose never appear unless the rules allow
  them. An internal view is a filter on top, not a different report.
- **Narrative is automatic.** The analysis model writes the verdict and
  findings for every finished run, without a manual "Analyse" step. The
  request is paid, so it is reserved and settled in the weekly ledger like any
  other, and a run whose analysis the ledger cannot cover shows "Analysis
  pending" with the shortfall, never a half-written report.

Still open:

1. **Voice of the report.** Serif prose with sans UI (research-post look) or
   all-sans (dev-tool look)? Recommendation: serif prose.
2. **Front door.** Reports (findings first) or Runs (evidence first)?
   Recommendation: Reports, with the latest round on top.
3. **Chart set for the first cut.** Of the ten (pass rate with intervals,
   paired delta, task matrix, cost vs pass rate, time distribution, failure
   categories, trend over rounds, trace timeline, architecture figure, token
   waterfall), which three must be in the first report? Recommendation: pass
   rate with intervals, the paired table, cost vs pass rate.

## Sources

- Anthropic, Claude Opus 4.6 announcement: https://www.anthropic.com/news/claude-opus-4-6
- LangSmith, How to compare experiment results: https://docs.langchain.com/langsmith/compare-experiment-results
- Braintrust, Compare experiments: https://www.braintrust.dev/docs/evaluate/compare-experiments
- Inspect AI, Log viewer: https://inspect.aisi.org.uk/log-viewer.html
- Epoch AI, Benchmarking hub and its 2025 update: https://epoch.ai/benchmarks and https://epoch.ai/blog/benchmarking-hub-update
- Artificial Analysis, model comparison charts: https://artificialanalysis.ai/models
- Evaluation Cards, an interpretive layer for AI evaluation reporting (arXiv, June 2026): https://arxiv.org/html/2606.09809v1
- Distill, about and article guide: https://distill.pub/about/ and https://distill.pub/guide/
- Observable Framework: https://observablehq.com/platform/framework
- Observable Plot, getting started (CDN and UMD notes): https://observablehq.github.io/plot/getting-started
- Vega-Lite, embedding: https://vega.github.io/vega-lite/usage/embed.html
- Apache ECharts 6 features: https://echarts.apache.org/handbook/en/basics/release-note/v6-feature/
- uPlot: https://github.com/leeoniya/uPlot
- Vercel Geist design system breakdown: https://www.shadcn.io/design/vercel
- SaaS UI design trends 2026 (Linear-style density debate): https://www.saasui.design/blog/7-saas-ui-design-trends-2026
- Graph libraries decision guide 2026 (Cytoscape, vis-network, Sigma): https://www.pkgpulse.com/guides/cytoscape-vs-vis-network-vs-sigma-graph-visualization-2026
- Sigma.js quickstart (script-tag use): https://www.sigmajs.org/docs/quickstart/
