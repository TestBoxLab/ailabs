# WorkflowBench — Design v2.1

**Status:** post-adversarial-review revision, 31 Aug 2026 (supersedes v1, same day). Author: Waki. Reviewer: Deyton.
**Review inputs:** three-lens adversarial review (methods / platform engineering / vendor strategy) + two verification tracks (vendor-harness browser capabilities; SaaS & AI-vendor ToS). Findings and their absorption below.

## 0. What the review broke (and v2 fixes)

| Severity | Finding | v2 response |
|---|---|---|
| OVERTURNED | "Vendor-stock browser" is incoherent. Verified: only Claude Code has an official browser path (Claude in Chrome) — subscription-auth only, attended visible Chrome, disabled under API keys. Codex CLI: no browser (desktop app only). Gemini CLI: none (DevTools MCP is opt-in). | Bare arm splits: `bare/cua/*` (vendor computer-use APIs, reference loops — OSWorld/Online-Mind2Web precedent) primary; `bare/cli/*+fixture` (CLIs + one declared common browser MCP, documented invocation) secondary. API billing everywhere. |
| BLOCKER | Whole-state diff drowns on live SaaS and its noise is biased against browser arms (read-side-effects: Drive activity metadata, Slack read markers, SF modstamps/rollups). | REAL mode → scoped-resource diff: per-task watched collections, per-vendor field normalizers, read-side-effect neutralization, scoped guards. Whole-state dual invariant stays SYNTHETIC-only. No-op validation per tenant snapshot. Adversarial near-miss tests per checker. |
| BLOCKER | A Monarch-authored public leaderboard naming Claude Code/Codex is not credible and damages both partnership tracks. Sam's own instinct ("branded by us won't fly") confirmed. | Claims ladder: Rung 1 internal instrument (now) → Rung 2 public Monarch-vs-Monarch trajectory + open methodology → Rung 3 named-vendor comparisons ONLY behind neutral governance (open-governed repo / steering group / contribute corpus to third-party harness and appear as a submission). Rung 3 decided by Sam post-raise. |
| LEGAL | Salesforce MSA: services "may not be accessed… for any other benchmarking or competitive purposes"; Dev MSA = material breach. Slack AUP redirects to Salesforce's. Zendesk dev terms carry a similar clause. Google Workspace & Linear clean for own-tenant API automation. | T2 re-sequenced: Linear + Slack-pending-counsel; Salesforce/Zendesk behind written consent or anonymization, counsel engaged now. Design mitigations from day one: measure agents never the SaaS layer, official APIs, paid tenants, synthetic data, no load testing, vendor right-of-reply pre-publication. |
| REOPENED | No control arm ⇒ no delta attributable to anything (model, scaffold, prompt surface, interface all vary at once). | Minimal-scaffold control (bare API + generic tool loop) on ~100-task stratified subset. Reverses the Sunday product-vs-product-only call — with evidence; needs Waki confirm + Sam aware. |
| MAJOR | Nobody did the arithmetic. Verified: long-horizon computer-use $22–72/task (OSWorld 2.0); browser episodes 2–15 min. 576×2×k4 REAL ≈ six figures + tenant-capped weeks. | k=4 SYNTHETIC only; REAL k=2 on ~100-task stratified subset; REAL full-corpus sweep not in v1. Tenant-pool capacity model = named T0 deliverable with Deyton. Checkpoint/resume required before any multi-day run. |
| MAJOR | Lab arm = ATLAS with better tooling; gates guard the report builder, not the founder mid-raise. | Lab arm quarantined: no lab figure in any exportable artifact (report-builder enforced + watermarked internal rendering); promotion lab→stock needs named non-founder approver (proposed: Alex) + published config-hash diff in the PR. Deletion remains on the table (Sam+Alex call). |
| MAJOR | "Stock" is not definable for unattended runs (permission flags are non-default by definition). | "Stock" defined operationally: pinned version, all flags documented incl. permission modes named as non-default, published invocation, re-run policy on vendor releases. |

## 1. What it is now

