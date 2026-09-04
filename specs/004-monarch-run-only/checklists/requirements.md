# Specification Quality Checklist: Monarch in Run-Only Mode

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — the spec names commands (`wb monarch recipes`, the run-only plan) and the files a person edits, which are the product surface of a CLI tool; routes and module names live in `plan.md`, `research.md` and `contracts/`.
- [x] Focused on user value and business needs — the "Why" says what run-only answers that create + run cannot.
- [x] Written for non-technical stakeholders — plain names, vocabulary table, and a "What is being compared, plainly" section.
- [x] All mandatory sections completed.

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — three unknowns are recorded as Open Questions with owners; none blocks the offline scope, and the rename question was settled by reading Monarch's controller rather than left vague.
- [x] Requirements are testable and unambiguous — every FR maps to at least one acceptance scenario or success criterion.
- [x] Success criteria are measurable — counts, file contents, refusals, phase presence.
- [x] Success criteria are technology-agnostic.
- [x] All acceptance scenarios are defined — four stories, 24 scenarios.
- [x] Edge cases are identified — including the two this mode introduces: a run left in flight by a timeout, and a recipe that once passed and later fails.
- [x] Scope is clearly bounded — Out of Scope names 003, the release comparison, the scripted executor and the Monarch-side changes.
- [x] Dependencies and assumptions identified — feature 002 is a stated dependency.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria.
- [x] User scenarios cover primary flows — make the recipes, run the pilot, refuse on drift, read the docs.
- [x] Feature meets measurable outcomes defined in Success Criteria.
- [x] No implementation details leak into specification.

## Constitution check

- [x] §III: no fixed rule of `PLAN.md` §1 is changed. Rules 1, 2, 3, 5, 7, 9 and 11 are cited where the feature enforces them; rule 2's meaning in this mode ("same knowledge **within** a test mode") is stated plainly rather than assumed, per §1.4's own definition of run-only.
- [x] §IV: the recipes command is paid and gated by an explicit yes with a task count and cost band (FR-008); the pilot plan ships unapproved; SC-009 orders the live steps by cost.
- [x] §V: English, plain names throughout; the design of record was approved by Carlos on 4 Sep 2026.

## Feature-specific checks

- [x] "Known-correct" is defined by the checker, not by opinion (FR-002) — rule 3 holds.
- [x] Missing recipes are excluded for **every** competitor, not only Monarch (FR-029) — rule 7 holds.
- [x] The recipes file enters the run's configuration fingerprint (FR-025) — rule 11 holds.
- [x] The report says what run-only actually compares (FR-030) — rule 8 holds.
- [x] Nothing in run-only deletes a workflow (FR-016), including on a timeout (FR-021).

## Notes

- Validated 2026-09-04 in one pass; no spec updates were needed.
- Ready for `/speckit-plan`.
