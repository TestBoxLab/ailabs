# Git configuration activation: verification record

Date: 2026-09-11. Scope: US3 / FR-09 through FR-11 in [spec.md](spec.md).

## Hosted access is still blocked

Read-only checks at **2026-09-11 03:05:13 UTC** used the credential already
configured in `monarch-dev / production / ailabs-studio`. The Railway response
and token stayed in process memory; no secret values were printed or saved.

| Check | Observed result |
|---|---|
| `WB_CONFIG_GITHUB_TOKEN` | Present |
| `WB_CONFIG_REPOSITORY` | `TestBoxLab/ailabls-benchmark-config` |
| `WB_CONFIG_SNAPSHOT` | Enabled |
| GitHub `GET /user` with that token | HTTP 200 |
| GitHub `GET /repos/TestBoxLab/ailabls-benchmark-config` | HTTP 404 |
| GitHub `GET /repos/TestBoxLab/ailabls-benchmark-config/git/ref/heads/main` | HTTP 404 |

The token authenticates but cannot read the required repository. These responses
do not identify whether organization approval or repository selection is missing;
neither read nor write permission has been verified. No remote save, variable
change, deployment or benchmark launch was performed. The snapshot remains active.

A subsequent deployment audit found another prerequisite: deployment
`cafadef9-7a17-492a-a534-a92b0d0ad070` does not contain the feature-013 client or
editor. Its authenticated `GET /api/benchmark-config` returns HTTP 404. The
snapshot variable is configured, but the current hosted application cannot expose
that catalog until the integration is deployed. The implementation verified below
is in the local feature worktree. Import it while preserving the hosted fixes;
do not replace the service with an unrelated full worktree upload.

Resolved later in this session: deployment
`2f14a3ee-c5a0-429f-a6c5-88a52a1a0560` includes the integration while preserving
the hosted fixes. Authenticated `GET /api/benchmark-config` now returns HTTP 200,
41 files at `cecb7e4f8291e02a43082fe8d67e9420b07347f4`, and `writable=false`.
The hosted Settings browser check confirms read-only fields and disabled Save.
The GitHub-access blocker remains; no remote commit or source switch was made.
See the [deployment record](../../../monarch-benchmark/docs/rounds/2026-09-11-studio-run-controls.md).

## Existing implementation verified offline

No additional production code is necessary for the already implemented Git
editor path. `wb_orchestrator/config_repository.py` reads complete immutable
revisions, validates changes using existing loaders and saves directly to `main`
through a non-forced ref update. Its snapshot fallback refuses edits explicitly.
Historical configuration bytes are restored independently of current Git access.

From `monarch-benchmark/workflowbench/`:

```powershell
uv run python -m pytest tests/test_config_repository.py tests/test_config_repository_execution.py tests/test_studio_benchmark_config.py -q
```

Result: **47 passed in 29.32 seconds**. Coverage includes atomic saves, conflicts,
ambiguous save acknowledgement, immutable snapshots, tamper detection, invalid
configuration, explicit repository failure, source/hash drift and offline restore.

Browser verification used the offline `tests/browser/server.py` fixture on port
8773 and `tests/browser/benchmark-config.cjs`, with an isolated `config-activation`
browser session. Desktop and 390px layout checks passed. The editor journey
verified invalid YAML refusal, warnings, create/delete, multi-file validation and
diff/save, conflict and network-error draft retention, operator readiness and a
pinned explicit launch request. Configuration HTTP responses in this browser
fixture are mocked; this is **not** evidence of a live GitHub commit or hosted
write permission. The fixture launches no paid competitor.

## Complete activation when repository access is granted

1. Repeat the credential-scoped read checks above and load/validate the full Git
   catalog. Verify approved repository identity and record the exact main commit.
2. Verify there is no queued, running or draining work before changing the source.
   Preserve `WB_CONFIG_SNAPSHOT`'s file and record its previous setting for rollback.
3. Remove the snapshot environment override and deploy the reviewed application
   with `WB_CONFIG_REPOSITORY` and its server-only token intact.
4. In the hosted editor, verify read, edit, validation, diff, direct-main save,
   refresh and concurrent-edit refusal. Use a harmless documented configuration
   documentation edit and verify its actual resulting commit; do not change tasks
   or seeds for an access probe.
5. At that commit, compare CLI and Studio resolved configuration hashes and
   inputs. Confirm an earlier preview and a historical run retain their original
   revision and bytes, and verify credential/network failures retain the draft.

Do not mark US3 live activation complete until those hosted checks pass. No paid
run is required for activation verification.
