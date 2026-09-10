# Foundation tasks

- [x] Clone AILabs and review project history.
- [x] Record Lucas's decisions and USD 300 weekly budget.
- [x] Create private Trello board with scientific stages.
- [x] Install locked Python environment and pinned upstream dependency.
- [x] Record untouched baseline (703 passed, 3 skipped, 1 reproduced timeout failure).
- [x] Diagnose and repair the nondeterministic timeout test.
- [x] Compare repaired ApplicationBench against baseline; validate a separate derived candidate.
- [x] Remove unsafe host execution from Claude Code adapter; fail closed before exposure.
- [ ] Implement and adversarially verify isolated native execution.
- [ ] Implement native Codex adapter and verify real native trace capture.
- [x] Implement atomic weekly reservations, single-use claims, settlement and unknown-cost holds.
- [x] Connect provider-enforced bounds, paid dispatch and verified billing reconciliation (milestone M3, 8 Sep: the API loop reserves per request at the rate-card maximum, rounds are admitted against the week, `wb budget reconcile` checks a week against the providers' exports; Monarch and native competitors stay refused until M5 and M7).
- [x] Approval flow per decision D5: `WB_OPERATOR`, approval records in the results store, `wb approve` / `wb deny` / `wb approvals`, `wb run --request` (8 Sep).
- [x] Persist hashed attempt evidence and durable observable tool/message journals.
- [x] Add immutable, hash-linked regrade revisions and verify report verdict consistency.
- [x] Stop on journal storage failures while preserving known usage.
- [x] Reject corrupt/missing prior evidence and quarantine incomplete attempts before resume.
- [ ] Implement generation-preserving recovery and billing reconciliation for hard-crashed, incomplete or regraded attempts.
- [ ] Verify current Monarch release and stock one-off request API.
- [ ] Add two-track plans and separate clarification policies.
- [ ] Audit corpus and create reviewed difficulty classification.
- [ ] Build evidence-backed visual reports and calibrated analysis.
- [ ] Implement duplicate-aware experiment registration and lineage.
- [x] Schedule weekly research and link records to Trello (Monday 09:00 America/Sao_Paulo; first execution not yet observed).
- [ ] Run a reserved, bounded paid pilot after prerequisites pass.

Implementation evidence and remaining boundaries: [implementation.md](implementation.md).
