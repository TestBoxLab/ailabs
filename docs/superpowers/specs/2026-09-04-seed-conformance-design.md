# Seed conformance: every catalogue action executed before import

Feature 008. Design of record, 2026-09-04.

## What

`wb monarch conform` runs every action in the generated Monarch knowledge base
(`out/monarch-seeds/bench-<app>/*.json`, 47 apps, 686 actions) against the
simulated apps and says, per action, whether the seed tells the truth. A gated
copy of the same check sits in `wb monarch setup`, between generate and import.

## Why

The Monarch team's `validate-seeds.mjs` is static: it checks the shape of a seed
file, never whether the request it describes works or the response it declares
is the response the front door really returns. A wrong Google Sheets response
schema passed that validator, was imported, and made Monarch refuse every Sheets
task — the catalogue said `values` was an array of spreadsheet records
(`{id, title, worksheets}`) while the front door returns rows of cells
(`[["Spot","Type"],["P-101","Standard"]]`). Shape-valid, false.

A false catalogue is worse than a missing one: the builder plans against it, the
engine dispatches against it, and the benchmark scores Monarch on a lie it was
handed. The check must run before the import, not after a bad round.

## How

One world per service, not per action-with-a-fresh-world for reads. For each
service in the seeds, the corpus task (`corpus/imported-*`) with the largest
`initial_state[<service>]` becomes the world: the richest fixture is the one most
likely to contain a record every action can name. The world is built in-process
(`wb_world.episode.Episode`) and called through `ep.api_fetch`, mapping the
seed's front-door `url_template` (`https://<host>/<service>/<rest>`) onto the
service's `baseUrl` exactly as `wb_arms/http_shim.py::_rest` does. No HTTP, no
port, no server: the check is the same code path the shim would have taken.

The request is built from the seed itself: path and query placeholders from
`parameters`, body from `body_template` with `{{field}}` slots filled from the
record fields in the initial state where names match. An `entity_reference`
takes an id of its `entity_type` out of the world; a parameter named like a
collection takes that collection (`sobject` -> `Account`); one named like a
record field takes a real value (`title` -> an actual worksheet title, so a
Sheets range is a range that exists). Unfilled optional query pairs are dropped,
as the engine drops them. Writes run too, each on a fresh world so one write
never poisons the next.

## The verdicts

| verdict | means | gates? |
|---|---|---|
| `ok` | the request ran, the response matched the declared schema, every extract resolved | no |
| `schema_mismatch` | the real success response does not validate against `response_template.schema` (first three differences as `path: expected X, got Y`) | yes |
| `extract_empty` | a *required* extract path, or every extract, resolves to missing / null / empty | yes |
| `request_rejected` | a route that exists refused the arguments sent | yes |
| `no_handler` | the app's OpenAPI document declares the route but its router does not serve it | no |
| `write_not_landed` | a write's snapshot diff (`ep.finish()` vs `ep.snapshot0`) shows no change | no |
| `not_executable` | no request could be built from real data (says which parameter had no source) | no |

Plus one flag, not a verdict: `extract_thin` -- a read or list whose extracts
expose only ids, so the builder can chain but never read a field.

The schema check is a small stdlib validator (type, required keys, nested
objects, array item shape). Full JSON Schema is not the point: the failures that
matter are "declared object, got array of arrays" and "declared required key,
absent".

### Not crying wolf

A check that reports hundreds of failures gets switched off, so every verdict
that is really *this check's* ignorance is kept out of the gating set:

- a **path parameter, or a required query parameter**, may only be filled from
  real world data, an enum, or a real `example_value`. Never from a literal:
  asking for a Slack channel named `test` earns a 404 that says nothing about
  the seed. Unfillable means `not_executable`.
- an **optional** query pair is sent only when the world backs it, so a made-up
  filter never narrows a list to nothing and reads as an empty extract.
- an **error body is never schema-checked**: a rejected request is
  `request_rejected`, not a false schema.
- an **optional field left empty on this record** (a contact with no job title,
  a mail with no cc) is not a mismatch -- `null` says this row has no value, not
  that the contract is wrong. Only a *required* empty extract, or an action
  whose every extract is empty, counts.
- a **`{var}` left unsubstituted in the service's own `baseUrl`** (BambooHR's
  `{companyDomain}`, Recruitee's `{company_id}`) is a whole-service mapping
  fault: `not_executable`, once per action, never a seed defect.
- a **write whose router blew up on an invented body** is `not_executable`: only
  reads, whose requests carry no invented body, can be held to the contract.
- an **entity reference whose example is one of the generator's stock
  placeholders** (`001401`, `1`) is refused rather than sent: it asks for a
  record that exists in no world.
- a **tenant-scoping segment** (`companyId`, `realmId`) is free: one world is
  one tenant, so any value routes identically.

Applying these took the reported read failures from 275 to 64 across 674
actions, none above six per service, and the survivors are the believable kind:
`$.tables: expected object, got array` on an Airtable list,
`$.values[0]: expected object, got array` on the Sheets read that started this,
`resultSizeEstimate` typed object instead of integer on Gmail.

## The gate

`wb monarch conform` exits 1 when any checked service has a verdict outside the
benign set (`ok`, `not_executable`, `no_handler`). The benign ones are the
check's own limits or the simulated app's, not the seed's fault.

In `wb monarch setup` the step runs for the services the product lists and stops
with code 2 **before import** only when a *read or list* action, whose request
was built entirely from real world data, has `schema_mismatch`, `extract_empty`
or `request_rejected`. Everything else is a warning line: write failures,
`no_handler`, and `not_executable`. A write needs inputs the check cannot always
invent (a base64 RFC-2822 message, a well-formed nested body), so a failing
write is more often this check's ignorance than a false seed. Reads have no such
excuse -- they are what the builder reads the contract from, and they are where
the Sheets bug lived.

The gate can be turned off for a deliberate import: `wb monarch setup
--no-conform`, or `run(..., conform=False)`.

Report: a table per service to stdout, totals, and `out/monarch-seeds/conformance.json`.
