# Contract — the command-line surface

**Feature**: [026-external-benchmark-products](../spec.md) · **Date**: 2026-09-11

Three importers and two checks. **No new selection mechanism**: an external world is
selected the way every product already is, with `wb run --product X --plan Y` (FR-021).
That is the whole point of the feature, so nothing here adds a parallel path.

## `wb corpus import-eog`

```
wb corpus import-eog --domains <list|all> --mode <oracle|plus_5_tools|plus_10_tools|plus_15_tools>
                     --out corpus-eog/imported-{domain} [--limit N]
```

Reads the source's dataset rows and writes one task file per row: the request text from
`user_prompt`, the source pin, `source_ref` holding the task id, its verifiers and its
seed reference, and the approval rule.

## `wb corpus import-appworld`

```
wb corpus import-appworld --split <train|dev> --out corpus-appworld/imported-{split} [--limit N]
```

Refuses `test_normal` and `test_challenge` by name, explaining that their reference
solutions are not published and the answer-key competitor needs one
([research.md](../research.md) R5). Writes identifiers and the request text read from the
installed package; **no AppWorld content is written into this repository** (FR-020).

## `wb corpus import-tau2`

```
wb corpus import-tau2 --domains <list|all> --out corpus-tau2/imported-{domain} [--limit N]
```

## Rules every importer obeys

1. **Refuse rather than half-write** (FR-016). A task whose answer key is unpublished,
   whose world cannot be snapshotted, or whose check cannot run locally is skipped with
   its reason recorded in the manifest. A partially usable task is never written.
2. **Record the source pin** on every task and in the manifest (FR-019).
3. **Hash the content** into `contract_sha256`, the same way the existing importer does.
4. **Be idempotent.** A re-import of unchanged content writes nothing and reports the
   task as unchanged, exactly as `wb corpus import-ab` does today.
5. **Spend nothing.** Downloads and container pulls are free; no importer calls a paid
   provider.

## Freezing task sets

Unchanged. `wb corpus slate --ids FILE --out DIR --because TEXT`, `wb corpus tiers
--seed N` and `wb corpus split` work on an imported external corpus as they stand,
because imported tasks keep the shape those commands already read: a non-empty approval
rule and a hash that matches the content.

## The front door

```
wb world serve --product <name> --task <file> --port N
```

Publishes one product's world behind the three tools and writes its interface documents,
so the discovery step Monarch uses can map the product (FR-005). This generalizes what
`python -m wb_world.openapi --out out/openapi --server http://...` does today for the
simulated API set. A tool that is not already a REST resource is published as
`POST /{service}/{tool_name}` with the tool's own input schema as the request body
([research.md](../research.md) R4) — the tool's real name, never a guessed resource path.

## Readiness

```
wb doctor --product <name>
```

Reports the adapter's `prerequisites()` in plain words: the missing package, container
runtime, dataset or environment variable. It starts nothing and spends nothing, and it
is what stops a round from discovering a missing container after money is reserved
(FR-007).

## Refusals, in the shape this repository already uses

- unknown world name, naming the product and the known worlds
- source pin mismatch between the round's record and the installed source
- a task whose hash no longer matches its content, naming the task
- a test mode the product does not support
- a comparison spanning two products, naming both
