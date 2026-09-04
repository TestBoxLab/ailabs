# Contract: configuration files added or changed by feature 002

Extends `specs/001-declarative-benchmark-config/contracts/config-files.md`.
Shipped examples are the contract's executable form.

## harnesses/monarch.yaml (changed)

```yaml
name: monarch
kind: monarch
accepts: none
runnable: true
base_url: ${MONARCH_URL}                 # http://localhost:4174
credential_env: MONARCH_TOKEN            # set -> login skipped
login_email: dev-root@testbox.com
login_password_env: MONARCH_PASSWORD     # seeded default: monarch-dev
fd_url: ${MONARCH_FD_URL}                # http://localhost:3001
fd_api_key_env: FD_API_SHARED_SECRET     # optional; the Railway deployment has the gate on
shim_port: 9105                          # front door on the host, fixed
shim_public_host: host.docker.internal   # Monarch in Docker on this machine
shim_public_url: ${FRONT_DOOR_URL}       # optional: the front door's full public URL (a tunnel) when Monarch runs elsewhere
langfuse_url: ${LANGFUSE_URL}            # http://localhost:3000
langfuse_public_key_env: LANGFUSE_PUBLIC_KEY
langfuse_secret_key_env: LANGFUSE_SECRET_KEY
price_table: monarch-team-bedrock
monarch_repo: ../../../monarch           # relative to workflowbench/, or absolute
modes: [create-run]                      # full-flow and run-only return in 003/004
description: The product under comparison, driven through its own API. Version read from the checkout.
```

Rules: `release` is gone and rejected if present. One of `credential_env` or
`login_password_env` must be set in the environment at run time. The fixed
reply to questions is not a field.

`fd_api_key_env` and `shim_public_url` are optional. When `fd_api_key_env` names
a variable that is set, every `/v1/*` call to the discovery service carries
`x-fd-api-key: <value>`; the Railway deployment has that gate on for every
`/v1/*` route (`/health` is open), a local deployment has no gate (verified
4 Sep 2026). `shim_public_url` overrides `shim_public_host:shim_port` when the
front door is reached through a tunnel, and its host is what the generated
seeds name as their domain.

## models/monarch-team-bedrock.yaml (new, kind price-table)

```yaml
name: monarch-team-bedrock
kind: price-table
provider: bedrock
region: us-west-2
prices_verified: 2026-09-03
description: Bedrock prices for the models Monarch's authoring and engine may call.
models:
  - family: claude-opus-4-8
    match: [opus-4-8]
    usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}
  - family: claude-opus-5
    match: [opus-5]
    usd_per_million: {input: 0, cached: 0, cache_write: 0, output: 0}   # filled at implementation
  - family: claude-sonnet-5
    match: [sonnet-5]
    usd_per_million: {input: 0, cached: 0, cache_write: 0, output: 0}
  - family: claude-sonnet-4-6
    match: [sonnet-4-6]
    usd_per_million: {input: 0, cached: 0, cache_write: 0, output: 0}
  - family: claude-haiku-4-5
    match: [haiku-4-5]
    usd_per_million: {input: 0, cached: 0, cache_write: 0, output: 0}
```

Rules: `kind: price-table` files are skipped by `load_models` (they are not
competitors) and by `wb doctor`'s provider checks. Every entry needs all four
prices; `match` non-empty; families unique. Loaded by `load_price_table`.

## products/simulated-apps.monarch-kb.yaml (new, written by `wb monarch setup`)

```yaml
product: simulated-apps
generated_at: 2026-09-04T12:00:00Z
seeds_format: public-api-seeds@1
shim_public_url: http://host.docker.internal:9105
kb:
  bench-airtable: 6d07bde6f1c2…
  bench-asana: 272673e3a9b0…
  # … 47 entries, one per service of the product, sorted by slug
```

Rules: exactly the product's services, each prefixed `bench-`; hashes are the
strings Monarch's discovery service returned. Hand edits are pointless: the
run re-reads Monarch and refuses on drift.

## plans/pilot-monarch-create-run.yaml (new)

```yaml
name: pilot-monarch-create-run
description: Paired pilot, Monarch vs Claude Opus 4.8 raw, with the answer key. Internal.
tasks: tasks
mode: create-run
repetitions: 2
timeout_s: 900
concurrency: 4
competitors:
  - {harness: oracle}
  - {model: claude-opus-4-8, harness: api}
  - {harness: monarch}
baseline: claude-opus-4-8/api
audience: internal
cost_ceiling_usd: 15
approved_by: null          # Carlos approves the specific run before it starts
```
