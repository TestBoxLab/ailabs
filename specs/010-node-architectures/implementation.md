# Node architecture workspace

8 September 2026. Private local changes; no deployment or publication outside Studio.

## Delivered

A visual directed node editor with draggable positions, accessible input/output ports,
connection removal, zoom, arrangement and undo. Nodes cover benchmark input, product
graph fields, agent enrichment, additional agent roles, prompt changes, branch joins,
Default Monarch Enterprise and result output. Field paths/types/descriptions, target
fields, instructions and runner/model/reasoning choices are saved in node configs.

Save draft uses revision compare-and-swap. Publish version validates connections,
acyclic flow, reachability and upstream enrichment fields, resolves the Enterprise
GitHub revision, and writes an immutable numbered version with parent and graph hash.
Repeated publication of the same draft is idempotent. Versions can become a new draft
or be exported as JSON. Publication here means a local definition, not public hosting.

Claude Code, Codex, Fireworks and Gemini are selectable node runner configurations.
New run can also save runner profiles. Fireworks catalog refresh follows every page
for the public account and an optional FIREWORKS_ACCOUNT_ID; errors do not return a
partial catalog. It loaded 306 models with the user-supplied credential. Models may
require deployments or lack task-compatible capabilities; membership is not a launch
readiness claim.

Task rows display right-side Easy/Medium/Hard/Unrated indicators with failure/sample
counts. Only matching task-contract hashes are combined. Scripted controls,
infrastructure failures and incomplete evidence are excluded. Below five attempts,
labels are provisional. Failure-rate thresholds are one third and two thirds;
Wilson intervals and the dependency on tested configurations are retained. This is
observed difficulty, not intrinsic task complexity or proof of model superiority.

## Credentials and paid pilot

The provided Downloads/env file was installed into git-ignored .env without displaying
values. Google, OpenAI, Anthropic and Fireworks entries are configured.
The separately approved Google pilot studio-google-pilot-002 completed the exact Lisa
Park relocation task: passed, 9 tool calls, provider-usage cost estimate USD 0.017971.
This is one attempt, not a benchmark quality estimate. Invoices remain unreconciled.

## Remaining runtime work

Published graph execution is not yet integrated with Monarch Enterprise. Native Claude
Code/Codex isolation and Fireworks inference/billing admission are still unimplemented.
Saved profiles and model discovery do not bypass the execution gate. The working paid
path remains the bounded Gemini API control. No native/Fireworks inference was run.

## Evidence

187 tests passed in 11.80 seconds across Studio, architectures, blueprints, catalogs,
difficulty, shared budget and evidence. Exact new cases are in
.testagent/blueprints.md. Browser exercised enrichment authoring, connecting ports,
real draft persistence and version publication. Final confirmation verified edits
survive saving, discarded drafts stay discarded, keyboard focus remains usable, a
real pilot produces a provisional difficulty badge, no browser errors and no page
overflow at desktop/mobile sizes. Artifacts: .impeccable/review/graph-*.png.

Official Fireworks list API: https://docs.fireworks.ai/api-reference/list-models


## Comparison-launch correction

Scripted reference and near-miss fixtures are removed from the production runner
catalog and rejected by production launch admission. Internal test fixtures and
historical evidence remain intact. The run launcher now explicitly records
architectures=[without-monarch] for the available API control. Default Monarch
Enterprise and published graph versions are visible but blocked until their runtime
integration exists. Requests for unsupported architecture combinations fail before
job creation or spend; the UI does not silently substitute an API baseline.

Native isolation audit: native_sandbox.py is a launch prohibition, not an implemented
sandbox. Filesystem, environment, network, application gateway, native trace capture,
runtime pinning and billing verification are not implemented for native execution.
Existing Gemini evidence must not be presented as proof of native study readiness.
28 targeted tests passed; comparison-mode browser checks passed.
