# Merged Monarch deployment, 10 September 2026

Carlos authorized uploading his merged local Monarch branch to the personal
Railway `monarch-dev` project, `production` environment. No GitHub push, merge
performed by this deployment session, or paid benchmark attempt was used.

## Source and scope

The sibling checkout initially had `HEAD=b11c580cf` and an unfinished, resolved
merge of `26558c837`. Another session completed that merge during inspection.
Every upload used the resulting `0cf63a74ec668a7fb64d4849d6b50a8e2a660bb0`
(`chore: merge main into benchmark branch`). The documented previous verified
source was `d4d8da19f`; Railway upload deployment metadata does not provide a Git
commit, so previous deployment IDs and image digests are the rollback evidence.

Both existing uncommitted edits were retained:

- `.gitignore` excludes personal setup/configuration and allows the Pendo logo
  required by the web build. Its SHA-256 is
  `39669316b67a42e393b14a39d19616b968d2b70eb1a5bf941bf3cd6998a22985`.
- `feature-discovery/api/src/app.ts` wires the existing private-target option
  to `FD_ALLOW_PRIVATE_TARGETS === '1'`. That variable was absent on Railway,
  so the option remains disabled. Its SHA-256 is
  `7ef77d5e26fc2376a21172424694163cd125befe8e8c3436fe8003ca0aa55588`.

| Changed source | Services rebuilt |
|---|---|
| Feature Discovery API, knowledge base, auth client/contracts | `fdapi` |
| Enterprise backend/web/orchestrator and shared executor/workflow packages | `backend`, `web`, `workflow-orchestrator` |
| Auth server/contracts/mailbox | `auth-invoke` |
| Ingest and shared executor/contracts | `ingest-results-query`, `ingest-consumer`, `ingest-consumer-priority` |

`beat` runs an unchanged standalone Node script using only the standard library;
its image did not need rebuilding. Databases and `ailabs-studio` were untouched.
The changed LocalStack initialization hook adds an auth-strategy table. Instead
of restarting its volatile state, the missing `monarch-auth-strategies` table was
created additively with `integration` HASH and `strategy` RANGE keys. It was
ACTIVE with zero items; the existing sessions table already had its required
`pk` HASH key. No table was deleted. A dedicated temporary Railway SSH key was
registered for this check and creation, then removed from Railway and disk;
`railway ssh keys list` subsequently reported no registered keys.

## Database and build checks

`pnpm install --frozen-lockfile --ignore-scripts` passed. The scoped root build
for the API, backend, auth server and ingest passed: **14 successful packages**,
9 cache hits. The local runtime was Node 22.23.2, which produced the expected
Node >=24 engine warnings; the Railway runtime Dockerfiles use Node 24 for
enterprise/auth/ingest and Node 20 for FD.

Existing repository migrators applied successfully before replacing services:

- FD: migration 0072 to 0088; eval-corpus seed inserted zero artifacts.
- Backend: existing `reconcileBenchMigrations` preserved the three historical
  benchmark ledger entries and filled the main-branch history they would have
  caused Drizzle to skip, then migrated through 0049. There were zero product
  credential accounts. The rate-sheet migration changed zero stored recipes.
- Ingest: the two pending migrations applied through
  `20260828142423_create_document_extraction`.

## Catalogue preservation and image-fixture repair

Before deployment and after migrations, `bench-seeds.sh status` reported
**47 products, 686 actions, 47 in sync**, with 47 grants and no missing/extra
grants. The web service was already FAILED with zero running replicas before
this session.

The first new FD image exposed stale untracked fixtures from the sibling
checkout: they still named the old direct ngrok front door. The live database
retained the hosted Studio URLs and frozen hashes, so all 47 image fixtures
reported out of sync even though `wb monarch verify` still passed its database
hash check. `GET /v1/seeds/bench-airtable/diff` identified the exact URL/domain
differences. This was fixture drift in the uploaded image, not a changed KB.

Existing hosted artifacts from `workflowbench/out/monarch-seeds` restored the
47 image folders, with the old folders preserved under the sibling's ignored
`local-docs/setup/state/bench-seeds-before-20260910`. A direct canonical-projection
comparison then found 46 matching product hashes. QuickBooks was the exception:
its local create/read deposit response templates predated two templates already
in the frozen database. Only those two image fixture templates were restored
from the read-only seed diff's `before` values. This recovered the existing
catalogue; no source task, simulator data, generator output, or database record
was changed by the repair.

Before the final FD upload, the same `projectSeed` and `hashProjection` functions
used by the FD API confirmed **47 of 47 image fixture hashes equal the live KB**.
For example, Airtable remained
`e4f5bbd27e7f0ae4b009c6933be5e742bdb31065edb34ded5f8e02d9638a3731`
and QuickBooks remained
`3872afc91d9c7295489da36608ce75682c53db00b63725dc495aa77b8a538efc`.
No KB import or config-hash change was needed. FD alone was rebuilt for these
image-fixture corrections.

## Final verification

All eight replaced services finished **SUCCESS**, with one running replica each.
The final FD deployment is `347b7b9a-26a3-4fc7-aadb-c8c620388a62`, image digest
`sha256:f8cdcdeea1b138bdcad4c7832e2b98a8f33d440bef7d23ff496489f68d69bb42`.
The final catalogue is **47 products, 686 actions, 47 in sync**, with all 47 grants
intact. A second canonical comparison confirmed all 47 image hashes still match
the database. The frozen KB configuration remained unchanged.

`uv run wb monarch verify` passed all six checks after that final deployment:
configuration, backend, session, knowledge base, front door, and Langfuse.
The public health checks returned HTTP 200. An isolated `agent-browser` session
rendered the web sign-in screen with its Email input and Next button; the
screenshot is at `workflowbench/out/railway-web-20260910.png` and the browser
session was closed.

The [machine-readable evidence](2026-09-10-merged-monarch-deploy-evidence.json)
records every previous/final deployment ID and digest, the working-tree digest
recipe, and all 47 recovered image-to-database hash comparisons. The initial
working-tree SHA-256 was
`ed0388aa04c374b8380451f2e3aa8d57cc2e81ff210a23458a21ae22478817f9`;
the final FD fixture repair produced
`292f12adc708c46496c35d2e98604e7ec952b9385046ada404408ccb0387c540`.

The deployment subtask launched no paid diagnostic. The parent subsequently ran
the requested single attempt; [its separate evidence](2026-09-10-post-deploy-diagnostic.md)
shows successful application routing and Monarch workflow completion, zero
writes on the preserved filter trap, and a WorkflowBench price-table refusal.
The existing `bench-seeds.sh status` state-file header still describes the older
September 8 seed deployment; the live HTTP catalogue and recorded hashes above
are the verification evidence for this upload. Future FD uploads must retain
these recovered image fixtures, rather than copying the stale generator output
over QuickBooks again.
