# Specification Quality Checklist: Results Report as HTML Tables

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — the spec names commands and what a reader sees; the module names, the stdlib choice and the sorting script live in `plan.md`, `research.md` and `contracts/`.
- [x] Focused on user value and business needs — the "Why" says what a reader cannot do today and what the round sheet already promises.
- [x] Written for non-technical stakeholders — plain names, a vocabulary table, and every column of the page named in words.
- [x] All mandatory sections completed.

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — three unknowns are recorded as Open Questions with owners; none blocks the work, and each has a proposed answer.
- [x] Requirements are testable and unambiguous — every FR maps to at least one acceptance scenario or success criterion, and every metric has a formula in `contracts/report.md`.
- [x] Success criteria are measurable — table counts, exact strings, the absence of `inf` and `nan`, a byte-for-byte unchanged markdown report.
- [x] Success criteria are technology-agnostic — they describe what the page contains, not how it is built.
- [x] All acceptance scenarios are defined — five stories, 20 scenarios.
- [x] Edge cases are identified — including the three that would have shipped wrong: a competitor that passes nothing, tasks with no tier, and rows with no wall-clock.
- [x] Scope is clearly bounded — Out of Scope names charts, the Slack post, feature 005's tiers, and any change to what is recorded.
- [x] Dependencies and assumptions identified — features 001, 002 and 004 as they stand; nothing outside the repository.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria.
- [x] User scenarios cover primary flows — read one round, read Monarch's phases, compare rounds, trust the gate, read the round's size.
- [x] Feature meets measurable outcomes defined in Success Criteria.
- [x] No implementation details leak into specification.

## Constitution check

- [x] §III: no fixed rule of `PLAN.md` §1 is changed. This feature *renders* rule 7 (infrastructure failures counted separately and excluded from the denominator), rule 8 (every figure carries its source line), rule 9 (cost complete, price table versioned, missing-cost share stated) and rule 10 (audience rules are code). Rule 5 is enforced by refusing any paired figure pooled across task sets.
- [x] §IV: nothing here spends money. `wb report` and `wb summary` read the results store; no task, prompt or approval rule is touched and no hash moves.
- [x] §V: English, plain names throughout; the design of record was approved by Carlos on 4 Sep 2026.

## Feature-specific checks

- [x] Every number comes from the results store, computed in one module (FR-002) — no hand-typed figure, and a test asserts the page and the markdown report agree.
- [x] Infrastructure failures are a separate column and are excluded from the pass denominator, both visible in the same row (FR-005) — rule 7 holds.
- [x] Every table carries a source line, including the price-table version and the missing-cost share (FR-003) — rules 8 and 9 hold.
- [x] The audience gate is applied before any statistic is computed and the renderer cannot query the store (FR-023, plan design note 1) — rule 10 holds by construction, not by review.
- [x] No paired comparison is pooled across task sets, on either page (FR-021) — rule 5 holds.
- [x] Nothing that cannot be computed renders as zero (FR-027) — `n/a`, and no `inf` or `nan` on the page.
- [x] No new dependency (FR-026) — the standard library builds the page.

## Notes

- Validated 2026-09-04 in one pass.
- Two risks carried from the design into the spec's edge cases rather than left implicit: no pilot task carries a tier or a domain today, and rows written before phases were populated have no wall-clock.
- Ready for `/speckit-plan`.
