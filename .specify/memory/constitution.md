# AI Labs Constitution

The durable rules that govern every feature built in this workspace. Spec Kit
reads this file when generating specs, plans, and tasks; the combined
Spec Kit + Superpowers workflow (see `CLAUDE.md` → *Working conventions*)
enforces it at execution time.

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
providers' own usage exports. Lucas approves paid rounds (decision D5,
8 September 2026): a launch by Lucas runs at once under an approved record; a
launch by anyone else, Carlos included, creates an approval request and waits
for `wb approve`; smoke scale (at most 20 attempts per competitor) needs no
record. Every paid launch names its operator (`WB_OPERATOR`) and states the
number of attempts and a cost band before a run. Task prompts, starting data,
and approval rules are pre-registered: they are not edited after results are
seen without Lucas's sign-off, and any edit that changes a task hash is called
out as making old rows non-regradable.

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
- **Nothing is pushed** to `TestBoxLab/ailabs` until Carlos decides on repo
  visibility. Local commits are fine.
- **Vendored code is not ours.** `workflowbench/vendor/automation-bench` is
  upstream AutomationBench; patches go through Lucas, not into the vendor tree.
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
`/speckit-constitution` (which keeps dependent templates in sync) and are
recorded here with a version bump. When a spec, plan, or task conflicts with
Principle III or IV, the constitution wins and the artifact is revised.

**Version**: 1.1.0 | **Ratified**: 2026-09-02 | **Last Amended**: 2026-09-08 (§IV: the weekly ledger is the spending gate; Lucas approves, decision D5)
