# Implementation plan

Approved scope: [spec.md](spec.md), Carlos, September 11. Existing isolated branch:
`ailabs/config-repository`. No paid benchmark or AI Labs push is part of verification.

1. Extend the existing orchestrator with task-boundary admission/release callbacks
   and a read-only remaining-work calculation shared with retry scheduling.
2. Connect configured Studio controls to those callbacks. Persist pause and
   cancellation separately; reuse the OS ownership lock for exclusive execution,
   which is released on process death. Recheck frozen config, recorded competitor
   versions, unfinished evidence and billing before any explicit continuation.
3. Offer a read-only recovery preview and explicit Resume using the existing job
   routes. Preserve the run ID, finalized rows and cumulative ceiling; retain old
   unfinished observations before a permitted retry. Record execution segments.
4. Enable existing UI controls for configured runs, disclose remaining work and
   costs before Resume, and reconnect live events after a continuation.
5. Independently verify Git access and finish feature-013 activation only if the
   approved token can access the repository and no work is active. A denied PAT
   remains an explicit external blocker, with offline acceptance completed.

Validation: failing-first offline simulator tests for pause/drain/retry and
crash/restart, concurrent resume, drift and unknown billing; relevant existing
configuration, ordinary Studio control and reporting tests; browser verification.
Keep test state and ledgers isolated. Review the diff and update the deployment
drain procedure and backlog. Deployment must preserve persistent data and inspect
active jobs first. Existing runtime/version refusals remain effective.

Constitution: preserve upstream inputs, frozen history, API-key billing, operator
and budget gates. No new service, database or dependency. Reuse existing clients,
schemas, result projection and OS locks. UI and runtime changes require actual
verification; documentation alone is not completion.
