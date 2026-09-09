# AI Labs — the benchmark landscape and what to borrow, 9 September 2026

Purpose: WorkflowBench compares Monarch against raw models and coding agents
on business workflows across simulated SaaS apps. This note reviews the
benchmarks that measure the same kind of work, how they grade, how they
present results, and what is worth borrowing. Borrowing means new inputs to
the fixed methodology (`PLAN.md` §1) and new figures for the Studio reports.
No rule changes are proposed. Companion to
`AI-LABS-STUDIO-DESIGN-DIRECTION-2026-09-09.md`.

## Where WorkflowBench sits

- **Same corpus, third implementation.** Our tasks are Zapier's
  AutomationBench, vendored as the offline repair fork `1.0.6+evalrepair.10`.
  Zapier's official leaderboard runs a private, harder, held-out set and
  reports strict pass rate; Artificial Analysis runs AutomationBench-AA on a
  private subset and reports a different headline (objective share with
  violations scoring zero). Our fork's own release note says its scores are
  not interchangeable with Zapier's. Every public report of ours therefore
  needs one comparability sentence, the way Evaluation Cards recommend.
- **Same grading philosophy.** Deterministic end-state checks, positive and
  negative assertions, no judge model. AppWorld calls the negative side
  "collateral damage"; Zapier says "mostly-right is still wrong". Our approval
  rule ("expected result present and nothing else changed and normal finish")
  is the same idea.
- **What only we do.** A product under test (Monarch) against models and
  agents on identical requests, with test modes that isolate discovery,
  creation and execution, paired comparisons with intervals, complete cost,
  and audience rules in code. No benchmark below compares a product to the
  models it is built on; the closest is IBM's Open Agent Leaderboard, which
  compares agent systems rather than bare models.

## The benchmarks

| Benchmark | Work measured | Grading | Headline metric | Presentation worth noting |
|---|---|---|---|---|
| AutomationBench (Zapier) | 600 multi-app SaaS workflows, 6 domains, 47 apps | End-state assertions, positive and negative, no partial credit | Strict pass rate; cost per task | Rank, Model, Score, Cost/task; per-domain top model; failure modes told in prose; a walkthrough of one task |
| AutomationBench-AA (Artificial Analysis) | 657 private tasks, 40 apps | Same assertions; a task scores 0 on any guardrail violation | Objective share without violations; "Tasks completed" second | Score vs tasks-completed scatter; violations per task; objectives per violation; domain and app heatmaps normalised within the selected models; turns and tool calls per task; token and cost split; score vs release date |
| AppWorld (Stony Brook) | 750 tasks over 9 apps, 457 APIs, code-writing agents | State-based unit tests with collateral-damage checks | TGC (task) and SGC (scenario, all steps) | Two headline numbers so the easy one cannot oversell; normal and challenge splits; encrypted output bundles to avoid training contamination |
| WorkBench | 690 workplace tasks over 5 databases, 26 tools | Final database compared to ground truth | Pass rate | "Outcome-centric evaluation" as the named contribution; wrong-recipient errors called out |
| TheAgentCompany (CMU) | 175 tasks in a simulated software company | Result checks plus checkpoints for partial credit | Success, partial score, steps, cost | Steps and dollars per task next to success; "giving up early saves cost" as a finding |
| CRMArena-Pro (Salesforce) | 19 CRM task types, B2B and B2C, multi-turn | Exact answers; confidentiality refusals | Accuracy single-turn vs multi-turn | Skill breakdown (querying, reasoning, workflow, policy); the multi-turn drop as the story |
| τ²-bench (Sierra) | Customer-service dialogues with tools and a simulated user | Database end state | pass^1 and pass^k | pass^k: the chance all k trials pass, reported at k = 1, 2, 4; per-domain columns |
| Galileo Agent Leaderboard v2 | 5 industries, multi-turn support scenarios | LLM judges | Action completion and tool selection quality; cost per session | Two metrics with opposite winners; cost per session beside quality |
| APEX-Agents (Mercor) | Long professional tasks from lawyers, bankers, consultants | Expert rubrics with an LM judge | Mean rubric score, with Pass@1 as a toggle | Mean score vs Pass@1 toggle; per-role views; thinking level in the model name |
| Toolathlon, MCPMark, MCP-Universe | Real tools over MCP, long horizons | Verification scripts against live software | Solved rate, turns, tool calls, cost | Per-server tables; pass@1, pass@4, pass^4 side by side; trajectories published on Hugging Face; evaluation as a service |
| Vending-Bench 2 (Andon Labs) | Run a business for a simulated year | Money in the bank | Dollars, mean of 5 runs with error bars | One hero chart, balance over time; frontier trend with projection; a "good operator" baseline at ten times the best model; model posts titled as verdicts |
| GDPval (OpenAI) | 1,320 real deliverables from 44 occupations | Blind expert pairwise comparison | Win or tie rate vs human expert; catastrophic error rate | Win rate over time; sector breakdown; speed and cost vs the human; 2.7 % catastrophic errors as its own number |
| HAL (Princeton) | 9 benchmarks, 26,000 rollouts | Each benchmark's own grader | Accuracy and cost per benchmark | Cost vs accuracy scatter with the Pareto frontier; scaffold and model named separately; "100× the cost for 1 % more" as the caption |
| HAL Reliability Dashboard | Same, repeated runs | Twelve metrics in four dimensions | Consistency, predictability, robustness, safety | Task-by-run consistency grid; calibration (does confidence match success); safety kept out of the aggregate |
| Open Agent Leaderboard (IBM) | 6 benchmarks, agent system plus model | Each benchmark's grader under one protocol | Success and cost per configuration | "Same model, different agents, different results"; failed runs cost 20–54 % more than successful ones |
| METR time horizons | Software tasks with human time baselines | Binary success, ~8 runs per task | 50 % and 80 % time horizon | Log-scale trend with a 95 % band from hierarchical bootstrap; per-model task scatter with success as colour and weight as size; "unreliable above 16 h" placed next to the controls |
| ARC-AGI leaderboard | Abstract reasoning puzzles | Exact answers | Score and cost per task | Cost on a log axis; one model's reasoning levels drawn as a connected line; verified, community and preview entries marked; a $10,000 cap |

