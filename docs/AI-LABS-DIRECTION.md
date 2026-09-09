# AI Labs: current direction

Decision date: 7 September 2026. Owner: Lucas Wakigawa.
Status: agreed direction; implementation tracked in specs/007-lab-foundation/.
Unblock plan (8 September 2026): [AI-LABS-UNBLOCK-PLAN-2026-09-08.md](AI-LABS-UNBLOCK-PLAN-2026-09-08.md).
This supersedes conflicting assumptions in the September 2–6 plans.

## Outcome

Continuously connect research, hypotheses, experiments, deep analysis and
improvements to Monarch. A reader should understand the business result and
then inspect exactly which actions succeeded or failed. Visual reporting is an
entry point into the evidence, not a summary detached from it.

## Evaluation tracks

| Track | Task | User assistance | Outcome |
|---|---|---|---|
| Agentic request | Complete a one-off business request | No human answers during the attempt | Correct final state, constraints respected, finished unaided |
| Create and run | Build a workflow and execute it | Still an experimental policy | Saved workflow plus correct execution; total creation and execution cost |

For workflows, evaluate bounded clarification as a distinct configuration. A
scripted user can supply only pre-authored task-authorized facts, never oracle
answers or grading feedback. Record actual questions, user turns, waiting time,
and whether clarification enabled completion. Fewer turns are desirable only
when correctness is preserved. Assisted and unattended results remain separate.
Lucas has not yet settled this policy.

Execution-only and full application discovery remain possible extensions, not
substitutes for the initial two tracks.

## Competitors and fairness

Claude models use Claude Code; GPT models use Codex. Other families need an
appropriate verified harness. Preserve native prompts, planning, compaction,
shell and tool strategies; freeze model and harness versions before a round.
Select capable settings on development tasks, not on held-out scored answers.

Keep task briefs, business constraints, initial worlds and available application
information comparable. Record differences in interface, tools, effort and limits.
Raw API loops are scientific controls, not the headline native-agent competitors.
Monarch stock and experimental forks have separate identities.

AutomationBench's current world has APIs but no UI. Do not claim browser evaluation
until a real common application UI exists. Harness browser access is included
where the environment supports it.

## Evidence and analysis

Record observable messages, available provider reasoning summaries, tool calls
and results, errors, timestamps, workflow artifacts, phase transitions, final
output, usage and before/after state. Do not imply access to hidden model reasoning.
Keep secrets redacted and evaluator data outside competitor environments.

Every finding links to exact events and grader checks. Separate:
1. What happened: trace and state evidence.
2. Whether it satisfied the task: versioned grading.
3. Why it may have happened: a hypothesis, alternatives and confidence.
4. Whether a change helped: controlled experimental evidence.

Analyze successes as well as failures. Include false passes, missing work,
forbidden changes, entity grounding, precision, planning, tool selection,
execution, recovery, premature stopping and clarification. Identify the earliest
supported divergence and its downstream consequences. Final prose is not proof
of completion. Infrastructure, invalid tasks and product failures stay distinct.

Use programmatic checks for verifiable state. Use blinded, rubric-based LLM
analysis for semantic dimensions and hypothesis generation; calibrate against
human-reviewed examples, measure agreement, test order/model bias and retain
disagreements. LLM analysis does not override the checker or establish causation.

## Reports and interaction

| Question | Visual | Evidence reached by selection |
|---|---|---|
| Does it finish reliably? | Completion with uncertainty and sample counts | Task-by-competitor matrix and repeated attempts |
| What improved or regressed? | Paired wins/losses and deltas | Both traces on the same task; configuration diff |
| Is quality worth the cost? | Completion versus cost; phase breakdown | All spend, including unsuccessful attempts and retries |
| Where does it struggle? | Failure classes and difficulty/domain small multiples | First divergence, tool event and expected/observed effects |
| How much assistance? | User-turn distribution alongside completion | Exact questions and answers |
| Can this run be trusted? | Evidence coverage and integrity status | Pins, exclusions, missing telemetry, infrastructure failures |

Compute every number once from the results store. Distinguish zero, unavailable
and not applicable. Use direct labels, accessible color and keyboard operation,
responsive layouts and shared scales. Avoid ornamental metrics and decorative
dashboard cards.

