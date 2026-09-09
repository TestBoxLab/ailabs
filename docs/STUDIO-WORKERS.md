# Trusted Studio workers

The coordinator owns jobs, the weekly budget ledger, run reservations, worker claims, provider admissions, and final evidence. Workers access it through authenticated HTTP RPC; SQLite files must stay on the coordinator's local durable volume.

Run these commands from `monarch-benchmark/workflowbench`. Use the identical source revision and dependencies on every host. Worker claims verify a digest of the execution Python sources. Operators must also keep rate-card/configuration files consistent.

Every web instance, preview, experiment harness, and paid CLI launcher must use the same canonical weekly ledger. `STUDIO_LEDGER_PATH` explicitly selects that file for local Studio and worker coordinators, even when `STUDIO_DATA_DIR` isolates preview artifacts. Without this override, a data directory selects its own research ledger; do not treat a fresh preview ledger as a new weekly allowance. CLI launchers must use their ledger configuration/argument to select the same file. Remote workers use the coordinator ledger over RPC and never mount that SQLite file. The isolated gateway test hook ignores the override.

Coordinator environment:

```powershell
$env:STUDIO_EXECUTION_MODE = 'workers'
$env:STUDIO_LEDGER_PATH = 'C:/Users/Lucas Wakigawa/Documents/AILabs/research/budget.sqlite3'
$env:STUDIO_WORKER_TOKEN = '<operator-provisioned secret>'
$env:STUDIO_MAX_RUNS = '4'
$env:STUDIO_MAX_AGENTS = '8'
$env:STUDIO_PROVIDER_LIMITS = '{"openai":{"concurrency":2,"requests_per_minute":30,"tokens_per_minute":100000}}'
& .venv/Scripts/python.exe -m wb_studio.app --host 127.0.0.1 --port 8765
```

Publish the coordinator behind an HTTPS reverse proxy for remote hosts, using the existing Studio public-host and browser-auth settings. Worker RPC uses its own Bearer credential and does not use browser Basic authentication or CSRF tokens. The credential grants trusted operator capabilities; evaluated agents must never receive it. Loopback HTTP is allowed only for local development.

Worker environment:

```powershell
$env:STUDIO_WORKER_TOKEN = '<same operator-provisioned secret>'
$env:STUDIO_COORDINATOR_URL = 'https://your-coordinator.example'
$env:STUDIO_WORKER_DATA_DIR = 'C:/studio-worker-evidence'
& .venv/Scripts/python.exe -m wb_studio.worker --worker worker-01
```

Each worker process claims one run at a time. Start additional processes with distinct worker names to use more machines or process capacity. `--once` processes at most one queued job and exits. Provider credentials belong on the worker host; budget reservation, dispatch claims, provider concurrency, requests per minute, and optional conservative tokens per minute are enforced centrally. Tokens are not refunded on completion without verified usage. A run's requested agent concurrency reserves that many coordinator slots throughout its claim; the UI labels these allocated slots, not observed active agents.

Each claim receives the frozen task inputs and versioned architecture/product-graph files needed by the job. Native runs additionally require the matching accepted native image and source-bound acceptance record on the coordinator and each participating worker. `STUDIO_NATIVE_RUNTIME_DIR` selects each host's local native runtime directory. Remote worker native capability discovery is not implemented; the coordinator's readiness display reflects its own verified installation. Enterprise front-door routing must be configured for the worker's environment.

Workers heartbeat while executing, forward events and job progress, and upload hashed artifacts before publishing final completion. Uploaded result links are rebased to coordinator evidence paths. Artifact chunks and completed requests are idempotent. Local worker evidence is retained after execution and connection failures; operators should manage that directory's retention after confirming central evidence.

Queued unclaimed jobs survive restarts. A lost or expired worker claim becomes interrupted and is never reassigned automatically. Late claims, cached dispatch acknowledgements, and new provider admissions are rejected after fencing. Unknown billing and provider admissions remain held after worker loss; unused reservations are conservatively retained until operator reconciliation establishes that no request can still dispatch. This may reduce available budget or capacity until reconciliation. There is no automatic paid retry or resume.

Verification is offline: the regression suite launches two actual worker processes over loopback HTTP, runs distinct scripted outcomes, verifies central evidence manifests and portable result links, and checks shared admission, cancellation, lease loss, artifact validation, and scoped billing. This is local multi-process evidence, not a paid or cross-machine deployment acceptance result.

## Operator recovery after a lost claim

1. Stop the lost worker process and its evaluated containers, and establish that it cannot restart with the old claim. Keep the job interrupted; do not delete the claim or change its state back to active. Preserve local worker evidence and take a consistent backup of the coordinator job directory and SQLite ledgers.
2. Identify the interrupted job, its worker, and its request reservations. On the coordinator, `BudgetLedger.reservations(scope_id=job_id)` lists request IDs, dispatch timestamps, maximum holds, and any recorded actual cost. Match those request IDs to provider receipts. Do not infer zero cost from a timeout, missing response, dead process, or missing worker file.
3. Apply `BudgetLedger.settle(request_id, verified_actual_usd)` only for receipt-backed costs, or confirmed zero-cost requests that never dispatched. Leave an unknown request unsettled (or settle with `None`, which retains its maximum hold). Record the receipt and operator reasoning in repository evidence.
4. Only after the worker has been fenced and no remaining request can dispatch, call `BudgetLedger.finish_run(job_id)` to release unallocated envelope capacity. This preserves unknown request holds and does not replay the job.
5. Inspect `workers.sqlite3` admissions for that exact job. Set `released=1` only for individually verified terminated provider requests, inside a local SQLite transaction; retain any unresolved admission. Do not delete admission rows: their timestamps and token estimates continue enforcing the one-minute window. Never bulk-release every interrupted worker's admissions based solely on heartbeat expiry.
6. Verify the budget status, provider admission counts, interrupted job history, and preserved evidence. If a deliberate replication is needed, create a new run with its purpose and parent links instead of resetting the old job.

There is no automatic reconciliation command that can establish these external billing and process facts. Unresolved admissions and billing remain held by design.

## Reproduce offline validation

```powershell
& .venv/Scripts/python.exe -m pytest tests/test_studio_workers.py -q --tb=short
```

Observed 2026-09-08: **52 passed in 23.08 seconds**. This command includes the two-real-worker-process integration check and makes no paid provider calls.
