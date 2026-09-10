# The boundary between WorkflowBench and Monarch

Who describes what, where the truth lives, and what each side asks of the
other. Settled 9 September 2026 between the AI Labs session (this repo) and the
Monarch session (the sibling `../monarch` clone), and recorded on both sides.

The Monarch-side copy is the appendix of
`../monarch/local-docs/benchmark/response-schema-synthesis.md` ("The
FD/WorkflowBench boundary, settled 2026-09-09"). That repo is not ours to
restructure; this file is the AI Labs copy, in English, carrying only what is
still true on 10 September 2026.

## The rule, in one sentence

**Where a mock exists, the mock is the truth and the AI Labs generator
describes it. Where only the real platform exists, the vendor spec plus an
observed response body describe it, and Monarch's synthesizer does that.**

## Why the split falls there

The 47 simulated apps under test are AutomationBench mocks. What they actually
accept and return is visible only in their Python source: the data models, the
router lambdas, and the handler signatures. No crawler and no OpenAPI document
can see those. That is why the bench-side generator is the right authority for
those 47 products, and why nothing on the Monarch side should reconstruct them
from the front door's OpenAPI document.

The failure this rule prevents is concrete. The bench's front-door OpenAPI is
transcribed from the *real* vendor, while its response bodies come from the
*mock*, and the two disagree completely: Gmail's `Message` is
`snippet` / `payload` / `threadId` in the document and
`body_plain` / `attachment_ids` / `thread_id` on the wire. A schema matched
from the document would describe real Gmail and lie about the mock — and the
mock is the system under test, so a publishable benchmark result must mirror
it.

Monarch pins this with `tests/bench-exclusion.test.ts`, which fails if anyone
regenerates the bench seeds from the front door's document. It asserts the
naming-convention divergence rather than an exact-zero field intersection, so
it does not break the day either side adds a shared field.

## Who owns which artifact

| Artifact | Owner | Where |
|---|---|---|
| The 47 simulated apps and their behaviour | AutomationBench (vendored) | `workflowbench/vendor/automation-bench` |
| The bench seeds Monarch learns from (product knowledge for the 47 apps) | AI Labs generator | `wb monarch setup`, output in `workflowbench/out/monarch-seeds*/` |
| The front-door OpenAPI documents | AI Labs | `workflowbench/wb_world/openapi.py` |
| The HTTP front door itself | AI Labs | `workflowbench/wb_arms/http_shim.py` |
| Response contracts for *real* platforms (not the mocks) | Monarch, Feature Discovery | `implementation_steps.response_template.schema` |
| The knowledge-base hashes pinned per round | AI Labs | `config/products/simulated-apps.monarch-kb.yaml` |

## Catalog integrity, verified end to end (9 September 2026)

- The generator's 733 output files hash byte-identically to what sits in the
  Monarch repo and to what the Railway Postgres holds: 47 products, 686
  actions, all carrying the modern `schema` member.
- The bench harness signs in as an organisation holding exactly 47 grants, all
  `bench-*`. The 14 non-bench products in Feature Discovery are granted only to
  the development organisation, and the product gate is deny-by-default, so
  they never enter a round.

That last point is what makes the comparison fair: Monarch sees the same
catalogue as every other competitor and nothing else.

## The 40 actions without top-level properties

Verified by running `projectResponseContract` against the real shapes. Three
groups, and two are not problems:

| Group | Count | Status |
|---|---|---|
| Writes whose mock returns `{}` on purpose | 25 | Passes Monarch's lint Rule 39. A precision request only: omitting the member rather than writing `{}` would make the projection answer `known_empty`, which is the accurate signal. Nothing breaks today. |
| Lists returning a bare root array | 9 | Already works. The projection walks the tree rather than looking for top-level properties, so these were never blocked; the "no properties" count was a heuristic, not the projection's criterion. |
| find-or-create POSTs (Intercom, HelpScout) | 6 | Case by case; the only group where a real gap may exist. |

## What each side asks of the other

**Monarch asks the bench generator:**

1. **Keep `required` faithful to the mock.** Deriving it from handler
   signatures is optimistic — a parameter with a default is optional in
   practice. Where Monarch finds a `required` the mock accepts omitting, it
   reports the case rather than assuming fidelity. `unknown` is preferable to
   an invented `required`.
2. **Declare every new seed member in the shared zod contract.** The contract in
   Monarch's `packages/executor-contracts` **strips undeclared keys**. A new
   member emitted by the generator works in fixtures and disappears silently on
   every real read unless it is declared there. Monarch hit exactly this defect
   with its own `schema_source` member.

**The bench asks Monarch** (open items, owner named):

1. A route to cancel a running workflow run —
   `POST /api/workflows/runs/:id/cancel` — that aborts the engine leg, releases
   executor claims and marks the run `cancelled`. Today the bench can only stop
   a run by deleting the workflow, so a timeout cannot clean up without
   destroying the evidence. (Deyton)
2. An executor-side failure must surface as a terminal run error rather than
   parking the engine in `awaiting_executor` until the bench deadline. Observed
   4 September 2026 on run `0eb9da87-5899-4450-9f9b-a3877a2364b7`. (Deyton)
3. A public authoring API reachable by API key, so the bench does not depend on
   session login. Today `WorkflowsController` and `RecipeRunController` are
   session-guarded only; the one API-key route is the read-only
   `GET /api/public/v1/runs`. (Deyton)
4. Feature Discovery learning the catalogue from the front door, estimated at
   about a week of work. (Deyton)
5. A knowledge-artifact import route. Confirmed 8 September 2026: no Enterprise
   or Feature Discovery route accepts one. Product knowledge is imported only
   from fixture folders shipped inside the `fdapi` image, replayed by
   `POST /v1/seeds/<slug>/import`. Everything the bench seeds must therefore
   travel as a committed fixture; the bench never writes to Postgres directly.
   (Deyton)
6. An unauthenticated `GET /api/version` returning the git sha baked at build,
   so external tooling can name the running release without repo access. Today
   the bench reads the sibling checkout with `git rev-parse --short HEAD` to
   build the competitor name. (Deyton, low priority)

## Telemetry the bench reads

Cost and phase timings for Monarch come from its Langfuse traces, priced by the
bench's own versioned table (`config/models/monarch-team-bedrock.yaml`). Two
facts about the trace shape, established 4 September 2026:

- The engine leg's root span is named `workflow.run`; `engine.run` and
  `engine.step` are children of it.
- Executions before the telemetry redeploy of 4 September 2026, 15:31 (UTC−3)
  carry no attempt id on the engine leg. Since that redeploy every
  `workflow.run` trace is tagged.

The contract the bench asked Monarch to satisfy is written in
`specs/002-monarch-create-run/contracts/monarch-telemetry.md`.

## A note on Bedrock

The 2 September investigation
(`../monarch/local-docs/benchmark/benchmark-access.md`) documents Monarch's
authoring as Bedrock-only, and none of Carlos's AWS SSO roles could call
`bedrock:InvokeModel` in `us-west-2` (tested 3 September 2026,
`AccessDeniedException` on all of them). **That blocker is gone.** Decision D2
of 8 September 2026 puts Monarch on plain Opus 5 through the Anthropic API, no
Bedrock, and the fork branch that runs it carries the direct-Anthropic
provider. See `STATE-OF-THE-PROGRAM.md`.
