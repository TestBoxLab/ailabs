# Report and artifact workspace PR integration

Carlos authorized merging PR #7 on September 12. The initial CI run
`34664303298` reported 2,357 passed, five skipped and four failures.

Three failures were invalid test fixtures: the setup test appended an existing
`fd_api_key_env`, and repeated plan edits appended `attempt_cap_usd` again.
Reusing the existing test editor preserves the duplicate-key refusal in the
application. Reproduction: three failures before correction; 22 targeted tests
passed afterward, including the duplicate-key guard and configuration hash test.

The fourth failure exposed an event ordering race. The workflow engine can call
the front door before the start response reaches Studio. These calls were
retained but labeled as authoring. A deterministic integration test waits for
the fake engine's calls before returning its start acknowledgement; it failed
with the same missing execution-tool assertion. Moving the tool classification
to execution after successful authoring fixes it without inventing a run ID or
rewriting historical events. Enterprise and live Monarch tests: 18 passed.

While preparing the merge, main advanced through PR #8 to `492f2a4`. Integration
preserves its Genesis, performance, external-product and shared-report behavior
alongside the readable report, separate evidence downloads, validated artifact
workspace and retained Monarch provenance. The retired internal/public report
split is not restored. Lab-build export restrictions remain enforced.

All validation here is offline or uses scripted browser fixtures. No paid run,
deployment, configuration-repository commit or historical-data migration.

## Integrated verification

- Configuration, repository and external-product checks: 184 passed.
- Studio API, provenance, Enterprise, CSP and paid-dispatch offline checks: 59 passed.
- All 416 tracked Python files passed the import ownership check.
- Browser acceptance passed for the report template, artifact editor and Monarch
  version display, including mobile layout, actual local downloads and standalone
  export without network. All browser runs used the free scripted fixture.
- The integration does not import unrelated hosted-only source absent from both
  branches, and does not deploy or replace the current hosted image.
- Final report, download, guide, baseline, lab-export, measure and definition
  checks: 89 passed, five skipped. Regression cases cover reused baselines,
  ungraded attempts and versions whose tasks are now archived.