Open each report with a concise, evidence-backed account of what changed, which
business work succeeded or failed, and the next investigation. No templated
celebration or causal certainty from one run. Updates stay under 140 words and
link to depth in the report rather than posting multiple attachments.

Agentic interactions operate on the same evidence: compare a failure to a
success, locate the first wrong record selection, or draft an experiment from
a failure cluster. Answers cite events; paid actions disclose scope and reserve
budget. Browsable charts and traces remain useful without chat.

## Difficulty

Lucas delegates AutomationBench difficulty ranking. Preserve legacy hashes and
tiers while introducing a versioned classification. The current sum of seeded
services, expected-change patterns and tools is only a structural proxy.

Classify from requirements and available information before seeing outcomes:
cross-system dependencies, required actions, record ambiguity, precision,
exclusions and horizon. Keep the multidimensional profile and score rationale.
A short exact calculation can be hard. Calibrate on a reviewed sample and later
compare against empirical difficulty on a separate development split.
Never define hard as simply tasks Monarch lost. Publish counts, domain coverage,
ties, exclusions and selection seed.

## Climbing the curve

Research inbox → hypotheses → ready to test → running → analysis → replication
→ decisions and engineering. Rejected and inconclusive ideas stay searchable.
Infrastructure work is clearly labeled, not dressed up as a scientific hypothesis.

Weekly scanning starts from search history, glossary, prior experiments and
unresolved failures. Map review papers and foundational references; examine
engineering practice, interaction research and competition. Apply three-pass
reading: relevance, methods/figures, then deep reconstruction where justified.

The synthesis matrix records source, hypothesis, method/data, findings,
limitations, contradictions, transfer conditions and unanswered questions.
Inaccessible sources remain unread. Citation counts guide discovery, not truth.

Pre-register each experiment: failure class, mechanism, falsifiable prediction,
control/treatment, split, metrics, minimum useful effect, stopping rule, maximum
spend, evidence requirements and decision criteria. Keep development and held-out
evaluation separate; retain negative results. Name the primary comparison and
label exploratory comparisons. Cluster uncertainty by independent task/template,
not by treating retries as independent tasks.

Search the ledger before proposing work. Repeats declare replication, changed
conditions, repaired measurement, or a new interaction. Combinations link parents
and compare to the components where feasible. Do not assume additive gains.

Report first-attempt success, success within a retry budget and repeated-trial
reliability separately. Also show both valid-attempt quality and all-attempt
operational outcomes so exclusions cannot hide infrastructure problems.

## Budget and operating home

USD 300 per calendar week, Monday 00:00 America/Sao_Paulo, no rollover.
This week convention is a stated implementation default. Include experiment
provider calls, retries, paid research/judging and directly attributable
experimental infrastructure. No separate per-experiment cap was specified.

Reserve maximum spend before dispatch, including parallel work. Reconcile actual
usage and preserve unknown billing. Never assume missing cost is zero. Shared
reservations must be implemented and verified before autonomous paid execution:
the current post-completion per-run ceiling cannot enforce the weekly limit.

Trello: https://trello.com/b/ntJfbkLx/ai-labs-research-experiments

The board is private in Lucas's connected workspace. Repository records hold
the scientific evidence; Trello holds working status and links to those records.

## Sources

- [Lab kickoff](https://testbox-talk.slack.com/archives/C0BU26293CM/p1788275489297909)
- [Research direction](https://testbox-talk.slack.com/archives/C0BU26293CM/p1788519080552859)
- [Communication correction](https://testbox-talk.slack.com/archives/C0BU26293CM/p1788728315040149)
- [ApplicationBench history](https://github.com/TestBoxLab/ApplicationBench/blob/main/docs/HISTORY.md)
- [Keshav: How to Read a Paper](https://cs.uwaterloo.ca/~brecht/courses/854-http-video-2012/readings/keshav-paper-reading.pdf)
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Tau-bench: repeated reliability and user interaction](https://arxiv.org/abs/2406.12045)

The specific design is AI Labs' choice. These sources inform the method; they
do not prove that a technique will improve Monarch.
