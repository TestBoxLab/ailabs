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
`specs/004-monarch-run-only/`, documents only, no code yet. Feature 005 (task
sets by difficulty tier: the six scored AutomationBench domains imported into
the corpus, an objective difficulty score, four frozen ten-task sets — simple,
medium, complex, random — drawn by `wb corpus tiers`) has spec, plan and tasks
on 4 Sep — `specs/005-task-tiers/`, documents only, no code yet.

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

- **Lucas approves paid rounds (decision D5, 8 Sep 2026).** A launch by Lucas
  runs at once; a launch by Carlos, or anyone else, creates an approval request
  (`wb approvals`) and waits for `wb approve <id>`, then runs with
  `wb run ... --request <id>`. Smoke scale (at most 20 attempts per competitor)
  and `wb doctor` need no record. Every paid launch names its operator
  (`WB_OPERATOR`). Before any `wb run`, state the number of attempts and a cost band.
- **The weekly ledger is the spending gate.** US$ 300 per calendar week
  (`research/budget.sqlite3`, Monday 00:00 America/Sao_Paulo): every paid
  request is reserved for its maximum before it is sent and settled from the
  receipt; a round the week cannot cover is refused with the shortfall; an
  attempt stops at `attempt_cap_usd` (US$ 3.00 unless the plan says otherwise);
  `wb budget status` shows what is left, `wb budget reconcile` checks a week
  against the providers' own usage exports. Monarch and Claude Code
  competitors stay refused until milestones M5 and M7.
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
| `.claude/skills/monarch-benchmark/` | Skill to prepare, confirm and run a round, and to create, edit and check every config file a round needs (`/monarch-benchmark [model\|harness\|product\|plan\|tasks\|check] ...`); `references/` holds one file per subcommand, `deferred.md` the deferred items. |
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
| `workflowbench/wb_orchestrator/cli.py` | The `wb` CLI (run, resume, status, doctor, grade, report, corpus — including `corpus import-ab --domains all` and `corpus tiers --seed N`, feature 005, and `corpus slate --ids FILE --out DIR --because TEXT`, which freezes a task set listed by id with its manifest, unblock plan M2; logic in `wb_orchestrator/slate.py`). |
| `workflowbench/config/` | Benchmark inputs as YAML; a run is one product × one plan (`wb run --product X --plan Y`). See `config/README.md`. |
| `workflowbench/config/products/` | What is under test: app set, data, supported test modes (`simulated-apps`); plus what Monarch was taught (`*.monarch-kb.yaml`) and, for run-only, the known-correct recipe per task (`*.monarch-recipes.yaml`). |
| `workflowbench/config/models/` | One language model per file: provider, prices, API key name. |
| `workflowbench/config/harnesses/` | How a competitor is driven: API loop, CLI agent, scripted check, Monarch. |
| `workflowbench/config/plans/` | Task set, test mode, repetitions, competitors, baseline, audience, cost ceiling, `approved_by`. |
| `workflowbench/config/side-effects.yaml` | Reviewed per-service side-effect list used by `wb corpus declare`. |
| `workflowbench/wb_orchestrator/orchestrator.py` | Attempt state machine, config hash, resume. |
| `workflowbench/wb_orchestrator/declare.py` | Approval-rule derivation and the side-effect list. |
| `workflowbench/wb_arms/providers.py`, `api_loop.py` | Model catalog with prices; generic tool loop (OpenAI chat, OpenAI Responses, Gemini, Anthropic). |
| `workflowbench/wb_arms/monarch.py` | Monarch competitor (feature 002): create + run through Monarch's API; `observer` hook and the engine run stream feed the Studio's live view (feature 011). |
| `workflowbench/wb_studio/enterprise.py` | Stock Monarch Enterprise as a Studio comparison version: verification probe, readiness, frozen runtime manifest, the attempt arm that streams builder frames and recipe nodes and reserves its ceiling in the weekly ledger (feature 011, `specs/011-monarch-runtime-integration/checkpoint-3.md`). |
| `workflowbench/wb_studio/static/tokens.css`, `ui.css`, `report.css`, `charts.css` | The Studio's design system (9 Sep): one token sheet over Radix Colors (sage neutral, green accent, a hue per model family), shared components, the report reading layer in Plex Serif, the chart styles. Component CSS uses tokens only; the CSS test in `tests/test_static_csp.py` fails on any hex colour, `!important`, inline style or external resource. |
| `workflowbench/wb_studio/static/vendor/` | Vendored Radix Colors, IBM Plex (woff2) and the Lucide icon sprite; licences in `THIRD_PARTY_LICENSES.md` at the repo root. |
| `workflowbench/wb_studio/measures.py`, `static/charts.js` | Measures computed once on the server from stored results and events (pass rate with Wilson interval, pass^k, objective share, violations, false completion, overlap, turns, paired delta, cost) and the chart kit that draws them as SVG styled by CSS classes. |
| `workflowbench/wb_studio/report_data.py`, `caveats.py`, `static/reports.js` | Reports, the Studio's front door: run and round reports that read verdict first, Standings in the round report, caveats written from data only, the public audience by default with an internal view for Carlos and Lucas, print and single-file HTML export. The narrative is written automatically for every finished run and reserved in the weekly ledger (`schedule_narrative` in `wb_studio/app.py`). |
| `workflowbench/wb_studio/live_graph.py` | The live Product Graph Monarch Enterprise uses, read from the Feature Discovery service (`fd_url` of the Monarch harness, `x-fd-api-key` gate) over GET only and cached for a minute; the Studio's Graph view in the product graph panel shows it, or any bench version, as products with their stored business actions. Nothing here can write to Monarch. |
| `workflowbench/wb_studio/scheduler.py` | Daily jobs for the owning Studio process: a module offers `DAILY = (name, hour, fn)`, the scheduler runs it once a day after its hour on the São Paulo clock and stamps it; `GET /api/genesis/schedule`, `POST /api/genesis/schedule/<name>/run`. |
| `workflowbench/wb_studio/code_index.py` | Genesis's code awareness (feature 019): a daily index of the Monarch checkout named by `MONARCH_REPO` (else `../monarch`) at the ref of the declared build, a change record since the previous commit filed in the library, Graphify when installed, a `MONARCH.md` of at most 2,500 characters written by code, and read-only tools `code_status`, `code_search`, `code_explain`, `code_read`, `code_changes` (internal-only facts). `wb genesis index` runs it by hand. |
| `workflowbench/wb_studio/memory.py`, `genesis_sleep.py` | Genesis's three-tier memory (feature 019): `SOUL.md`, the identity file (feature 020: voice, priorities, what Genesis never does; a starter text on first start, edited only by a person from the Memory tab, 2,500 characters, the first block of every prompt, no Genesis tool reaches it), `LAB.md` (2,500 characters, Pinned, Known, Recent, every entry tagged `[rec:kind:id]`), `MONARCH.md` from the code index, notes per card (4,000), an FTS5 record over turns, analyses, cards and sources; injection scan, seven-day probation, thirty-day decay, pinned entries never decay; the nightly job writes the Daily brief card and, when a model route and the ledger allow, one consolidation turn under `STUDIO_GENESIS_NIGHT_USD` (0.50). |
| `workflowbench/wb_studio/genesis_watcher.py` | Cards as inputs (feature 019): `Genesis.drop` turns a link, a run id or a sentence into a card with a question; the watcher works queued cards one at a time under `STUDIO_GENESIS_CARD_USD` (2.00) per card and `STUDIO_GENESIS_DAILY_USD` (6.00) per day, only for runs and sources that arrive after it first ran, never launching anything; pause, stop and status routes under `/api/genesis/watcher`. |
| `workflowbench/wb_studio/library.py` | Genesis research library: sources with publication and discovery dates, Saved or Analyzed only, one fixed topic list (`TOPICS`, keyword classification with Other as the fallback; Genesis or a person can reclassify), "Used in" as version metadata, import from `research/search-log.jsonl`; the hypothesis record (green, white, red) with its written rules. |
| `workflowbench/tests/browser/` | The browser suite: `node tests/browser/suite.cjs` starts the offline fixture Studio (`server.py`, three recorded runs by the scripted checks) and checks every view in both themes; `snapshots/` holds the screenshots for review, not for pixel diffing. |
| `docs/AI-LABS-IMPLEMENTATION-PLAN-2026-09-09.md` | The Studio plan of 9 Sep: seven phases mapped to features 012 to 018, the design-system choice, and the decisions assumed. The design direction and the benchmark landscape research sit beside it under `docs/`. |
| `workflowbench/wb_world/openapi.py`, `wb_arms/http_shim.py` | OpenAPI documents + HTTP front door for Monarch. |
| `workflowbench/wb_report/audiences.yaml` | Which competitors may appear in which report. |
| `workflowbench/tasks/`, `workflowbench/corpus/` | 10 pilot tasks (manual rules); 200-task corpus (derived rules). |
| `workflowbench/deferred.md` | Deferred items of the bench: the sandbox for competitor harnesses (future), `wb doctor --record`, and smaller items carried from features 002 to 006. |
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
