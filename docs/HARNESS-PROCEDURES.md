# Shared procedures for Claude Code and Codex

Read [AGENTS.md](../AGENTS.md), the whole [CLAUDE.md](../CLAUDE.md), and the
[constitution](../.specify/memory/constitution.md) first. These procedures preserve
the method when the harness cannot invoke the eleven skills in
[.claude/skills](../.claude/skills/). Keep those skills for Claude sessions;
Codex reads their relevant reference files and performs the steps with native
file, shell and review tools. No copied skill installation or slash-command
emulation is required. Private global Claude settings are not a dependency of
the repository procedure.

The September 7 direction and Carlos's September 9–10 approval and correction
decisions supersede older skill instructions: either Carlos or Lucas may approve
a paid round; only the repairs allowed by his final decision below remain
authorized; an existing authorization is not lost at a skill boundary. Preserve
all spending, integrity and evidence gates. Routine authorized local preparation
does not require a second confirmation before each file save.

Carlos's final September 10 decision supersedes all earlier repair permission:
AutomationBench's world, routes, seeds, task requests, initial data and assertions
remain unchanged, including the ignored Airtable filter and weak invoice
assertion. Only WorkflowBench's own approval-rule translation may be corrected,
with simulator evidence and preserved prior rules/hashes. Bad tasks may be
excluded with a recorded reason or reported upstream; never silently edit them.
The earlier request to locate and adopt `1.0.6+evalrepair.10` is suspended, with
the question pending Lucas. Do not resume it without a new explicit decision.

## Feature work without Spec Kit commands

Ground the work in `graphify-out/GRAPH_REPORT.md` (use the wiki index if present),
the relevant code, prior research and existing feature artifacts. Resolve intent
through the installed brainstorming skill; an explicit, settled brief supplies
the requirements already. Keep the existing lightweight-change exception.
For non-trivial new work, use the spec → plan → tasks artifacts below, then
execute them through the installed Superpowers workflow. Do not restart planning
when continuing an already specified correction.

| Claude skill | Equivalent procedure in Codex |
|---|---|
| `speckit-specify` | Reuse the relevant feature, or choose one unused numbered directory under `specs/` using `.specify/init-options.json`. Fill `.specify/templates/spec-template.md` with prioritized user stories, acceptance scenarios, measurable requirements, edge cases and assumptions; create `checklists/requirements.md`. Record the selected directory as `feature_directory` in `.specify/feature.json`. Feature-directory and branch names are independent. Resolve template overrides if configured. |
| `speckit-clarify` | Read the spec and resolve only material ambiguities absent from the brief (at most five questions). Record accepted answers under a dated Clarifications section and update the affected requirements immediately; do not ask the user to repeat settled decisions. |
| `speckit-plan` | Run `.specify/scripts/powershell/setup-plan.ps1 -Json` for the selected feature, inspect its resolved paths, and fill `plan.md` from the plan template. Check the constitution before and after design. Resolve unknowns in `research.md`; produce the relevant `data-model.md`, interface documents under `contracts/`, and runnable validation instructions in `quickstart.md`. Update shared agent context directly if the referenced context-update helper is absent. Planning does not implement code. |
| `speckit-tasks` | Run `.specify/scripts/powershell/setup-tasks.ps1 -Json`; read the resolved tasks template and the spec/plan. Write small, dependency-ordered tasks grouped by user story with exact file paths: `- [ ] T001 [US1] ...`. Use `[P]` only for independent work on different files. Include the mandatory failing-test-first steps; the generic template's optional-test language does not override constitution II. |
| `speckit-analyze` | After tasks exist, compare spec, plan and tasks read-only for coverage, ambiguity, duplication, inconsistent terms and constitution violations. Report severity, exact locations and remediation; analysis alone does not change files. |
| `speckit-checklist` | Create or append `checklists/<topic>.md` using the checklist template, continuing `CHK` numbering. Assess requirement completeness, clarity, consistency and measurability with spec references; this is not evidence that implementation works. Preserve existing items. |
| `speckit-implement` | Read the entire plan/tasks and checklist state; execute through Superpowers (isolation where needed, TDD, task-scoped delegation, review and branch completion). Resolve checklist gaps within the authorized scope; apply any explicit user decision to proceed. Respect dependencies and serialize shared-file edits. Mark tasks complete only after runnable verification. Do not silently replace the plan or perform unauthorized publication. |
| `speckit-converge` | After implementation, compare current code and runnable evidence against the spec/plan/tasks. Append only the remaining traceable work in a new Convergence phase of `tasks.md`, with new IDs. Never rewrite existing tasks, alter the spec/plan, or implement code during this assessment. If nothing remains, leave the file byte-identical. |
| `speckit-constitution` | Apply an explicit governance decision to the constitution, bump its version/date and record a sync-impact note. Check dependent templates and agent instructions for conflicts; propagate the decision without inventing new policy. |
| `speckit-taskstoissues` | Only when GitHub issue publication is explicitly requested: confirm `remote.origin.url`, read tasks and search open and closed issues for existing task IDs before creating missing, dependency-ordered issues in that exact repository. Trello remains the working-status home; this step is not part of routine execution. |

