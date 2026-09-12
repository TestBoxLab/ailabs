# Tasks: benchmark artifact workspace

Paths below are relative to `monarch-benchmark/workflowbench/` unless stated.

- [x] T001 [US1] Reproduce README writes, duplicate YAML keys and schema gaps in `tests/test_benchmark_artifacts.py` and `tests/test_config_future_modes.py`.
- [x] T002 [US1] Add shared artifact classification and write enforcement in `wb_orchestrator/config_repository.py`; preserve historical snapshots.
- [x] T003 [US2] Reproduce config-author spoofing in `tests/test_benchmark_artifacts.py`; derive server actor and Git author/history in `wb_studio/benchmark_config.py` and repository operations.
- [x] T004 [US1] Reproduce Settings placement/ungrouped editor in `tests/browser/benchmark-config.cjs`; move navigation/editor via `static/index.html`, `app.js`, `benchmark-config.js`, `benchmark-config.css`.
- [x] T005 [US4] Reproduce unsupported declaration handling and hash stability; extend `wb_orchestrator/config.py` with validated future definitions and pre-dispatch refusals.
- [x] T006 [US3] Reproduce missing/declared/proven provenance displays; expose retained version evidence and freeze available new-run/segment facts without historical backfills.
- [x] T007 [US1] Verify guided YAML editing, direct API protection, history, draft retention and mobile layout in browser fixtures.
- [x] T008 [US3] Verify source/KB/version labels and unchanged report metrics against retained evidence.
- [x] T009 Update repository-root `monarch-benchmark/docs/STUDIO-FOLLOW-UPS.md`, feature checks and scoped Graphify context; retain verification evidence.
- [x] T010 Integrate reviewed changes with current hosted source and deploy only when no paid work is active. Re-run hosted browser acceptance.

Carlos accepted the segregation and authorized push/PR after editing restoration.
Hosted editing/history now pass; README is preserved. Merge remains pending.
