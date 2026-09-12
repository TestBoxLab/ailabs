# Benchmark artifact workspace: revised hosted acceptance

Carlos rejected the configuration page in the readable-report release. This
revision moves benchmark artifacts into a dedicated Benchmarks module, enforces
supported YAML manifests, attributes configuration commits to the authenticated
account, and displays retained Monarch provenance. Carlos explicitly chose
feature-discovery definitions now, with execution/evaluation later.

Status: deployed and browser verified. PR/merge remain
withheld until Carlos reviews the revised UI.

## Source and deployment

The isolated upload starts from the exact source of hosted release
`c822b12d-d7a0-44d8-b0ea-995776424331`, preserving unpublished Genesis/orb,
Appearance, performance/report behavior, Studio deep links and setup names.
Only this revision's changes were integrated from `ailabs/report-template`
after `cf77591`; uploading that Git worktree wholesale would discard hosted
source. Five files required semantic merge resolutions, independently reviewed.

Railway target: `monarch-dev / production / ailabs-studio`.
Final deployment ID: `faa848df-d257-41a9-a58f-316853bbfc5c`, **SUCCESS**.
Image digest: `sha256:a02848170d57e604e3ce4ddd5039228f365282d1af302db430f0dbd9880d4c82`.
The intermediate deployment `99c88d0f-24c1-41f0-8380-6a1a2856ba11` passed
acceptance checks before a repeated version-explanation sentence was removed.
The final delta contains only that presentation expression and its browser test.
The upload manifest covers 2,950 files and has canonical SHA-256
`3e8ce91063874c1f5d62fdff8692446757b4805c910b8a0626473dc1f693d234`.
The final package preserves 2,927 baseline files byte-for-byte; changed/new
application and test files plus a staged test-cache exclusion are recorded
separately. Vendor AutomationBench, service variables and other services are
unchanged. No benchmark attempt or paid analysis was launched.

Immediate preflight found no active jobs or Genesis turns among 11 visible jobs.
Configuration was a read-only snapshot at
`cecb7e4f8291e02a43082fe8d67e9420b07347f4` with 41 retained files. Actual GitHub
saving is unavailable until repository credentials have the required access;
the save/history checks use an offline GitHub fixture and browser mocks.

## Verification

- Final integrated Python checks: 73 passed. Configured execution, pause/resume
  and provenance: 27 passed in each source tree. New boundary/factory regressions
  failed first and passed after correction. Full details and overlapping test
  groups are in the [feature verification record](../../../specs/013-benchmark-config-repository/artifact-workspace/verification.md).
- Browser fixtures passed at desktop and 390px for grouped YAML editing,
  manifest guidance, read-only generated evidence, authenticated attribution,
  history, draft retention, conflicts and pinned run controls. A separate check
  verifies full source/KB hashes and explicit historical absence in Runs.
- An initial integration failure came from tests reusing a fake commit in a
  shared immutable cache. The fixture now isolates its cache; the protection
  and frozen manifests were not weakened. An incomplete CLI test fixture was
  also corrected for the retained hosted runtime.
- The integrated report retains 106 attempts and seven competitors. Monarch
  retains 3/10 initial solves, 4/10 after retries and USD 41.357219. Performance
  details and evidence-guide hashes also match the retained source.
- Before deployment, the canonical run API reported 106 attempts, completed,
  USD 51.06925921. Its JSON fields have SHA-256
  `854a2dd6af1d16bf98efecdde95e12cc9bd0d9f49885eb94a409ca0874189511` after
  excluding only the new response-only `monarch_provenance` projection.
- Final hosted browser verification produced the identical hash, 106 attempts
  and USD 51.06925921. All four routes work: 9 harnesses, 11 model artifacts,
  16 plans and 4 product/supporting artifacts. README is absent, generated
  evidence is read-only and the authenticated account is displayed.
- Eight final HTTP checks returned 200. Served application/editor scripts and
  editor styles matched staged hashes. No jobs or Genesis turns were active.
  The mobile page measures 380px within a 390px viewport. The historical Monarch
  version section explicitly says its deployed commit was not recorded.

[Open Benchmarks](https://ailabs-studio-production.up.railway.app/#benchmarks/plans).
Reload an already open Studio page to load the updated navigation and scripts.
The [verification receipt](2026-09-11-benchmark-artifact-workspace-verification.json)
records the final deployment, manifest, HTTP checks and unchanged run evidence.

## Product limits

The shared authenticated Basic account is the configuration author; it does
not identify which person shares that password. The declared paid-run operator
remains separate and existing approval/budget checks remain in force.

Provenance distinguishes a local checkout, operator declaration, retained
service evidence and missing history. No current endpoint independently attests
the deployed Monarch source SHA. Historical commits are not invented; complete
per-service source attestation is still required. Discovery execution, verified
model routing, deployment orchestration and individual SSO/approval profiles are
tracked in [Studio follow-ups](../STUDIO-FOLLOW-UPS.md).

## Subsequent editing activation

Carlos accepted the artifact segregation and authorized push/PR after restoring
editing. The earlier read-only status above records the first deployment.
Removing only the obsolete snapshot selector restored Git-backed editing and
history on the same validated image; README and historical inputs are intact.
Hosted browser checks passed. Merge remains pending.
See the September 11 Studio configuration editing restoration record.
