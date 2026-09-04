# `product` — the product under test

`config/products/<name>.yaml` says **what is being tested against**: which apps
exist, what data an attempt starts from, which side effects are allowed, and
which test modes the product supports. Today there is one: `simulated-apps`, the
47 simulated business apps from AutomationBench.

All commands run from `monarch-benchmark/workflowbench/`.

## Fields

Every key is required except `description` (`config.py::load_product`).

| Field | What it is | Allowed |
|---|---|---|
| `name` | Must equal the file stem | lowercase with hyphens |
| `kind` | What sort of product | `simulated`, `real-api-ui`, `real-api` (`PRODUCT_KINDS`) |
| `data.dataset` | Which starting data an attempt loads | a name, e.g. `automationbench-47-apps` |
| `data.mutable` | Does each attempt start from a fresh copy? | `true` / `false` |
| `services` | The apps the product exposes | see the picker below |
| `side_effects` | The reviewed side-effect list | a path, e.g. `config/side-effects.yaml` |
| `modes` | Which test modes may run against it | `full-flow`, `create-run`, `run-only` (`MODES`) |

## Offer the services

The 47 service names come from the schema files; show them and let the user pick
rather than typing names that will fail validation later:

```bash
uv run python -c "
from wb_world.openapi import load_schemas
names = sorted(load_schemas())
print(len(names), 'services')
for i in range(0, len(names), 6): print('  ' + ', '.join(names[i:i+6]))
"
```

A task may only touch services the product lists: `resolve` fails with
*"task \<id\> touches service \<x\>, which \<product\> does not list in
services"*. So a smaller product means a smaller usable task set — say that
before trimming the list.

## Test modes, in plain words

- **full-flow** — discovery + workflow creation + execution. The whole product.
- **create-run** — the knowledge base is fixed; creation and execution measured.
- **run-only** — a known-correct workflow is replayed; the engine measured alone.

`modes` is the ceiling: a plan's `mode` must be in this list, and a Monarch
harness has its own `modes` list that must also contain it.

## The file to write

```yaml
name: <name>
description: <what it is, and roughly what an attempt costs>
kind: simulated
data:
  dataset: <dataset name>
  mutable: true                 # every attempt starts from a fresh copy
services: [airtable, asana, ...]
side_effects: config/side-effects.yaml
modes: [full-flow, create-run, run-only]
```

Copy the shape of `config/products/simulated-apps.yaml`. Show the whole file,
get a "sim", then write it.

## Validate

```bash
uv run python -c "from wb_orchestrator import config; print(config.load_product('config/products/<name>.yaml'))"
```

Show any `ConfigError` verbatim. Then check the side-effect file parses, since
the product points at it:

```bash
uv run python -c "from wb_orchestrator import config; print(len(config.load_side_effects('config/side-effects.yaml')), 'services with declared side effects')"
```

## When Monarch will run against this product

Monarch has to be **taught** the product before it can be a competitor: the
bench generates seeds, imports them, and records a hash per service in
`config/products/<name>.monarch-kb.yaml`. Without that file, resolving a plan
with a Monarch competitor fails with *"file is missing; run `wb monarch setup`
first"*.

Say so, and offer the command — it talks to a live Monarch, so it needs a yes:

```bash
uv run wb monarch setup --product <name>
```

The knowledge-base file is written by that command. **Never hand-write or
hand-edit it**: its hashes are what prove Monarch was taught exactly this
product, and they are part of the run's config hash.

In `run-only` mode a second generated file is needed,
`config/products/<name>.monarch-recipes.yaml`, from `uv run wb monarch recipes`.
Same rule: generated, never hand-edited.

## Editing an existing product

Adding or removing a service, or changing the dataset, **moves the config hash**
and can drop tasks from a set. Say that before writing: runs in flight can no
longer be resumed, and comparisons against older rounds are no longer on an
identical set. Removing a service that a task touches makes the plan fail to
resolve — check first:

```bash
uv run python -c "
from wb_world.episode import load_suite
used = {s for t in load_suite('tasks') for s in t['info']['initial_state']}
print('services the task set touches:', ', '.join(sorted(used)))
"
```
