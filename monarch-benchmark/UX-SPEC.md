# WorkflowBench — UX Spec v1

Waki · 31 Aug 2026 · Companion prototype: the "WorkflowBench Console" artifact (interactive, real data)

## Design stance

- **Two visual worlds, on purpose.** The console is dark, dense, mono-accented — an operator's tool for people who live in terminals. The **public report variant renders as a light, clean document** matching monarchagents.ai's enterprise language. Theme follows audience, exactly like the arm-allowlist gates: flipping to "public" is the same action that strips bare/lab arms. Credibility is a rendering mode, not a separate site.
- **Provenance is chrome.** Every figure carries its source line (suite · version · denominator · arm · run) as a visible element, not a tooltip. The August reconciliation failure is designed out at the pixel level.
- **Charts follow the dataviz method.** Categorical palette validated (dark: `#6E80F0` Opus / `#D4754F` Sol on `#14161D`; light: `#2B3FD6`/`#A83F2B` — all six checks pass). Treatment (bare vs +Monarch) is encoded by hollow/filled marks, never a third hue. Status colors reserved. CI whiskers live in the score cells (Terminal-Bench's pattern).

## The ten adopted patterns (from the product survey)

1. Sticky explicit baseline + verdict header (Improvement/Regression/Tradeoff, net W/L) — Braintrust
2. Clickable regression counters in column headers that filter to those rows — LangSmith
3. "Changed only" toggle hiding rows where nothing moved — W&B Weave
4. Any cell click opens the trajectory side panel; side-by-side traces in compare — LangSmith/Langfuse
5. Row identity by stable task id, never position — Langfuse
6. Cost/tokens/wall-clock as peer columns with signed deltas — tbench/Langfuse
7. CI whiskers in cells + cost-vs-completion Pareto as the report's hero chart — tbench/HAL
8. Provenance badges + trajectory access on public rows; gate depth, not honesty — SWE-bench/OSWorld
9. Failure taxonomy: pinned human categories + suggested clusters, distribution bars, exemplar links — LangSmith Insights/Braintrust Discover
10. Annotation-queue review mode (rubric pane, hotkeys, pairwise A/B) for failure labeling — LangSmith

Anti-patterns designed against: comparison modes that degrade drilldown; 1D leaderboards mixing verified and self-reported; implicit baselines; >3-way side-by-side.

## The five surfaces

**1. Report** *(prototype: deep)* — verdict banner → paired table with CI whiskers and source lines → Pareto scatter (cost per completed task × strict pass, bare→+M connected) → failure-bucket bars → audience toggle (internal dark / public light; public strips gated arms and swaps exact dollars for ratios per DESIGN descope).
**2. Runs** *(prototype: functional)* — live matrix (tasks × arms), failures-first sort, termination-taxonomy chips, resume banner, per-provider concurrency meters.
**3. Explorer** *(prototype: functional)* — baseline chip (sticky), per-task paired grid, regression counters in headers, changed-only toggle, click → trajectory panel (tool-call list, gate decisions), pairwise A/B keyboard review mode.
**4. Corpus** *(prototype: framed)* — task file with live CI status (no-op, oracle), vacuous-assertion warnings inline at the failing check, contract hash visible.
**5. Tenants** *(prototype: framed)* — pool cards (lease state, verify_clean, resets/hour), capacity model readout, orphan-sweep log. Synthetic-only note until M5.

## Build path

Prototype (today) → M4 report builder emits the Report surface as its html output (same components) → Runs/Explorer wrap `wb_results` queries as a local web app (`wb ui`, FastAPI + static) → Corpus/Tenants land with M5/M6. No separate design system: tokens in this spec are the design system.
