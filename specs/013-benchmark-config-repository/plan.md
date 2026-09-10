# Implementation Plan: Versioned benchmark configuration repository

**Branch**: `ailabs/config-repository` | **Date**: 2026-09-10
**Spec**: [spec.md](spec.md)

## Summary

Keep schemas and execution in AI Labs; move editable artifacts to the private
`TestBoxLab/ailabls-benchmark-config` repository. Read immutable Git revisions,
validate and save directly to main with optimistic concurrency, then resolve
and execute the same product/plan through CLI and Studio. Preserve existing
formats, frozen hashes, upstream tasks and billing/approval gates.

## Technical context

Python 3.13 through uv; existing PyYAML, dataclasses, pathlib, urllib, hashlib,
difflib and tempfile. Studio uses its existing stdlib HTTP server and vanilla
JavaScript UI. No new framework, database, background sync service or submodule.
GitHub REST Git objects provide multi-file commits; non-forced ref updates detect
races. A complete revision cache lives beneath the persistent data directory.
A token scoped to repository contents stays in server environment. Local CLI can
use existing authenticated GitHub CLI credentials; credentials never enter files.

## Constitution check

Approved brainstorming recorded in spec. Strict TDD and browser verification
required. Existing loaders are authoritative, not a parallel permissive schema.
Upstream data, methodology, approvals and budget gates unchanged. Saving never
launches an attempt. All files English. Read current Graphify graph; refresh
code graph after implementation. No paid model call needed for validation.

## Implementation boundaries

- `wb_orchestrator/config_repository.py`: fixed repository configuration, GitHub
  client, bounded and verified immutable snapshots, safe file paths, structural
  validation/diff, atomic main saves and revision provenance.
- `wb_orchestrator/config.py`: resolve external config against an explicit runtime
  root, preserve legacy defaults/hashes; snapshot source metadata separately.
- `wb_arms/providers.py`, `api_loop.py`, `orchestrator.py`: bind the resolved model
  provider to the attempt instead of reading a refreshed global catalog.
- `wb_orchestrator/cli.py`: repository/revision selection and preview, same existing
  configured run and resume gates. Existing local explicit paths remain supported.
- `wb_studio/benchmark_config.py` and minimal routes in `app.py`: authenticated
  browse/validate/save/preview/run endpoints, persist source with each configured
  job, run through the configured orchestrator rather than lossy model-name mapping.
- `wb_studio/static/benchmark-config.js` with existing navigation/style hooks:
  file list, YAML editor, diff, commit message, conflict errors, revision/history
  link and plan preview/launch. Reuse current design tokens and API/CSRF helpers.
- `tests/test_config_repository.py`, `tests/test_config_repository_execution.py`,
  `tests/test_studio_benchmark_config.py`: API fake plus real loader/world tests.
- `scripts/migrate_benchmark_config.py`: prepare exact-byte migration and manifest;
  existing command-line Git tooling publishes only after local validation.

## Execution and persistence

An immutable revision contains all config bytes and their sha256 digests. A run
resolves using this revision and the installed WorkflowBench task/runtime root.
The revision is copied with evidence so cache deletion cannot lose provenance.
Configured Studio jobs use CLI semantics explicitly; legacy Studio comparisons
remain readable and are not reinterpreted. Run launch is an explicit paid action
with its existing reservation/approval requirements. Unsupported launchers refuse.
Generated knowledge-reference files can be versioned but changing them does not
perform knowledge import or suppress the knowledge drift check.

## Validation and rollout

Start with offline baseline configuration tests. For each implementation unit,
observe an intended failing test before code, then targeted green tests. Exercise
actual immutable tasks with scripted controls; no provider calls. Check conflict,
ambiguous save, path traversal, invalid YAML, cross-file refs, revision pinning,
price freezing, historical hash equality and preserved approval gates. Inspect
UI in a local browser with a deterministic repository fixture. Broaden to the
existing config, orchestrator, Studio, static CSP and billing tests once. Run the
full suite detached if affected surfaces justify it, record platform flakes.
Prepare a private config repo from reviewed bytes, publish to main, verify read
and real commit round trip without paid runs; configure hosted access only after
credential availability and artifact validation. Record any external blocker
without claiming rollout complete. Do not push or merge AI Labs code beyond the
scope authorized in the conversation; config-main commits are explicitly approved.

## Complexity tracking

No new dependencies. Refresh is explicit/on preview; no webhooks or background
polling. Plain YAML editing avoids a speculative dynamic form framework. Auth
reuses the existing person layer, with declared operator distinguished from
verified identity under shared Basic Auth. File-level conflicts are surfaced;
there is no custom merge engine.
