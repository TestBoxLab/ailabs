# Implementation tasks

- [x] T001 Record Carlos's approval and inspect existing orchestrator/Studio controls.
- [x] T002 [US1] Write failing remaining-work/retry tests; implement shared calculation in `wb_orchestrator/orchestrator.py`.
- [x] T003 [US2] Write failing real-world pause/drain/retry tests; add admission/release callbacks in `wb_orchestrator/orchestrator.py`.
- [x] T004 [US1] Write failing configured recovery, ownership, drift and billing tests in `tests/test_configured_controls.py`.
- [x] T005 [US1] Implement recovery preview and exclusive continuation through `wb_studio/benchmark_config.py`, `app.py` and a focused control helper if needed.
- [x] T006 [US2] Connect persisted pause/cancel state to configured execution; verify restart and cancellation races.
- [x] T007 [US1] [US2] Enable existing controls and recovery preview in `wb_studio/static/app.js`; verify with browser tooling.
- [ ] T008 [US3] Verify hosted PAT access and existing config editor behavior; activate Git only when prerequisites pass, documenting any external refusal.
- [x] T009 Terminate an offline worker process, restart and continue concurrently; compare final results and retained earlier rows.
- [x] T010 Run relevant regressions, independent review, deployment readiness/drain check, and update backlog with evidence.

US3 remains externally blocked: the hosted token authenticates, but the required
repository and main ref return HTTP 404. Offline editor checks pass; no live
Git write or source switch is claimed. See [git-activation.md](git-activation.md).
