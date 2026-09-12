# Independent Genesis repair service

Status: local control API, recovery UI, authenticated GitHub reader, funded native
worker and complete patch transfer are implemented and validated locally. Both
container images build and pass offline runtime checks. Hosted deployment,
private-repository credentials, outage funding and release/rollback remain unfinished.
The latest checkpoint below supersedes earlier implementation-status notes.
Lucas expanded the objective on 11 September 2026 to include internet research,
GitHub access to both repositories, and repair availability during Studio outages.

## Verified starting point

Studio currently hosts the model loop, voice sideband and daily engineer job in
its own process. `genesis_engineer.implement` creates an isolated git worktree,
reserves paid usage, runs Codex, captures the diff and independently runs an
allowlisted verification command. It returns a proposal; it does not publish.
`code_index` already supports both `lab` and `monarch` with five typed read tools.
The local GitHub account can read TestBoxLab/ailabs and TestBoxLab/monarch. This
machine's login is not a credential provisioning mechanism for a hosted service.

## Required deployment boundary

The repair service needs its own independently versioned deployment, durable job
storage, health endpoint and authenticated operator endpoint. It must start without
importing or contacting the Studio app. A Studio outage must not prevent reading
job progress, submitting an explicitly authorized repair, retrieving repository
code, or checking the deployed revision. The operator endpoint needs an independent
URL; an embedded Studio panel alone is unavailable when Studio is down.

Studio submits bounded jobs with an idempotency key, actor, repository alias,
expected base commit, requested change, verification requirements and existing
spend authorization. The service persists acceptance before execution. A repeated
request returns the same job. Restart distinguishes interrupted execution from
success and never repeats a possibly published action without reconciliation.

Keep GitHub and deployment credentials in this service, outside agent worktrees.
Use a GitHub App installed only on the two named repositories, with scoped,
short-lived installation tokens. Repository content permissions allow branch edits;
pull-request permissions allow review artifacts. Publication credentials belong to
a separate release operation, not arbitrary shell commands in an agent workspace.

Reuse existing verified budget accounting, native harness execution, isolated
worktrees and verification evidence. Do not create an unmetered second model loop.
Protect benchmark worlds, tasks, assertions and stored scientific records even if
a requested UI repair touches nearby source files. A candidate release must name
its exact source commit, changed services, validation, observed healthy revision
and rollback target. Studio and repair-service releases must remain independent.

## Implementation order and acceptance

1. Extract a repair job contract and durable store with duplicate-submission and
   restart tests; avoid importing Studio at service startup.
2. Connect the existing engineer executor through the job boundary, retaining
   billing reservations, usage uncertainty and actual command exit evidence.
3. Add GitHub App provisioning and repository access at pinned commits. Verify
   refusal for repositories outside the installation and paths outside worktrees.
4. Add a separately authenticated recovery endpoint and independently deployable
   service image. Kill Studio during an accepted job and verify progress remains
   accessible, then restart the repair service and verify recovery.
5. Integrate Genesis tool calls and the existing UI with durable job receipts.
   Prepare a scoped candidate release against current deployed art and approved
   billing behavior; do not deploy the shared dirty workspace wholesale.
6. Verify real web discovery, cited answers, memory recall after refresh, first
   navigation timing, first useful audio timing, and an isolated UI repair with
   observed deployment and rollback. Offline tests do not establish these results.

## Primary references inspected

