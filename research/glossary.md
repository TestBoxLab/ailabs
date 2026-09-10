# AI Labs research glossary

These terms define the experiment record and interface. They are working definitions for AI Labs, informed by the [research report](../docs/AI-LABS-UI-RESEARCH-2026-09-08.md) and [current direction](../docs/AI-LABS-DIRECTION.md). They do not establish observed product capabilities.

| Term | Meaning in AI Labs | Do not confuse with |
|---|---|---|
| Agentic request | A one-off business task completed without human answers during the attempt. | A workflow-authoring evaluation. |
| Workflow creation + execution | Creating a saved workflow artifact and executing it to reach the required outcome. | Executing only an existing workflow. |
| Native harness | The model family's appropriate agent application, such as Codex or Claude Code, with its version and settings preserved. | A hand-written loop around a raw model API. |
| Evaluation harness | The infrastructure that assigns tasks, isolates environments, collects evidence, grades and aggregates. | The competitor's own agent harness. |
| Bare | A frozen model/native-harness control with the task and authorized application access, without added workflow methodology. | A universal control reusable after harness, model or environment changes. |
| Monarch stock | A versioned import of Monarch Enterprise's own upstream configuration and behavior. | A single component inside an experimental graph. |
| Experimental architecture | A separately identified, versioned composition being evaluated. | An automatically updated stock import. |
| Component | A versioned implementation of a role, such as brain, action builder, tool adapter or enrichment stage. | A model name alone. |
| Evaluator plane | The isolated grader and analysis services outside competitor access. | Agent-visible judge prompts or expected answers. |
| Manifest | The immutable resolved versions and policies attached to a run. | Mutable defaults shown in settings today. |
| Task | One specified request with authorized information, starting state and success criteria. | Each repeated attempt. |
| Trial / attempt | One execution of a task by a competitor under a frozen configuration. | An independent task when computing uncertainty. |
| Run | A recorded batch of attempts with shared configuration and lineage. | One model response. |
| Track | The evaluation mode: agentic request or workflow creation + execution. | A model or task domain. |
| Cohort | A declared comparable set of tasks, attempts and evaluation conditions. | Any collection of historical scores. |
| Paired comparison | A comparison matched on the same task and compatible conditions. | Uncontrolled comparison between different task sets. |
| Percentage point (pp) | Absolute difference between rates. From 60% to 66% is +6 pp. | A relative increase of 10%. |
| First-attempt success | Completion on the first attempt under the declared policy. | Success after any number of retries. |
| Success within retry budget | Whether a task is solved within a fixed allowed number/cost of attempts. | First-attempt success or repeated reliability. |
| Repeated-trial reliability | Consistency across repeated executions. | Chance of succeeding at least once. |
| Trace / trajectory | Observable messages, actions, results and state transitions of an attempt. | Hidden model reasoning or proof that the final state is correct. |
| Outcome | The final business/application state. | A model's written claim of completion. |
| Grader / checker | Versioned logic applying a declared criterion to evidence or final state. | An unquestionable oracle. |
| Earliest supported divergence | The first recorded event where observed behavior can be shown to depart from task requirements. | A guessed root cause. |
| Primary failure class | A single selected observable failure category under a versioned taxonomy. | Every contributing factor. |
| Contributing factor | An additional evidenced circumstance associated with a failure. Multiple factors can overlap. | Mutually exclusive categories that must sum to 100%. |
| Causal hypothesis | A proposed mechanism for a result, with alternatives and uncertainty. | A causal finding established by a trace alone. |
| Ablation | A comparison removing or changing a component to test its contribution. | A broadly changed architecture that cannot isolate the component. |
| Replication | A deliberate repeated experiment with explicit parent linkage and purpose. | An accidental duplicate. |
| Synthesis matrix | A row-based comparison of sources, methods, findings, limits, contradictions and open questions. | A list of article summaries. |
| Reading pass | The depth of engagement with a source: relevance scan, methods/figures comprehension or reconstruction. | Merely opening a PDF. |
| Horizon scanning | Mapping recent work and foundational references before choosing deep reading. | Treating trending links as validated methods. |
| Enrichment patch | A reviewable set of proposed field/entity/relationship changes with provenance. | A replacement graph without a change record. |
| Observed sequence | A visualization of recorded execution order and supported dependencies. | An authored workflow DAG. |
| DAG | Directed acyclic graph, when the structure truly has no directed cycles. | Every agent graph, especially loops and retries. |
| Durable execution | Work whose recorded lifecycle can survive browser or worker interruption under an implemented recovery policy. | A browser timer, background promise or saved configuration. |
| Concurrency | How many attempts or activities may be in flight. | Requests or tokens allowed per unit time. |
| Rate limit | A bound on requests, tokens or another resource over a defined period. | A concurrency slider alone. |
| Lease | Time-bounded ownership of work with renewal/recovery rules. | Permanent ownership after a worker crash. |
| Idempotency key | A request identity that prevents a repeated launch from creating duplicate work. | Guarantee that every external application action is inherently idempotent. |
| Budget reservation | A maximum-spend hold made before paid dispatch. | Actual settled cost or a post-run spending check. |
| Evidence coverage | Which required events, state snapshots, usage and grading records are present. | A success score. |

Source anchors: [Anthropic evaluation vocabulary](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), [Temporal execution concepts](https://docs.temporal.io/workflow-execution), [Keshav reading method](https://cs.uwaterloo.ca/~brecht/courses/854-http-video-2012/readings/keshav-paper-reading.pdf), and [τ-bench repeated reliability](https://arxiv.org/abs/2406.12045). Definitions specific to AI Labs are product conventions, not quotes from these sources.

