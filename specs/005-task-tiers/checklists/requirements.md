# Specification Quality Checklist: Task Sets by Difficulty and the Scored AutomationBench Domains

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — the spec names commands and the files a person edits, which are the product surface of a CLI tool; module names, the shuffle order and the hash ignore list live in `plan.md`, `research.md` and `contracts/`.
- [x] Focused on user value and business needs — the "Why" states the question one blended number cannot answer.
- [x] Written for non-technical stakeholders — plain names, a vocabulary table defining "tier", "the draw" and "difficulty score", and the four rounds' size always in the agreed words.
- [x] All mandatory sections completed.

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — five unknowns are recorded as Open Questions with owners; only the first blocks a deliverable (committing the drawn sets), and none blocks the code.
- [x] Requirements are testable and unambiguous — every FR maps to at least one acceptance scenario or success criterion; the difficulty measure is stated as arithmetic, not as a description.
- [x] Success criteria are measurable — counts, byte-identical comparisons, hash equality, printed differences, refusals.
- [x] Success criteria are technology-agnostic.
- [x] All acceptance scenarios are defined — five stories, 25 scenarios.
- [x] Edge cases are identified — including the three this feature creates: a patched vendored task forcing a redraw, a tier drawn entirely from one domain, and the random set overlapping the tier sets.
- [x] Scope is clearly bounded — Out of Scope names feature 006, the rounds themselves, the run-only variants and the answer-key extension.
- [x] Dependencies and assumptions identified — the field shape of the scored domains, the absence of a vendor difficulty label and the service coverage are all stated as **measured on 4 Sep 2026**, not assumed.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria.
- [x] User scenarios cover primary flows — import, classify, draw, plan the rounds, read the docs.
- [x] Feature meets measurable outcomes defined in Success Criteria.
- [x] No implementation details leak into specification.

## Constitution check

- [x] §III: no fixed rule of `PLAN.md` §1 is changed. Rule 5 is why drawn tasks are byte copies whose hash does not move (FR-019, FR-020); rule 7 is why the four rounds are separate and never pooled (FR-029) and why a short tier makes the draw refuse (FR-022); rule 8 is why the manifest exists (FR-023); rule 11 is untouched — the drawn task files carry their own hashes, which a run already records.
- [x] §IV: nothing in this feature spends. The four plans ship unapproved (FR-027) and every statement of a round's size uses the agreed words (FR-028). The classification is pre-registered before the sets are committed (FR-013) — settling the measure after seeing results is exactly the edit §IV forbids.
- [x] §V: English, plain names throughout; "tier" is defined in the vocabulary table rather than assumed; the design of record was approved by Carlos on 4 Sep 2026.

## Feature-specific checks

- [x] The difficulty measure is objective and computed from the task file alone (FR-008), with no judgment call and no external input.
- [x] The measure is presented as the default **with** its alternative recorded (design §3, research R5) and an open question that must be answered before the sets are frozen (FR-013) — not slipped in as settled.
- [x] Adding a tier label cannot make a drawn task a different task (FR-020), and a test asserts no existing hash moved (plan, data-model §8).
- [x] A task with no approval rule never enters a drawn set (FR-021) — a task nobody can grade must not appear in a round.
- [x] The draw is reproducible from the repository alone: seed, measure and cut points recorded (FR-012, FR-015, FR-023).
- [x] The draw never writes into the corpus it reads (FR-025).
- [x] The service coverage claim ("none missing") is measured and re-checkable by a command (FR-006), not a static assertion.

## Notes

- Validated 2026-09-04 in one pass; no spec updates were needed.
- The spec states plainly that the lower tercile is dominated by the baseline
  domain and the upper by the scored domains (research R5). That is a real
  limitation of the measure, and the stratified draw mitigates it without
  removing it. A reader must be told, which is why it is in the design's
  decisions, the research and the manifest's `measure` text.
- Ready for `/speckit-plan`.
