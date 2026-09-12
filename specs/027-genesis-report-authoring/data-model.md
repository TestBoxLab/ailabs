# Report records

Each run retains report-work.json (current state), report-work/<workflow>/ with
frozen evidence.json, attempts.json, each numbered draft, review JSON, state.json
and publication.json. report-publication.json is the last accepted version.
Historical analysis.json is never overwritten or regraded.

State: analysis → author → review → published, or review → repair → review_again
→ published. Any incomplete, rejected, stopped or stale stage fails. A retry is
explicit and creates a new workflow directory with its own reservations.

The evidence digest binds source task briefs, checks, events, results, settings,
task hashes and finish state. The draft digest binds prose AND complete attempt
analysis. Review acceptance must name both current digests. Attempt identity is
the stored result index plus run, task and setup; ambiguous event repetition
identity is disclosed rather than invented.

Percentages, categories and counts are computed by report_patterns.py from the
report's stored attempt projections. Every slice contains exact attempt refs.

Analysis uses sequential fresh turns grouped at at most 8 attempts or 100,000
source characters (a single oversized attempt stays together and pages).
analysis_keys and analysis_cursor identify the active batch; each turn retains
its assigned indexes. Reservations split the original analysis share across
batches, with the same total ceiling and explicit per-turn startup preflight.
No batch may overwrite another batch's analysis.

The evidence digest also binds frozen before/after snapshots and computed pattern
values. Whole long evidence packets use lossless character pages; read spans
cannot skip a middle fragment. Draft pages default to 20 attempts and shrink to
fit. Serialized draft, attempt analysis and review limits are 20k, 30k and 4k
characters respectively. Startup recovery fails stranded work without replay.
