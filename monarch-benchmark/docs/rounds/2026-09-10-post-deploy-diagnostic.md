# Post-deploy front-door diagnostic, 10 September 2026

Carlos requested one Monarch attempt, no task retry, estimated US$ 2–3.
`WB_OPERATOR="Carlos Mattos"` launched the unchanged `diag-front-door` plan after
the merged deployment and six verification checks. The harness reserved US$ 25;
the normal infrastructure retry scope was disclosed, but no retry occurred.

| Identity | Value |
|---|---|
| Run | `run-20260910-155059` |
| Configuration hash | `995ffb6626eaf429` |
| Task | `simple.airtable_find_update` |
| Task hash | `c999452d6ddd0439` |
| Competitor | `monarch@0cf63a74e+feat/railway-dev-deploy` |
| Upstream world | `1.0.6`, unchanged |
| Attempt window | 15:51:00–15:54:36 UTC |
| Workflow run | `adda5af1-a0ce-4c95-9e8d-3ffbbbb99ff3` |
| Engine trace | `4130fd2cb487ddf856f84546fae4a631` |

## Observations and verdict

Artifacts are under `workflowbench/out/run-20260910-155059/episodes/`:
`simple.airtable_find_update/monarch@0cf63a74e+feat_railway-dev-deploy/t0/`.

- `front-door.jsonl` lines 1–2 show Airtable base/table discovery, both HTTP 200.
  Lines 9–10 show the contact and VIP lookups, both HTTP 200. Both return the
  same `rec_001` with `Status=Active`. There are no writes.
- `attempt-000/turns.jsonl` line 109 records the final Monarch poll: `success`,
  engine `done`, four completed steps, `create_vip` skipped, zero writes. Its
  branch treated the nonempty VIP lookup as an existing VIP. This corroborates
  the offline reproduction; it does not require changing the simulator.
- `snapshot0.json` and `snapshot1.json` preserve the unchanged world;
  `episodes.jsonl` at the run root records `n_changes=0`, failed positive and
  approval judges, no retry, and `infra:harness_crash`.
- The infrastructure refusal is `model 'claude-opus-4-6' is not in price table
  monarch-team-bedrock`. `wb_arms/monarch.py::_add_cost` intentionally stops on
  an unknown model price; `_settle` retains the maximum hold. This is a price
  coverage refusal after product completion, not evidence of a product crash.

The deployment's application path is verified. The requested WorkflowBench
`completed` termination is **not achieved**. Do not publish this as a pass rate,
rename its termination, regrade it under a changed hash, or interpret its stored
US$ 0 as free usage. The original run, plan and price table remain frozen.

## Cost and next step

The attempt's US$ 25 reservation is `unknown_hold`, actual cost null. Combined
with the historical liability hold, the ledger records US$ 1.251886 actual,
US$ 59.064 held and US$ 239.684114 available. Formal historical provider billing
verification remains false. No additional paid attempt was launched.

Read-only Langfuse accounting found **22 unique generations, US$ 0.89375475**:
US$ 0.89002375 authoring and US$ 0.003731 execution. The writer's six Opus 4.6
generations account for US$ 0.23675975. These are observed token costs, not a
provider invoice settlement; the maximum hold remains in place.
[Per-generation evidence](2026-09-10-diagnostic-costs.json) has SHA-256
`bd667783dd87a93b8bccfc3fb3505616dd01fce50d8c895b13947fe52a36a4d0`.

## Price coverage corrected for future attempts

The new `monarch-team-anthropic-20260910.yaml` preserves the original table and
adds the observed writer's standard prices from
[Anthropic's official price table](https://platform.claude.com/docs/en/about-claude/pricing):
US$ 5 input, 0.50 cache read, 6.25 five-minute cache write, 25 output per million.
Other prices are inherited unchanged from the 3 September table.

The provider identity is also corrected. On deployed Monarch `0cf63a74e`,
`monarch-enterprise/apps/backend/src/config/env.ts:354` defaults the writer to Opus 4.6.
`recipe-writer.ts:173` calls the shared single-turn helper;
`single-turn-model.ts:137` selects direct Anthropic through
`config/bedrock.ts:63`. The backend has a nonempty Anthropic key, confirmed by
[boolean-only Railway evidence](2026-09-10-diagnostic-provider.json).
The engine delegates to that same backend helper (`engine-llm.service.ts:721`),
and the brain uses `agentSdkBedrockEnv` (`anthropic-recipe-brain.ts:1058`), whose
direct branch strips inherited provider switches (`config/bedrock.ts:354`).
The stale Bedrock comments do not describe the observed route.

The current Monarch harness points to the successor table. Its
[previous configuration](2026-09-10-monarch-harness-before-pricing.yaml), original
table and this run's embedded configuration remain available. Future resolved
configurations change; this completed run cannot be resumed under them:

| Plan | Before price correction | Prepared replacement |
|---|---|---|
| diag-front-door | `995ffb6626eaf429` | `b474bb1dc69b6c86` |
| tier-simple | `90069901b24e7fce` | `a3dbc30fc6d376b1` |
| tier-medium | `b788cef293980d55` | `c676b5549e395691` |
| tier-complex | `09e701c0682d3e56` | `13a825830187b4ba` |
| random-10 | `cd5ef08b9765ab67` | `786a1c35289520f2` |
| pilot-monarch-create-run | `41769e05aa5618a9` | `1912201bfea8a62a` |

The pilot row was added during PR #3 CI review: its pinned test still expected
the old price configuration. Resolving the same tasks with the archived harness
and original table reproduces `41769e05aa5618a9`; the successor alone produces
`1912201bfea8a62a`. Updating the test expectation preserves the historical hash
and changes no benchmark data.

An offline test first reproduced the exact `PriceLookupError` using the configured
harness and observed model name, then passed with the successor table. The full
Langfuse/config group passed **129 tests**. No stored result or billing record was
recalculated in place and no further paid attempt was launched. Future dispatch
still requires billing readiness; pricing this known model does not resolve that
gate or the unchanged task's filter limitation.

The 22 stored generation records also replay successfully through the new price
table offline: US$ 0.893755 after the existing per-generation microdollar rounding.
This is supplementary cost evidence, not a replacement of the stored run.
The standard internal report was generated without model calls at
`workflowbench/out/report-run-20260910-155059-internal.html`; it retains the
original infrastructure verdict and unknown-billing flags.
