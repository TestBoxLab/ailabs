# Run controls — 9 September 2026

Pause, Resume and Cancel are available in the active run header. Pause becomes Resume while a pause is requested. The state first reads Pausing while admitted tasks drain, then Paused. Cancel is available in both states and becomes disabled while cancellation completes. Ended runs hide the controls. History includes pausing/paused filters, and reloading the page preserves pause state.

Pause stops new task admission. It does not interrupt a model request or suspend a task halfway through its tool sequence. Existing tasks finish and retain their evidence; Resume processes the remaining tasks within the same run, budget and frozen configuration. A paused run retains its run slot and budget reservation, but releases agent slots as tasks drain. Cancel prevents further task admission and uses the existing cooperative cancellation path for active requests. Unclaimed queued runs cancel immediately.

The pause flag is durable and protected from stale progress writes. Remote workers acquire task admission from the coordinator, so a stale local snapshot cannot override Pause. Existing request IDs deduplicate worker admissions. Queued paused runs survive restarts. Claimed execution interrupted by a server/worker failure remains interrupted and cannot be resumed blindly; this change does not add unsafe replay of partially executed work.

| Requirement | Evidence |
|---|---|
| Pause drains current task; no new task begins | `test_pause_drains_current_task_then_resume_or_cancel_without_replay` |
| Resume preserves completed results and runs remaining task once | same test, resume parameter |
| Cancel while paused preserves completed results and skips remainder | same test, cancel parameter |
| Queued pause persists across restart | `test_queued_pause_survives_restart_and_can_cancel_without_execution` |
| Stale writes cannot undo controls | `test_stale_progress_cannot_undo_pause_or_resume` |
| Terminal runs cannot be resumed or paused | `test_ended_runs_reject_pause_and_resume_without_mutation` |
| Coordinator enforces pause against remote tasks | `test_worker_pause_gate_blocks_new_tasks_and_stale_progress_cannot_resume` |

Browser acceptance: `artifacts/genesis-check/run-controls-browser.cjs` passed against a real disposable HTTP server with scripted offline controls. It clicked Pause, Resume and Cancel; checked Pausing → Paused, persisted state after reload, exactly two results after Resume and one after Cancel, hidden controls after termination, no page errors and no horizontal mobile overflow. Screenshots contain explicitly named Offline control check fixtures. No paid calls or changes to historical runs were made.

The idle local preview was restarted after confirming no active runs or Genesis turns.

Verification: the six-file run/control suite completed with 194 passing checks and one subprocess startup timeout in the existing process-lock test. That test passed on isolated rerun (1 passed). Browser acceptance passed against actual endpoints.
