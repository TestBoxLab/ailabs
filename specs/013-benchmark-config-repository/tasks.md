# Tasks: Versioned benchmark configuration repository

## Specification and baseline

- [x] T001 Record approved repository name, main-save policy and feature boundaries in spec.md.
- [x] T002 Prepare isolated worktree from the deployed Gmail repair and install unchanged vendor with uv.
- [x] T003 Review specification independently and record baseline configuration tests.

## US1: Shared artifacts and editing

- [x] T004 Write failing repository tests for reads, safe paths, malformed YAML and immutable revision caches in tests/test_config_repository.py.
- [x] T005 Implement bounded GitHub reads and existing-loader validation in wb_orchestrator/config_repository.py.
- [x] T006 Write failing tests for multi-file save, no-op, concurrent main update and ambiguous delivery; implement non-forced commit publication.
- [x] T007 Add authenticated Studio browse/validate/save routes and tests in wb_studio/benchmark_config.py and tests/test_studio_benchmark_config.py.
- [x] T008 [P] Build config editor, diff and history navigation in wb_studio/static/benchmark-config.js using existing UI conventions.

## US2: Frozen plan execution

- [x] T009 Write failing tests comparing legacy and external resolution, unchanged hashes and runtime-root paths in tests/test_config_repository_execution.py.
- [x] T010 Extend config.py resolution/provenance without changing legacy defaults.
- [x] T011 Write a failing test where a model edit cannot change an already resolved provider; bind providers per attempt.
- [x] T012 Add CLI revision selection/preview and keep run/resume approval and budget gates.
- [x] T013 Add configured Studio preview/run using the shared orchestrator; test frozen revisions and cancellation without paid calls.
- [x] T014 Connect editor plan preview and explicit launch controls, with attempts/cost/readiness visible before launch.

## US3: Migration and verification

- [x] T015 Prepare exact-byte config migration with manifest and private repo README; preserve originals and all frozen data.
- [x] T016 Run targeted regression groups, inspect editor and conflict flow in a browser, and perform independent code review.
- [x] T017 Publish reviewed config artifacts to TestBoxLab/ailabls-benchmark-config main and verify revision/file hashes.
- [ ] T018 Verify hosted credential availability, prepare deployment, and complete free hosted browse/save/preview verification when authorized and runnable.
- [ ] T019 Refresh Graphify and record tests, migration hashes, deployment status and any outstanding limitation in the feature quickstart/evidence.

No paid benchmark round is part of this implementation verification. Check a task
only after evidence exists; configuration-main publication is authorized, not a
blanket authorization to push AI Labs code or modify Monarch.
