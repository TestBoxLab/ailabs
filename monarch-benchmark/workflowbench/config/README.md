Benchmark inputs as YAML, one file per entry, in four kinds: `products/`, `models/`, `harnesses/`, `plans/`. Field tables and examples: `specs/001-declarative-benchmark-config/contracts/config-files.md` (repo root), extended by `specs/002-monarch-create-run/contracts/config-files.md` for the Monarch harness, the price-table kind, the knowledge-base hash file and the pilot plan below.
Values like `${MONARCH_URL}` are placeholders expanded by the harness at launch, not by the loader.

## harnesses/monarch.yaml

The Monarch competitor is runnable. Beyond the fields every harness has, it
carries: Monarch's own address and credential, the discovery-service address,
the front door's fixed port (so Monarch's containers can reach the bench's
simulated apps), the tracing-service (Langfuse) address and keys, and the
price-table name. Field-by-field table and a full example:
`specs/002-monarch-create-run/contracts/config-files.md`.

Two fields are optional and only matter when Monarch runs somewhere other than
this machine. `fd_api_key_env` names the variable holding the discovery
service's key: when it is set, every `/v1/*` call sends `x-fd-api-key`, which
the Railway deployment requires and a local one ignores. `shim_public_url`
gives the front door's full public address (a tunnel) instead of
`shim_public_host:shim_port`; its host is also the domain the generated seeds
name, so a change there means rerunning `wb monarch setup`.

## models/*.yaml, kind: price-table

A model file can carry `kind: price-table` instead of describing a single
competitor model. It lists several model families with cloud-provider prices,
for pricing a competitor (like Monarch) that calls more than one model
internally. `wb doctor` and `load_models` skip these files; they are read
separately by `load_price_table`. Example: `models/monarch-team-bedrock.yaml`.

## products/<name>.monarch-kb.yaml

`wb monarch setup --product <name>` writes `products/<name>.monarch-kb.yaml`: the
knowledge-base hash of every simulated app after the discovery service imported it,
plus the front-door URL those seeds point at. `wb run` refuses a Monarch competitor
without it, and refuses again if the hashes have drifted. The file is committed only
after the setup has run against a live Monarch, so it is absent until then.

## plans/pilot-monarch-create-run.yaml

The paired pilot plan for feature 002: `create-run` mode, the 10 pilot tasks, 2
repetitions, competitors {answer key, Claude Opus 4.8 raw, Monarch}, internal
audience, a cost ceiling, `approved_by` left empty until Carlos approves the
specific run. Full example: `specs/002-monarch-create-run/contracts/config-files.md`.
