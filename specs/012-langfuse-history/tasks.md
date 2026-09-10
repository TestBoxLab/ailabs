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
- [ ] T007 Run detached full tests and CI corpus validation; refresh Graphify,
  update evidence/PR description, commit, push and wait for GitHub CI.
