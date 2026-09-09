# AI Labs interface and evaluation research

## Recommended direction

AI Labs should become a light, precise experiment workbench: a place to design an experimental architecture, compare it with a frozen native-harness control, and inspect the exact business actions behind the result. The closest single interaction reference is Braintrust's experiment comparison. Its persistent baseline, regression filters, expandable trials, and per-example diffs closely fit this product. It is a reference for behavior; no reusable license for its application frontend was established. [1]

The strongest practical foundation is a composition: the existing AI Labs light shell, React Flow core for an experimental graph editor, and an Inspect-inspired evidence viewer. React Flow's core and Inspect carry MIT licenses. A wholesale observability-platform fork would bring a second data model and product hierarchy without solving AI Labs' central requirement: fair, versioned comparisons between native harnesses and experimental architectures. [2][3][4]

The terminal character should come from exact numbers, compact tables, restrained rules, command shortcuts, and crisp analytical graphics. Preserve light backgrounds and ordinary readable prose. The supplied cost-chart reference contributes its stacked series, aligned totals, legible labels, and strong numeric hierarchy; its black canvas does not override the explicit decision to keep the light style.

These recommendations supersede the incumbent product document's treatment of Monarch as a node and its outcome-derived definition of task difficulty. Monarch stock is an independently configured system. Difficulty must follow the current scientific direction, with empirical results retained as a separate observation.

## Reference matrix

These are qualitative fit judgments, not a measured product ranking. Documentation establishes available patterns; no claim of completed hands-on interaction testing is made here.

| Reference | Verified pattern | Best application in AI Labs | Limit or rejection |
|---|---|---|---|
| Braintrust | Baseline selection, comparison keys, regression filtering, expandable trials and inline/side-by-side diffs | Runs, task matrix, paired comparisons | Do not inherit automatic “latest branch” baselines; AI Labs needs an explicit frozen Bare identity. [1] |
| Inspect View | Evaluation history, live sample progress, message/scoring/metadata drilldown, filtering | Task attempt inspector and evidence links | Preserve native harness evaluation; adopting its viewer concepts does not require replacing Codex or Claude Code with Inspect agents. [2] |
| React Flow | Custom graph primitives, keyboard navigation and screen-reader support | Experimental architectures and graph enrichment views | A diagram library is neither an execution engine nor automatic collaboration. [3] |
| React Flow Workflow Editor | Node palette, ELK layout, customizable nodes, sequential example runner | Editor composition reference | Official template is Pro; the example runner is not a durable multi-user runtime. [5] |
| Langfuse | Dataset experiments, configurable evaluators, comparisons; SDK/webhook route for full agent logic | Trace integration, analysis links, versioned evaluator selection | Its prompt-only UI path cannot stand in for native-harness architecture evaluation. [6] |
| Phoenix | Experiments, repetitions, traces and programmable logging | Evidence schema reference; alternative trace backend | Current main license is ELv2, including a restriction on substantial hosted-service functionality. Do not assume a permissive application fork. [7] |
| Vercel Geist | Developer-oriented typography, explicit color scales, command and table components | Light terminal character, tables, empty states | Borrow hierarchy; do not imply all documented components are an openly licensed UI kit. Fonts have a separately verified OFL license. [8] |
| Grafana | Time-series bars, shared tooltip, table legend, series selection and time zoom | Cost and latency breakdowns | Use chart interaction ideas. Grafana main is AGPLv3, not an MIT component collection. [9] |
| AppWorld | Programmatic state checks and checks for unintended changes across app tasks | Before/after business state, correct entity selection, collateral effects | Original paper is 2024; its model scores are historical and should not appear as current SOTA. [10] |
| τ-bench | Final database-state evaluation and repeated-trial reliability | Reliability alongside first-attempt task success | Simulated user assistance is a separate evaluation condition. Do not mix it into unattended scores. [11] |
| Anthropic agent-evaluation guidance | Task/trial/grader/trace/outcome distinction; model and harness evaluated together | Evidence contract and honest task summaries | Practitioner guidance supports methodology; it does not establish the cause of a particular Monarch failure. [12] |
| Temporal | Persistent workflow/activity queues, worker capacity routing and activity throttling | Runtime state model and future durable execution adapter | Provider requests/tokens, budget reservations, application idempotency and tenancy still need explicit enforcement. [13] |

## Product structure and journeys

### Global structure

