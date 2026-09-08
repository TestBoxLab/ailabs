Benchmark inputs as YAML, one file per entry, in four kinds: `products/`, `models/`, `harnesses/`, `plans/`. Field tables and examples: `specs/001-declarative-benchmark-config/contracts/config-files.md` (repo root), extended by `specs/002-monarch-create-run/contracts/config-files.md` for the Monarch harness, the price-table kind, the knowledge-base hash file and the create + run pilot plan, by `specs/004-monarch-run-only/contracts/config-files.md` for run-only mode, the recipes file and the run-only pilot plan, and by `specs/005-task-tiers/contracts/config-files.md` for the four tier plans, the drawn task sets and the manifest.
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

## plans/*.yaml, key `retry_on_fail`

Optional, an integer of 0 or more, 0 when absent. A plan that sets it gives
every prompt a competitor failed that many extra attempts, on a fresh copy of
the data, on top of `repetitions`. Only a real failure earns one: a prompt that
passed is not retried, and neither is one whose attempt died on the
infrastructure (those are already retried inside the attempt and are not the
task's verdict). The extra attempt's row carries the flag `retry`, so a report
can count and separate them; the first attempt carries no flag.

The key is part of the config hash, so changing it starts a different round. It
also moves the size: a plan with `repetitions: 1` and `retry_on_fail: 1` runs
between one and two attempts per prompt per competitor, and `wb run` prints the
range before anything is spent. The cost ceiling counts every attempt, retries
included, and so does the approval gate — the approval is for what the round
could cost, not for its best case.

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

## plans/tier-simple.yaml, tier-medium.yaml, tier-complex.yaml, random-10.yaml

Four pilot plans for feature 005: `create-run` mode, the same seven
competitors and baseline as `pilot-monarch-create-run`, one attempt per prompt
plus one retry on failure (`repetitions: 1`, `retry_on_fail: 1`), internal
audience, `approved_by` left empty until Carlos approves each round
separately. Each `tasks:` points at one of the drawn task sets below. Every
description states the size the same way: "prompts: 10; attempts per prompt: 1
plus 1 retry on failure; attempts per competitor: 10 to 20". The four move as a
set: change a competitor, the ceiling or the baseline in one and change it in
all four, or a difference between the rounds stops being a difference in the
tasks. Field table and full examples:
`specs/005-task-tiers/contracts/config-files.md`.

## tasks/tier-simple/, tier-medium/, tier-complex/, random-10/

Four frozen task sets, ten tasks each, drawn from the corpus by
`wb corpus tiers` from a recorded seed. Each file is an exact copy of its corpus
original plus the two labels `info.tier` and `info.domain`; `contract_sha256` does not
move, so a label never turns into a task change. Field table:
`specs/005-task-tiers/contracts/config-files.md`.

## tasks/tiers-manifest.yaml

Written by `wb corpus tiers`: the difficulty measure in words, the two cut
points, the seed, `per_tier`, one row per corpus folder, the `excluded`
mapping with reasons, and per drawn set the per-domain counts and one row per
task with its score, tier and hash. `seed` plus the corpus folders reproduce
every drawn folder byte for byte. Full example:
`specs/005-task-tiers/contracts/config-files.md`.

## `wb corpus import-ab --domains all --dest 'corpus/imported-{domain}'`

Free, offline. `--domains` now also accepts the six scored AutomationBench
domains by name or the word `all` (those six plus the baseline `simple`);
`--dest` with `{domain}` writes one folder per domain. Full flags, exit codes
and output: `specs/005-task-tiers/contracts/cli.md`.

## `wb corpus tiers --seed N`

Free, offline. Scores every usable corpus task, cuts it into terciles, draws
four ten-task sets (three by tier plus one unstratified random set, disjoint
from the tiers) and writes them plus the manifest above. Same seed over the
same corpus reproduces the same bytes. Full flags, exit codes and output:
`specs/005-task-tiers/contracts/cli.md`.

## plans/achievable-50-request.yaml, achievable-50-workflow.yaml

The two gauntlet plans of the unblock plan of 8 Sep 2026 (milestone M2), one
per evaluation track: `track: agentic-request` (the competitor gets the request
once and acts on it) and `track: create-run` (it builds a workflow and runs
it). Everything else is identical: `tasks: tasks/achievable-50`, `create-run`
mode, one attempt per prompt plus one retry on failure, four competitors
(answer key, `claude-opus-5/api` as the baseline, `monarch-stock`,
`monarch-lab`), internal audience, a US$ 220 ceiling, `approved_by` left empty
(Lucas approves, decision D5). The two Monarch harness files arrive with
milestone M5, so until then the plans load but do not resolve; the Claude Code
competitor joins with M7. Results are never pooled across the two tracks.

## tasks/<name>-ids.txt, tasks/<name>/, tasks/<name>-manifest.yaml

A slate: a frozen task set whose members were listed by hand (one id per line,
`#` comment lines holding the rule and its source) rather than drawn by a
seed. `wb corpus slate --ids tasks/<name>-ids.txt --out tasks/<name> --because
"<why>"` copies each corpus file unchanged into the folder and writes the
manifest beside it: when, the selection rule, why the set exists, the suite
revision, the difficulty measure and cut points reused from
`tasks/tiers-manifest.yaml`, the corpus folders, the count per domain, and one
row per task with its domain, score, tier and hash. The first slate is the
50-task gauntlet, `tasks/achievable-50-ids.txt`.

## `wb corpus slate --ids FILE --out DIR --because TEXT`

Free, offline. Refuses, naming every offender and writing nothing, when an id
is not in the corpus, has no approval rule (`expected_changes` or
`allowed_changes` absent, or no expected change), does not match its own hash,
or already sits in a frozen set (`tier-*`, `random-10`, or any folder with a
manifest beside it); `--allow-frozen-overlap` lets the last case through and
records the overlap in the manifest. A folder that already holds a set needs
`--refreeze`, which keeps the ids the manifest records and refreshes the
copies, the hashes and the manifest (`refrozen_at`, `refrozen_because`) after
an approval-rule change or a corpus re-import. Exit codes: 0 written; 1 the
corpus cannot be read as one pool (two folders with the same domain); 2 a
refusal, or `--ids` missing on a fresh freeze; 3 the id list or a corpus
folder is missing.

## `wb monarch recipes`

Makes the recipes file above. **Spends model money** (Monarch authors each task
off the clock, up to `--attempts` times, default 3). Prints the task count, the
attempt ceiling and a cost band before touching anything, then refuses with
exit 5 unless run with `--yes` or against a plan whose `approved_by` is set.
Idempotent: a task already covered for the current knowledge base costs
nothing on a rerun. Full flags, exit codes and sample output:
`specs/004-monarch-run-only/contracts/cli.md`.