## What to borrow for the methodology (inputs, not rules)

1. **pass^k for repetitions** (τ-bench, MCPMark, APEX). We already run
   repetitions; report the chance that all repetitions pass, at k = 1 and
   the k we ran, beside the mean pass rate. It separates reliability from
   luck, which is the question a buyer asks about Monarch.
2. **Two headline numbers** (AppWorld TGC and SGC, AA Score and Tasks
   completed). Keep strict pass as the official number and add the objective
   share (checks passed over checks defined) as the second. Both come from
   the stored checks; nothing new is graded.
3. **Violations as their own metric** (AA violations per task, Zapier
   negative assertions). Our "changes outside permitted scope" failures are
   violations. Report violations per attempt and objectives per violation, so
   an architecture that is right but reckless is visible.
4. **False-completion rate** (AutomationBench's dominant failure: 72 to 91 %
   of failures declared success; HAL's predictability dimension). Compare the
   agent's final message against the verdict and report "claimed done but
   wrong". This is the plainest finding a report can carry and it is already
   in our snapshots.
5. **Success overlap between competitors** (Opus and Gemini share only 29 % of
   solved tasks in the AutomationBench paper). A Jaccard overlap per pair,
   drawn from the task matrix, answers "does Monarch solve different tasks or
   the same ones better".
6. **Steps, turns and tool calls per attempt** (AA, TheAgentCompany,
   Toolathlon). We have actions taken; add turns. Cheap, and it explains cost.
7. **Ceiling and floor lines** (GDPval's human expert, Vending-Bench's good
   operator, OfficeBench's 93 % human). Our answer key is the ceiling and the
   sloppy and null checks are the floor; draw them on every pass-rate figure.
8. **Comparability sentences** (Evaluation Cards, the Zapier versus AA split).
   Generate them from data: fork version, public versus private set, task-set
   hash, thinking level, harness, price table version.
9. **Verified versus reported marking** (ARC, HAL). Mark runs with full
   version pins and a config hash as reproducible; mark the rest.
10. **Evidence bundles** (AppWorld's encrypted bundles, Toolathlon's published
    trajectories). Offer a per-run download of snapshots and events; consider
    encryption for public bundles so the tasks do not leak into training sets.

## What to borrow for the reports

| Figure in the direction doc | Borrowed from | Data we already store |
|---|---|---|
| Pass rate with 95 % interval, ceiling and floor lines | METR bands, GDPval baseline | results, repetitions, scripted checks |
| Paired table with green and red deltas | LangSmith, Braintrust, AA heatmaps | results by task and competitor |
| Task matrix and consistency grid | HAL reliability grid, Braintrust regression filter | results by repetition |
| Cost vs pass rate, log cost, Pareto line, thinking levels connected | HAL, ARC, AA, Zapier visualizer | cost per attempt, thinking setting |
| Violations per attempt, objectives per violation | AA | checks, unexpected changes |
| False completion | AutomationBench paper, HAL calibration | final output, verdict |
| Domain heatmap normalised within the compared set | AA | task category |
| Overlap of solved tasks | AutomationBench paper | task matrix |
| Trend per Monarch release | AA score vs release date, Epoch, Vending-Bench | rounds |
| Verdict-titled narrative | Andon Labs model posts, Anthropic release posts | analysis findings |

Two presentation habits stand out across the field. Every serious leaderboard
puts cost next to accuracy in the same table, and the ones people trust
(METR, HAL, AA) put the caveat next to the chart, not in an appendix.

## What not to borrow

- **Judge models** (Galileo, APEX, GDPval's automated grader). Our rule is
  that nothing grades itself; deterministic state checks stay.
- **Composite indices** (AA Intelligence Index). They hide the trade-offs
  the paired table exists to show.
- **Partial credit as the winner** (the Zapier visualizer ranks by average
  score). Strict pass stays the headline; objective share is second.
- **Money as the metric** (Vending-Bench). Our tasks have no bank account;
  cost per pass is the nearest honest equivalent.

## Implications for the Studio

- The report gains five numbers that need no new grading: pass^k, objective
  share, violations per attempt, false-completion rate, overlap.
- The Runs table gains turns and violations columns.
- The caveat generator needs the fork version and the public-set note as
  standard sentences on every public report.
- The vendored AutomationBench ships a Chart.js visualizer of its own
  (`vendor/automation-bench/visualizer`): cost vs score scatter, score
  distribution, token usage, task-by-task comparison. It loads Chart.js and
  Tailwind from CDNs, which our CSP blocks, and it is Zapier-branded, so it is
  a reference for chart choice, not code to reuse.

## Sources

- Zapier AutomationBench: https://zapier.com/benchmarks and https://github.com/zapier/AutomationBench
- AutomationBench white paper (arXiv 2604.18934): https://arxiv.org/html/2604.18934
- AutomationBench-AA: https://artificialanalysis.ai/evaluations/automationbench-aa and https://artificialanalysis.ai/articles/announcing-zapier-automationbench-aa
- AppWorld: https://appworld.dev/appworld/ and https://github.com/StonyBrookNLP/appworld-leaderboard
- WorkBench (arXiv 2405.00823): https://arxiv.org/html/2405.00823v2
- TheAgentCompany: https://github.com/TheAgentCompany/TheAgentCompany and https://arxiv.org/html/2412.14161v1
- CRMArena-Pro: https://arxiv.org/abs/2505.18878 and https://www.salesforce.com/blog/crmarena-pro/
- τ-bench and τ²-bench: https://arxiv.org/abs/2406.12045 and https://github.com/sierra-research/tau2-bench
- Galileo Agent Leaderboard v2: https://galileo.ai/blog/agent-leaderboard-v2
- APEX-Agents: https://www.mercor.com/apex/apex-agents-leaderboard/ and https://arxiv.org/pdf/2601.14242
- Toolathlon: https://github.com/hkust-nlp/Toolathlon; MCPMark: https://mcpmark.ai/leaderboard; MCP-Universe: https://mcp-universe.github.io/
- Vending-Bench 2: https://andonlabs.com/evals/vending-bench-2 and https://andonlabs.com/blog/opus-4-8-vending-bench
- GDPval: https://openai.com/index/gdpval/ and https://arxiv.org/pdf/2510.04374
- HAL: https://hal.cs.princeton.edu/ and https://arxiv.org/html/2510.11977v1
- HAL Reliability Dashboard and "Towards a Science of AI Agent Reliability": https://hal.cs.princeton.edu/reliability/benchmark/gaia/ and https://arxiv.org/html/2602.16666v1
- Open Agent Leaderboard (IBM): https://huggingface.co/blog/ibm-research/open-agent-leaderboard
- METR time horizons: https://metr.org/time-horizons/ and https://metr.org/blog/2026-1-29-time-horizon-1-1/
- ARC-AGI leaderboard: https://arcprize.org/leaderboard
- OfficeBench (arXiv 2407.19056): https://arxiv.org/abs/2407.19056; WorfBench: https://github.com/zjunlp/WorfBench; FlowBench: https://arxiv.org/abs/2406.14884
- Evaluation Cards (arXiv 2606.09809): https://arxiv.org/html/2606.09809v1
