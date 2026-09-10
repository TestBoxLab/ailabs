<!--
Sync impact: 1.1.0 -> 1.3.0 (2026-09-10).
Principles I/IV and governance: harness-independent procedure; Carlos or Lucas
approval (Carlos, September 9). Carlos's final September 10 decision supersedes
earlier repair permission: AutomationBench world/routes/seeds/requests/initial
data/assertions stay immutable; only WorkflowBench approval-rule translation
may be corrected. Bad tasks: recorded exclusion or upstream report.
Alternative dataset adoption stays suspended, with the question pending Lucas.
No methodology change. Publication remains explicitly authorized only.
Reviewed plan/spec/checklist templates: no changes required. Tasks template:
updated to state the existing mandatory TDD rule above generic optional tests.
AGENTS.md and CLAUDE.md synchronized; docs/HARNESS-PROCEDURES.md added.
Claude skill sources preserved; shared current decisions override stale defaults.
No deferred placeholders.
-->

# AI Labs Constitution

The durable rules that govern every feature built in this workspace. Spec Kit
reads this file when generating specs, plans, and tasks; the combined
Spec Kit + Superpowers workflow (see `CLAUDE.md` → *Working conventions*)
enforces it at execution time. [AGENTS.md](../../AGENTS.md) is the entry point
for every harness. Current explicit human decisions and the September 7
direction supersede conflicting historical wording here.

## Core Principles

### I. Brainstorm first; Spec Kit writes the artifacts; Superpowers executes (NON-NEGOTIABLE)
Every non-trivial change flows: **brainstorm → spec → plan → tasks → execute**.
The front door is always `superpowers:brainstorming`; Spec Kit is never invoked
cold. Once the design is settled, Spec Kit owns every written artifact
(`/speckit-specify` → `/speckit-plan` → `/speckit-tasks`, producing
`specs/<id>/{spec,plan,tasks}.md`). `superpowers:writing-plans` is retired
from this flow. Superpowers then executes (`executing-plans` /
`subagent-driven-development`: worktree → TDD → code review → finish-branch).
Planning does not write code; execution does not re-plan.
When the harness cannot invoke the local Claude skills, it follows the same
artifacts and gates through [the prose procedure](../../docs/HARNESS-PROCEDURES.md)
using the checked-in templates and PowerShell helpers. A well-understood small
change may collapse stages as already specified in `CLAUDE.md`; an existing
settled brief is not a reason to restart discovery.

