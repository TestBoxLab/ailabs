# Contract — the world adapter

**Feature**: [026-external-benchmark-products](../spec.md) · **Date**: 2026-09-11

Every product's world implements this. The list was **read from what the orchestrator and
the arms already demand of an episode** ([research.md](../research.md) R8), not designed
fresh — which is why `wb_world/episode.py` satisfies it today with no behavioural change
and becomes the AutomationBench implementation by declaration.

## Lifecycle

One adapter instance serves exactly one attempt. It is constructed with the task and an
attempt id, it is used, and it is closed. A second attempt gets a second instance and a
second private world; no state crosses between them.

```
construct(task, episode_id, frozen_time=None)
  -> the world is seeded, snapshot0 is taken, the three tools are live

attach_journal(directory)      before any tool use, once
artifacts_dir                  where an arm may drop its own files

api_search(query, top_k)       the three tools, identical on every product
api_fetch(method, url, params, body)
base64_encode(text)

snapshot()                     the world now
finish()                       the world at the end; sets snapshot1
close()                        release the runtime; safe to call twice

tool_calls                     what was called
events                         the observation record
record_agent_event(entry)      the harness's own observations
```

## Required properties

- **`snapshot0`** is taken at construction, before the competitor can act.
- **Snapshots are deterministic.** Two dumps of an untouched world are identical. Rows
  are sorted by primary key before dumping. A world that cannot promise this cannot be a
  product, because every unordered re-dump would read as collateral damage.
- **Snapshot shape** is `{service_name: plain JSON}`, `meta` reserved for harness state.
  Top-level keys equal the product's declared `services`.
- **The three tools are the whole surface.** No product may offer a fourth tool or
  withhold one of the three. A competitor's starting surface must not differ by product.
- **`api_fetch` dispatches into this attempt's own world**, never a shared one.
- **Closing is idempotent and always safe**, including after a timeout or a crash mid
  attempt. An adapter that holds a container or a subprocess releases it here.

## Three class methods, off the instance

```
prerequisites()  -> [] when the world can run here,
                    else a list of missing things named in plain words
service_names()  -> the top-level keys a snapshot of this world carries
positive_check(task, snapshot0, snapshot1, artifacts) -> PositiveResult
```

**`service_names()`** is what a product's declared `services` is checked against at
configuration load. An approval rule addresses a service by name; a name the world
does not have would match nothing, and every attempt would read as clean. It must
not start anything: for a world of tools these are the domain names, which are
static.

**`prerequisites()`** is what FR-007 rests on. It is called during round preparation,
before any money is reserved. It names what is missing — a package, a container runtime,
a dataset, an environment variable — and it never starts anything to find out.

**`positive_check(...)`** runs the source's own check, as shipped, from stored state:

- EnterpriseOps-Gym: execute each verifier's SQL against the post-attempt database and
  compare with its `expected_value`.
- AppWorld: `.evaluate()`, keeping `success`, `passes` and `fails` whole.
- τ²-bench: its own reward, taken whole, including the parts that score actions.
- AutomationBench: the vendor's assertion registry, exactly as `grader/grade.py` does it
  today.

It returns:

| Field | Holds |
|---|---|
| `passed` | the source's verdict |
| `detail` | whatever the source returned, kept whole, not summarized |
| `source` | which checker produced it, for the report sentence |
| `side_effects` | the source's own collateral finding, or `None` where it has none |

**It is a class method for a reason.** Grading runs later, out of process, from stored
snapshots — the attempt's adapter instance is long gone, and it must be, or something
would be grading itself.

**It may raise.** A checker that fails to produce a verdict leaves the attempt
`ungraded` with the error retained. It is never turned into a pass and never into a
fail.

## Administrative operations are the lab's, not the competitor's

A world that can be seeded, reset and queried over the same HTTP surface the
competitor uses is a world the competitor can cheat in. EnterpriseOps-Gym's ITSM
server publishes `/api/sql-runner`, `/api/seed-database`, `/api/reset-database`,
`/api/clone-database`, `/api/delete-database`, `/api/database-state` and
`/api/download-db-file` beside its 79 real operations ([research.md](../research.md)
S1).

Every adapter therefore declares:

```
ADMIN_PATHS  -> the operations only the lab may call
```

The front door **removes them from the published interface document** and **refuses
them on the wire**, and the adapter reaches them by its own client, not through the
door it opened for the competitor. Without this, a competitor could write the
expected result directly with one query, read the verifier's own target, or erase
the evidence of what it did.

## What the adapter must not do

- It must not grade in-process, alongside the competitor.
- It must not edit, re-derive or filter the source's assertions, verifiers or reward.
- It must not write source content that its licence forbids redistributing into this
  repository.
- It must not import its source package at module import time. Import is lazy; absence
  is a named refusal from `prerequisites()`, not an `ImportError` at start-up. This is
  what keeps the offline suite runnable with none of the three sources installed.
- **It must not make its source a dependency of this project.** All three external
  worlds run out of process in their own environments and are reached over HTTP
  (research.md R10): AppWorld pins pydantic below 2.0 while this project needs 2.0,
  so they cannot share an environment even in principle. An adapter is an HTTP
  client of its source, and `prerequisites()` checks a reachable endpoint.

## Registration

`wb_world/registry.py` maps a product's `world` name to its adapter, importing lazily. An
unknown name refuses the product by name. The registry is a dictionary; three
implementations do not need a plugin system, and the repository already has one in
`wb_studio/genesis_plugins.py` for the case that genuinely did.
