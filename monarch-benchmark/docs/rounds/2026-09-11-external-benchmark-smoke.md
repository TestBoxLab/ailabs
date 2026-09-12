# External benchmark alternatives: implementation and paired smoke

Status: source adapters and private controls verified; paid comparison pending.

Lucas requested two tasks per alternative, comparing Monarch Enterprise with a
native-agent baseline. He selected reviewed task-specific EnterpriseOps-Gym rules
on 11 September 2026. These decisions supersede the original ten-task offline
smoke and open rule-derivation question in feature 026.

## Design and scope

The three alternatives are independent products: EnterpriseOps-Gym ITSM/oracle,
AppWorld dev, and Sierra tau2 retail/base. Source requests, worlds, data and source
checkers stay unchanged. WorkflowBench translates public API transport and adds
its separate permitted-change check and normal-completion requirement. Sources
and their scores are never pooled. AutomationBench's world and tasks are untouched.

These are one-off business requests. Monarch may create and execute a workflow
internally; native Codex fulfills the same request with the same application access.
This is not workflow reuse, a representative performance estimate, or a controlled
experiment isolating architecture from underlying models and harnesses.

Native baseline: Codex 0.153.4, gpt-5.6-sol, xhigh effort, API-key billing, isolated
container with no host mounts or network. Its broker allows the common application
tools and verified provider requests. Acceptance proof used real native CLI tool
calls with free scripted provider replies; it is not a scored model attempt.
Monarch: c6f42272ae3f7af6f0214a1075fdfc51b9bf2c56, named custom deployment,
unattended authoring, frozen direct-Anthropic price table. Each source has a separate
organization granted only its catalogue. No experimental Monarch code was merged.

## Source controls and evidence

- EnterpriseOps-Gym: two correct setup controls pass and two null controls fail;
  stored SQLite evidence regrades identically after teardown. No source reference
  solution exists, so these controls do not establish an answer-key ceiling.
- AppWorld: two source reference controls pass, two null controls fail, and an
  additional collateral control fails. Four complete Orchestrator/Store/report
  attempts regrade identically. Detailed source content and outputs remain outside
  this public repository; repository manifests contain identifiers and hashes only.
- tau2: genuine source reward tests preserve ALL and each task's reward_basis;
  strict replay and timeout failures are tested. Both selected tasks use DB reward;
  tasks requiring an additional paid source natural-language judge were not selected.
  The customer uses a separately recorded, billed gpt-5.6-sol participant.

Evidence pointers:
- `workflowbench/out/eog-9efb6d5a/summary.json`
- `workflowbench/wb_worlds/appworld/orchestrator-control-manifest.json`
- `workflowbench/out/tau2-source-verification-20260911-1553/`
- `workflowbench/out/external-smoke-preflight.json`

## Catalogue deployment and authorization

Lucas explicitly approved the additive fdapi deployment, the three source-only
organization grants, and use of the temporary Cloudflare tunnel and hosted relay.
The latter is temporary: restore STUDIO_FRONT_DOOR_TARGET to
http://127.0.0.1:9105 after the smoke. The existing ngrok account refused connection
with ERR_NGROK_102 (account suspended after a failed payment); no account or payment
settings were changed.

fdapi deployment: 41d36d03-0127-417b-89e9-88d29d755973. The prepared context contains
unchanged tracked Monarch code, byte-identical baseline fixtures, and 13 new source
catalogue entries / 482 actions. After import, all 60 bench entries / 1168 actions
are in sync; all 47 prior entries / 686 actions match the saved live baseline exactly.
Other existing non-benchmark products were not imported or granted.

The source facade preserves source schemas. AppWorld uses explicit token inputs,
JSON for form inputs and query parameters for DELETE inputs, consistently for both
competitors. Mixed-type source bodies are represented as an object payload with the
complete source schema in discoverable constraints; no fields or examples are guessed.

Deployment and grant evidence:
`workflowbench/out/external-catalogue-verification.json`,
`workflowbench/out/external-source-orgs-granted.json`.

## Paid launch envelope

Operator: Lucas. Planned: 12 evaluated attempts (2 tasks x 3 products x 2 competitors).
No discretionary retries. At most two automatic infrastructure retries per attempt:
36 possible invocations, at most18 per competitor across all three products. Each
product's round is capped at USD60; the three-round maximum is USD180, including
customer calls and retries. No paid report analysis is planned.

The shared week starting 7 September has USD292.271657 available before these runs,
after USD6.385959 recorded spend and USD1.342384 retained unknown holds. Historical
billing remains unverified; those holds are retained, not converted to zero. Each
round must reserve its complete capped liability before the first provider dispatch.
Actual attempt receipts and Langfuse costs will be recorded separately from this cap.

## Results

Pending live comparisons and final validation. No paid outcome is claimed here.