Use a persistent top navigation: **Architecture Studio · Runs · Leaderboard · Product graph · Research**. Put **New run** at the right as the primary action. Runtime capacity is visible in the run launcher and available under a dedicated runtime/settings view; it should not compete with experiment history for the first navigation position.

Architecture Studio starts with two explicit tracks: **Agentic requests** and **Workflow creation + execution**. Within a track, provide three distinct runner families: **Bare native harness**, **Monarch Enterprise stock**, and **Experimental architecture**. This separates what is being evaluated from the architecture's components. In the workflow track, Bare receives the authorized task and equivalent application access, without Monarch methodology; its task must still define the required saved-workflow artifact and execution outcome.

Monarch stock shows its source repository, tracked main branch, imported commit, import time and compatibility status. **Check for updates** compares the remote head without changing history. **Sync latest** imports a new immutable snapshot and validates it. If already current, show “Already up to date” with the checked commit and timestamp; repeated clicks must not create duplicate versions. Existing experiments retain their original commit. A failed check says whether GitHub access, compatibility or validation failed and gives the next action.

### Journey 1: Benchmark 50 tasks

1. Select the track and frozen task set; show “50 tasks × 3 setups × 2 trials = 300 attempts.”
2. Choose stock Monarch, one experimental version and Bare. Display the exact baseline's model, native harness, tool access and frozen task/world identity.
3. Select repetitions, concurrency and provider-specific limits. Display requested concurrency and the effective limit with its reason.
4. Review estimated/reserved maximum spend, weekly funds available, version pins and any execution blockers.
5. Launch once using an idempotency key. Navigate directly to the durable run record.
6. Watch phase counts and individual attempts. Refreshing or leaving the page must not own the run's lifetime.
7. On completion, open paired wins/losses, regressions and failure categories before creating the next hypothesis.

The API and UI must create the same run specification. Model, brain, action builder, tool adapter, judge and analysis configuration are versioned references, not hidden mutable defaults. The launch response includes the resolved immutable configuration, run ID, reservation ID and effective dispatch constraints. A judge belongs to the evaluator plane and must never become a competitor-visible graph node or prompt.

### Journey 2: Understand a failure

Selecting a run opens a table of tasks. Selecting a task opens its attempts; selecting an attempt opens a three-part view: the requirement and verdict, the ordered observed events, and the exact evidence/state comparison. The selected row, filters and baseline survive browser back navigation.

The event display can look like a workflow: phase lanes, nodes for consequential actions, and visible retry branches. A native trace is an **observed sequence**, not an authored DAG. Edges show recorded ordering or dependency, with the distinction labeled. A failure marker identifies the earliest supported divergence; it must not jump to the final error merely because that is easiest to detect.

The right panel answers five questions in order: What was required? What happened? Which check failed? Where does the evidence first diverge? What remains uncertain? Raw JSON and complete transcripts are one step deeper.

### Journey 3: Improve the product graph

Start with a stable overview and a compact list of entities. Select one entity to see its fields, connections and provenance. **Preview enrichment** produces a reviewable patch: additions, removals, field changes, newly inferred connections and validation issues. The graph highlights only the changed neighborhood.

Use **Before / After / Changes** views with synchronized selection and a shared camera where possible. A field table shows old value, proposed value, source event, confidence where meaningful, and applied/draft state. “No value” differs from “not collected.” A change log records who or what produced each patch, the enrichment model/version, source material and timestamp. Applying a patch creates a graph version; undo restores the prior editable draft without rewriting already used experiment versions.

A side-by-side graph alone is insufficient: node movement can look like semantic change. Preserve layout across versions, separate position changes from data changes, and offer a text diff that does not require spatial interpretation.

## Runs and comparison design

The Runs page should be a real history table with a sticky header, keyboard-operable expansion and a restrained toolbar. Default columns: run name, track, task set, setups, status/progress, completion, delta versus Bare, recorded cost, started and owner. Show the version in an expanded panel unless essential to disambiguate adjacent entries.

Search and filters cover status, track, architecture, model/harness, task set, date and failure class. Sorting should be stable; selected rows can be compared or exported. Pagination or virtualization must not silently change aggregate denominators. Make filters part of the URL and give **Clear filters** a visible place. A result count should say “12 of 84 runs” rather than leaving the table's scope implicit.

The expanded row contains phase progress, frozen configuration, failure/infra counts and a compact task table. Nested unlimited expansions become hard to navigate; the full attempt inspector deserves its own addressable view. Empty states distinguish no runs, no matching runs, and unavailable history.