### II. Test-First (NON-NEGOTIABLE)
TDD is mandatory via `superpowers:test-driven-development`: red → green →
refactor. No task is marked complete without runnable evidence
(`superpowers:verification-before-completion`). Non-trivial logic leaves at
least one runnable check behind. The suite is
`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.

### III. The methodology is fixed; features change its inputs
`monarch-benchmark/PLAN.md` §1 is the constant: same request text for every
competitor; nothing grades itself; pass = expected result present AND nothing
else changed AND normal finish; every task frozen by hash before any competitor
runs; paired comparisons only on identical sets, with error bars; every figure
carries its source line; cost is complete; audience rules are code; config hash
per run; API-key billing only. A spec MAY change what feeds the methodology
(config files, competitors, products under test, test modes, outputs) and MUST
NOT reopen these rules unless Carlos explicitly says so.

### IV. Money and pre-registration gates
A benchmark round costs real money, and the money is shared: US$ 300 per
calendar week (Monday 00:00 America/Sao_Paulo, no rollover), kept in the weekly
ledger (`research/budget.sqlite3`). The ledger is the spending gate: every paid
request is reserved for its maximum before it is sent and settled from the
provider's receipt; a round is admitted only when the week can cover its maximum
liability; an attempt stops at its cap; a week's spend is reconciled against the
providers' own usage exports. Either Carlos or Lucas approves paid rounds
(decision D5, 8 September 2026, approver widened by Carlos on 9 September):
a launch requested by either uses that person's identity; other launches create
an approval request and wait for human `wb approve`, then use `--request`.
An agent never approves its own round. Smoke scale (at most 20 attempts per
competitor, retries included) needs no approval record. Every paid launch names
its operator (`WB_OPERATOR`) and states the number of attempts and a cost band
before a run. Existing explicit authorization survives a harness or skill change.
Task prompts, starting data and approval rules are pre-registered. Carlos's final
10 September decision supersedes earlier repair permission: AutomationBench's
world, routes, seeds, task requests, initial data and assertions are immutable,
including the ignored Airtable filter and weak invoice assertion. Only
WorkflowBench's own approval-rule translation may be corrected. Reproduce that
defect against the unchanged simulator, preserve prior rules, and record
old/new hashes and evidence in `monarch-benchmark/docs/rounds/`. Old rows are
non-regradable against replacement hashes. Bad tasks may be excluded with a
recorded reason or reported upstream; never silently edit them. Do not adopt
`1.0.6+evalrepair.10` or another replacement dataset without a new explicit
decision; the question remains pending Lucas. Methodology changes still require
explicit human approval.

### V. Plain language, knowledge-graph-grounded
Every file in the repo is in English; conversation with Carlos is in
Portuguese. Shared docs and person-edited config files use the plain names in
`CLAUDE.md` → *Plain names* (competitor, task set, repetitions, attempt,
approval rule, answer key, product under test), not the internal code names.
Graphify (`graphify-out/`) is the knowledge layer: consult
`GRAPH_REPORT.md` before architecture or codebase questions and before a spec
that touches existing code; refresh the graph after code changes.

## Additional Constraints

- **Stack**: Python 3.13 with `uv`; stdlib-first (the world server, HTTP shim,
  and mock OpenAI server are stdlib). New dependencies need a reason in the plan.
- **Laziness within discipline** (ponytail): YAGNI, reuse what is in-repo,
  stdlib before dependencies, shortest working diff — after fully understanding
  the change. Laziness shortens the solution, never the comprehension.
- **Pushes require Carlos's explicit request.** The repository is public;
  local commits are fine. No implied permission to publish results, post to
  Slack or merge experimental changes into Monarch.
- **The upstream world is immutable.**
  `monarch-benchmark/workflowbench/vendor/automation-bench` is AutomationBench.
  Do not patch its code, routes, seeds or assertions locally. Record limitations
  and the actual source revision; do not relabel it as a repaired version or
  bypass the revision guard. Exclusions require a reason and provenance;
  upstream reports do not imply authorization to modify the benchmark locally.
- **Provenance over convenience.** Results rows keep versioned competitor
  names, model ids, price-table versions, and task hashes. No hand-typed
  numbers in reports.

## Development Workflow & Quality Gates

1. **Brainstorm** (`superpowers:brainstorming`) — the mandatory front door.
2. **Specify** (`/speckit-specify`, optionally `/speckit-clarify`) → `spec.md`.
3. **Plan + Tasks** (`/speckit-plan`, `/speckit-tasks`) → `plan.md`, `tasks.md`.
   Do not skip `/speckit-tasks`.
4. **Execute** via Superpowers — worktree → TDD → subagent-per-task → code
   review (`superpowers:requesting-code-review`) → finish-branch
   (`superpowers:finishing-a-development-branch`). Do not re-plan mid-execution.
5. **Analyze / checklist** (`/speckit-analyze`, `/speckit-checklist`) optionally
   validate cross-artifact consistency before implement.
6. **Refresh** the Graphify graph after code changes; update `PLAN.md` status
   and decisions log in place.

## Governance

This constitution supersedes ad-hoc practice. Amendments are made through
`/speckit-constitution` or its shared prose equivalent (which keeps dependent
templates in sync) and are recorded here with a version bump. When a spec, plan, or task conflicts with
Principle III or IV, the constitution wins and the artifact is revised.

**Version**: 1.3.0 | **Ratified**: 2026-09-02 | **Last Amended**: 2026-09-10 (shared harness procedure and final upstream-immutability decision)
