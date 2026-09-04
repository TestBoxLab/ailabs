# `harness` — how a competitor is driven

`config/harnesses/<name>.yaml` says **how** a competitor is put to work: the
model calls tools directly, a coding agent is launched on the command line, a
script applies a known answer, or Monarch itself is driven through its API.
A competitor in a plan is a model plus a harness; this file is the harness half.

All commands run from `monarch-benchmark/workflowbench/`.

## The four kinds

Read the required and optional keys from the code, never from memory:

```bash
uv run python -c "
from wb_orchestrator.config import _HARNESS_KEYS
for kind, (req, opt) in _HARNESS_KEYS.items():
    print(f'{kind:9} required: {list(req)}')
    print(f'{\"\":9} optional: {list(opt)}')
"
```

Every kind also takes `name`, `kind`, `accepts` (required) and `runnable`,
`description` (optional). `accepts` is either a list of providers
(`config.py::PROVIDERS`) or the string `none` for a harness that takes no model.

| kind | What it is | Shipped examples |
|---|---|---|
| `api` | The model calls the tools directly, no product in between | `api.yaml` |
| `cli` | A coding agent launched headless | `claude-code.yaml`, `codex.yaml`, `gemini-cli.yaml`, `opencode.yaml` |
| `scripted` | A check that spends nothing: `oracle` (answer key), `sloppy`, `null` | `oracle.yaml`, `sloppy.yaml`, `null.yaml` |
| `monarch` | The product under comparison, driven through its own API | `monarch.yaml` |

`runnable: false` marks a harness that is configured but must not be picked yet;
`resolve` refuses a plan that names it.

## `harness add <name>` — the interview

Ask the kind first, then only that kind's keys, from the `_HARNESS_KEYS` output.

**`api`** — nothing beyond `accepts`. Ask which providers may run through it.

**`cli`** — `launcher` (`claude-code`, `codex`, `gemini-cli`, `opencode`;
`config.py::LAUNCHERS`), `command` (the headless invocation, e.g. `claude -p`),
optional `env` (a string→string map; `{model}` is filled with the model id) and
`output` (how the agent prints results, e.g. `json-stream`). Say that CLI
competitors are API-key billing only — never a personal subscription.

**`scripted`** — `script` is one of `oracle`, `sloppy`, `null`
(`config.py::SCRIPTS`) and `accepts` is `none`. These are the checks that keep
the checker honest; there is rarely a reason to add one.

**`monarch`** — the long one; see below.

## `${VAR}` placeholders

An address may be written `${MONARCH_URL}` instead of a literal. The variable is
resolved from `.env` **at run time**, not when the file is written, so the file
stays the same whether Monarch runs locally or behind a tunnel. `resolve`
refuses to start a round when a placeholder's variable is unset
(`config.py::_check_monarch_env`), so a missing address stops the round before a
cent is spent, not halfway through it. Check presence without printing values:

```bash
grep -c "^MONARCH_URL=." .env
```

## `kind: monarch`

Copy the shape of `config/harnesses/monarch.yaml`; the field table is in
`specs/002-monarch-create-run/contracts/config-files.md`. Required:

| Field | What it is |
|---|---|
| `base_url` | Monarch's backend (`${MONARCH_URL}`) |
| `credential_env` | Variable holding a session token; set = login skipped |
| `login_email` | Owner of the bench org, which sees only the `bench-*` products |
| `login_password_env` | Variable holding that user's password |
| `fd_url` | The discovery service (`${MONARCH_FD_URL}`) |
| `shim_port` | Port of the front door on this machine, 1024–65535 |
| `langfuse_url`, `langfuse_public_key_env`, `langfuse_secret_key_env` | Tracing service, where the cost of a Monarch attempt comes from |
| `price_table` | Stem of the `kind: price-table` file in `config/models/` |
| `monarch_repo` | Path to the Monarch checkout; the version is read from it |
| `modes` | Which test modes this harness supports (`create-run`, `run-only`; `full-flow` returns in feature 003) |

Optional: `shim_public_host` (default `host.docker.internal`, for Monarch in
Docker on this machine), `shim_public_url` (the full public URL of the front
door when Monarch runs elsewhere behind a tunnel — it overrides host:port), and
`fd_api_key_env` (set when the discovery service gates `/v1/*`, as the Railway
deployment does).

