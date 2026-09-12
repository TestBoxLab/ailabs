# Product Graph Fast Path: architecture audit and candidate

Date: 11 September 2026. Status: research proposal; no new benchmark was run.
Owner: AI Labs. Requested outcome: higher strict completion and lower end-to-end
latency than matched models in their native harnesses.

## Decision

Build the next candidate around a compact, source-pinned product map and one
executor. Move retrieval, exact record binding and repeated-read reuse into the
runtime only where the available contracts justify them. Escalate ambiguous
bindings locally; do not require a model to certify a complete plan before it may
act. Keep Genesis's research helpers outside the scored attempt.

This is a new combination to test, not a claim of an unprecedented algorithm or
a measured win. Its parents are reviewed graph delivery, typed resolution and
runtime context reduction. The historical record argues against another planner,
reviewer and permission-ledger chain on every request.

## Audit scope and provenance

The audit covers the available recovered catalog's A1-A18, B1-B31, C1-C26,
D1-D19 and E30-E47 families, its E1-E29 cross-reference, the two recovered graph
provenance inventories, WorkflowBench's September rounds and current runtime
code. It is a complete family-level review of those records, not a reconstruction
of every original trajectory: several historical run manifests and graph bytes
are missing. No suspended dataset acquisition or replacement was resumed.

Lab checkout HEAD at inspection: `7640a0a676b7b127f8e06e93ba1aac5ed4888668`.
The workspace contains later uncommitted work; code citations describe the files
read on this date, not a deployed release. Sibling Monarch checkout HEAD:
`c6f42272ae3f7af6f0214a1075fdfc51b9bf2c56`; read-only inspection establishes
source identity, not the deployed build.

Primary local evidence:

- [Recovered AutomationBench attempts catalog](<C:/Users/Lucas Wakigawa/Monarch_Main/docs/bridge/AUTOMATIONBENCH_ATTEMPTS_CATALOG.md>), through 12 August. SHA256 `ed868a5978ce2e3094c60f8d5978b75f4baa91f65dc77f73a6ecf63ac68e5834`. Detailed outcomes below are transcriptions of its assessments, not newly recomputed scores.
- [PG-Waki reconstruction](pg-waki/v1/provenance.md) and [BRIDGE v2/v9.12 inventory](bridge-v2-v9.12/provenance-report.md): missing original graph/run manifests and differing historical model/effort settings prevent treating reconstructed artifacts as exact reproductions.
- [Program state, especially sections 12-14](../../monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md), [September 10 diagnostic](../../monarch-benchmark/docs/rounds/2026-09-10-post-deploy-diagnostic.md) and [unchanged upstream limitations](../../monarch-benchmark/docs/rounds/2026-09-10-upstream-limitations.md).
- [Existing experiment index](../experiments.jsonl): EXP-2026-001 and EXP-2026-002 propose reconstructed knowledge comparisons; neither records a run. The candidate below is a descendant with a different latency mechanism, not an accidental repeat.
- [Execution code](../../monarch-benchmark/workflowbench/wb_studio/execution.py), [product knowledge](../../monarch-benchmark/workflowbench/wb_studio/product_graphs.py), [native acceptance](../../monarch-benchmark/workflowbench/wb_studio/native.py), [blueprint contracts](../../monarch-benchmark/workflowbench/wb_studio/blueprints.py), and [benchmark/product boundary](../../monarch-benchmark/docs/BOUNDARY-BENCH-AND-MONARCH.md).

## What earlier architectures established