### Green and red have a precise meaning

For a selected, comparable Bare baseline:

- Green: a beneficial measured delta, labeled “+6 pp completion vs Bare” or “12% lower cost.”
- Red: an adverse measured delta, labeled “−4 pp completion vs Bare” or “18% higher cost.”
- Neutral: tie, missing baseline, incomparable cohorts, or insufficient evidence.
- Amber: tradeoff or an unresolved interpretation, rather than a hidden winner.

Color the delta and associated comparison marks, not entire tables. A cost reduction is beneficial only within its declared dimension; it does not turn an architecture with lower completion into a global winner. Reserve blue for selection/activity and violet/orange/teal for categorical series. Sign, direction, label and icon must make the result understandable without red–green perception, consistent with WCAG's use-of-color requirement. [14]

A positive observed delta can be green while still labeled “uncertain”; the interface must not call it a proven improvement. Show task counts and interval estimates. Never combine a provisional leaderboard entry with a “best architecture” claim.

### Bare reuse and the leaderboard

Reusing frozen Bare results is valuable, but task identity alone is insufficient. Reuse requires compatible task/world hashes, track, tool and application access, native harness and model version, non-default settings, trial policy, limits, assistance policy and grading version. Freeze those fields in a baseline manifest. A newly imported Monarch version does not invalidate an unchanged compatible Bare manifest.

If a provider changes a model alias or the harness version changes, retain the historical result and identify it as historical. Do not silently reuse it for a claim about today's native harness. If only the grader changes and preserved evidence supports regrading, create a linked regrade record; keep the original verdict.

The top-three area is a compact highlight of the currently selected comparable cohort, followed by the complete table. Rank by a declared primary metric, show paired deltas and sample size, and expose the tie-breaker. Provide “Highest completion,” “Lowest cost at target completion,” and “Most reliable” as explicit views rather than blending all metrics into an unexplained score. Separate tracks, assisted/unattended settings and incompatible task sets.

## Task analysis and failure graphs

The analysis store needs structured findings before polished paragraphs: task and attempt IDs, classification version, observed event references, grader-check IDs, expected/observed state, earliest divergence, contributing factors, explanation confidence, alternatives, reviewer and supporting experiment IDs.

Use this provisional failure taxonomy, with one primary observable failure per failed attempt and optional contributing labels:

| Primary bucket | Observable evidence required | Distinguish from |
|---|---|---|
| Wrong entity or context | Selected entity contradicts task constraints or authorized context | Ambiguous task with no sufficient information |
| Missing required work | Required final change absent | Tool failure or intentional policy refusal |
| Incorrect transformation | Wrong computation, value, ordering or mapped field | Grader defect |
| Forbidden side effect | Unexpected mutation violates an explicit constraint | Harmless alternate valid solution |
| Tool/application failure | Recorded API or tool error, timeout or unavailable capability | Agent misuse of a working tool |
| Failed recovery or premature stop | Prior issue and available recovery evidence; stopping before required work | Budget/time termination |
| Workflow construction failure | Invalid or missing saved workflow artifact or invalid binding | Execution failure in an otherwise valid artifact |
| Unclassified / insufficient evidence | Failure is real but evidence cannot locate its source | An invented confident explanation |

Keep infrastructure incidents, invalid tasks and grader defects visible beside this taxonomy, not buried in model failure percentages. An API 429 is observed infrastructure behavior; whether bad agent retry behavior worsened it is a separate, evidenced contributing factor.

For “X% failed because of this,” default to **“Share of classified failures”** and show counts. Example display copy, explicitly illustrative rather than a result: “Wrong entity: 8 of 20 failed attempts (40%); 3 failures unclassified.” If categories overlap, label them “Contributing factors; totals can exceed 100%.” Show all attempts, valid attempts and classified failures as distinct denominators.

Use sorted horizontal bars for failure categories. Clicking a bar filters the task matrix and lists exact attempts. Use a phase-flow diagram only when phase transitions and counts exist; an attractive Sankey assembled from guesses would imply causal evidence that is absent.

An acceptable analytical statement is: “The agent updated account B at event 18, while the request named account A. Check 4 failed because A remained unchanged. The trace shows two returned matches but does not establish why B was chosen. A disambiguation step is a testable hypothesis.” Unacceptable: “The model lacks reasoning and needs a smarter brain.”

Generate summaries from the structured evidence, retain the evidence links and show analysis status: unreviewed, reviewed, disputed or experimentally supported. Analyze matched successes as well as failures. A controlled ablation or replication can support a mechanism; an LLM narrative cannot establish it.

