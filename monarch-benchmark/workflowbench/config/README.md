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

## plans/*.yaml, key `attempt_cap_usd`

Optional, an amount above 0, US$ 3.00 when absent. The most one attempt of an
API competitor may spend: before every provider request the loop adds the
request's rate-card maximum to what the attempt already settled or holds, and
refuses the request when the sum would pass the cap. The attempt ends as
`infra:attempt_cap`: not a pass, not the model's failure, and final (a resume
does not run it again). Like `track`, only a non-default value moves the config
hash. Monarch attempts have their own per-attempt ceiling instead:
`MONARCH_ATTEMPT_CEILING_USD` in the environment, US$ 25.00 when unset.

## plans/*.yaml, key `approved_by` (ignored since 8 September 2026)

Still allowed so older files load, but it approves nothing: since decision D5
an approval is a record in the results store, made at launch. `wb run` prints
a one-line notice when the key is set. See "Approvals and the weekly ledger" below.

## Approvals and the weekly ledger (`wb run`, `wb approve`, `wb deny`, `wb approvals`)

Every paid launch names its operator: `WB_OPERATOR=<name>` in the environment
(`wb run`, `wb resume` and provider probes of `wb doctor` refuse without it).
Default approvers are Carlos and Lucas: `carlos`, `carlos mattos`, `lucas`,
`lucas wakigawa`. Names are matched exactly after trimming and lowercasing;
there is no inferred alias expansion. A nonempty `WB_APPROVERS=a,b` replaces
the entire default list, so `WB_APPROVERS=lucas` explicitly excludes Carlos.
Attribute `WB_OPERATOR` to the human who requested the round, never the agent;
configuration is not permission for an agent to approve its own round.
Above smoke scale (20
attempts per competitor, retries included), an approver's `wb run` runs at once
under an approved record; anyone else's `wb run` writes a pending request,
prints `<id> awaiting approval` and stops. An approver decides with
`wb approve <id>` or `wb deny <id>`; then anyone runs the same product and plan
with `wb run ... --request <id>`, once, while the config hash still matches.
`wb approvals` lists the records. Smoke scale needs no record.

The weekly ledger (`research/budget.sqlite3`, US$ 300 per calendar week from
Monday 00:00 America/Sao_Paulo, override the path with `wb --ledger`) is the
spending gate whatever the approval: every provider request is reserved for its
maximum before it is sent and settled from the usage receipt; a round is admitted
only when the week can cover its maximum liability (API attempts x attempt cap +
Monarch attempts x their ceiling, capped by `cost_ceiling_usd`), and the
refusal names the shortfall; an exhausted week stops the run with
`stop_reason: weekly_budget`, resumable with `wb resume` when the week has room.
`wb budget status` shows what is held, spent and available.

Today only API competitors launch. Monarch competitors, `wb monarch recipes`
and the doctor's Monarch probe are refused with "Monarch instance not verified:
milestone M5"; Claude Code and other native competitors with "native runtime
not verified: milestone M7".

## `wb budget reconcile --week YYYY-MM-DD --provider <name> --csv FILE`

Compares one week's provider usage with what the ledger settled for that
provider in that week (a reservation belongs to the week it was dispatched in)
and writes `research/reconciliation/<week>.md` and `.json` with both numbers and
the difference. `--week` is the week's Monday; `--provider` and `--csv` repeat.
The week's `historical_billing_verified` (shown by `wb budget status`) is true
only when every provider with spend, in the ledger or in an export, has been
reconciled within 5 % of its own total; unsettled holds are listed, never
released.

The rows are normalized by hand or by a short script into one CSV with the
header `date,provider,usd`: one row per day (or per export line), the date as
`YYYY-MM-DD`, the provider as one of `anthropic`, `openai`, `fireworks`,
`google`, `moonshot`, `zai`, `monarch`, the amount in US dollars. Where they
come from:

- **Anthropic**: the Console's Usage page (Settings, Usage, or the Cost tab of
  the organization), filtered to the API key the bench uses, exported as CSV,
  or the Admin API's usage and cost reports; keep the date and the cost columns.
- **OpenAI**: the platform's Usage page, per project and per day, exported as
  CSV, or the costs endpoint of the Usage API; keep the date and the amount.
