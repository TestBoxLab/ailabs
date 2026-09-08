# Wire Enterprise and recover BRIDGE v2 / v9.12

Status: investigated implementation plan, 8 September 2026. Target implementer: **gpt-5.6-sol, medium**. No runtime changes or paid experiments performed for this plan.

## Outcome and identities

A user selects a task set, comparison versions, supported models and thinking levels, then watches actual execution and inspects the resulting business outcomes. A saved architecture must change execution, not merely the displayed diagram.

Keep three identities explicit:

| Version | Meaning | Promotion rule |
|---|---|---|
| Without Monarch | Native harness with the common task and application interface, no Monarch graph, contract, gates or cross-attempt memory | Working isolated adapter and evidence/billing checks |
| Default Monarch Enterprise | Official `TestBoxLab/monarch`, `monarch-enterprise`, current main resolved and frozen before launch, stock product behavior | Pinned build actually serving requests; required services, permissions and billing verified |
| Product graph enrichment — BRIDGE v2 + v9.12 | Versioned experimental architecture implementing the recovered historical knowledge and runtime settings | Exact source/artifact provenance and behavioral verification; Enterprise port is a new experimental identity |

Do not insert the experimental contract into Default Enterprise. Do not call the historical API shim Claude Code or Codex. Do not claim the Enterprise port reproduces the old score merely because its nodes have matching labels. Preserve existing published demo v1; replace the default template with a new version after verification, with an explicit parent/migration note.

## Verified findings

1. `wb_studio/architectures.py` resolves a GitHub SHA, but does not build or launch it. `blueprints.py` validates and freezes node JSON; publication remains `adapter_required`. `app.py` rejects Monarch comparison launches. These guards are correct until actual adapters exist.
2. Official main was `60faf2a238fcfd3dd420d52b558f6a78181baa68`. The monorepo is distinct from historical local `Monarch_Main/ATLAS`. Do not build Default from that older repository.
3. Existing `wb_arms/monarch.py`, `monarch_client.py`, `http_shim.py` and `wb_orchestrator/monarch_setup.py` provide useful create/run, SSE, graph-hash and application-front-door seams. They contain older Railway-specific assumptions and must be checked against the pinned product, not enabled unchanged.
4. Enterprise `operator/operator.controller.ts` creates one-off runs through `POST /api/operator/runs`; goal, productSlug, origin and threadId are accepted. `operator-run.controller.ts` exposes stream, confirmation, reply, cancellation and operation-result routes. One-off execution may require a bridge worker: prove which operations can execute headlessly before enabling this track.
5. Enterprise `workflows/recipe-agent/recipe-run.controller.ts` creates recipe sessions, streams them and supports reply/cancel/rehearse. Its `brain` field accepts named presets, not arbitrary model/effort values. Workflow execution is a separate phase. Existing benchmark client paths include `/api/workflows/:id/run`, `/api/workflows/runs/:id` and recipe streams.
6. Enterprise `operator/runner/models.ts` delegates availability to Bedrock; `config/bedrock.ts` selects BEDROCK_REGION/AWS_REGION. Current direct Anthropic/OpenAI keys alone do not establish stock Enterprise billing. The API request shapes inspected do not support arbitrary per-run model and thinking overrides. Enumerate actual environment/brain support; refuse unsupported selections. A new provider seam is a custom build, never an invisible stock change.
7. `product-graph/product-graph.source.ts` defines ProductGraphSource and the PRODUCT_GRAPH_SOURCES registration token; organization/permission projection happens downstream. Adding graph metadata to this interface alone does not prove that the operator or recipe agent consumes it. Trace both consumers.
8. `wb_arms/native_sandbox.py` is explicitly a launch prohibition, not an implemented sandbox. Native comparator execution remains a prerequisite, not an achieved property.

