# AI Labs — Project Instructions

## Project context

TestBox AI Labs is an internal lab run by Carlos Mattos (owner of this repo) and
Lucas Wakigawa ("Waki" in older docs). Its first program, **started 2026-09-02**,
is a recurring benchmark of **Monarch** (TestBox's product that maps a SaaS
platform and turns a plain-language request into a runnable workflow) against
raw language models and coding agents doing the same tasks.

The benchmark code is **WorkflowBench**, designed by Lucas (`DESIGN.md` v2.1,
`BUILD-SPEC.md` M0–M6) and extended by Carlos. Everything lives under
`monarch-benchmark/`; the tracking surface is `monarch-benchmark/PLAN.md`.

**The methodology is fixed; three things vary and plug into it** (`PLAN.md` §1):

- **Product under test** ("target"): today the simulated API set (AutomationBench
  mock, 47 apps, cents per attempt). Later: a real platform with API + UI, or a
  real API-only service. Each product gets its own task set.
- **Test mode**: how much of Monarch is under test. *Full flow* (discovery +
  workflow creation + execution), *create + run* (fixed knowledge base), or *run
  only* (a known-correct workflow, engine measured alone).
- **Competitors**: the scripted checks (gabarito/oracle, sloppy, null), raw
  models with three tools (Claude Opus 4.8 is the baseline because it is
  Monarch's own authoring brain; GPT-5.6 Sol; cheap models), Claude Code
  headless, and Monarch itself (`stock` per release; `lab` for Lucas's
  experiments, internal reports only).

**Fixed rules that every change must respect** (`PLAN.md` §1.1): same request
text for every competitor; nothing grades itself (the checker runs later from
stored snapshots, `wb grade`); pass = expected result present AND nothing else
changed AND normal finish; every task frozen by hash before any competitor runs;
paired comparisons only on identical sets, with error bars; every figure carries
its source line; cost is complete (cached vs not, versioned price table);
audience rules are code; config hash per run; API-key billing only.

**Where things stand (2026-09-03, evening):** repo at
`C:\Users\cgmat\Desktop\TestBox\ailabs` (off OneDrive; moved twice on 3 Sep, see
`monarch-benchmark/docs/HANDOFF-2026-09-03.md`). `main` pushed to `origin` on 3 Sep;
the GitHub repo is public. 199 tests green. Feature 001, declarative benchmark
configuration, is merged: `wb run --product --plan`, inputs in `workflowbench/config/`,
approval gate and cost ceiling in code. Two smoke runs (`smoke-frontier-001`, `-002`)
agree: Opus 90%, GPT-5.6 Sol 100%. Feature 002 (Monarch as a competitor, create + run
mode, cost from Langfuse) is merged into `main` and pushed (merge `5468dbf`,
`origin/main` at `89172ac`, 321 tests green offline): `wb monarch setup`, the
real Monarch competitor in `wb_arms/monarch.py`, doctor checks, report source
line. Live gates T053–T057 in `specs/002-monarch-create-run/tasks.md` are
pending: Monarch running (locally, or on Railway with a public host for the
front door), `bedrock:InvokeModel` for Carlos's AWS roles, and the Monarch-side
telemetry PR. See `monarch-benchmark/docs/HANDOFF-2026-09-03.md`. Feature 004
(Monarch in run-only mode: `wb monarch recipes`, one known-correct recipe per
task, the engine measured alone) is specified and planned on 4 Sep —
`specs/004-monarch-run-only/`, documents only, no code yet.

**Team:** Carlos (program owner, this workspace), Lucas (co-lead, design of
record, AutomationBench patches), Deyton (Monarch engine; authoring endpoint
and Feature Discovery questions), Sam (GTM), Alex (proposed approver for lab
competitors in reports).

**Next in line** (`PLAN.md` order): Monarch on the simulated product in three
modes (frente B), Monarch phase telemetry (C), Langfuse + Slack output (D),
corpus leftovers (F), second product (E).

The user's global `~/.claude/CLAUDE.md` is loaded automatically and applies
here. This file holds project-specific additions only.

## Plain names

Carlos reads plans and config files; he should never need a decoder ring.
In conversation, shared docs, and any config file a person edits, use the plain
names. Code identifiers may keep the internal ones.

| Internal name (code) | Plain name (docs, config, chat) |
|---|---|
| arm | competitor (competidor) |
| suite | task set (conjunto de tarefas) |
| k, trials | repetitions (repetições) |
| episode | attempt: one task, one competitor, one repetition (tentativa) |
| contract, invariant | approval rule: what must change, what must not (regra de aprovação) |
| oracle | answer key (gabarito) |
| target | product under test (produto sob teste) |
| audience | who reads the report: internal or public |
| smoke | small run to test the machine, not to draw conclusions |
| WS-B, WS-C… | frente de trabalho B, C… — always say what it is |

## Working conventions

### The combined workflow — Spec Kit plans WHAT, Superpowers controls HOW

This workspace runs the same standard as `data-generator-2.0`: **Superpowers**
for Socratic discovery + workflow-enforced execution, **Spec Kit** for
artifact-driven planning in between, **Graphify** as the knowledge layer. The
governing contract is the constitution at `.specify/memory/constitution.md`.

**The front door is always Superpowers brainstorming — never Spec Kit cold.**
Mental model: *Superpowers brainstorming figures out what we're actually doing;
Spec Kit writes that up as spec + plan + tasks; Superpowers executes it;
Graphify grounds all of it in the existing code.*

For any non-trivial feature, bug fix, or behavior change, follow the pipeline —
each stage hands its artifact to the next:

| Stage | Owner | Command / skill | Artifact |
|-------|-------|-----------------|----------|
| 0. Ground | Graphify | read `graphify-out/GRAPH_REPORT.md` | context |
| 1. Brainstorm | Superpowers | `superpowers:brainstorming` | shared understanding |
| 2. Specify | Spec Kit | `/speckit-specify` (+ `/speckit-clarify`) | `specs/<id>/spec.md` |
| 3. Plan + Tasks | Spec Kit | `/speckit-plan`, `/speckit-tasks` | `plan.md`, `tasks.md` |
| 4. (optional) Validate | Spec Kit | `/speckit-analyze`, `/speckit-checklist` | consistency report |
| 5. Execute | Superpowers | `executing-plans` / `subagent-driven-development` (worktree → TDD → review → finish-branch) | branch, tests, code |
| 6. Refresh | Graphify | rebuild code graph | updated `graphify-out/` |

**Handoff rules:**
- **Brainstorm first, always.** Do not open `/speckit-specify` on a cold
  request — run `superpowers:brainstorming` to settle intent, requirements, and
  design, *then* feed that understanding into `/speckit-specify`.
- **`superpowers:writing-plans` is retired from this flow.** Spec Kit's
  `/speckit-plan` + `/speckit-tasks` are the implementation plan now.
- **Do not skip `/speckit-tasks`.** Superpowers' `executing-plans` consumes
  exactly the small (2–5 min) task shape Spec Kit produces.
- **Planning does not write code; execution does not re-plan.** Once `tasks.md`
  exists, hand it to Superpowers: *"Execute `specs/<id>/tasks.md` using
  Superpowers — worktree, strict TDD, subagent per task, code review,
  finish-branch. Do not re-plan."*
- **TDD and evidence are non-negotiable** (constitution §II): red→green→refactor
  via `superpowers:test-driven-development`; no "done" without runnable output
  (`superpowers:verification-before-completion`).
- **Lightweight changes may collapse stages.** A one-line, well-understood fix
  doesn't need a full spec. When in doubt, spec it; the ladder shortens the
  solution, not the comprehension.

### Benchmark-specific rules (constitution §III–§V)

- **No full benchmark round without explicit approval of that specific run.**
  Smoke scale (10 tasks, 2 repetitions) and `wb doctor` are fine. Before any
  `wb run`, state the number of attempts and a cost band.
- **Pre-registration.** Do not edit a task's prompt, starting data, or approval
  rule after seeing results without Lucas's sign-off. Hash changes make old
  rows non-regradable; say so.
- **The methodology does not change through features.** `PLAN.md` §1 is the
  constant; features change its inputs (files, competitors, products), never
  its rules. A spec that reopens a fixed rule needs Carlos's explicit say-so.
- **Pushes to `TestBoxLab/ailabs`** happen only when Carlos asks (first push 3 Sep).
  The repo is public; the specs carry vendor legal notes.
- **Language.** Conversation with Carlos in Portuguese. Every file in the repo
  in English, plain language, no internal jargon in shared docs.
- **Graphify grounds everything.** Read `graphify-out/GRAPH_REPORT.md` before
  architecture or codebase questions and before specs that touch existing
  code; refresh the graph after code changes. The vendored
  `workflowbench/vendor/automation-bench` is excluded from the graph.
- **Stack:** Python 3.13 managed by `uv`. Environment:
  `cd monarch-benchmark/workflowbench && uv sync && uv run python -m pytest tests -q`.
  Keys in `workflowbench/.env` (gitignored). AutomationBench vendored at
  `workflowbench/vendor/automation-bench` (gitignored; re-clone if missing).

## What lives where

| Path | Purpose |
|---|---|
| `CLAUDE.md` | This file — project-specific instructions. |
| `.claude/skills/monarch-benchmark/` | Skill to prepare, confirm and run a round, and to create, edit and check every config file a round needs (`/monarch-benchmark [model\|harness\|product\|plan\|tasks\|check] ...`); `references/` holds one file per subcommand, `differs.md` the deferred items. |
| `.specify/memory/constitution.md` | Governing rules for all features. |
| `.specify/templates/` | Spec Kit spec/plan/tasks/checklist templates. |
| `specs/<id>/` | Per-feature `spec.md` + `plan.md` + `tasks.md` (Spec Kit). |
| `specs/001-declarative-benchmark-config/` | Feature 001: benchmark inputs as files; `contracts/` holds the CLI and config-file contracts. |
| `specs/002-monarch-create-run/` | Feature 002: Monarch as a competitor, create + run mode; spec, plan, tasks, `contracts/` (config-files, cli, monarch-telemetry). In progress on branch `002-monarch-create-run`. |
| `specs/004-monarch-run-only/` | Feature 004: Monarch in run-only mode — one known-correct recipe per task, the engine measured alone; spec, plan, tasks, `contracts/` (cli, config-files). Documents only so far; design of record `docs/superpowers/specs/2026-09-04-monarch-run-only-design.md`. |
| `specs/005-task-tiers/` | Feature 005: the six scored AutomationBench domains in the corpus, and four task sets drawn by difficulty tier; `contracts/` holds the CLI and config-file contracts. Documents only so far; design of record `docs/superpowers/specs/2026-09-04-task-tiers-design.md`. |
| `workflowbench/tasks/tier-simple/`, `tier-medium/`, `tier-complex/`, `random-10/` | The four frozen task sets, ten prompts each, drawn by `wb corpus tiers` from a recorded seed (feature 005, not yet drawn). |
| `workflowbench/tasks/tiers-manifest.yaml` | How the four sets were chosen: the difficulty measure, the cut points, the seed and every drawn task's score, tier, domain and hash (feature 005). |
| `specs/006-html-report/` | Feature 006: the round's official report as an HTML page with real tables, and `wb summary` across rounds; `contracts/report.md` holds every table, column and formula. Documents only so far; design of record `docs/superpowers/specs/2026-09-04-html-report-design.md`. |
| `monarch-benchmark/PLAN.md` | Methodology, variables, deliverables, tasks, decisions, open questions. |
| `monarch-benchmark/docs/HANDOFF-2026-09-03.md` | Resume-here note: repo move, feature 001, next steps. |
| `monarch-benchmark/docs/HANDOFF-2026-09-02.md` | Previous handoff: background and standing rules. |
| `monarch-benchmark/docs/ai-labs-context.html` | Onboarding dossier in plain language. |
| `monarch-benchmark/DESIGN.md`, `BUILD-SPEC.md`, `PROGRAM-SPEC.md` | Lucas's design of record. |
| `monarch-benchmark/workflowbench/` | The benchmark code (`wb` CLI). |
| `workflowbench/wb_orchestrator/cli.py` | The `wb` CLI (run, resume, status, doctor, grade, report, corpus). |
| `workflowbench/config/` | Benchmark inputs as YAML; a run is one product × one plan (`wb run --product X --plan Y`). See `config/README.md`. |
| `workflowbench/config/products/` | What is under test: app set, data, supported test modes (`simulated-apps`); plus what Monarch was taught (`*.monarch-kb.yaml`) and, for run-only, the known-correct recipe per task (`*.monarch-recipes.yaml`). |
| `workflowbench/config/models/` | One language model per file: provider, prices, API key name. |
| `workflowbench/config/harnesses/` | How a competitor is driven: API loop, CLI agent, scripted check, Monarch. |
| `workflowbench/config/plans/` | Task set, test mode, repetitions, competitors, baseline, audience, cost ceiling, `approved_by`. |
| `workflowbench/config/side-effects.yaml` | Reviewed per-service side-effect list used by `wb corpus declare`. |
| `workflowbench/wb_orchestrator/orchestrator.py` | Attempt state machine, config hash, resume. |
| `workflowbench/wb_orchestrator/declare.py` | Approval-rule derivation and the side-effect list. |
| `workflowbench/wb_arms/providers.py`, `api_loop.py` | Model catalog with prices; generic tool loop (OpenAI chat, OpenAI Responses, Gemini, Anthropic). |
| `workflowbench/wb_arms/monarch.py` | Monarch competitor (feature 002, in progress). |
| `workflowbench/wb_world/openapi.py`, `wb_arms/http_shim.py` | OpenAPI documents + HTTP front door for Monarch. |
| `workflowbench/wb_report/audiences.yaml` | Which competitors may appear in which report. |
| `workflowbench/tasks/`, `workflowbench/corpus/` | 10 pilot tasks (manual rules); 200-task corpus (derived rules). |
| `workflowbench/out/` | Run outputs and reports (gitignored where large). |
| `graphify-out/` | Knowledge graph (read before code questions; refresh after). |
| `.github/workflows/` | `ci.yml` (PRs to main or manual; free) and `smoke.yml` (manual; ~US$ 2). |
| `../monarch` | Sibling clone of Monarch; `feature-discovery/docs/public-api-seeds-runbook.md` for the OpenAPI path. |

## Key references

- **PLAN.md** — `monarch-benchmark/PLAN.md`. The single tracking surface.
- **Handoff** — `monarch-benchmark/docs/HANDOFF-2026-09-02.md`.
- **Smoke report** — `workflowbench/out/report-smoke-frontier-001-internal.md`.
- **Monarch authoring endpoint** — `POST /api/workflows/recipe/runs {goal}`,
  session auth; knowledge base via Feature Discovery's `api_spec` handler.
- **Slack** — `#benchmarks` is the destination for round summaries; Langfuse the backend behind it.

## Open questions in flight

- Repo visibility (private vs scrub) before the first push. (Carlos)
- Replace the pilot tasks' manual approval rules with the derived ones. (Lucas)
- Lucas's AutomationBench patches (`1.0.6+evalrepair.10`) are not upstream; get them from him.
- Service-account or API-key path for Monarch's authoring endpoint, or session login from the bench. (Deyton)
- Second product under test: real, mapped by Feature Discovery, legally clean. (Lucas + Carlos)
- Approval-rule gap found by the smoke (`simple.sf_opp_closed_won`: `is_closed`/`is_won`). Needs Lucas's sign-off.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
