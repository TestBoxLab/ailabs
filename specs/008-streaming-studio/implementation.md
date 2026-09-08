# Live comparison workspace — 2026-09-08

Lucas requested paid execution and a polished streaming UI, with model comparison as the primary surface and task drilldowns.

## Delivered

- Private localhost application at http://127.0.0.1:8765, started by `uv run --frozen wb studio` from `monarch-benchmark/workflowbench`.
- Comparison creation with up to ten frozen tasks and four available runners, an explicit shared comparison maximum, task selection, execution lanes, individual action/output inspection, results, stop controls and durable history.
- Actual tool start/completion/error events stream through reconnectable SSE. The diagram depicts observed execution order, not a fabricated authored workflow DAG.
- JSON records render as structured fields/tables; model prose renders as escaped text with basic document formatting. Raw evidence and copy remain available. Large tables disclose displayed records/fields.
- Same-origin/session write checks, fixed static file allowlist and server-only credentials. Runtime job artifacts are ignored by Git.
- Production Studio instances share the canonical `research/budget.sqlite3`, even when their output directory differs. Request IDs and durable execution claims prevent replay.
- A bounded Gemini 3.7 Flash API control. It is explicitly separate from native-harness benchmarking. Every generation reserves and claims capacity first, with no automatic provider retry. Unknown billing stays held; usage estimates include thinking tokens. Receipts are retained in the event journal and attempt evidence.
- Credential refresh when opening New comparison. Root `.env` and workflowbench `.env` are server-only configuration; explicit file values take precedence.

## Paid boundary

The gateway is implemented and offline-verified, but the live pilot did **not** generate: the existing Google credential returned `HTTP 400 / INVALID_ARGUMENT / API_KEY_INVALID` during token preflight. No generation, reservation or charge was recorded for that pilot.

The exact synthetic task was explicitly approved by Lucas with a USD 5 cap after automatic approval review initially rejected its Google disclosure. The task was `simple.email_sf_contact_city_update`: Lisa Park's office relocation email and updating her simulated Salesforce mailing city. The initial rejection was resolved by that explicit approval; the credential rejection is a separate provider issue.

A valid `GEMINI_API_KEY` is still needed. No real Claude/OpenAI API credentials were received in the workspace during implementation. Native Claude Code/Codex remain unavailable: Docker's backend exited during startup; its Windows service is stopped and this session cannot start it. There is no claimed verified native sandbox or real native execution.

The gateway conservatively reserves USD 1.048576 per default request, covering the model's full input ceiling plus thinking ceiling and the configured candidate output cap. Therefore a comparison cap smaller than that refuses generation even if likely usage would cost less. It settles to a rounded-up estimate from reconciled provider usage, **not a verified invoice**. It ignores cache discounts conservatively. Missing usage retains the full hold.

Verified rate card expires 2027-01-01. Sources: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), [model limits](https://ai.google.dev/gemini-api/docs/latest-model), [usage metadata](https://ai.google.dev/api/generate-content#UsageMetadata), [token counting](https://ai.google.dev/api/tokens), [function response IDs](https://ai.google.dev/api/generate-content#FunctionResponse).

The original unrestricted paid CLI/native paths remain blocked. Supported paid API controls are launched through Studio. Workflow authoring-plus-execution remains a separate future runner contract; this increment runs the agentic-request track.

## Validation

```powershell
uv run --project monarch-benchmark/workflowbench --frozen python -m pytest monarch-benchmark/workflowbench/tests/test_studio_app.py monarch-benchmark/workflowbench/tests/test_studio_paid.py monarch-benchmark/workflowbench/tests/test_budget.py monarch-benchmark/workflowbench/tests/test_evidence.py monarch-benchmark/workflowbench/tests/test_foundation_cli.py -q
```

**125 passed in 9.86s.** This is the relevant regression set, not a new full-suite claim.

A real offline comparison ran both the reference and near-miss controls against the same task through the live server: reference passed, near-miss failed. Both have persisted events and verified original evidence. Fake-provider tests execute multiple model turns and real simulated tool calls without spending.

Browser verification at desktop 1440x1000 and mobile 390x844 found no runtime errors or page overflow, and proved output drilldowns, retained keyboard focus, cleared stale outputs and explicit truncation disclosure. Screenshots are in `.impeccable/review/`. Browser automation used bundled Playwright after the standard CUA tool failed with the environment's deny-read ACL error.

Mechanical design checking ran in regex fallback because its parser modules were unavailable; its empty result is not a full contrast/design pass. Independent UI review found three defects (stale inspector, lost focus, silent table truncation), then those fixes were implemented and browser-verified.

## Remaining prerequisites

1. Supply a valid server-side Gemini credential and run the explicitly approved bounded pilot.
2. Restore Docker or another real isolated native runtime, implement/verify native adapters, then connect Claude/Codex billing credentials.
3. Add workflow creation-plus-execution and actual authored DAG rendering without confusing it with observed action sequences.
4. Add verified provider invoice reconciliation; current monetary values are usage estimates and conservative held liabilities.
