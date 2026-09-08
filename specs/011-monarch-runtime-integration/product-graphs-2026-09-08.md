# Product graphs: versioned, AI-filled, extendable knowledge

8 September 2026. Lucas's brief: a Product Graph module with a node that shows the information
passing through it, and a setup where new versions of the graph are made by declaring fields,
handing their descriptions to an AI that fills them, and saving the result as a version that can
be reused or extended.

## Model

- A **product graph** is a schema (typed fields with descriptions) plus one record per product in
  the benchmark corpus (42 products today), filled once by a researcher agent with catalog access
  (`api_search`). The field description is the prompt for that field.
- A **version** is immutable: fields (each stamped with the version that last researched it),
  records, researcher, cost, turns, tool calls, problems, sha256, events file.
- **Extending**: the draft always describes the next version. Preparing it researches only the new
  or changed fields (a changed description or type counts), carries the untouched fields' values
  from the parent version, and pins the result as the next number. If nothing changed, preparation
  is refused ("Nothing new to research… reuse version N").
- A failed preparation is recorded under its number with no records and can be retried under the
  same number; the budget must cover the researcher's first-request reservation (Gemini ≈ $1.05),
  checked before anything is claimed.
- An architecture references a version through a **Product graph step**. The step card shows the
  graph, version, field count, product count and "Delivers <fields> for every product to each step
  after it". Publishing pins the referenced versions (their hashes go into the runtime manifest and
  the run's execution manifest); a run refuses to start if a referenced version changed.
- At run time the step emits `step_started`/`step_finished` with the output
  "Delivered 42 products × 3 fields from 'Catalog basics' v2 (…) to Worker", so Activity and the
  live canvas overlay show the information passing through; downstream agent steps receive the
  records in their system prompt.

The former `graph-fields` and `enrich` step types (per-architecture enrichment pinned to an
architecture version) are gone; product graphs are the one mechanism. Two stored pilot blueprints
built on those step types were deleted; their job evidence stays.

## Code

- `wb_studio/product_graphs.py` (new): `save_draft`, `plan`, `prepare`, `load_version`, `listing`,
  `render`, `request_floor`, `parse_knowledge`, `validate_fields`.
- `wb_studio/execution.py`: `product-graph` runtime kind, `bound_graphs`, `execution_manifest`
  over graph hashes, delivery events; enrichment code removed.
- `wb_studio/blueprints.py`, `runtime_registry.py`: node validation ("Choose a prepared product
  graph version"), readiness `preparation_required` with the exact reason, `graphs` bindings on
  every listed version.
- `wb_studio/app.py`: `/api/product-graphs` (GET listing + corpus products, POST draft, POST
  prepare, GET plan, GET version events); `pg.js` on the static allowlist.
- `wb_studio/static/pg.js` (new), `graph.js`, `index.html`, `graph.css`: the Product graphs tab
  (fields table with new/changed/carried chips, plan line, researcher, versions with records
  tables, load-into-draft, use-in-architecture), the Product graph step and its inspector.

## Evidence

- Offline: `tests/test_studio_execution.py` (prepare once, extend carries fields, failed-then-
  retried, budget floor refused before any claim, records flow into scored attempts and the
  delivery event), `test_studio_blueprints.py` (step validation); every test file touching
  `wb_studio`: see the session record.
- Live (`.impeccable/review/verify-pg.cjs`, 13 of 13 checks, zero page errors):
  "Catalog basics" v1 prepared over 42 products for $0.018 (after one refusal on a $0.30 budget,
  recorded as failed and retried under the same number), v2 extended with one new field for $0.008
  with the two carried fields intact, template "Product graph, then act" bound to v2, published as
  "Informed worker" v1, one live run on the first corpus task (Airtable expense approvals):
  Activity shows the delivery step, the worker ran with the records, task checks failed (a quality
  outcome on a hard task, not a wiring failure), $0.14. Screenshots `.impeccable/review/pg-*.png`.

## Not done

- No per-product editing of records; a version is exactly what the researcher returned.
- No diff view between product graph versions beyond the researched/carried markers.
- Removed fields are dropped from the new version's schema and records (recorded as `removed`).
