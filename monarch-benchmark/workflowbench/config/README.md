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

## `wb corpus import-ab --revision LABEL --out DIR` (world revisions, 8 Sep 2026)

The world the tasks run on is the vendored AutomationBench package
(`vendor/automation-bench`, installed as an editable dependency). When that
package changes, so do the tasks: the repaired `1.0.6+evalrepair.10` release
changed every scored task's starting data and most assertion sets. A corpus
is therefore imported once per world revision, into its own folder:

```
uv run wb corpus import-ab --domains all --revision evalrepair10 --out corpus-evalrepair10
```

- `--out DIR` is the folder that holds the per-domain folders
  (`DIR/imported-<domain>/`). Without it, and without `--dest`, the folders
  land under `corpus/` as before. `--dest` (a pattern with `{domain}`) is still
  accepted; giving both is an error.
- `--revision LABEL` stamps every imported task with the world it was imported
  under, inside `info.world`: the package name, the installed version and the
  label. The block is part of the task's hash, so a task under a new world is a
  new contract even when its text did not change. Every row a round records on
  such a set carries the suite id `workflowbench-synthetic@<version>` (for
  example `workflowbench-synthetic@1.0.6+evalrepair.10`); sets imported before
  worlds were recorded keep `workflowbench-synthetic@0.1`. Reports and
  `wb summary` never pool rounds of different suite ids.
- Without `--revision`, the import refuses unless the installed package is the
  upstream `1.0.6`: an import from a repaired world must say so, or it would
  land in `corpus/` looking like the old one.
- With `--revision`, the import also writes `DIR/MANIFEST.yaml` (below).

The approval rules are derived per folder exactly as for `corpus/`, then the
manifest is refreshed so its usable counts describe the declared tasks:

```
for d in simple finance hr marketing operations sales support; do
  uv run wb corpus declare corpus-evalrepair10/imported-$d --overwrite --product simulated-apps
  uv run wb corpus validate corpus-evalrepair10/imported-$d
done
uv run wb corpus manifest corpus-evalrepair10
```

## `wb run` and the installed world

`wb run` (and `wb resume`) refuse a task set whose recorded world is not the
installed package version, naming both: a set imported under
`automation-bench 1.0.6` does not run on `1.0.6+evalrepair.10` by accident,
and the other way round. A set that records no world counts as `1.0.6`, the
only world the bench had before it recorded one. Draw new sets from the corpus
imported under the installed world; the old frozen sets stay as records.

## `corpus-<label>/MANIFEST.yaml`

Written by `wb corpus import-ab --revision` and rewritten by
`wb corpus manifest DIR`: the revision label; the world (package, version, and
what `vendor/automation-bench/VENDORED-FROM.txt` records about where that copy
came from: source path, Git tree id as given, content hash); the import date;
one row per domain folder with its task count, whether its rules are declared
and how many tasks are usable (a non-empty approval rule and a hash that
matches the content, the same two checks `wb corpus tiers` applies); the
totals; and the list of tasks without a rule, each with its reason.

## `scripts/vendor_automation_bench.py`

Replaces `vendor/automation-bench` with a source tree of the version you name
(`--expect-version`; anything else is refused and nothing is copied), leaving
behind its virtual environment, caches, logs and Git folder, and writes
`VENDORED-FROM.txt` beside the copy: source path, version, the hash of its
`pyproject.toml`, the file count, a content hash of the whole copy, the Git
tree id as given on the command line, and the date. Then `uv lock` and
`uv sync`. Adoption record: `specs/007-lab-foundation/dependency-adoption.md`.

## `wb corpus tiers --seed N`

Free, offline. Scores every usable corpus task, cuts it into terciles, draws
four ten-task sets (three by tier plus one unstratified random set, disjoint
from the tiers) and writes them plus the manifest above. Same seed over the
same corpus reproduces the same bytes. Full flags, exit codes and output:
`specs/005-task-tiers/contracts/cli.md`.

## `wb monarch recipes`

Makes the recipes file above. **Spends model money** (Monarch authors each task
off the clock, up to `--attempts` times, default 3). Prints the task count, the
attempt ceiling and a cost band before touching anything, then refuses with
exit 5 unless run with `--yes` or against a plan whose `approved_by` is set.
Idempotent: a task already covered for the current knowledge base costs
nothing on a rerun. Full flags, exit codes and sample output:
`specs/004-monarch-run-only/contracts/cli.md`.
