# The WorkflowBench Program

Waki · 31 Aug 2026 · The umbrella: what the whole program is, its workstreams, owners, cadence, and gates.
Children: DESIGN.md v2.1 (what/why) · BUILD-SPEC.md (how, M0–M6) · T0-INGESTION-SPEC.md (done) · workflowbench-t0.zip (running code)

## 1. Program goal

One evaluation system that serves four customers at once, from the same episode rows:

| Customer | What they get | Vehicle |
|---|---|---|
| Monarch engineering | Where Monarch loses, per failure class, per release | internal report + release artifact |
| Sam / GTM | Numbers that survive diligence, with source lines | rung-2 public trajectory + NDA'd customer reports |
| Waki's lab | A quarantined arm to test frontier configs, with a promotion path into the product | monarch/lab@cfg-hash |
| The outside world | A credible methods voice (audit lineage, honest cost, negative results at n that means something) | rung-2 posts, conference talk, eventual rung-3 |

Program bar (from the review mandate): by 28 Feb the system runs, reports, and improves **without Waki in the loop**, and two named people own surfaces of it.

## 2. Workstreams

**WS1 — Platform** (BUILD-SPEC M1–M4). Orchestrator, arms, results store, stats, report builder + gates. Owner: Waki → hands M3/M4 to Owner A.
**WS2 — Corpus.** 10 (done) → 60 bridge set (M5) → 576 legacy-parallel (M6) → **customer-shaped tasks**: every pilot conversation (FedEx-class) contributes de-identified workflow shapes to a private split. Contract hashes, no-op CI, oracle CI. Owner: Waki → Owner A.
**WS3 — Arms.** Scripted (done) → claude-code/codex CLIs (M1) → monarch stock+lab (M2) → CUA arms (M5) → roster decision for Gemini/others at M5. "Stock" disclosure policy per DESIGN §3. Owner: Waki.
**WS4 — REAL mode & tenants.** Google tranche (M5) → Linear (+Slack pending the vendor question) → CRM behind consent. Tenant pool, normalizers, capacity model. Owner: Owner B + Deyton.
**WS5 — Product integration.** Telemetry events land in Monarch itself (the RFC's trace-emission ask); bench report as release artifact (M6); the correlation study — does synthetic movement predict live movement — which decides whether anything ever gates a release. Owner: Deyton + Owner B.
**WS6 — External.** Weekly internal lab note → monthly rung-2 public post; the AutomationBench audit + 9 filed issues as the first public artifact; conference talk (submitted, decision pending); rung-3 governance parked with Sam. Owner: Waki with Mercedes routing.

## 3. Timeline (maps to the 26-week plan)

| Weeks | Milestone beats |
|---|---|
| W2–4 (Sep) | M1 first real bare arm · M2 first paired claude-code vs monarch/stock · owners named by 2 Oct |
| W4–6 (Oct) | M3 legacy continuity · M4 reports with gates · first weekly bench report in standup |
| W6–10 (Oct–Nov) | M5 Google REAL tranche + bridge gap number · CUA arms · pre-leave alignment: Sam reads the first full internal report |
| W11 | Leave-period operating doc: report cadence continues without Sam or Waki pushing it |
| W12–19 (Nov–Jan) | M6 release artifact · corpus to 576 · correlation study · absence-test week proves the program runs itself |
| W20–26 (Jan–Feb) | Rung-2 publication rhythm established · review dossier assembles itself from the results store |

## 4. Operating cadence

- **Weekly:** bench report auto-rendered from the store, posted internally (#benchmarks); one lab note.
- **Per release:** the M6 artifact, report-only.
- **Monthly:** one rung-2 external post; talent/ownership check on the two surfaces.
- **Per readout:** template from the RFC — what we now believe / what must happen next / confidence label / cost with source line.

## 5. Gates (all code, not policy)

1. `audiences.yaml` arm allowlists — lab and bare arms cannot render into public reports.
2. No figure without a source line (the store's query view is the only path to a rendered number).
3. Corpus CI — no task merges with a vacuous assertion or failing oracle.
4. `verify_clean` — no episode starts on a dirty tenant.
5. Lab→stock promotion — PR with config-hash diff + non-founder approver (proposed: Alex).

## 6. Open decisions (unchanged, tracked)

Sam: claims ladder ratification · leave-period external veto · rung-3 governance (post-raise). Sam+Alex: lab-arm approver. Waki: control arm on the 100-task subset · CUA roster at M5. Deyton: engine MCP-vs-HTTP (blocks M2 only).

## 7. Program risks

Single-person dependency until owners are named (mitigation: BUILD-SPEC hands M3/M4 and M6 to them as concrete first milestones) · harness version drift (`wb doctor` + pins) · tenant throughput capping REAL cadence (capacity model first) · the correlation study coming back negative (pre-committed response: stop reporting synthetic externally, say so plainly).

## 8. Next deep dive: UI/UX

The program grows five surfaces; today they are CLIs and JSON. The UX work should treat them as one product:

| Surface | User | Today | UX question |
|---|---|---|---|
| **Run console** | Waki, owners | `wb run/status/resume` | live matrix view, failures-first triage |
| **Results explorer** | eng + lab | SQLite + jsonl | paired-delta drilldown, trajectory viewer, failure taxonomy browsing |
| **Report viewer** | Sam, GTM, external | rendered md/html | the same page serving internal-full and public-gated variants credibly |
| **Corpus workbench** | Owner A | task json + CI | authoring with live no-op/oracle feedback |
| **Tenant ops** | Owner B | scripts | pool health, reset failures, capacity |

Proposed UX entry point: **the paired-run report page** — it is what every audience touches and what Sam reads first. When we start, first step is a survey of the best existing eval/benchmark UIs (Terminal-Bench's leaderboard, Braintrust/LangSmith run views, W&B) taken from their real products, then wireframes against Monarch's design language.
