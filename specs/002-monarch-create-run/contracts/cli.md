# Contract: CLI additions

Feature 001's `wb run / resume / status / grade / report / corpus` are
unchanged. This feature adds one command group and one doctor extension.

## `wb monarch setup`

```
wb monarch setup [--product NAME|PATH] [--harness NAME|PATH] [--out DIR]
```

- `--product` defaults to `simulated-apps`; `--harness` to `monarch`;
  `--out` to `workflowbench/out/monarch-seeds`.
- Spends no model money. Idempotent.
- Steps, in order, each printed as a line `[ok]`, `[stop]` or `[warn]`:
  1. `generate`: writes `<out>/bench-<service>/` for every service of the
     product; prints `operations_in_spec=686 files_written=686 folders=47`;
     refuses to write a partial set (exit 2, nothing written).
  2. `mounted`: `GET <fd_url>/v1/seeds` must list all 47 slugs. If not, prints
     the `docker-compose.override.yaml` snippet below and exits 3.
  3. `register`: removed on 4 Sep 2026; the seed import creates the product (the discovery service slugifies registered slugs, which created empty duplicates).
  4. `import`: `POST <fd_url>/v1/seeds/<slug>/import` × 47; prints
     `actions_imported` and `kb_hash` per slug.
  5. `granted`: prints the slugs the bench user's organisation cannot use, or
     `unknown (open question 2)`; never fails the command.
  6. `write`: writes `config/products/<product>.monarch-kb.yaml`; prints its
     path and whether it changed.
- Exit codes: 0 done; 2 generation incomplete; 3 seeds not mounted; 4 FD API
  unreachable or an import failed (names the slug).

Override snippet printed at step 2:

```yaml
services:
  fdapi:
    volumes:
      - <absolute out dir>:/app/api/src/seeds/fixtures/public-api-seeds/bench-mounted:ro
```

(The exact container path is confirmed against the Monarch image at
implementation time and recorded in the Monarch pull request; the snippet
prints whatever `seed-catalog.ts` resolves.)

## `wb doctor`

```
wb doctor [--arms LIST] [--monarch-probe]
```

- When `config/harnesses/monarch.yaml` is runnable, the report gains a block
  `monarch` with four lines: `backend`, `backend_health`, `fd`, `langfuse`,
  each `OK`/`FAIL` with the address tried.
- `--monarch-probe` adds `authoring_probe`: one `POST /api/workflows/recipe/runs`
  with the goal `Connectivity check. Do nothing.`, cancelled on the first
  frame; reports the first frame's status or the error. Costs model money;
  off by default.
- Exit code 1 if any check fails, as today.

## `wb run` (behaviour additions, no new flags)

- With a Monarch competitor in the plan: refuses before any attempt if the
  knowledge-base hash file is missing, the Monarch checkout has no readable
  version, or the price table names a field the loader does not know.
- Before the first Monarch attempt: compares `GET /v1/seeds` hashes with the
  file; refuses on drift naming the app.
- Banner line adds `monarch: <name>, kb <n> apps, price table <name>@<date>`.
