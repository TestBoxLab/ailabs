# Benchmark artifact workspace: acceptance revision

Created: 2026-09-11. Branch: `ailabs/report-template`.
Status: implemented, deployed and browser verified; Carlos accepted segregation
and authorized push/PR after editing restoration, now verified. Merge pending.

## Settled scope

Carlos rejected the Settings placement and unrestricted-looking repository editor.
Keep the approved visual language. Move benchmark artifacts into a dedicated
Benchmarks module, organized by artifact type. AI Labs owns formats and validation;
`TestBoxLab/ailabls-benchmark-config` owns artifact values and direct-main history.
This supersedes feature 013's editable-README requirement, without changing any
historical configuration snapshot.

Carlos explicitly clarified: declare feature discovery in YAML now; implement
discovery execution and evaluation later. Deployment orchestration and future
SSO/approval profiles are backlog work, not current execution capabilities.

## User stories and acceptance

### US1: Edit valid benchmark artifacts (P1)

- Benchmarks is independent of Settings, with Harnesses, Models, Plans and
  Products routes/segments. Supporting product YAMLs remain with Products.
- Only recognized YAML artifacts appear. README and arbitrary repository files
  cannot be created, edited or deleted through this UI or its write API.
- New artifacts choose a type and a name; the server describes supported types
  and required fields. Existing executable loaders remain the schema authority.
- Reject duplicate YAML keys, unknown fields, invalid types and unresolved new
  references before a commit, including direct API calls that skip validation.
- Generated knowledge/recipe evidence is inspectable but not a hand-editable
  substitute for its generator. Preserve valid historical snapshots and existing
  warnings for untouched, suspended plans. Failed saves preserve drafts.

### US2: Attribute configuration history to the authenticated person (P1)

- Saves derive the actor from a verified person key or authenticated Basic login;
  client-supplied author/operator values cannot impersonate a configuration author.
- The shared admin account appears as that account, not as Carlos or the PAT owner.
  Record authentication provenance without tokens or passwords.
- Commit author and the technical Git credential committer remain distinguishable.
  Show bounded commit history with author, time, message and immutable revision.
- A declared run operator remains distinct from the configuration author; do not
  grant paid approval powers to an admin name through this change.

### US3: Understand Monarch provenance (P1)

- Runs has a Monarch version section reading retained evidence only: full commit
  when recorded, evidence status, recorded build label, knowledge-base content
  hash and service-specific deployment/image/source identity when present.
- A local checkout or environment declaration is never labeled deployed proof.
  Historical absence is displayed as Not recorded; never backfill from today's
  checkout, environment or service.
- New runs freeze available provenance and continuation segments retain their
  runtime evidence. Separately deployed monorepo services may have different
  commits; dirty uploads require additional source identity.

### US4: Declare later evaluation capabilities (P2)

- Product/plan definitions can describe `feature-discovery` using the existing
  file layout. Validation is distinct from runnable support: preview/execution
  must refuse this mode before any dispatch, with an explicit explanation.
- Monarch harness definitions can declare model-family requirements by role.
  Validate their structure and family references against available price metadata.
  Declaring a family must not silently be treated as a live routing override.
  Until runtime selection/verification is supported, such requirements block
  execution explicitly. Existing harnesses without the new fields are unchanged.
- Existing configuration hashes remain byte/semantically stable when optional
  new fields are absent. New inputs participate in new hashes.

## Edge cases and constraints

Read-only snapshots, missing PAT approval, concurrent saves, history failures,
empty artifact groups, dirty drafts across tabs, unsupported roles/families,
stale preview, missing provenance, and malformed YAML must remain understandable.
No new round, model call, Monarch deployment, dataset edit, regrading or history
rewrite is authorized by this acceptance revision. Existing spending gates remain.

## Future work

Record deployment selection/orchestration with immutable source, per-service
identity, active-run draining, verification and rollback. Record discovery's own
task/evaluation contract and model-routing integration. Record SSO with stable
subject IDs, roles, per-user ceilings, approval requests bound to exact revisions
and amounts, and append-only audit history. The identity provider is not selected.

## Success criteria

Backend regression tests reproduce and prevent invalid edits and actor spoofing.
Browser checks cover grouped navigation, guided creation, errors/draft retention,
history, provenance and mobile layout. Existing report acceptance checks remain.
The feature remains unmerged until Carlos approves the revised hosted UI.