Either `credential_env` or `login_password_env` must be set in `.env`, or the
round stops at resolve.

## Validate

```bash
uv run python -c "from wb_orchestrator import config; print(config.load_harness('config/harnesses/<name>.yaml'))"
```

Show any `ConfigError` verbatim. The loader is strict about unknown keys: a
Monarch-only field on an `api` harness fails with `unknown key; allowed: ...`.

## `harness test <harness> [--model NAME ...]` — proof of life

Runs the doctor for each harness+model pair and **stores** the result, so nobody
re-verifies by hand before every round.

1. Work out the pairs. `--model` may be repeated. With no `--model`, list the
   models in `config/models/` whose `provider` is in the harness's `accepts`,
   show them, and ask which to test. For `kind: monarch` there is no model: the
   single pair is `monarch@monarch`.
2. Ask: **"Isso faz uma chamada de teste por par, custa centavos. Confirma?
   (sim/não)"** Nothing runs without the yes.
3. Run it. `--arms` takes model names, comma-joined; `monarch` selects the
   Monarch block instead of a provider:

```bash
uv run wb doctor --arms <model1>,<model2>      # or: --arms monarch
```

4. Write one proof file per pair, from the doctor's printed lines:

```bash
mkdir -p config/harnesses/proofs
```

`config/harnesses/proofs/<harness>@<model>.yaml`:

```yaml
date: 2026-09-04
harness: config/harnesses/api.yaml
model: config/models/claude-opus-5.yaml
model_id: claude-opus-5
provider: anthropic
prompt: "Call the base64_encode tool on the text 'doctor' and then stop."
answer: "tool call: True"
cache_reported: yes
cost_usd: null
wb_commit: 4d969c0
```

- `prompt` is the doctor's fixed prompt (`doctor.py::_TOOL_PROMPT`). It is the
  same bytes every time on purpose, so the repeat call proves a cache hit.
- `answer`: the doctor does **not** print the model's text, so write
  `"tool call: True"` / `"tool call: False"` from the `tool_call_works` line. If
  a future doctor prints the answer, put its first line here instead.
- `cache_reported`: `yes` when `cache_hit: True`, else `no` — and copy the
  `cache_warning` line into a `note:` field when there is one.
- `cost_usd`: `null` unless the doctor prints a cost; do not estimate one.
- `wb_commit`: `git -C . rev-parse --short HEAD`.

Show each file before writing it. **`wb doctor` has no `--record` flag today**,
so the skill writes these files by reading the doctor's printed lines; a
`--record` flag that writes them from inside the code is listed as deferred in
`monarch-benchmark/workflowbench/deferred.md`.

## `harness list`

One row per harness: name, kind, accepts, runnable — and, for each model the
harness accepts, the last proof of life and its age:

```bash
uv run python -c "
import datetime
from pathlib import Path
from wb_orchestrator import config
import yaml
today = datetime.date.today()
for p in sorted(Path('config/harnesses').glob('*.yaml')):
    h = config.load_harness(p)
    acc = 'none' if h.accepts == 'none' else ','.join(h.accepts)
    print(f'{h.name:12} {h.kind:9} accepts={acc:45} runnable={h.runnable}')
    for pf in sorted(Path('config/harnesses/proofs').glob(f'{h.name}@*.yaml')):
        d = yaml.safe_load(pf.read_text(encoding='utf-8'))
        age = (today - d['date']).days if isinstance(d.get('date'), datetime.date) else '?'
        print(f'    prova {pf.stem}: {d.get(\"date\")} ({age} dias) {d.get(\"answer\")}')
"
```

Warn — a warning, never a block — for any pair with **no proof** or a proof
**older than 30 days**. `check` repeats the same warning for the pairs a plan
names, and the round's confirmation block says
**"sem prova de vida para \<par\>"**.

## After a Monarch harness

Offer, only after a yes: `uv run wb doctor --arms monarch`. It checks four
addresses (backend, session health, discovery service, tracing service) and
reports each as `OK <url>` or `FAIL <url>: ...`. Add `--monarch-probe` only when
the user asks: it fires one real authoring request and **costs model money**.
