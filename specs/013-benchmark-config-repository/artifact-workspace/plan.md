# Implementation plan

Python 3.13, existing PyYAML/loaders and stdlib HTTP; vanilla JavaScript and the
existing design tokens. No new application dependency or second schema engine.

1. Add a shared artifact classifier/write boundary alongside the existing
   historical snapshot path validator. Reuse loader field definitions for editor
   guidance. Keep immutable README bytes loadable but exclude them from editing.
2. Reject duplicate YAML keys in the shared loader. Preserve hosted support for
   versioned side-effect files; validate generated product references separately.
3. Resolve the configuration actor at the authenticated HTTP boundary. Pass it
   to Git save/history, never accept an author supplied by browser JSON. Preserve
   run-operator and paid-approval semantics.
4. Move the existing editor into Benchmarks, with type-specific routes and guided
   new-file names, manifest help, diff, validation, history and saved-plan preview.
   Keep drafts while navigating; use existing CSS and accessible native controls.
5. Add declarative discovery/model-family fields with explicit execution refusal
   and unchanged legacy hashes. Add a retained-evidence provenance projection and
   freeze available version facts on new execution segments; expose it in Runs.
6. Validate offline first, then browser fixtures. Integrate into a freshly checked
   production source baseline before any authorized preview deployment; do not
   overwrite unrelated changes published by the other active session.

Constitution check: methods, frozen tasks, historical runs, reservations and
approvals unchanged. Carlos's detailed review is the settled brief; do not restart
discovery or require approval of routine implementation choices. Discovery
execution, SSO, per-user budgets and deployment orchestration remain unimplemented
backlog capabilities. No PR or merge while browser acceptance is rejected.