| Family and source rows | Recorded result | Consequence for this candidate |
|---|---|---|
| Reviewed graph and graph-inline v8; A2-A4, A16 | Historical paired comparisons favored the complete graph/Operator bundle; safety did not transfer uniformly across models. | Retain product knowledge. Do not attribute a bundle's lift to one sentence or claim superiority over today's native harnesses. |
| Source upgrades and reachability; A6-A10, A17-A18 | Benchmark upgrades changed worlds/assertions; interface mismatches and unpinned closures invalidated comparisons. | Freeze task, world, knowledge, harness and runtime identities. Separate unavailable actions from model errors. |
| Model-written authorization and overlays; B1-B9, B28, C18-C19 | Correctness fixes made the protocol runnable but did not rescue its completion; writes were repeatedly blocked. | No new model-written permission format on the ordinary write path. |
| Short doctrine and host knowledge; B10-B21, B26-B31 | Specific destination/ID guidance sometimes helped; extra procedure or textual skills often tied, regressed or failed to transfer. | Prefer compact action facts and actual response fields. Measure changed content separately from token volume. |
| Plan ensembles and self-review; B22-B25, C6-C8, D13-D15 | More plans, work orders, stop reminders or self-assessment did not reliably recover omitted actions. | No unconditional planner or reviewer agent. A summary saying complete is never an outcome signal. |
| Typed resolution and useful reads; C1-C5, C26 | Exact IDs/exclusions helped selected panels; replicated attribution sometimes favored the discovery reads alone. | Bind actual reads, and compare binding against the same reads without a fact block. Do not assume it fixes under-action. |
| Compact runtime records; C10, D16 | Recorded cost reduction on a small panel with unchanged outcomes. | A plausible latency/cost parent, not evidence that shorter prompts increase completion or wall-clock speed. |
| Exact scalar/math and provenance; C11-C15 | Optional tools often went unused; source provenance could not establish the correct formula. | Keep exact copying inside a host seam only after the source and operation are known. Do not equate grounded arithmetic with authorized business logic. |
| Completion/receipt controls; C16-C21 | Observed calls and settlements could not reveal an obligation never extracted. | Receipts prove observed effects, not overall completion. Report unavailable readback honestly. |
| Model and effort routing; D1-D12, D17-D19 | Results depended on domain, model, settings and activation; blanket effort increases were inconsistent. | Hold model and effort fixed for the first comparison. Any later router uses observable features, never task IDs or prior answers. |
| Compilers and formal planners; E30-E42, E45-E46 | Missing effects, bindings, exhaustion, retry and verifier contracts defeated broad proof claims; synthetic successes remained unscored. | No SAT planner or universal workflow compiler. Unknown contracts stay unknown. Local checks validate only what they can prove. |
| Shadow execution, reconciliation and negotiation; C25, E32, E43-E44 | Simulator privileges/private assertions were unfair; real idempotency/readbacks and interactive users were absent. | No private worlds, grader-fed rules, guessed safe retries or simulated human approval. |
| Orthogonal compiler paid launch; E47 | Outer retry behavior violated the experiment contract before a scored episode existed. | Count nested retries in liability and attempt limits; an invalid launch is not a zero-completion result. |

The recovered PG-Waki document transcribes a later 403/600 strict result, while
the BRIDGE inventory transcribes a different 361/600 comparison and warns of
mismatched effort. Those are different identities. Neither reconstructs a current
native-harness baseline, and the original consumed graph is absent. They motivate
replication, not a target score for the new UI to display as achieved.

September's evidence adds an independent warning. The September 5-6 WorkflowBench
rounds cannot establish an architecture ranking because derived approval rules
rejected valid work or accepted extra work. Later corrections moved task hashes;
old rows remain tied to their old versions. The September 10 diagnostic reached
Airtable but read an Active record through the ignored filter, skipped creation
and changed nothing. A product terminal success did not mean task completion, and
missing writer pricing caused a separate harness/billing failure. Preserve both
facts rather than choosing the more favorable label.

## Proposed mechanism

Call the lineage `product-graph-fast-path`, with distinct immutable versions for
each ablation. Product knowledge supplies capabilities and relationships, the
request supplies authorization, and live read results supply record values.
None of those channels may borrow the grader's private expectations.

```text
Frozen product knowledge -----> relevant capability packet
                                      |
Unchanged task request --------> one executor --------> ordinary app calls
                                      ^                       |
                                      |                       v
                              local uncertainty <----- exact read receipts
                                      |
                               bounded targeted read
                                      |
                            observed effect + final answer

Separate evaluator: before/after state + frozen checks + normal termination
```

1. **Choose relevant knowledge without a new model round.** Match the request's
   product/action terms against the frozen catalog, include a bounded relationship
   neighborhood, and retain a catalog-search escape hatch. Pin the selection
   algorithm and include the selected capability IDs in evidence. A miss must
   permit ordinary discovery, not silently remove an available action.
2. **Keep one executor on the critical path.** Deliver the original request,
   compact knowledge and ordinary tools to the selected runtime. There is no
   up-front no-tool planning turn or compulsory second-model review. Genesis can
   run independent research helpers while designing the candidate; those helpers
   are not extra hidden assistance during evaluation.
3. **Reuse only safe read facts.** A receipt identifies the call, source response,
   selected record and observed fields. Cache an identical deterministic read
   only within an attempt, with the same arguments and identity, and invalidate
   after a potentially relevant mutation. Unknown side effects or freshness mean
   no reuse. Never cache a write or carry a task's state into another attempt.
4. **Make uncertainty local and explicit.** If an ID is ambiguous, a response does
   not satisfy the requested predicate, or a field is absent, obtain the smallest
   available disambiguating read. Validate returned rows against task-derived
   predicates even when the server accepted a filter. Unsupported pagination or
   incomplete results remain unresolved; do not assert that every record was seen.
5. **Bind exact values without inventing semantics.** Reuse observed IDs and exact
   source values for writes once the executor has selected them. Arithmetic and
   joins remain semantically fallible; a host check cannot certify that the task
   meant that formula. Local binding is not a complete obligation model.
6. **Record effects without an extra success ritual.** Keep ordinary API receipts
   and exposed readback where available. A timeout with ambiguous write outcome
   is not permission to repeat the write. The independent checker decides strict
   completion from stored evidence after the attempt.