**Rung 1 — the instrument (build now).** Full internal paired eval: all arms, both modes, honest cost accounting, feeding the release pipeline and failure taxonomy. The most valuable artifact in the project; needs no external governance.
**Rung 2 — public trajectory, own product only.** Monarch-vs-Monarch progress + open methodology (corpus contract, grading design, audit lineage). External voice with zero vendor-relations cost.
**Rung 3 — named-vendor comparisons.** Only behind neutral governance; the credible endgame is our corpus as a *submission* on someone else's board.
Pre-registration from Rung 1: tasks/graders/oracles hash-frozen before any arm runs; grader + corpus open-sourceable; authorship firewall (Monarch-arm configurators don't touch tasks/checkers).

## 2. Arms

| Arm | Definition | Publishable |
|---|---|---|
| `bare/cua/<vendor>` | Vendor computer-use API in vendor's reference loop over a common browser env. Primary REAL bare arm. API-billed, symmetric, precedented. | Per ladder |
| `bare/cli/<harness>+fixture` | Vendor CLI (Claude Code, Codex, Gemini) + one declared browser MCP fixture, identical for all; SYNTHETIC mode: CLIs with MCP tools directly (genuinely stock there). Invocation published. | Per ladder |
| `control/minimal@<model>` | Bare API + generic tool loop, same prompt, ~100-task subset. Attribution anchor. | Per ladder |
| `monarch/stock@<release>` | Product as shipped; agent authors workflow; engine executes; full phase telemetry. | Only Monarch arm ever publishable |
| `monarch/lab@<cfg-hash>` | Waki's experimental arm. Quarantined (above). | Never |

## 3. Modes & legal map

- **SYNTHETIC** — AutomationBench's 47 tools (MIT) exposed to every arm as plain MCP/OpenAPI (identical interface — no Monarch-graph-shaped advantage; Monarch ingests the same schemas). Deterministic world; whole-state dual invariant; no-op validation; oracle CI.
- **REAL** — benchmark tenants; template-import provisioning (MCPMark pattern); per-episode ephemeral users (WorkArena); vendor-API readback; scoped-resource grading (above). Bridge subset runs both modes; synthetic↔live gap published per-arm, never pooled.
- **LEGACY** — subprocess/container-isolated adapter re-runs 1.0.6/v9.12 (pinned env quarantined from ours); 5,427 rows imported with nulls+flags where fields can't populate.

Vendor legal (verified 31 Aug): Google Workspace ✅, Linear ✅, Slack ⚠ counsel traces AUP chain, Salesforce ⛔ consent-or-drop, Zendesk ⚠ counsel. Anthropic/OpenAI: no benchmark bans found; subscription-auth automation is gray → API billing only.

## 4. Statistics & budget

- Pairing enforced physically (interleaved arms, same tenant, tight window) or the paired claim is dropped for that slice; window recorded.
- Clustering: task-template × tenant (not scenario-only). SEM beside every mean; W/L counts under every pair (McNemar); infra taxonomy excluded from Pass^k, rate reported.
- k-policy: SYNTHETIC k=4 (cents/task); REAL k=2 on ~100-task stratified subset ($0.10–5/task short-horizon anchor); full-corpus REAL sweep deferred (would be six figures at OSWorld-2 rates).
- Tenant capacity model (pool size, provisioning latency, per-org API budgets shared across arms, reset-verification call cost) = T0 deliverable with Deyton; parallelism is tenant-capped, not compute-capped.

## 5. Build strategy (unchanged where it survived)

Vendor Harbor's agent-adapter layer (keep file layout for upstream syncs). Bespoke: orchestrator (authoring→execution state machine), tenant pool manager, out-of-sandbox grader (getter/metric split), results store, report builder with ladder-aware gates. Rejected: Harbor-as-framework, free-form Python graders, UI automation in setup, in-process legacy. **Descoped from v1:** CDP/proxy telemetry tap (vendor-billed tokens/cost/wall-clock only); external cost-per-workflow dollars (bands/ratios only); public "WorkflowBench" branding (deferred to Rung 3).
Named owner: normalizer layer + vendor-release regression job (golden oracles re-run on vendor ships) = Surface A / Owner A.

## 6. Decisions — status 31 Aug

1. Bare arm = vendor computer-use APIs primary — **ACCEPTED (Waki)**.
2. Salesforce/Zendesk clauses — **proceed per Waki** (his read: clauses cover benchmarking the SaaS, we measure agents). "We measure agents, never the SaaS layer" framing stays in methodology; flag remains visible for Sam/counsel. Tranches restored to original order.
3. Name: **WorkflowBench** (no collision found; nearest are FlowBench and WorFBench, different scope).
4. Cost constraints **lifted** — k=4 allowed in REAL mode. Time still binds: 2–15 min/browser task, tenant-capped parallelism; capacity model with Deyton stays.
5. Open — Sam: claims ladder, leave-period veto. Open — Sam+Alex: lab-arm gate. Open — Waki: minimal-scaffold control on ~100-task subset (the arm that says WHY Monarch wins, not just that it does).
