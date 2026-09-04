Benchmark inputs as YAML, one file per entry, in four kinds: `products/`, `models/`, `harnesses/`, `plans/`. Field tables and examples: `specs/001-declarative-benchmark-config/contracts/config-files.md` (repo root), extended by `specs/002-monarch-create-run/contracts/config-files.md` for the Monarch harness, the price-table kind, the knowledge-base hash file and the create + run pilot plan, and by `specs/004-monarch-run-only/contracts/config-files.md` for run-only mode, the recipes file and the run-only pilot plan.
Values like `${MONARCH_URL}` are placeholders expanded by the harness at launch, not by the loader.

## harnesses/monarch.yaml

The Monarch competitor is runnable. Beyond the fields every harness has, it
carries: Monarch's own address and credential, the discovery-service address,
the front door's fixed port (so Monarch's containers can reach the bench's
simulated apps), the tracing-service (Langfuse) address and keys, and the
price-table name. Field-by-field table and a full example:
`specs/002-monarch-create-run/contracts/config-files.md`.

`modes` now lists `[create-run, run-only]` (full-flow returns later). Nothing
else on this file changes for run-only: the recipes file below is found next
to the product file by name, the same way the knowledge-base file already is.

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

## products/<name>.monarch-recipes.yaml

`wb monarch recipes --product <name>` writes `products/<name>.monarch-recipes.yaml`:
one known-correct workflow per task — the workflow id, the recipe version Monarch
authored, and how many attempts it took — plus a `missing` list for tasks that
never passed the checker, each with a reason. It is the input a run-only plan
needs; `wb run` refuses a run-only Monarch competitor without it, and refuses
again if a recorded recipe version has drifted or the knowledge-base file has
changed since. Like the knowledge-base file, it is committed only after the
command has run against a live Monarch — it is a paid step. Field table and full
example: `specs/004-monarch-run-only/contracts/config-files.md`.

## plans/pilot-monarch-run-only.yaml

The paired pilot plan for feature 004: `run-only` mode, the same 10 tasks, 2
repetitions and competitor set as `pilot-monarch-create-run` so the two modes
read side by side, internal audience, a cost ceiling, `approved_by` left empty
until Carlos approves the specific run. Full example:
`specs/004-monarch-run-only/contracts/config-files.md`.

## `wb monarch recipes`

Makes the recipes file above. **Spends model money** (Monarch authors each task
off the clock, up to `--attempts` times, default 3). Prints the task count, the
attempt ceiling and a cost band before touching anything, then refuses with
exit 5 unless run with `--yes` or against a plan whose `approved_by` is set.
Idempotent: a task already covered for the current knowledge base costs
nothing on a rerun. Full flags, exit codes and sample output:
`specs/004-monarch-run-only/contracts/cli.md`.
