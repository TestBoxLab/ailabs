Method: dual-agent (A: /root/design_review · B: /root/browser_review), followed by source review and controlled startup reproduction.

# AI Labs adversarial review — 9 September 2026

The visual cleanup has outpaced the product's reliability and decision support. Square geometry is now coherent; the next investment should make it hard to run the wrong experiment or draw an unsupported conclusion. This review did not change application code or launch paid runs.

Design specificity: task graphs, versioned architectures, knowledge plugins, and business-state evidence fit AI Labs. Repeated status prose and generic report composition still obscure the product's distinctive value: explaining why an architecture improves a business outcome.

## Design health

Expert heuristic assessment, not measured user-study performance. Assessment A scored 25/40 before seeing detector evidence. Synthesis lowers status and recovery by one point each after the independently reproduced startup failure: 23/40.

| Heuristic | Quality /4 | Main concern |
|---|---:|---|
| System status | 2 | Frontend initialization failure presented as connection failure |
| Real-world match | 2 | Architecture names and replacement model configurations differ |
| User control | 2 | Browser history does not preserve investigations |
| Consistency | 3 | Cohesive controls; uneven failure terminology |
| Error prevention | 3 | Validation exists; comparison baseline matching incomplete |
| Recognition | 2 | Effective experiment must be mentally reconstructed |
| Efficiency | 2 | Extra navigation to outcomes and evidence |
| Minimalism | 2 | Repeated failure and launch guidance |
| Error recovery | 2 | Retry recovers startup but diagnosis is misleading |
| Help | 3 | Useful contextual instructions and shortcuts |

## Five priority changes

### P1 — Make startup deterministic

Browser review observed fresh sessions fail with `readableRunConfig is not defined`. Independent reproduction delayed `/analytics.js` by 700 ms: the error persisted after the function became available. `workspace.js` consumes the helper defined in `analytics.js` during startup. This is a dependency race, not evidence that the backend disconnected.

Proposal: one application initialization boundary after dependencies load; explicit loading/error/ready states; distinct frontend versus API error reporting. Acceptance: fresh loads and delayed script/API responses reach the same usable state without Retry. Evidence: `artifacts/adversarial-review-B/startup-repro.cjs`, `browser-evidence.json`. Suggested workflow: impeccable harden.

### P1 — Make leaderboard improvement mean a matched comparison

`static/analytics.js` uses one selected native Bare baseline to color and compute deltas for every entry. It does not enforce entry-by-entry model/thinking matching. Cohorting in `leaderboard.py` protects tasks and evaluation contract but is not model matching. A stronger model could therefore appear to demonstrate architecture improvement. This is a code-confirmed latent risk; the live leaderboard contains no full qualifying runs, so populated interactions were not tested.

Proposal: calculate pairings server-side using task identity, evaluation/world contract, model, thinking and applicable harness pins; identify intended experimental differences explicitly. Show unmatched rows as unpaired, not improved. Keep green/red for observed paired deltas, with a separate uncertainty label. Show wins, losses, ties and unique tasks. Use task-aware uncertainty for repeated trials. Retain full-run eligibility and expose excluded/interrupted runs alongside it. Qualification suites need immutable identities plus separate development suites; the current catalog-50 sample is deterministically rebuilt from the current catalog.

Native Claude Code and Codex controls currently report unavailable in `/api/state`; verifying their readiness is a prerequisite to native-Bare claims. Suggested workflow: impeccable shape plus backend comparison validation.

### P1 — Show exactly what the run will execute

Selecting an architecture currently leads to a model sweep that replaces every agent node's model and thinking setting. It is disclosed, but a Gemini-named or mixed-model architecture no longer means what its saved configuration suggests. See `app.js:501`, `index.html:72`, `execution.bind_comparison_model`, and `artifacts/adversarial-review-A/launch-selected.png`.

Proposal: offer two modes: Run saved configuration; Compare replacement models. In the latter, show a compact effective-node configuration before launch. An experiment matrix should explicitly list setup, model/role assignments, thinking, task suite, repetitions, matched Bare and estimated/reserved spend. Preserve setup-first then models, as requested. Use an advanced per-role sweep only when needed. Acceptance: a user can state the actual node configurations without opening Studio. Suggested workflow: impeccable clarify/distill.

### P1 — Replace repeated failure summaries with an investigation workspace

The observed failed run repeats a failed count, a 100% failure bar, another count, and a Needs investigation label. The first view does not identify the actual forbidden change. `analysis.py` sends a whole-run payload and rejects content over 500,000 characters, asking for a smaller task batch; this creates a dead end for large existing runs.

