---
name: monarch-benchmark
description: Use when preparing, confirming or running a benchmark round of Monarch against language models, or when creating or editing the files a round needs — the user types /monarch-benchmark, asks to run a round, a plan, a task set or wb run, asks what a round would cost before spending, or asks to add a model, a harness, a product under test or a plan.
argument-hint: "[--product NAME] [--plan NAME] | model|harness|product|plan|tasks|check ..."
---

# Run a benchmark round

Prepare one round through the `wb` CLI, show the user exactly what will be spent,
get an explicit yes, then run. Everything below runs from
`monarch-benchmark/workflowbench/`.

**Talk to Carlos in Portuguese. Keep file names, config field names, competitor
names, task ids and command lines exactly as they are — do not translate them.**

## Rules you may not break

- No round beyond smoke scale (10 tasks, 2 repetitions = 20 attempts per
  competitor) without Carlos approving that specific round AND `approved_by`
  filled in the plan file. `wb run` enforces this; do not work around it.
- Always state attempts and a cost band before running. Never run without the
  explicit "sim".
- Pre-registration: never edit a task's prompt, starting data or approval rule.
  Never edit prices. If the user asks for an edit after seeing results, say it
  needs Lucas's sign-off and that it makes old rows non-regradable.
- Same request text for every competitor. Audience rules live in
  `wb_report/audiences.yaml`; do not hand-pick who appears in a report.

## Subcommands

`/monarch-benchmark` with no subcommand (or with `--product` / `--plan`) prepares,
confirms and runs a round — sections 1 to 6 below. Anything else **writes or
inspects config files and never runs a round**. Read that subcommand's reference
file with the Read tool and follow it; do not guess the fields.

| Subcommand | Read this file |
|---|---|
| `model add\|edit <name>`, `model list` | `references/model.md` |
| `harness add\|edit <name>`, `harness list`, `harness test <name>` | `references/harness.md` |
| `product add\|edit <name>` | `references/product.md` |
| `plan new\|edit <name>` | `references/plan.md` |
| `tasks list`, `tasks show <folder>` | `references/tasks.md` |
| `check --product <p> --plan <n>` | `references/check.md` |

Paths are relative to `monarch-benchmark/workflowbench/`.
Deferred items of the bench and of this skill: `monarch-benchmark/workflowbench/deferred.md`.

### Rules for every subcommand

- **Show before saving.** Print the whole file you are about to write, in a
  fenced block, and get a "sim" before the Write tool touches the disk.
- **Validate after saving**, with the loader named in the reference file. A
  `ConfigError` is shown **verbatim**, then explained in Portuguese, offering to
  fix that one field. Never paraphrase the error away.
- **Nothing runs without an explicit yes.** `wb doctor` costs cents and is
  offered, never assumed. `wb run` is never started from a subcommand.
- **Task files are never edited.** `tasks` only lists and shows. Changing a
  task's prompt, starting data or approval rule needs Lucas's sign-off, and it
  makes old rows non-regradable.
- **`git commit` is offered, not done.** Suggest the paths; wait for a yes.
- **Names are file stems**: every loader requires `name:` to equal the file name
  without `.yaml`.
- **`edit` reads the file first**, shows each field's current value, and changes
  only what was asked. Any edit moves the config hash, so a run in flight can no
  longer be resumed — say so before writing.

## 1. Resolve the inputs

`--product` / `--plan` take a plain name (`simulated-apps`, `railway-round-001`)
or a path. If either is missing: `ls config/products config/plans`, show the
names, ask the user to pick. Never invent a plan.

If the user describes a round no plan file matches, draft a new file under
`config/plans/` — copy the shape of `config/plans/railway-round-001.yaml`, with
`approved_by: null`, `audience: internal` and a `cost_ceiling_usd` — and show it
before continuing. Field tables: `config/README.md`,
`specs/001-declarative-benchmark-config/contracts/config-files.md`,
`specs/002-monarch-create-run/contracts/config-files.md`.