Source revision and local document hashes are in `investigation-sources.json`. GitHub source links use that exact commit: [Enterprise source](https://github.com/TestBoxLab/monarch/tree/60faf2a238fcfd3dd420d52b558f6a78181baa68/monarch-enterprise).

## Historical identity and knowledge specification

`C:/Users/Lucas Wakigawa/Monarch_Main/Monarch_Report.html` explicitly names **v9.12**. It reports Opus 5 medium **361/600**, cost **$216.57**, versus bare Opus 5 max **289/600**, cost **$235.63**; paired wins/losses 128/56. These are report claims, not independently recomputed results in this investigation. Different efforts mean this is a setup comparison, not an isolated enrichment effect.

The report identifies `config/monarch/graph-inline-v6-evalrepair10.json`: 216 actions, 358 reviewed tasks. It describes:

- Reviewed action semantics: non-effects, idempotency, response record locations, argument/value semantics; remove notes redundant with tool schemas.
- Product summaries and cross-product relationships, including destination identity chains.
- Four relationship slots, near-duplicate removal, task-relevant relationship priority.
- Local lexical/semantic retrieval with merged rankings; pre-run delivery of knowledge.
- Family-specific operator contracts, a declared work list, write gates and reconciliation. These are runtime behaviors, not graph fields.

The July diagram `MONARCH_BRIDGE_V2_DIAGRAM.html` instead names brief, reference, inventory, dead ends, gates, evidence; gates include provenance, duplicates, rosters, schema, coverage and format. It explicitly dates its measurement July 7. The old `ATLAS/docs/bridge/archive/BRIDGE_V2_PLAN.md` corresponds to `atlas-monarch-v2`. Do not automatically union every July gate into v9.12: later experiments rejected several heavy gate/prompt variants.

The August 12 attempt catalog reports graph-inline v8 Opus max 322/591 vs 261/591. That is a different release/panel from v9.12's reported 600-task comparison. Preserve both denominators and do not splice their statistics.

### Concrete recovery lead found after the initial inventory

`C:/Users/Lucas Wakigawa/Documents/Codex/2026-08-15/continue/vendor-patch-output/scripts/vendor-monarch-graph-inline-v6.ts` generates the exact graph filename named in the v9.12 report. This is a verified graph-producer source lead, **not yet a verified complete v9.12 runtime**. A work copy also exists under `vendor-patch-work`.

The source sets schema `monarch-graph-inline-v6-evalrepair10.v1`, implementation `atlas-monarch-v8-1-p0-runtime-record-opus5-graph-inline-v6-evalrepair10-port-v2`, suite `1.0.6+evalrepair.10`, and hashes its canonical artifact body. It checks exactly 358 reviewed tasks and complete current source provenance. Its dependency closure names:

- `.automationbench-local/suite-package-7a08b5047c89/actor/actor-contract.json` in the original project root.
- `AutomationBench-repair/adjudication/microscopic-brittleness-358-v1.json`.
- `ATLAS/backend/data/bench/bridge-v8/zapier-wired273-4a8e106-manifest-v1/capability-manifest-v1.json`.
- `ATLAS/backend/config/bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json`.
- `config/monarch/source-provenance-evalrepair10.json`.
- `ATLAS/backend/scripts/dev/automationbench-capability-runtime.ts` and `automationbench-shim.ts`, including `AUTOMATIONBENCH_OPUS5_GRAPH_INLINE_V6_DOCTRINE`.
- Current reviewed implementations of Slack user-by-ID, QuickBooks bank deposits and Recruitee job creation.

For unchanged actions it reuses reviewed v6 behavior; changed implementations receive current source/schema descriptions, and stale product contexts are replaced. Preserve these source-freshness rules. Do not copy all old descriptions into a new task/tool version.

The follow-up inventory found the historical manifest, catalog and 358-task adjudication, but not the actor contract, source-provenance JSON, generated graph or full 600-task run manifests. The existing AutomationBench-repair checkout has since advanced beyond evalrepair.10, so its current files cannot substitute for the frozen source revision. `bench-host-state/runs/evalrepair10-smoke12-v1/rehearsal/{request,result}.json` records only a zero-provider rehearsal, not scored v9.12 evidence. The `port-v2` suffix in the producer is not proof of identity with July's `atlas-monarch-v2`.

First recovery task: inventory and hash these dependencies in their original layout; locate the generated graph and report-associated runtime/manifests in backups or original worktrees. A regenerated artifact only qualifies as historical reproduction if its hash matches the original manifest. Otherwise label it a reconstructed candidate. Do not run this source directly from the temporary patch directory, whose relative imports point to nonexistent siblings.

**Provenance gate:** recover the v9.12 runtime, exact graph bytes, full run manifests, prompts, retrieval implementation/index/model, benchmark and grader revisions, provider settings, evidence and cost records. Link the report to concrete run IDs. Hash the complete runtime closure, including uncommitted source where applicable. Independently reproduce aggregate counts and pairings. If unavailable, keep the preset `source_required`; do not synthesize missing exact prompts or assert best-result reproduction. Independent Enterprise integration can proceed while this is unresolved.

## Implementation sequence

### 1. Runtime manifest and capabilities

Add `wb_arms/runtime_manifest.py` and `wb_studio/runtime_registry.py` (proposed paths). Expand architecture resolution/publication in `architectures.py` and `blueprints.py` with a schema-versioned executable manifest:

- Repository, full commit, dirty patch hash if any, lockfile and image digests, runtime entrypoint and dependency closure.
- Evaluation track; provider, exact model, supported effort, native harness/SDK version and non-default settings.
- Graph artifact, contract, retrieval index, prompt and compiler hashes; field provenance and parent version.
- Public tool-surface and world-contract hashes, budget policy, limits and evidence schema version.

Resolve latest at an explicit refresh or new stock run, then freeze it. Never follow moving main during execution/resume. Return separate source/publication/runtime readiness states. Capability discovery drives the picker; no arbitrary effort silently ignored and no provider fallback.

Acceptance: stock resolution is repeatable at a pinned SHA; changed graph/prompt/build changes identity; unsupported choices fail before job creation, reservation or provider dispatch; historical runs remain unchanged.

### 2. Isolated application and provider boundary

Implement real `native_sandbox.py` runtime enforcement and native Codex/Claude Code adapters. Reuse the evaluator-owned Episode gateway and budget ledger. Runtime gets a clean HOME and workspace, scoped application gateway, its own logs and bounded provider route. Evaluator/grader/task snapshots/other traces/host environment stay outside. No repository mount, Docker socket or unrestricted host/control-plane network route.

Use an enforced container/VM boundary with immutable images, resource and wall-time limits, per-attempt networks and state, and a narrowly scoped billing broker or equivalent enforceable mechanism. Container presence alone is not verification. For native streaming calls, reserve a conservative upper bound before dispatch, including retries; prevent hidden subscription billing. Preserve unknown-cost holds on timeout or loss of usage telemetry.

Acceptance: adversarial attempts to read evaluator canaries, other attempt state, host secrets or control endpoints fail; concurrent attempts cannot interfere; native tools operate normally on allowed workspace; cancellation terminates descendants; crash/retry cannot double-launch or release unresolved spend. Without Monarch cannot receive enriched notes via the common gateway.

### 3. Real Default Enterprise adapter

Add a pinned local build/deployment recipe under `monarch-benchmark/runtime/enterprise/` and an adapter such as `wb_arms/enterprise.py`; reuse the existing MonarchClient where compatible. Read upstream AGENTS and service compose dependencies first. Do not launch its full default compose with host mounts/network access without reducing it to the benchmark boundary.

Provision isolated backend, required FD/engine/queue/storage services and a benchmark organization with explicit graph/action grants. Route every application action to the episode gateway. Keep platform service credentials outside the evaluated agent surface. Verify actual backend build identity, graph served hash and consumer-visible context. Stock model/provider settings must be supported by the actual release. Verify Bedrock billing access without printing secrets; otherwise report this one readiness blocker while finishing offline work.

Implement separate one-off and create/run adapters. New threads per attempt. No automatic human answers for one-off tasks; record a clarification request as requiring assistance. Preserve product confirmations and permission behavior; any benchmark authorization policy must be explicit and shared where comparable. Create/run freezes the authored workflow, then executes it and captures both phases and costs. Do not treat simulation or recipe generation as successful execution. Never reuse a failed run's world for a retry.

Acceptance: a synthetic allowed request demonstrably changes only its episode world through the real product; missing permissions/services fail clearly; workflow artifact and execution result are distinct; cancel/crash produce durable partial evidence. Stock adapter must pass independently of the enrichment implementation.

### 4. Recover and package enrichment

Create an immutable historical bundle registry under `research/architectures/bridge-v2-v9.12/` with source manifest and provenance report (exclude private evaluator content from runtime packaging). Preserve the original fork/environment for exact legacy replay; do not reimplement it from report prose.

Define the new editor preset as visible stages: **Load reviewed product knowledge → Select relevant relationships and action notes → Run operator → Reconcile work and capture evidence**. The operator stage exposes the exact recovered contract, gates and memory configuration. Keep any original loops inside the runtime node; don't force a cyclic agent runtime into the editor's acyclic graph.

Graph enrichment is a preparation operation: typed fields with evidence/provenance, candidate edits, validation and immutable publication. Reuse frozen reviewed knowledge for scored attempts. An agent filling new fields produces a new candidate version, with its own runner/prompt/usage/evidence; it cannot silently rewrite the preset during a benchmark. Training/review tasks must be recorded: 358 reviewed tasks warrant a contamination/overlap audit before held-out claims. No hidden grader assertions or expected destinations can become graph facts.

Map historical graph fields into Enterprise's actual operator/recipe context consumers. Preserve org grants and action authorization. If a product patch is needed, record it as a custom Enterprise build. Support **graph-only** and **full recovered runtime** as explicit ablations; never call graph-only the full BRIDGE bundle.

Acceptance: byte-exact context/retrieval fixtures against recovered implementation; all active settings recorded; changed prompt/graph produces a new immutable version; invalid fields or unsupported node types fail preflight; bare arm gets no treatment artifacts. Report any unrecovered component separately.

### 5. Execute published node versions and compare

Add `wb_studio/execution.py` to compile published node definitions to validated handlers, typed inputs/outputs and runtime manifests. Implement handlers only for supported nodes; reject unsupported execution rather than running decorative nodes. Define deterministic merge conflicts, deadlines, failure propagation and durable node states. Bind all execution to the published version hash, not the mutable draft.

Replace hard-coded launch rejection in `app.py` only when a selected adapter is ready. Expand a run into task × version × supported model/effort × repetition, with a shared paired task identity and fresh episode world per cell. Do not require stock Enterprise to pretend it supports arbitrary GPT/Fireworks models. Native baselines and raw API controls stay accurately labeled.

In `static/app.js`, `graph.js` and related markup, use human labels, an execution-readiness explanation, visible architecture version, and node outputs. Show **Product graph enrichment — BRIDGE v2 + v9.12** with recovered settings and a readable version diff. Preserve published demo v1 in history, no mutation. Every claimed running/succeeded node must correspond to an actual event; expose omitted/skipped/failed nodes.

Acceptance: a changed custom architecture visibly changes the consumed context/runtime; a comparison runs independent worlds; a saved unsupported architecture remains editable but not launchable; desktop/mobile and keyboard interaction verified using Impeccable.

### 6. Evidence, analysis and scientific promotion

Extend existing `wb_results/evidence.py`, Studio reports and analysis adapters with evaluator-owned append-only events: node, phase, attempt, provider request, native event, tool request/result, rejection, usage and state revision IDs. Record raw observable events plus redacted readable views; retain supplied reasoning summaries only, never imply hidden reasoning capture. Gaps make an attempt incomplete, not a clean scored pass.

Add Sol-medium paid analysis through the same shared budget. It reads completed evidence on the evaluator side; outputs observation, grader verdict, hypothesis, alternatives and evidence IDs. It cannot overwrite grading or write into competitor context.

Run offline API-contract, isolation, manifest, node-dispatch, cancellation, concurrency, evidence-gap and budget checks first. Then one bounded synthetic end-to-end pilot per ready adapter, followed by a preregistered paired development panel. Total spend, including enrichment/analysis/retries, stays within the existing $300 weekly ledger; reserve worst case, respect currently held spend. No full 600-task replay based on historical budgets. Register deliberate replication and parent runs; keep old task versions separate from today's 800-task corpus.

Promotion requires actual traces and final states, verified run identities/billing, and clearly scoped paired findings. The historical report is a reproduction target, not an acceptance threshold for a different corpus or native harness.

## Delivery checkpoints for Sol medium

Finish one checkpoint at a time, with paths changed, exact tests run, trace/artifact examples and remaining blockers. Do not mark the entire feature complete at a configuration-only milestone.

1. Provenance/manifest inventory and capability matrix.
2. Offline isolated native boundary and adapter proofs.
3. Stock Enterprise synthetic one-off/create-run evidence (each track independently).
4. Recovered historical bundle and verified Enterprise port/context equivalence.
5. Executable editor versions and paired run launcher.
6. Budgeted pilot and evidence-linked outcome report.

No push, deployment to shared production, Slack publication, or Monarch upstream merge is authorized. Isolated local preparation is authorized. Missing historical artifacts or Bedrock access block only their dependent checkpoints; continue the rest without inventing a substitute.