Proposal: run title opens outcomes directly, with a separate configuration disclosure. Lead with the affected record and field, expected versus observed value, and the supporting event. A task matrix filters wins, regressions, and shared failures; task selection opens aligned traces, world-state differences, and the earliest supported divergence. Clearly separate observed error, grader verdict, causal hypothesis, and tested explanation. Analyze/cache tasks independently, then aggregate findings across the full run. Failure buckets show counts and their denominator; primary categories partition failures, secondary tags may overlap. Permit Unknown rather than forced causal prose. Acceptance: an operator reaches the first relevant event within two actions, and full-run analysis does not require rerunning a smaller benchmark. Suggested workflow: impeccable distill/shape.

### P2 — Repair navigation and mobile editing

`workspace.js:17` replaces browser history during navigation. Run identity is not represented as a durable investigation route. Mobile Studio places the canvas about 950 px below initial page top; desktop-to-mobile resizing can leave nodes outside the current camera until Fit is pressed. Controls measured 30–42 px high are below a 44 px touch comfort target; this alone does not establish a WCAG failure.

Proposal: durable run/task/event routes and Back/Forward behavior; run titles open outcomes while a chevron opens configuration. On mobile use a node outline and full-width selected-node settings, with compact architecture metadata. Refit safely after viewport changes or provide an obvious reset without destroying intentional pan/zoom. Acceptance: a copied task URL restores the same evidence; Back returns to prior context. Suggested workflow: impeccable harden/adapt.

## Enhancements after the five fixes

- Request-level cost explorer: model → node → request; separate uncached input, cache writes, cache reads and output. Keep current per-model vertical bars and add a time view. Reconcile run costs with preparation and analysis in the shared ledger. `usage.py` currently groups mixed-model architectures as Mixed / unattributed models and omits preparation/analysis from charts, with an honest note. Backfill only when retained receipts support attribution.
- Experiment notebook: optional hypothesis, parent experiment, one changed factor, acceptance criterion, and decision attached to a run family. One action creates a replication or ablation without editing frozen results.
- Research-to-experiment pipeline: weekly inbox → relevance decision → synthesis matrix → testable hypothesis → experiment → adopted/rejected/inconclusive. Separate competitive/interaction research from orchestration research. Avoid adding another feed that generates reading without decisions.
- Architecture dry-run: inspect each node's effective inputs, knowledge attachments and expected output contract before spending. A disconnected plugin should visibly show zero recipients. Static validation must not claim that a prompt will achieve the business task.

## Strengths and persona risks

Keep the light square style, setup-first journey, source-only knowledge plugins, explicit evidence/interpretation distinction, conservative unknown billing, and full-run leaderboard eligibility. Do not reopen the cosmetic redesign.

First-time operator: saved architecture versus effective run needs decoding. Investigator: duplicated failure summaries and browser history interrupt evidence tracing. Mobile operator: long metadata and separated inspector make graph editing cumbersome. Power user: outcome inspection has an unnecessary intermediary.

## References worth adapting

- LangSmith experiment comparisons: side-by-side per-task results and regression filtering, https://docs.langchain.com/langsmith/compare-experiment-results
- Inspect evaluation logs and errored-sample handling: retained per-sample evidence, recovery and explicit completion status, https://inspect.aisi.org.uk/eval-logs.html and https://inspect.aisi.org.uk/errors-and-limits.html
- Langfuse observability model: trace/span/generation hierarchy for request-level usage, https://langfuse.com/docs/observability/data-model

Adapt these interactions; do not port an entire product shell.

## Detector and review limitations

Detector attempted: three matches using degraded regex fallback, exit 1. Grid-background finding is exempt for the actual graph canvas; layout-transition matches SVG stroke-width, not demonstrated layout thrash. A critical-analysis border rule was found in CSS but not observed in the reviewed views. Missing parser modules prevented full selector/custom-property analysis. CSP blocked four overlay injections; no user-visible overlay exists. No accessibility clearance is claimed.

Independent assessments used fresh Chrome contexts. Four routes were reviewed on desktop/mobile by B; A reviewed startup, setup and outcomes, but did not finish Tasks/Review. Parent inspected fresh launch/outcome screenshots and reproduced startup. No paid execution, multi-user load test, screen-reader audit or populated-leaderboard visual test was performed. Browser helper stopped. No app code changed.

Recommended sequence: startup → valid comparisons and explicit launch matrix → task investigation → navigation/mobile → cost and research workflows.
