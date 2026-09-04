# `plan` — one round, written down

`config/plans/<name>.yaml` is a round: which task set, which test mode, how many
repetitions, which competitors, who is the baseline, who reads the report, and
what it may cost. A run is one product × one plan.

**This subcommand never runs anything.** It writes the file, validates it, and
shows the same confirmation block the run command shows.

All commands run from `monarch-benchmark/workflowbench/`.

## `plan new <name>` — the interview

Show the real options at each step; do not ask the user to remember names.

### 1. Competitors

List what exists, then let the user pick pairs:

```bash
uv run python -c "
from pathlib import Path
from wb_orchestrator import config
print('MODELOS')
for p in sorted(Path('config/models').glob('*.yaml')):
    if config.is_price_table(p): continue
    m = config.load_model(p); print(f'  {m.name:20} {m.provider}')
print('HARNESSES')
for p in sorted(Path('config/harnesses').glob('*.yaml')):
    h = config.load_harness(p)
    acc = 'none' if h.accepts == 'none' else ','.join(h.accepts)
    print(f'  {h.name:20} kind={h.kind:9} accepts={acc}' + ('' if h.runnable else '   [não executável]'))
"
```

A competitor is `{model: X, harness: Y}`, or `{harness: Y}` alone when the
harness `accepts: none` (`oracle`, `sloppy`, `null`, `monarch`). Its name in
every table is `model/harness`, or the harness name alone.

Rules the loader enforces, worth stating up front:
- the model's provider must be in the harness's `accepts`;
- a harness with `runnable: false` cannot be picked;
- no duplicate competitors;
- the model's `key_env` must be set in `.env`.

Suggest including a scripted check: `oracle` (the answer key) spends nothing and
anchors the pairing — every shipped plan has it.

### 2. Mode

Must be one of the **product's** `modes`, and for a Monarch competitor also one
of the **Monarch harness's** `modes`. Say what each means in one line:
`create-run` = knowledge base fixed, creation and execution measured;
`run-only` = a known-correct workflow replayed, engine alone; `full-flow` = the
whole product (returns in feature 003).

### 3. Task set

`tasks:` is a folder under `workflowbench/`, e.g. `tasks` (the 10 pilot tasks)
or a folder drawn by `wb corpus tiers`. Use `tasks list` (see
`references/tasks.md`) to show what exists with counts.

### 4. Repetitions, and how to say the size

`repetitions` is how many times each competitor runs **each prompt**. Never
report only the total. Always say all three numbers:

> tentativas por prompt e competidor: **N** · prompts: **M** · por competidor: **M × N**

Smoke scale is **20 attempts per competitor** (`SMOKE_SCALE_ATTEMPTS`). Above
that, `approved_by` must be filled or the plan will not resolve.

### 5. The rest

| Field | Ask | Note |
|---|---|---|
| `timeout_s` | Quanto tempo cada tentativa pode levar? | seconds, > 0; shipped plans use 600 |
| `concurrency` | Quantas tentativas em paralelo? | ≥ 1; shipped plans use 4 |
| `baseline` | Contra quem os outros são comparados? | **must be one of the competitors**, by full name (`claude-opus-5/api`) |
| `audience` | Quem lê o relatório? | from `wb_report/audiences.yaml`: `internal`, `public-rung2` |
| `cost_ceiling_usd` | Teto de custo da rodada? | > 0; the run stops when it is crossed |
| `approved_by` | | see below |

Audiences, read from the file rather than typed:

```bash
uv run python -c "from wb_report.report import load_audiences; print(', '.join(load_audiences()))"
```

`internal` shows every competitor; `public-rung2` shows only `monarch`. The
allowlist is code — never hand-pick who appears in a report.

### 6. `approved_by`

**Write `null` unless both are true**: the round is above smoke scale (more than
20 attempts per competitor) **and Carlos has named himself as the approver in
this conversation**. Never fill it from an inference, from "ele já aprovou
antes", or from your own judgement. If the round is above smoke scale and he has
not named himself, write `null`, let the validation fail, and show him the error
— it names exactly what is missing.

## The file to write

```yaml
name: <name>
description: <what this round is for, in one or two sentences>
tasks: tasks
mode: create-run
repetitions: 2
timeout_s: 600
concurrency: 4
competitors:
  - {harness: oracle}
  - {model: claude-opus-5, harness: api}
  - {model: gpt-5.6-sol, harness: api}
baseline: claude-opus-5/api
audience: internal
cost_ceiling_usd: 12
approved_by: null          # smoke scale: 20 tentativas por competidor
```

Copy the shape of `config/plans/railway-round-001.yaml`. Show the whole file,
get a "sim", then write it.

## Validate, then show the confirmation block

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from wb_orchestrator import config
rc = config.resolve('config/products/<product>.yaml', 'config/plans/<name>.yaml')
print('product', rc.product.name, rc.product.kind, len(rc.product.services), 'services')
print('mode', rc.plan.mode, 'prompts', len(rc.tasks), 'reps', rc.plan.repetitions)
print('per_competitor', rc.attempts_per_competitor, 'total', rc.attempts_total)
print('competitors', [c.name for c in rc.competitors], 'baseline', rc.plan.baseline)
print('audience', rc.plan.audience, 'ceiling', rc.plan.cost_ceiling_usd, 'approved_by', rc.plan.approved_by)
print('hash', rc.hash)
"
```

`resolve` needs a product, so ask which one the plan is meant for (it is not in
the plan file — a run is one product × one plan).

Show any `ConfigError` verbatim. The ones this interview produces most:

| Error | What to fix |
|---|---|
| `baseline: 'X' is not a competitor; have: ...` | The baseline must be a competitor's full name |
| `approved_by: N attempts per competitor exceed smoke scale (20); set approved_by` | Cut repetitions or the task set, or get Carlos's approval |
| `competitors[i].model: unknown model 'X'; known: ...` | Typo, or the model file does not exist yet |
| `competitors[i].harness: harness 'X' is not runnable yet` | `runnable: false`; pick another |
| `mode: 'X' is not in the modes of <product>` | The product does not support that mode |
| `key_env: environment variable X is not set` | The key is missing from `.env`; only Carlos adds it |

Then print the **same confirmation block section 3 of `SKILL.md` shows** —
round, product, mode, the three attempt numbers, ceiling, `approved_by`, scale,
config hash, the competitor table with prices, the task list, baseline and
audience. Add the proof-of-life warning from `references/harness.md` for any
harness+model pair with no proof or one older than 30 days.

End with: **"O arquivo está pronto. Para rodar:
`/monarch-benchmark --product <product> --plan <name>`."** Do not run it.

## `plan edit <name>`

Read the file, show the current value of every field, change only what is asked.
Any edit **moves the config hash**, so a run in flight can no longer be resumed
(`wb resume` refuses with a drift error and the round starts over). Say that
before writing. Editing a plan after seeing results is pre-registration
territory: if the user wants to change the task set or the repetitions to chase
a result, say it needs Lucas's sign-off.
