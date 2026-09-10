# Historical usage accounted before the diagnostic, 10 September 2026

Carlos identified Langfuse as the source of historical Monarch usage. The read-only
audit covers Monday 7 September 03:00 UTC through 10 September 15:40:27 UTC.
[Exact observations, tokens, prices and attempt joins](2026-09-10-historical-costs.json)
have SHA-256 `5615e8051e6287c3ec9eab91537ebab4dcac999234f3228a6a9bb2526070fb0c`.
No prompt content or credentials are in that artifact.

| Source | Coverage | Observed US$ |
|---|---|---:|
| Langfuse, priced with the frozen Monarch table | 45 traces, 271 unique generations | 31.084633 |
| OpenAI receipts, frozen run prices | 24 attempts | 1.07278880 |
| Anthropic receipts, frozen run prices | 12 attempts | 1.75786500 |
| Fireworks receipts, frozen run prices | 24 attempts | 1.39999704 |
| Total observed | Failed and timed-out attempts included | 35.31528384 |
| Previously recorded in the weekly ledger | Two Monarch authoring settlements | 1.251886 |
| Previously unaccounted observed usage | Total minus existing settlements once | 34.06339784 |

The 18 scripted answer-key rows cost zero and are excluded. All three Langfuse
pages were read; generation IDs are unique, every model has a price, and no
generation lacks usage. Non-Monarch token totals reprice exactly to the stored
row totals. Two untagged Monarch traces (US$ 0.005182) are conservatively included.
The Studio pilot's US$ 1.962602 is included although absent from the CLI results DB.

Two CLI errors stored zero Monarch cost although their traces price to US$ 2.583201
and US$ 0.717440. The two existing ledger settlements also omit later engine
generations (US$ 0.001563 and US$ 0.001409). None of those omissions is treated as
free usage, and historical result rows were not rewritten.

The zero-token GPT error was a local OpenAI SDK import deadlock, with empty turns
and a 0.198-second attempt. This supports failure before dispatch; there is no
historical HTTP capture, so it is identified as an inference. The supposedly
provisional GLM rates were checked against the
[official Fireworks model page](https://fireworks.ai/models/fireworks/glm-5p3):
US$ 1.40 input, 0.26 cached input, 4.40 output per million, matching the frozen file.
No historical price file or configuration hash was changed by that check.

## Ledger treatment

Before the new diagnostic, the existing BudgetLedger.reserve operation added
**US$ 34.064 held**, conservatively covering the observed gap and rounding:
`historical-usage-20260907-through-20260910T154027Z`.
Its metadata pins the exact evidence SHA above. The referenced original scratch
JSON was subsequently expanded with follow-up checks; its exact initial bytes
were recovered as `langfuse-costs-initial.json` and preserved in the linked artifact.

The hold was first checked against a copy of the ledger. The live record is not
claimed (no new model dispatch) and not settled as an invoice. Existing settlements
remain immutable. After the hold: US$ 1.251886 recorded, US$ 34.064 held,
**US$ 264.684114 available**. The formal `historical_billing_verified` reconciliation
flag remains false: usage and rate checks are not a provider invoice export.

The diagnostic uses the already-authorized smoke scope with its separate normal
reservation. Historical observed liability stays held, rather than using the old
US$ 298.75 display as spendable budget or declaring missing costs zero. This audit
does not claim completeness for unrelated projects/accounts or infrastructure.
Future accounting must identify this hold before importing the same generations
or API rows, so it cannot count them twice. Finalize it only from complete billing
evidence, preserving the distinction between observed usage and invoice settlement.

The new attempt must be checked again after Langfuse ingests its engine generations;
the historical audit does not establish completeness of a future receipt.
