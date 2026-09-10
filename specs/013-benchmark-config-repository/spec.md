# Feature Specification: Versioned benchmark configuration repository

**Feature Branch**: `ailabs/config-repository`
**Created**: 2026-09-10
**Status**: Approved design; implementation pending

## Approved decisions

Carlos approved the design in conversation on September 10. The exact repository
name is **TestBoxLab/ailabls-benchmark-config**, including the spelling `ailabls`.
Studio saves commit directly to its `main` branch. AI Labs owns the schemas,
accepted values, cross-file validation and runtime code. The associated repository
owns the concrete artifacts under the existing `config/` directory structure.
No Git submodule or deployment on each configuration save is required.

## User scenarios and acceptance

### US1 — Read and edit the shared configuration (P1)

Carlos opens Studio Settings, browses plans, models, harnesses, products and
supporting configuration files, edits YAML and reviews the diff before saving.

1. Given a configured repository, opening the editor shows its main commit and files.
2. A validated save creates one commit containing all changed files and records
   the operator and message. A no-op save creates no commit.
3. An intervening remote commit produces a conflict; neither author's work is lost.
4. Invalid configuration produces file/field errors and no branch update.
5. A remote edit is visible on refresh without redeploying Studio.

### US2 — Run a plan from an immutable revision (P1)

Carlos selects a product and plan in Studio or the CLI. Both use the same
configuration resolution, validation and execution semantics for that plan.

1. Preview resolves every selected artifact from a single commit and shows task
   count, competitors, attempts, cost ceiling, readiness and revision before launch.
2. Launch uses the previewed commit, even when main changes after preview.
3. A revision change during an active run cannot change its models, prices,
   harness parameters, task selection or grading inputs.
4. Results retain repository, commit, artifact hashes and resolved configuration.
5. Missing runtime capabilities, credentials, task versions or approval records
   remain refusals. Merely saving or synchronizing never launches paid work.

### US3 — Migrate and recover without changing the benchmark (P2)

1. All current config artifacts migrate with identical bytes and a manifest.
2. Tasks, corpus, AutomationBench, secrets, results and ledger are not migrated.
3. Legacy results remain readable with their original identities and hashes.
4. A network failure preserves the draft and reports that refresh/save failed;
   it never silently substitutes bundled defaults or claims a commit succeeded.
5. Reverting configuration creates a new normal commit. Historical snapshots remain.

## Functional requirements

- FR-001: AI Labs remains the authority for the existing file formats; preserve
  `models/`, `harnesses/`, `plans/`, `products/`, `side-effects.yaml` and README.
  Include price tables, knowledge maps, knowledge-base and recipe references.
  Do not introduce a Kubernetes envelope or repurpose existing `kind` values.
- FR-002: Reuse the existing loaders and resolver. Separate structural validation
  and cross-file checks from environment-dependent launch readiness, so suspended
  historical plans can remain versioned without becoming runnable.
- FR-003: All repository operations are confined to the configured repository and
  allowed config files. Reject traversal, symlinks, executable content and secret
  values; credentials are environment-variable references. Bound remote payloads.
- FR-004: A save compares the expected base commit, writes one Git tree/commit,
  and advances main without force. A race cannot overwrite another commit. An
  ambiguous write is reconciled by reading the exact candidate commit/ref; never
  blindly create a duplicate save. Record a service committer and the authenticated
  person where available; a declared operator is not proof of personal authentication.
- FR-005: Keep a persistent cache of complete, immutable revisions. Validate before
  activating a revision; never expose a partially downloaded or edited directory.
- FR-006: CLI and Studio use the shared resolver and existing approval/spending
  gates. A plan's unsupported behavior is refused rather than translated silently
  into a different Studio comparison. Freeze price/model objects per run; do not
  hot-swap a process-global provider registry underneath active work.
- FR-007: Resolve `config/...` within the revision; resolve existing task, corpus
  and Monarch checkout references against the WorkflowBench runtime root. Preserve
  the strings in frozen configurations and their existing semantic hashes.
- FR-008: Configuration source provenance is additive. Persist the actual config
  bytes and revision with new runs; resume must use that source or explicitly refuse
  drift. Do not rewrite old results or launch on a floating main reference.
- FR-009: Keep secrets in Railway/local environment, reuse Studio authentication,
  CSRF protection and person permissions, and require operator identity for writes.
  Treat the remote token as a server credential; it is never returned to the browser.
- FR-010: Saving config cannot import Monarch knowledge, alter AutomationBench,
  regenerate grading rules, release budget holds, execute a harness or start a run.

## Success criteria

- The editor can read, validate, diff, commit and refresh a model and a plan without
  a Studio deployment, and the commit exists in the configured remote repository.
- Two saves against the same starting commit cannot silently lose either change.
- An offline recorded run retains its original price/model after a newer commit.
- CLI and Studio previews resolve identical product/plan configuration at one commit.
- Migration verifies every file hash; upstream tasks and vendor remain unchanged.
- Backend TDD, existing configuration/approval tests and browser verification pass.

## Assumptions and limits

The new repository is private by default. Main saves are explicitly authorized;
this does not authorize publishing benchmark scores or modifying Monarch. Initial
integration uses refresh on demand and before preview, without webhooks. Changes
are visible to new previews; old previews retain their revision. Introducing a new
provider adapter or harness runtime still requires an AI Labs code deployment.
Configuration schemas are executable loaders plus documented contracts initially;
avoid a second, divergent validation engine. Current JSON run records are evidence,
not a competing editable plan store. Existing experimental architecture artifacts
outside `config/` are outside this migration.

## Review resolutions (September 10)

- Existing local explicit-path CLI runs remain a clearly identified local mode;
  configuring a remote source never silently falls back to it. Repository-mode
  runs require a committed revision. Existing ad hoc Studio comparisons remain
  explicitly distinct from repository plans; new plan edits use Git, not JSON drafts.
- Old runs keep the existing resume behavior. Repository-backed runs resume the
  original frozen source; a higher cost ceiling requires a new committed plan and
  a new run with normal approval, rather than mutating historical evidence.
- Preview records the resolved semantic hash and task hashes under a server-issued
  preview ID. Launch requires that ID and refuses changed external task content
  before any reservation/provider dispatch. The ID also binds product/plan/revision.
- Independent review found no architectural change necessary; these resolutions
  make the legacy boundary and external-input freeze explicit.
- Baseline validation reproduced four missing-harness references in two historical
  achievable-50 plans. Migration preserves their bytes. Editing other files may
  retain identical errors in untouched historical files as visible warnings;
  introducing an error or editing an invalid file requires correction. Preview
  and launch validation never waive those errors for the selected plan.

## Evidence and dependencies

- `wb_orchestrator/config.py`: loaders, resolver, path assumptions and hashes.
- `wb_orchestrator/orchestrator.py`: configured execution and spending admission.
- `wb_arms/providers.py`: model registry currently loaded at process import.
- `wb_studio/app.py`: JSON job creation, runner snapshots, auth and durable state.
- `scripts/studio-entrypoint.sh`: one-time persistent-volume seed, not config sync.
- `specs/001-declarative-benchmark-config/`: existing configuration contracts.
- Constitution and Carlos's final upstream-data preservation ruling remain binding.