- **Fireworks**: the account's Usage or Billing page, per day; export or copy
  the daily totals.
- **Google (Gemini API)**: the Google Cloud billing report for the project the
  API key belongs to, filtered to the Generative Language API, grouped by day.
- **Monarch**: Monarch bills through its own model accounts, so its rows are
  built from Langfuse: the sum of the generations' costs per day for the
  bench's traces (the `bench_episode_id` metadata), priced with the price table
  the harness names; the same numbers `wb_arms.langfuse_cost` uses.

Rows for other providers or other weeks in the same file are ignored.

## plans/pilot-monarch-create-run.yaml

The paired pilot plan for feature 002: `create-run` mode, the 10 pilot tasks, 2
repetitions, competitors {answer key, Claude Opus 4.8 raw, Monarch}, internal
audience, a cost ceiling; approval is a record made at launch (decision D5).
Full example: `specs/002-monarch-create-run/contracts/config-files.md`.

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

## products/<name>.knowledge-map.yaml

The explicit table behind the lab seeds (unblock plan of 8 Sep 2026, M6): one
row per entry of a reviewed knowledge catalog, naming the bench action that
performs the entry's operation over the simulated app (`zapier:<app>_<tool>`
on the left, `bench-<app>:<verb>:<object>` on the right), plus `notes` saying
why a row is what it is and why an entry has none. Hand-written from the data,
never derived: the catalog's ids are AutomationBench's Zapier tools, the seeds'
are REST routes, and no rule maps one onto the other. `wb monarch knowledge`
refuses a row whose action the generator does not produce. The shipped table
(`simulated-apps.knowledge-map.yaml`) covers 257 of the PG-Waki catalog's 273
entries; the 16 without a row are listed with their reasons.

## `wb monarch knowledge --knowledge <catalog.json> [--out out/monarch-seeds-lab] [--front-door <url>]`

Free, offline, imports nothing. Writes the lab seeds: the stock seeds
(`wb monarch setup` step 1) with `business_action.description` enriched from
the catalog through the table above -- purpose, what the action does not do,
whether repeating it is safe, where the records sit in the response (only
where the seed's own schema reaches that path) and what its arguments mean
(only for parameters the seed has) -- and each product's paragraph prefixed
"Product:" on its first action. Ids, verbs, url templates, parameters,
extracts, schemas and `_meta.json` are byte-identical to the stock set, so
both validate alike and run alike. Also writes `<out>/KNOWLEDGE-MAPPING.yaml`
(the catalog's sha256, the rule, the counts, every pair, the entries without
a row, the actions without an entry) and puts `knowledge_sha256` and
`knowledge_source` into `ok.txt` next to the seed version. Same inputs, same
bytes. `wb monarch setup --knowledge <catalog.json>` runs the same step
before validating, checking and importing, and records the two fields in the
knowledge-base hash file, so a lab instance's file says what it was taught.
Note: the SPEC stores `description` but does not serve it to the builder
today; making the builder read it is a Monarch-side change.

## plans/pilot-monarch-run-only.yaml

The paired pilot plan for feature 004: `run-only` mode, the same 10 tasks, 2
repetitions and competitor set as `pilot-monarch-create-run` so the two modes
read side by side, internal audience, a cost ceiling; approval is a record made
at launch (decision D5). Full example:
`specs/004-monarch-run-only/contracts/config-files.md`.

## plans/tier-simple.yaml, tier-medium.yaml, tier-complex.yaml, random-10.yaml

Four pilot plans for feature 005: `create-run` mode, the same seven
competitors and baseline as `pilot-monarch-create-run`, one attempt per prompt
plus one retry on failure (`repetitions: 1`, `retry_on_fail: 1`), internal
audience; each round is approved at launch as a record (decision D5). Each
`tasks:` points at one of the drawn task sets below. Every
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
exit 5 unless run with `--yes` (a plan's `approved_by` no longer counts).
Idempotent: a task already covered for the current knowledge base costs
nothing on a rerun. The `wb` subcommand itself is refused with "Monarch
instance not verified: milestone M5" until a Monarch instance is verified.
Full flags, exit codes and sample output:
`specs/004-monarch-run-only/contracts/cli.md`.
