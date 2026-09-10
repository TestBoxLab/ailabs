# Tasks

- [x] T001 Preserve prior corrections and integrate main; inspect CI job/logs.
- [x] T002 Reproduce and fix the three CI failure causes with focused tests.
- [x] T003 [P] Write failing exporter tests; implement durable OTLP delivery,
  stable identities, safe attributes and explicit retry/status/backfill.
- [x] T004 Connect ledger and usage receipts across every paid entry point;
  test unknown billing, failures, retries and existing Monarch cost ownership.
- [x] T005 Add CLI/Studio attempt summaries, including keyless completion,
  and verify that exporting cannot change the saved result.
- [x] T006 Run focused checks and a telemetry-only live probe. Delegated CI
  review completed; remaining exporter review was performed locally after
  delegated agents hit their usage limit. Official v4 review caught and fixed
  unsafe exported-span updates and blind retries.
- [x] T007 Run detached full tests and CI corpus validation; refresh Graphify,
  update evidence/PR description, commit, push and wait for GitHub CI.
  Final code: GitHub run 34510275623, 2,096 passed and nine skipped; both
  corpus checks passed. Windows transport limitation and live delivery/recovery
  evidence are in docs/rounds/2026-09-10-pr3-ci-and-langfuse.md under monarch-benchmark.
