# Feature Specification: Genesis report authoring

Created: 2026-09-11. Owner: Lucas. Status: implemented and validated locally; live model quality unmeasured.
Feature directory is independent of the current shared branch.

## Clarifications

Lucas requests a concise decision-focused opening with full analysis below it.
Reports must explain why Monarch wins or loses using recorded evidence, show
clear error patterns as percentage slices per setup, and let Genesis delegate
analysis, author, review, fix and publish. The attached live-workspace plan is
context; its architecture-editor operations do not define report operations.

## User Scenarios & Testing

### US1 — Understand the result (P1)
Given a finished run, Genesis delegates a complete evidence reading, writes the
central finding, and explains observed winning/losing behavior, alternatives,
uncertainty and a discriminating next experiment. Every recorded attempt has an
analysis. Missing evidence is explicit; no inference becomes a proven cause.

### US2 — Trust publication (P1)
Given a draft, a separate review judges evidence and readability. A revision is
reviewed again before publication. Incomplete coverage, foreign citations,
changed evidence, malformed output, cancellation or a failed review cannot
publish. Prior publications remain available; the workflow and Genesis share
the same durable record and exact version.

### US3 — See error patterns (P1)
Given setups with different attempt counts, vertically stacked percentage slices
show their outcome mix on a shared scale. Behavioral failure modes are separate
from failed checker categories. Counts, denominators, infrastructure and unknown
classifications remain visible, with exact attempt drilldowns. Round summaries
link to each run's authored report and do not invent cross-run causal claims.

## Requirements

- FR-001: Use Genesis's configured author/analysis/review routes and native loop.
- FR-002: Ship versioned analysis, writing and review procedures in the prompt;
  Genesis knows how to start, inspect and complete reports.
- FR-003: Page recorded evidence without silently dropping it. Analysts must
  cover successes and failures and cite events belonging to each attempt.
- FR-004: Persist work before moving stages. Bind review to draft and evidence
  digests. One repair/re-review cycle, bounded total budget, idempotent callbacks.
- FR-005: Restrict report subagents to this report's evidence/draft tools.
- FR-006: Reserve the cycle's maximum before the first paid dispatch, preserve
  unknown charges, obey pause and allowances, never launch benchmark work.
- FR-007: Publish inside Studio only. No external posting, push or deployment.
- FR-008: Preserve historical analysis, frozen tasks, grading and world data.
- FR-009: Code computes counts and percentages once; all slices sum to the
  denominator, no-result groups stay unknown, and patterns expose their source.
- FR-010: Concise opening, full analysis, limitations and attempt details are
  rendered safely in the incumbent report style at desktop and narrow widths.

## Success Criteria

Offline regressions prove lifecycle, coverage, citations, stale evidence,
restricted tools and spending limits. Browser fixtures verify rendering and
drilldowns. Live model quality is reported as unmeasured until a billed run is
explicitly exercised; structural validation is not semantic proof.