- [GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)
- [Installation access token API](https://docs.github.com/en/rest/apps/apps)
- [Railway healthchecks](https://docs.railway.com/deployments/healthchecks): deployment
  readiness does not provide ongoing monitoring; attached-volume deployments can
  still have downtime. Separate services do not guarantee immunity to a provider outage.


## Local implementation checkpoint

`wb_repair` now imports and starts independently of all Studio modules. Its SQLite
job store persists acceptance, deduplicates identical requests across restart,
refuses conflicting idempotency-key reuse, claims a job for exactly one worker,
and protects terminal transitions with worker ownership. A stale heartbeat does
not requeue work. Supervisor-confirmed worker exit can mark it interrupted without
replay. Execution receipts stop at awaiting_review, not published.

The authenticated HTTP API provides `/health`, `POST /jobs`, `GET /jobs/<id>` and
`GET /repos/{lab|monarch}`. Authentication derives the actor from an access-key hash;
request bodies cannot supply another actor. Repository aliases are fixed. Genesis
has typed `request_repair`, `repair_status` and `repository_read` tools with stable
retry keys and per-person credentials. No service URL comes from model arguments.

GitHub reads use App JWTs signed with RS256 and short-lived installation tokens
requested with Contents read access for one named repository at a time. Tokens are
cached until near expiry. Reads resolve the current default-branch commit, then
require its full SHA for paged UTF-8 source or directory reads. Credential paths,
non-source binary files and arbitrary repositories are refused. Retrieved code is
internal evidence, never authorization. No GitHub credential has been provisioned,
created or copied from the development machine.

The separate Dockerfile copies only the recovery package. Configuration:
- `GENESIS_REPAIR_DATA`: durable data directory, default `/data`.
- `GENESIS_REPAIR_KEY_HASHES`: JSON mapping authenticated actor names to SHA-256
  access-key hashes; use distinct high-entropy keys.
- `GENESIS_REPAIR_REVISION`: exact independently deployed source revision.
- `GENESIS_GITHUB_APP_ID`, `GENESIS_GITHUB_INSTALLATION_ID`,
  `GENESIS_GITHUB_PRIVATE_KEY_FILE`: service-only GitHub App configuration.
- Studio uses `GENESIS_REPAIR_URL` and `GENESIS_REPAIR_ACTOR_KEYS` (JSON mapping its
  authenticated `human:<name>` values to the corresponding service keys).

### Verification

`uv run python -m pytest tests/test_repair_jobs.py tests/test_repair_server.py tests/test_genesis_repair.py tests/test_repair_github.py -q`
passed **19 checks in 1.59 seconds**. Real local HTTP requests exercised the recovery
API; GitHub provider calls were mocked. A separate isolated Python import confirmed
no `wb_studio` module was loaded. No Docker build or hosted acceptance was claimed.

| Requirement slice | Exact evidence |
|---|---|
| Durable repair acceptance | `test_duplicate_submission_survives_restart_and_conflicting_reuse_refuses` |
| Concurrent workers do not duplicate execution | `test_concurrent_acceptance_and_claim_execute_a_request_once` |
| Restart does not silently replay uncertain work | `test_running_job_survives_restart_and_old_heartbeat_without_replay` |
| Actor authentication and job ownership | `test_unauthorized_or_forged_actor_cannot_submit`, `test_health_and_repair_roundtrip_work_without_studio` |
| Retry after an uncertain network outcome | `test_unknown_acceptance_retains_retry_identity` |
| GitHub scopes and credential renewal | `test_installation_tokens_are_repository_scoped_readonly_and_renewed` |
| Code provenance and paged source reads | `test_head_resolution_and_paged_file_reads_name_exact_commit` |
| Repository/path boundaries | `test_unsafe_or_credential_paths_refuse_before_token_minting`, `test_unpinned_commit_and_binary_files_are_not_read_as_source` |

### Remaining integration, not a completion claim

The service reports `execution_enabled: false`. No executor is wired to accepted
jobs yet. Connecting the paid executor requires a verified shared spending
reservation that survives a Studio outage; a second independent weekly SQLite
ledger would incorrectly duplicate the weekly allowance. Implement reservation
transfer and reconciliation before enabling paid execution. Existing reservations
must retain uncertain charges until remote execution evidence settles them.

Still required: worker supervision and isolated verification, independently usable
recovery UI, GitHub App installation, hosted configuration and deployment, release
and rollback operations, general internet discovery, and measured live acceptance
of fast answers, navigation, durable memory, refresh and a real UI repair. The
current API and read adapter alone do not fulfill autonomous live repair.


## Funding transfer checkpoint

`repair_funding.issue` now reserves and claims one immutable execution liability
in the original shared budget ledger before signing a remote grant. The grant binds
actor, job, specification hash, model, effort, cap, reservation and expiry. Retrying
returns the same grant and does not reserve more money. A closed scope cannot be
reopened. These helpers are not yet called automatically by Genesis; execution
remains disabled until the worker integration is complete.

`POST /jobs/<id>/funding` verifies the signature with the service-only
`GENESIS_REPAIR_FUNDING_KEY`, matches the authenticated actor and stored job, and
stores one reservation per job. A funded-only worker claim ignores unfunded and
expired jobs. A reservation cannot fund two jobs. Terminal reconciliation preserves
unknown liability, and a known charge requires usage evidence. No signing key or
funding authorization was configured in production during this work.

The complete repair test command now passes **27 tests in 2.52 seconds**:
`uv run python -m pytest tests/test_repair_funding.py tests/test_repair_jobs.py tests/test_repair_server.py tests/test_genesis_repair.py tests/test_repair_github.py -q`.

Additional exact evidence:
- `test_funding_reserves_once_and_survives_source_restart`
- `test_grant_cannot_change_actor_job_spec_or_amount`
- `test_unknown_remote_cost_keeps_full_liability_after_terminal_receipt`
- `test_verified_cost_releases_only_unused_reserved_capacity`
- `test_only_funded_jobs_are_claimed_and_reservation_cannot_fund_two_jobs`
- `test_funding_endpoint_requires_signed_owner_and_job_specific_allowance`
- `test_wrong_receipt_or_missing_usage_cannot_release_reserved_money`
- `test_expired_funding_does_not_allow_a_worker_to_start`

The next implementation must connect a separately isolated worker to funded jobs,
reuse native execution and independent verification, and keep control-service
GitHub/signing credentials out of the agent environment. A funding test is not
proof that a provider's paid execution is capped or that a repair is deployed.


## Worker execution checkpoint

The remote worker now claims only funded, unexpired jobs, persists its claim request
before sending it, and reuses the original job/token after a lost claim response.
It supervises one executor subprocess while sending heartbeats. Finished results
stay in a durable outbox until the control service acknowledges them; a lost finish
acknowledgement retries the same receipt without rerunning the executor. Restart
with an uncertain dispatch leaves the job for supervisor reconciliation instead of
assuming the process stopped. A filesystem lock prevents two worker entry points
from owning the same recovery directory.

`wb_repair.executor` now reuses `genesis_engineer.implement` with an explicitly
configured repository mirror, model/effort from the signed grant, operator-owned
verification command and a per-job ledger limited to the amount already reserved
at the source. The native executor retains the complete patch and SHA-256 on the
worker, reports provider usage, and runs verification independently after the agent
finishes. Protected benchmark/credential paths prevent a verified repair result.
The source checkout is never overwritten by this workflow.

Genesis exposes `start_repair` after queueing. It honors the engineering dial and
existing allowance checks, persists the signed funding grant, and reconciles a
terminal `repair_status` receipt into the original ledger. It does not publish.

Verification command:
`uv run python -m pytest tests/test_genesis_repair.py tests/test_repair_executor.py tests/test_repair_worker.py tests/test_repair_jobs.py tests/test_repair_server.py tests/test_repair_funding.py tests/test_repair_github.py tests/test_genesis_engineer.py -q`
passed **70 tests in 6.30 seconds** before the additional worker lock. The focused
worker suite then passed **5 tests in 1.98 seconds**, including the Windows lock.

New exact evidence:
- `test_worker_runs_subprocess_and_retries_lost_finish_ack_without_reexecution`
- `test_lost_claim_response_recovers_same_job_and_token`
- `test_restart_does_not_replay_an_executor_whose_status_is_unknown`
- `test_control_credentials_do_not_cross_executor_environment`
- `test_prepaid_native_executor_writes_patch_and_independently_verifies_it`
- `test_protected_benchmark_changes_cannot_be_offered_as_verified_repair`
- `test_genesis_dispatch_and_terminal_status_share_one_original_reservation`
- `test_disabled_engineering_does_not_reserve_or_dispatch_repair`
- `test_only_one_worker_can_own_a_recovery_directory`

The native executor test uses a real Git repository, worktree and verification
subprocess with a fake Codex executable. Its assertion fails on the original source
and passes on the changed worktree. It verifies patch content/hash, usage-derived
cost, unchanged source checkout and worktree cleanup. It makes no paid model call.

Worker configuration adds `GENESIS_REPAIR_WORKER_KEY` and a matching control-service
`GENESIS_REPAIR_WORKER_KEY_HASH`; separate durable worker storage; repository mirrors
`GENESIS_REPAIR_REPO_LAB` / `GENESIS_REPAIR_REPO_MONARCH`; and JSON argv verification
commands `GENESIS_REPAIR_VERIFY_LAB` / `GENESIS_REPAIR_VERIFY_MONARCH`. The executor
subprocess does not receive GitHub App, funding, actor or worker control keys.
Deployment isolation must also prevent those files from being mounted or readable;
an environment-variable test alone does not prove filesystem isolation.

The worker Dockerfile pins Codex CLI 0.153.4, matching the installed local version.
A source-only image build is in progress. No hosted configuration, paid repair,
GitHub App installation, independent recovery UI, full artifact download, live
release or rollback has been completed. The native CLI's actual spend can exceed
an estimate; funding accounting retains overruns rather than claiming a hard
provider-side dollar cap.


## Container and hosted-access validation

The final integrated offline command passed **71 tests in 9.85 seconds**. The first
worker image built successfully, but its runtime smoke test failed because the
model catalog was absent. The Dockerfile now includes `config/models`, Playwright
1.62.1 and its Chromium runtime, and preserves browser settings in the executor
environment. Codex remains pinned to 0.153.4.

The rebuilt image completed all build steps and exported manifest list
`sha256:99d28b3af44efe178acf1bacf5435ca92af11c8b1c9b5eb4345864b12a681138`, but Docker
Desktop lost its engine connection while unpacking. Build exit was 1; subsequent
image inspection returned HTTP 500. This is **not a successful container smoke
test**. Docker backend processes remain present and the C drive has over 200 GB
free. No shared Docker service or existing container was restarted or deleted.
The isolated source-only build context is recorded in the ignored
`.tmp/genesis-worker-build-context.txt`. The container runtime and browser smoke
tests remain pending until Docker answers reliably.

Read-only Railway inspection found an existing `WB_CONFIG_GITHUB_TOKEN`. Its value
was neither printed nor persisted. Repository metadata checks using it returned
200 for TestBoxLab/ailabs and 404 for the known-private TestBoxLab/monarch. Therefore
this hosted credential does not establish the required Monarch access. No hosted
credential was copied, replaced, or broadened, and no service was deployed.


## Latest checkpoint: independent UI and complete patches (11 September 2026)

The independent `/` page authenticates with a per-actor recovery key, lists only
that actor's latest 50 jobs, resolves the fixed repository's current full commit,
queues an idempotent specification, shows its receipt and downloads a complete
patch. The UI uses self-hosted Studio Plex fonts and the existing paper/ink/red
style. It does not import or fetch Studio. The key is memory-only, cleared on
refresh/disconnect. The page never presents queue acceptance as execution or
verification as release. It currently offers queue/review operations, not a
funding or release button.

Patch bytes are stored immutably in SQLite, limited to 8 MB, authenticated by the
claiming worker and checked against SHA-256. Actor-only downloads return the
complete artifact. A review-ready terminal receipt requires the matching stored
patch. Upload and terminal-ack retries do not rerun execution. The native executor
captures `git diff --cached --binary` as bytes; replacement decoding is used only
for the short display preview, preserving binary and non-UTF-8 source changes in
the artifact. Oversized/missing/mismatched patches remain in the worker outbox for
operator attention; automatic large-artifact storage is not implemented.

Evidence:

- `test_patch_download_requires_owner_and_exact_immutable_upload`: owner-only
  downloads, worker-only upload, wrong hash/token refusal, immutable retries,
  complete payload beyond the preview limit and actor-scoped job listing.
- `test_review_requires_complete_patch_matching_receipt`: missing artifact cannot
  transition to review-ready.
- `test_worker_runs_subprocess_and_retries_lost_finish_ack_without_reexecution`:
  real subprocess and HTTP transfer, complete stored patch, one execution despite
  lost acknowledgement.
- `test_prepaid_native_executor_writes_patch_and_independently_verifies_it`: real
  isolated Git worktree with a fake local Codex process, independent verifier,
  complete patch applied to a clean clone, exact binary/non-UTF-8 bytes, cost
  receipt and unchanged source checkout. Git's newline policy is explicitly
  disabled for clone/apply in this byte-level portability check.
- `test_recovery_page_and_assets_work_without_studio_or_auth`: public static shell,
  same-origin CSP and fixed asset allowlist. Authentication is still required for
  private job data and changes.
- `.tmp/recovery-browser.cjs`: real Chrome, 1440 px desktop and 390 px mobile;
  authentication error/success, source resolution, queue/retry, refresh, receipt
  focus, disconnect, no horizontal overflow, no key in persistent browser storage.
  Screenshots: `.impeccable/review/recovery/{desktop,mobile}.png`. Synthetic local
  data is explicitly labeled. Two visual rounds only. Independent finish reviewer
  scored connected-state clarity and receipt focus/visibility resolved; its ship
  verdict covers those two fixes. The detector ran in degraded regex mode (no
  findings; computed contrast was not checked). Recovery design is documented in
  `wb_repair/DESIGN.md`, preserving the historical root design document.

Both builds used the existing explicit source-only staging directory under `.tmp`.
No local credentials or runtime data were added. The existing vendored benchmark
package was copied unchanged to satisfy imports, not acquired or adopted for any
benchmark round. No evaluated run, provider model request, push or deployment was
performed.

Built control image `ailabs-genesis-repair:20260911`:
`sha256:e9469fbc2e0e5d4eac219a62172b3c68241d4ca950c113ff41cacb38f5533ada`.
With `--network none`, it served the final UI, health and authenticated queue while
`/app/wb_studio` was absent. Built worker image `ailabs-genesis-worker:20260911`:
`sha256:158f4ded343adcbb229dd65792b85bafd9b647a25c45d9cdaaa422e69f91f33f`.
Offline runtime smoke imported the native executor, loaded 10 configured models,
and launched Chromium to click a page control. Codex is pinned to 0.153.4 and
Playwright to 1.62.1. Earlier Docker daemon failures recovered without restarting
or killing shared containers.

Remaining requirements are explicit: deploy/version the independent service and
worker with durable volumes; provision scoped credentials for both repositories
(the existing hosted token cannot read private Monarch); supply operator-owned
mirror/verification configuration; reserve a recoverable emergency allowance in
advance so a new paid repair can start while Studio is down; implement reviewed
release and rollback; run an observed hosted outage/recovery exercise. These
local tests do not establish those outcomes. The broader Genesis goal also still
needs general web discovery, broader grounded spoken answers, and measured live
latency/memory/navigation acceptance. Existing public URL reading is not search.

Final focused regression command (from `monarch-benchmark/workflowbench`):

```text
uv run python -m pytest tests/test_genesis_repair.py tests/test_repair_executor.py tests/test_repair_worker.py tests/test_repair_jobs.py tests/test_repair_server.py tests/test_repair_funding.py tests/test_repair_github.py tests/test_genesis_engineer.py -q
```

Result: **74 passed in 8.46 seconds**, exit 0. Earlier failures were resolved;
the final result includes the raw-byte patch and Windows newline fixture fixes.