Expected completion mechanism: fewer wrong-record selections and fewer suppressed
writes. Expected speed mechanism: fewer catalog-discovery turns, fewer repeated
reads and no unconditional handoff. These are separate hypotheses. More precise
checks may improve completion while making requests slower; retrieval may omit
necessary context; caching may be unusable for many endpoints. Report those
outcomes instead of treating the design as a guaranteed win.

## What can run with the present editor

| Layer | Current code supports | Additional implementation required |
|---|---|---|
| Architecture draft | Task Input -> agent -> Result Output, with a prepared product-graph node feeding the agent; immutable publication and knowledge hashes. | None for the simple draft. It still needs an actually prepared graph and a runnable selected runtime. |
| Knowledge delivery | `execution.py:133` (`ArchitectureArm._system`) renders bound product-graph records into the agent prompt; `knowledge_delivered` is observable. | Deterministic request-specific selection and packet-size control are new behavior. Current rendering is not a retrieval index. |
| Multi-agent execution | `execution.py:173` (`ArchitectureArm.run`) iterates compiled steps serially; advise nodes have no tools. | Conditional escalation, parallel execution and shared receipt caching are not represented by drawing more nodes. |
| Native comparison | Native containers, credential broker, retained streams and source-bound acceptance gates exist in `native.py:439` (`require_acceptance`). | Verify acceptance on the actual host and integration for the exact candidate. A runner label or rendered graph does not establish it. |
| Stock Monarch | A separate Enterprise reference implementation with deployed runtime verification. | Applying this mechanism to Monarch requires a distinct experimental build/patch and measured integration. A Studio agent blueprint is not stock Monarch. |

The first honest deliverable is therefore the compact one-agent candidate using
existing graph delivery. Introduce selection and read binding as successive
runtime treatments, each with its own version. Do not claim that a prompt-only
version already implements cache invalidation, exact host bindings or conditional
execution. Product graphs for the 47 mocks must follow the bench-owned contracts;
real-vendor docs do not replace what the unchanged mocks accept and return.

## Comparable experiment, once exact X and Y are supplied

Resolve X to a count of unique tasks in the named frozen set Y, using a recorded
seed/subset manifest if selection is needed. Preserve the requested track. An
undersized exploratory run remains useful for activation and diagnostics but
cannot support a broad superiority claim. Prefer development tasks while changing
architecture; keep held-out prompts and evaluator material out of design work.
The existing `achievable-50` revision block remains in force.

Controls: the matched model in its verified native harness; stock Monarch as a
separately identified reference; and the simplest graph-delivery candidate.
Raw API loops can be diagnostic controls, never labeled bare Codex or Claude Code.
Match request, initial world, available app catalog, model/effort when isolating
architecture, caps, repetition count and concurrency. Disclose interface differences.

Test one addition at a time: compact knowledge delivery, then relevant selection,
then exact read binding/reuse. A targeted read-binding comparison must also include
the same discovery reads without binding so the old attribution error is not
repeated. Do not multiply every model by every variant before proving activation.

Predeclare strict completion as the primary quality outcome and end-to-end latency
as the speed outcome. Report paired completion wins/losses and uncertainty;
latency for all attempts with termination labels; latency on jointly successful
task pairs; timeouts; median and tail latency; phase times; cost; unrequested
changes; and coverage/activation of each mechanism. A fast failure is not a speed
win. Count graph preparation separately and show amortized reuse only alongside
its actual up-front cost. Keep create-and-run and one-off request results separate.

For initial development promotion, propose a minimum useful completion change of
five percentage points and a median successful-pair latency ratio at or below 0.85,
with no observed increase in unrequested changes. These are proposed criteria to
freeze in the concrete experiment record, not a fitted conclusion or power
calculation. A small X may be unable to resolve them; report inconclusive and do
not silently enlarge a paid run. Confirmatory comparisons need task-clustered
uncertainty and adequate independent tasks, not retries counted as new evidence.

Before launch disclose total attempts, all retry scopes, cost band and maximum
liability; verify the shared ledger, billing, runtime, catalogue and front door.
Use the existing approval flow for the actual proposal and requester. No paid
round, approval record, experiment verdict or source refresh is created by this
design document.

## Genesis presentation and evidence

Use `present` for coherent milestones, reusing a stable card ID while its snapshot
changes. A research card names the inspected records and caveats; a thinking card
summarizes a public hypothesis; an architecture card names the saved version;
a configuration card shows the actual task set, count, competitors and limits;
an execution card comes only after a run exists; a result card cites computed
outcomes; a warning card preserves a real refusal and the next action.

The brain, search, graph-building and lightning animations convey those moments.
They do not reveal private reasoning, create progress percentages, imply writes
or run ahead of tool receipts. All substantive facts remain readable with motion
disabled. `show` can reveal the real architecture or launch surface under the
person's Follow preference. `edit_architecture` streams provisional graph changes;
only `save_architecture` acknowledges a durable revision. No assistant-generated
HTML or arbitrary navigation is necessary.

The live window and rich cards are a delivery layer over the same evidence. They
must distinguish a proposal, a saved draft, an accepted runtime, a launched run and
a measured result throughout the journey.