## Chart and editor craft

The supplied chart's legend behaves like a small table: a color key, meaningful label and right-aligned total. Keep that pattern for prompt, cached read, cache write and completion costs when those billing categories are actually recorded. Unknown cost is a separate missing-coverage indication, never a zero-height bar. Include retries and unsuccessful attempts in totals.

A dense cost chart should support keyboard-selectable periods, inspectable totals, a table alternative, the same series order across views and an explicit timezone. Avoid dual axes for unlike quantities and tiny stacked segments that can be understood only by hover. Grafana's documented table legends and shared tooltip are useful precedents. [9]

The graph editor should have a narrow component palette, a dominant canvas, and a selection inspector. Nodes show a readable role, implementation/version and validation state. Typed ports reject incompatible connections with an explanation. Include fit view, zoom percentage, auto-layout, undo/redo, selection search and an accessible ordered-list mode. React Flow provides keyboard and screen-reader primitives; application-specific labels and validation remain AI Labs' responsibility. [3]

Do not use permanently animated connections as decoration. Motion indicates current execution or a selected path, respects reduced motion, and stops when activity stops. Do not animate every trace event or recenter the canvas while the user reads.

## Runtime and versioning requirements surfaced through UX

Concurrency is a request, not a guarantee. The launch form should disclose global concurrency, per-provider allowance, currently occupied slots, queued attempts and the limiting rule. A provider limit needs separate request-rate and token-rate enforcement where relevant; “five agents” is not a complete rate-limit policy.

Expose durable states: queued, waiting for provider capacity, starting, running, retry scheduled, cancellation requested, completed and failed. Include last activity, last checkpoint, retry count and next scheduled attempt. Lease expiry and worker recovery must not produce duplicate externally visible effects. Temporal is a useful reference for persistent workflow/activity queues and server-side activity throttling, but it does not by itself implement the entire policy. [13]

A minimum versioned contract should resolve architecture, component implementations, prompts, graph/schema, model, harness, tool interface, environment, evaluator, analysis rubric and price table. Read APIs return manifests, run status, attempts, events, outcomes and comparison eligibility. Write APIs create drafts, validate versions, reserve/launch, cancel and import upstream snapshots. Server authorization and scoped credentials apply equally to UI and harness callers.

The status page must distinguish a saved setting, a validated adapter and verified production capacity. A design, a local test or a configured concurrency number is not proof that multiple users can safely execute in parallel.

## Weekly research and R&D

The repository already records a weekly research automation named `ai-labs-weekly-research`. Maintain and verify that schedule rather than creating a duplicate. A configured or updated schedule is not evidence of a completed weekly delivery; actual executions need their own source and output records.

The Research page should separate **Agent engineering**, **Interaction and form factors**, and **Competitive landscape**. Each weekly digest starts with what changed, why it matters to Monarch, evidence strength and at most three proposed investigations. Primary engineering sources should precede trend aggregation.

Use Keshav's staged reading to avoid labeling a title scan as a deep review. The method distinguishes relevance, substantive comprehension and reconstruction; its literature-survey guidance follows repeated references and researcher communities. Citation popularity is discovery evidence, not proof of correctness. [15]

A synthesis table should contain citation, publication/version date, accessed date, reading pass, hypothesis, method/data, findings, declared limitations, independent concerns, contradictions, transfer conditions, unanswered questions and linked experiment IDs. Filterable rows are more useful than disconnected summaries. A source graph should distinguish citation, agreement, contradiction and hypothesized mechanism; never label every proximity edge a citation.

The R&D journey is **failure cluster → source comparison → falsifiable hypothesis → preregistration → implementation → controlled experiment → replication → decision**. Require parent links for replications/combinations and preserve rejected ideas. Each proposal states expected effect, primary metric, minimum useful gain, control, task split, stopping rule, maximum spend and evidence needed. Paid research and judging consume the same weekly reservation budget as experiments.

## Verification and priorities

Implement the identity and comparison contract first; otherwise polished green/red deltas can communicate invalid comparisons. Next deliver first-class navigation, run history and a truthful launch form. Then make the task inspector and product-graph change review usable. Add richer aggregate graphics only after their source fields and denominators are reliable.