The prerequisite helper is
`.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks`
after tasks exist (`-PathsOnly` for read-only path discovery). Run helpers from
the repository root. Inspect the selected feature before mutation; setup helpers
copy templates and must not overwrite a populated plan during a resumed task.
If `.specify/extensions.yml` exists, inspect enabled before/after hooks in the
corresponding source skill; do not invent hooks, execute conditional expressions
by guesswork, or let a publication hook exceed current authorization. A missing
helper or mandatory hook must be reported with the equivalent manual step or
the specific unresolved prerequisite.

After code changes, refresh Graphify using the installed skill and `uv`-managed
Python environment, and update the existing tracking surface. Run the relevant
offline checks and browser verification for UI changes. Strict TDD for a defect
means a reproduction against the actual simulator and frozen task that fails for
the reported reason before the fix, then passes afterwards. Preserve historical
task/config versions; record hash moves from permitted WorkflowBench approval-rule
corrections in the round evidence. Do not change upstream assertions or the world.

## Prepare and run a round

This is the Codex equivalent of
[`monarch-benchmark`](../.claude/skills/monarch-benchmark/SKILL.md).
All `uv`/`wb` commands and `config/`, `tasks/`, `out/` paths below are relative
to `monarch-benchmark/workflowbench/`. The weekly ledger is the repository-root
`research/budget.sqlite3` (the CLI's default), shared across the lab.

1. **Resolve the actual inputs.** Read the requested product and plan, then
   `config/README.md` and `wb_orchestrator/config.py` for current schemas. Use
   `wb_orchestrator.config.resolve` under `uv run python`, loading `.env` with
   `dotenv.load_dotenv('.env')` when calling Python directly. Print only the
   non-secret resolved product, mode, tasks/prompts, repetitions, competitors,
   baseline, audience, concurrency, timeouts, maximum attempts including retries,
   cost ceiling, attempt cap and config hash. Do not invent inputs or substitute
   a different plan. For config errors, preserve the exact safe diagnostic and
   explain the named file/field; resolve the cause before proceeding.
2. **Check provenance and readiness.** Search prior experiment/round records;
   declare replication or repair and parent links. Confirm task hashes, vendor
   revision, native harness/model versions, non-default settings, API-key billing
   and evaluator isolation. Read the current milestone evidence and respect the
   implemented verification gates. Missing or older-than-30-day harness proof
   files are warnings; a configured but unverified harness is not made runnable
   by prose. Never print `.env` or resolved credentials.
3. **Disclose spend and use human authorization.** Read sourced, dated model
   prices and prior comparable attempts from `out/wb.sqlite3`; give a cost band
   and its basis, or state when no historical data exists. State total and
   per-competitor attempts including retry scope **before any `wb run`**. Inspect
   `uv run wb budget status` and verified billing/reservations. US$ 300 per Monday
   00:00 America/Sao_Paulo calendar week, no rollover. Include paid analysis and
   retries; unknown costs stay unknown. Attribute `WB_OPERATOR` to the human
   requester, Carlos or Lucas when either requested the paid round. Never forge
   human approval. At most 20 attempts per competitor needs no approval record;
   above that, use the implemented approval/request flow. A plan's `approved_by`
   is not approval. Existing explicit authorization does not need to be asked
   for again; if authorization is missing, prepare the concrete round first.
4. **Verify Monarch before dispatch.** Follow the current deployment runbook,
   check the actual deployed build and catalogue (47 products, 686 actions,
   47 in sync), and run `uv run wb monarch verify`, including its front-door
   check. For CLI rounds keep the fixed ngrok tunnel to `127.0.0.1:9105` alive;
   the hosted Studio's `STUDIO_FRONT_DOOR_TARGET` must reach it. A public page
   answering is insufficient. Knowledge-base and run-only recipe files must be
   generated through the CLI, never hand-edited; re-importing knowledge moves
   dependent config hashes. Resolve drift and verification refusals rather than
   bypassing them. `wb doctor` provider calls and `--monarch-probe` spend money;
   treat them as paid work, even though doctor needs no round approval record.
5. **Dispatch the authorized plan.** In PowerShell set `$env:WB_OPERATOR` to
   the requester's name, then `uv run wb run --product <product> --plan <plan>`
   (with `--request <id>` where required). Use a detached process with stdout,
   stderr and exit status retained; Windows `Start-Process` helpers are hidden.
   Monitor tunnel health, progress and spend. The plan's ceiling is a stop
   signal, not a substitute for a maximum-spend reservation. `wb resume <run_id>`
   also spends money and requires matching configuration and available budget.
6. **Read the evidence.** After completion use `uv run wb grade <run_id>` and
   `uv run wb report <run_id> --audience <configured audience>`. Preserve source
   lines, paired comparisons and every failed attempt, plus snapshots, observable
   trajectories and final state. For Monarch inspect `terminations`, phases,
   missing cost, questions, errors and `front-door.jsonl` application calls.
   `completed` alone does not prove any write occurred. Settle receipts in the
   ledger, report unknown billing and update local research/round records and
   Trello status. Slack posts, public results, repository pushes and Monarch
   merges require their own explicit authorization.

## Prepare configuration without launching a round

The helper's six references remain the field-level procedure. Read the relevant
one, inspect the existing file and reuse its shape; validate saved inputs with
the actual loaders below, then resolve the complete product/plan offline.
Configuration preparation never implicitly launches `wb run` or provider calls.

| Operation | Reference | Offline validation |
|---|---|---|
| Model or price table | [model](../.claude/skills/monarch-benchmark/references/model.md) | `config.load_model` or `config.load_price_table`; sourced prices and verification date, API-key variable name only. |
| Harness and proof of life | [harness](../.claude/skills/monarch-benchmark/references/harness.md) | `config.load_harness`; read `_HARNESS_KEYS`, accepted providers and runnable state. Proofs record observed output; proof calls are paid. |
| Product | [product](../.claude/skills/monarch-benchmark/references/product.md) | `config.load_product`, `config.load_side_effects`; services from `wb_world.openapi.load_schemas`. Generate knowledge/recipe hashes through `wb monarch setup` / `wb monarch recipes` only. |
| Round plan | [plan](../.claude/skills/monarch-benchmark/references/plan.md) | `config.load_plan`, then `config.resolve`; baseline, audience, task set, repeats, retries and caps must agree. |
| List or inspect tasks | [tasks](../.claude/skills/monarch-benchmark/references/tasks.md) | `wb_world.episode.load_suite` / `load_task_file`; display prompt, approval rule and hash without mutating them. Only WorkflowBench approval-rule translation repairs follow the preservation/refreeze procedure; upstream assertions stay unchanged. |
| Readiness check | [check](../.claude/skills/monarch-benchmark/references/check.md) | Resolve config, check required environment names without values, proof age and Monarch readiness; report missing prerequisites. A check never launches the round. |

`name` must equal the YAML file stem. Changes to plans, products, models,
harnesses, task files and generated knowledge may move a config hash and make an
in-flight round non-resumable; preserve prior versions and disclose the impact.
