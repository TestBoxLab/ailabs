# `model` — one language model per file

`config/models/<name>.yaml` describes **one model as one provider sells it**:
which API to call, what it costs, and which environment variable holds the key.
A competitor in a plan is a model plus a harness; this file is the model half.

All commands run from `monarch-benchmark/workflowbench/`.

## `model list`

Read every file in `config/models/` and print one table. `kind: price-table`
files share the folder but are **not competitors** — mark them as such.

```bash
uv run python -c "
from pathlib import Path
from wb_orchestrator import config
rows = []
for p in sorted(Path('config/models').glob('*.yaml')):
    if config.is_price_table(p):
        t = config.load_price_table(p)
        rows.append((t.name, 'price-table', f'{t.provider}/{t.region}', '-', str(t.prices_verified)))
        continue
    m = config.load_model(p); u = m.usd_per_million
    rows.append((m.name, m.provider, m.model, f'{u.input}/{u.cached}/{u.output}', str(m.prices_verified)))
w = [max(len(str(r[i])) for r in rows) for i in range(5)]
for r in rows: print('  '.join(str(x).ljust(w[i]) for i, x in enumerate(r)))
"
```

Present it in Portuguese with these headers: `modelo | provedor | id no provedor
| US$/milhão (in/cached/out) | preços conferidos em`. Say which lines are price
tables: *"`monarch-team-bedrock` é a tabela de preços do time (conta da Monarch
na Bedrock), não um competidor."*

## `model add <name>` — the interview

Ask these in one message, with the allowed values shown, and let the user answer
in one block. Never invent a price.

| Field | Ask | Allowed / note |
|---|---|---|
| `provider` | Quem vende? | `anthropic`, `openai`, `google`, `zai`, `moonshot`, `fireworks` (`config.py::PROVIDERS`) |
| `model` | Qual o id exato do modelo no provedor? | Copied as the provider spells it, e.g. `accounts/fireworks/models/kimi-k3` |
| `effort` | Nível de raciocínio? | `xhigh`, `high`, `medium`, `low`, `none` (`EFFORTS`) — the bench uses `xhigh` |
| `usd_per_million` | Preço por milhão de tokens: entrada, cache lido, saída? | Numbers; `cache_write` too when the provider bills writes separately (Anthropic does) |
| price source | De onde veio esse preço e em que data? | Goes to `prices_verified` (a date) and into `description` as a sentence |
| `key_env` | Qual variável do `.env` guarda a chave? | A name only, e.g. `FIREWORKS_API_KEY`; the value is never read or written |

Optional, ask only when relevant:

| Field | When |
|---|---|
| `adapter` | The provider's wire format is not its default: `openai`, `openai_responses`, `gemini`, `anthropic` (`ADAPTERS`) |
| `base_url` | The provider is reached at its own address (Fireworks, Z.ai) |
| `header_fallbacks` | Cached tokens come back in a response header, not the body, e.g. `[fireworks-cached-prompt-tokens]` |
| `cache_min_prompt_tokens` | The provider only caches above a floor (Anthropic: 1024) |

**Rule: a price without a source and a date does not go in the file.** If the
user does not have one, stop and ask for the page or the invoice. The date goes
in `prices_verified`; the sentence goes in `description`.

## The file to write

Copy the shape of the shipped files. `name` must equal the file stem.

```yaml
name: <name>
provider: fireworks
model: accounts/fireworks/models/kimi-k3
effort: xhigh
usd_per_million: {input: 3.00, cached: 0.30, output: 15.00}
key_env: FIREWORKS_API_KEY
base_url: https://api.fireworks.ai/inference/v1
header_fallbacks: [fireworks-cached-prompt-tokens]
prices_verified: 2026-08-31
description: <what it is, plus where the price came from and when>
```

Three shipped examples worth reading before writing: `claude-opus-5.yaml`
(cache_write and a cache floor), `kimi-k3-fireworks.yaml` (base_url and a header
fallback), `gpt-5.6-sol.yaml` (the plainest shape, plus a note that the model
needs the Responses API).

Show the whole file, get a "sim", then write it.

## Validate

```bash
uv run python -c "from wb_orchestrator import config; print(config.load_model('config/models/<name>.yaml'))"
```

Any `ConfigError` is shown verbatim, then explained in Portuguese. Common ones:
`name: must equal the file stem`, `provider: must be one of ...`,
`usd_per_million: required key missing`.

## Check the key without printing it

```bash
grep -c "^<KEY_ENV>=." .env
```

`1` = the variable exists and is not empty; `0` = missing. **Never `cat .env`,
never echo the value.** If it is `0`, say the model is configured but no round
can use it until the key is in `.env`, and that only Carlos puts it there.

## Offer the doctor (spends cents)

Only after the file validates and the key exists, ask:
**"Quer que eu faça uma chamada de teste? Custa centavos. (sim/não)"**

```bash
uv run wb doctor --arms <name>
```

`--arms` takes the **model name** (the file stem). Show the OK/FAIL lines as
printed. `tool_call_works: True` is the pass; a `cache_warning` is worth
repeating, because it means a paid round should not be planned assuming cache
savings on that provider.

To keep the result, see `harness test` in `references/harness.md` — it writes a
dated proof file for the harness+model pair.

## Price tables are not models

A `kind: price-table` file (today only `monarch-team-bedrock.yaml`) holds prices
for models a competitor calls through **someone else's account** — Monarch on
Bedrock. It never appears in a plan's `competitors`; a Monarch harness points at
it with `price_table`. Loader: `config.load_price_table`. Editing one is an edit
to how a past round's cost is computed — say so, and treat it with the same
source-and-date rule.