## 2. Read the resolved config (never hand-type it)

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from wb_orchestrator import config
rc = config.resolve('config/products/<product>.yaml', 'config/plans/<plan>.yaml')
print('product', rc.product.name, rc.product.kind, len(rc.product.services), 'services')
print('mode', rc.plan.mode, 'repetitions', rc.plan.repetitions, 'timeout_s', rc.plan.timeout_s, 'concurrency', rc.plan.concurrency)
print('competitors', [c.name for c in rc.competitors], 'baseline', rc.plan.baseline, 'audience', rc.plan.audience)
print('attempts_total', rc.attempts_total, 'per_competitor', rc.attempts_per_competitor, 'ceiling_usd', rc.plan.cost_ceiling_usd, 'approved_by', rc.plan.approved_by)
print('tasks', [t['task'] for t in rc.tasks])
print('config_hash', rc.hash)
for t in rc.tasks: print('PROMPT', t['task'], '::', t['prompt'][1]['content'])
"
```

A `ConfigError` names the file and the field (an unset API key, an unknown
competitor). **Show it verbatim and stop.**

Then read prices per competitor from `config/models/<name>.yaml`
(`provider`, `usd_per_million`); for a Monarch competitor read `base_url` and
the version source from `config/harnesses/monarch.yaml`.

Cost band from earlier rounds on the same tasks:

```bash
uv run python -c "
import sqlite3; c=sqlite3.connect('out/wb.sqlite3')
for r in c.execute('select arm, count(*), round(sum(cost_usd),3), round(avg(cost_usd),5) from episodes where run_id like \"%\" group by arm'): print(r)
"
```

Multiply the per-attempt average by the attempts per competitor. If a competitor
has no rows, say **"sem dados anteriores"** for it — never guess.

## 3. Confirmation (in Portuguese)

```
Rodada: <plan> · produto sob teste: <product> (<kind>, <N> apps) · modo: <mode>
Prompts: <n_tasks> · tentativas por prompt e competidor: <k> · por competidor: <n> (= prompts × tentativas) · total: <total>
Teto de custo: US$ <ceiling> · approved_by: <valor ou "não definido">
Escala: <smoke (<=20 por competidor) | acima de smoke — exige approved_by>
Hash da configuração: <hash>

| competidor | harness | provedor | US$/milhão (in / cached / out) |
|---|---|---|---|
| ... uma linha por competidor; gabarito e checks scripted sem preço ... |

Banda de custo estimada (rodadas anteriores, out/wb.sqlite3):
- <competidor>: ~US$ X (US$ Y por tentativa x <n>)   |   sem dados anteriores

Conjunto de tarefas (<N> tarefas, mesmo texto para todos os competidores):
- <task id>: <texto do pedido>
  ...

Baseline: <baseline> · público do relatório: <audience>
```

## 4. Checks before spending

```bash
uv run wb doctor --arms <comma list of the plan's model names>   # add ,monarch if Monarch is in the plan
```

Show the OK/FAIL lines. If Monarch is a competitor, also:

- Monarch must be up:
  `bash C:/Users/cgmat/Desktop/TestBox/monarch/local-docs/setup/scripts/railway-ops.sh status`
  (`unlock` if it is locked).
- The ngrok tunnel behind `FRONT_DOOR_URL` must be running.
- If `config/products/<product>.monarch-kb.yaml` is missing, say to run
  `uv run wb monarch setup --product <product>` first.

## 5. Ask, then run

Ask **"Confirma a rodada? (sim/não)"**. Only on "sim":

```bash
uv run wb run --product <product> --plan <plan> > out/run-$(date +%Y%m%d-%H%M%S).log 2>&1
```

Run it in the background with the log in a file; tell the user it can take from
minutes to an hour, and report when it finishes.

## 6. After the run

```bash
uv run wb grade <run_id>
uv run wb report <run_id> --audience <plan audience>
```

Show the per-competitor table and the paired comparisons **with their `src:`
lines**. Then list every failed attempt:

```bash
uv run python -c "
import sqlite3, json; c=sqlite3.connect('out/wb.sqlite3')
for t,a,j in c.execute('select task_id, arm, row_json from episodes where run_id=? and passed=0', ('<run_id>',)):
    d=json.loads(j)
    print(t, a, [u['path'] for u in (d.get('unexpected_changes') or [])], d.get('error') or '')
"
```

If Monarch ran, add its own fields from the same `row_json`: questions asked,
`phases`, the share of attempts with no cost recorded, and the `no_workflow`
reasons in `error`.

Offer to commit `out/report-<run_id>-<audience>.md`. If Monarch was in the plan,
offer `railway-ops.sh lock` at the end.

**Interrupted run:** `uv run wb resume <run_id>` continues it. The config hash
must still match — any edit to the plan, product, models, harnesses or tasks
makes resume refuse with a drift error, and the round has to start over.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `config error in ...: key_env: ... not set` | The API key is missing from `.env`. Show the line; do not run. |
| `config error in ...: approved_by: ...` | Above smoke scale without approval. Ask Carlos; only he fills `approved_by`. |
| Knowledge-base drift error | The seeds Monarch imported no longer match. `uv run wb monarch setup --product <product>` again, then say the config hash moved. |
| Monarch unreachable / 502 | Railway is locked or asleep: `railway-ops.sh status`, then `unlock`. |
| Monarch reaches nothing / front door times out | The `FRONT_DOOR_URL` tunnel is down. Restart ngrok; if its host changed, rerun `wb monarch setup`. |
| Attempts end in `no_workflow` | Monarch never produced a workflow; the reason is in `episodes.row_json` → `error`. Report it, do not retry blindly. |