Visual acceptance should cover desktop and a narrow viewport in one review pass: navigation, keyboard focus, table expansion/filter reset, baseline mismatch, long labels, zero runs, partial telemetry, failed upstream sync, provider waiting and graph change review. Use real rendered states. Fix the defects as one batch and confirm once. No screenshot-independent “SOTA” label should be used as a completion criterion.

Task acceptance is concrete: a researcher can configure a comparable 50-task experiment, understand why it is waiting, recover its history after a reload, identify the first supported divergence in a failed task, inspect before/after enrichment, and trace a leaderboard number to its attempts. The same actions should remain possible without a conversational assistant.

## Source register

Primary sources were checked on 8 September 2026. Product documentation is live and can change; imported code must pin its exact revision and preserve applicable notices. Paper access depth below is explicit. These sources support reference patterns and methodology, not measured improvements in AI Labs.

1. Braintrust, [Compare experiments](https://www.braintrust.dev/docs/evaluate/compare-experiments). Documentation sections read: baseline, matching, regressions, diffs, trials and summaries. Application frontend reuse permission not established.
2. UK AI Security Institute, [Inspect Log Viewer](https://inspect.aisi.org.uk/log-viewer.html) and [Inspect MIT license](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/LICENSE). Viewer history/live samples/details and license read.
3. xyflow, [React Flow accessibility](https://reactflow.dev/learn/advanced-use/accessibility) and [core MIT license](https://github.com/xyflow/xyflow/blob/main/LICENSE). Accessibility guidance and license read.
4. The MIT reuse recommendation is a scoped engineering assessment of sources 2–3, not permission to omit copyright notices or use every third-party asset.
5. xyflow, [Workflow Editor](https://reactflow.dev/ui/templates/workflow-editor) and [Undo and Redo](https://reactflow.dev/examples/interaction/undo-redo). Both pages identify Pro access; undo example explicitly identifies the xyflow Pro License. Template and example features read. No Pro code was imported.
6. Langfuse, [Experiments via UI](https://langfuse.com/docs/evaluation/experiments/experiments-via-ui) and [license](https://raw.githubusercontent.com/langfuse/langfuse/main/LICENSE). Prompt versus SDK/webhook distinction read. MIT Expat applies outside the specified enterprise directories and third-party restrictions.
7. Arize, [Phoenix repository](https://github.com/arize-ai/phoenix), [experiment API](https://arize-phoenix.readthedocs.io/projects/client/api/experiments.html) and [main license](https://raw.githubusercontent.com/Arize-ai/phoenix/main/LICENSE). Overview/API sections and ELv2 terms read.
8. Vercel, [Geist design system](https://vercel.com/geist/introduction), [colors](https://vercel.com/geist/colors) and [font license](https://raw.githubusercontent.com/vercel/geist-font/main/LICENSE.txt). Documentation and OFL 1.1 font terms read. Font permission does not establish component-source permission.
9. Grafana Labs, [Time series](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/time-series/) and [main license](https://github.com/grafana/grafana/blob/main/LICENSE). Chart interaction/legend sections and AGPLv3 identification read.
10. Harsh Trivedi et al., [AppWorld](https://arxiv.org/abs/2407.18901), 26 July 2024. Abstract read; no full methodology review claimed.
11. Shunyu Yao et al., [τ-bench](https://arxiv.org/abs/2406.12045), 17 June 2024. Abstract read; no estimator implementation derived from this reading.
12. Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 9 January 2026. Evaluation structure and methodology sections read; extends the repository's existing source record.
13. Temporal, [Workflow Execution](https://docs.temporal.io/workflow-execution) and [Task Queues](https://docs.temporal.io/task-queue). Durability, capacity and throttling sections read.
14. W3C WAI, [Understanding use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html). Guidance read.
15. S. Keshav, [How to Read a Paper](https://cs.uwaterloo.ca/~brecht/courses/854-http-video-2012/readings/keshav-paper-reading.pdf), July 2007. Full two-page text read; extends the repository's existing source record.

Internal lineage: [current direction](AI-LABS-DIRECTION.md), [prior HTML report design](superpowers/specs/2026-09-04-html-report-design.md), [research ledger guide](../research/README.md), [source history](../research/search-log.jsonl), [product context](../PRODUCT.md), and [incumbent visual system](../DESIGN.md). The supplied image is a private visual reference; no author, product identity or reuse license is inferred.


Supporting artifacts: [source synthesis matrix](../research/synthesis-matrix.csv) and [working glossary](../research/glossary.md). The matrix contains qualitative hypotheses for UI and methodology transfer, not experimentally measured UI gains.

