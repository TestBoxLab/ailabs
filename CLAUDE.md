# AI Labs — Project Instructions

Read [AGENTS.md](AGENTS.md) first. This entire file is shared repository context
for Claude Code and Codex; the entry point links here deliberately. Current human
decisions recorded there supersede older assumptions in this file and skills.
The [harness-independent procedures](docs/HARNESS-PROCEDURES.md) preserve the
eleven local Claude skills' method when their commands are unavailable.

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
one report, with no internal/public division; config hash per run; API-key billing only.

**Where things stand (2026-09-03, evening):** repo at
`C:\Users\cgmat\Desktop\TestBox\ailabs` (off OneDrive; moved twice on 3 Sep, see
`monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md` §10). `main` pushed to `origin` on 3 Sep;
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
telemetry PR. See `monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md`. Feature 004
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

Claude Code loads the user's global `~/.claude/CLAUDE.md` automatically. Codex
uses its own global instructions; repository method and governance must not
depend on a private harness-specific global file.

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

- **A human approves paid rounds (decision D5, 8 Sep 2026; approver widened by
  Carlos, 9 Sep 2026).** Either Carlos or Lucas may approve; a launch by the
  approver runs at once, any other launch creates an approval request
  (`wb approvals`) and waits for `wb approve <id>`, then runs with
  `wb run ... --request <id>`. Smoke scale (at most 20 attempts per competitor)
  and `wb doctor` need no record. Every paid launch names its operator
  (`WB_OPERATOR`). Before any `wb run`, state the number of attempts and a cost band.
  An agent never approves its own round: the name on the approval is the person
  who asked for it.
- **The weekly ledger is the spending gate.** US$ 300 per calendar week
  (`research/budget.sqlite3`, Monday 00:00 America/Sao_Paulo): every paid
  request is reserved for its maximum before it is sent and settled from the
  receipt; a round the week cannot cover is refused with the shortfall; an
  attempt stops at `attempt_cap_usd` (US$ 3.00 unless the plan says otherwise);
  `wb budget status` shows what is left, `wb budget reconcile` checks a week
  against the providers' own usage exports. Monarch and Claude Code
  competitors stay refused until milestones M5 and M7.
- **Pre-registration and upstream integrity.** Carlos's final 10 September
  decision supersedes the earlier repair authorization: preserve AutomationBench's
  world, routes, seeds, task requests, initial data and assertions unchanged.
  This includes the ignored Airtable filter and weak invoice assertion. Only
  WorkflowBench's own approval-rule translation may be corrected, with a
  reproduction against the unchanged simulator. Preserve prior rules and record
  old/new hashes and evidence in `monarch-benchmark/docs/rounds/`; old rows are
  non-regradable against replacement hashes. Exclude a bad task with a recorded
  reason or report it upstream; never silently edit it. Adoption of
  `1.0.6+evalrepair.10` remains suspended, with the question pending Lucas.
  Changes of methodology still require explicit human approval.
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
  Always `uv run`, never bare Python. On Windows run the full suite detached
  with logs and wait for its exit; it takes about 27 minutes. Verify UI changes
  with browser tooling. `wb` loads `.env` itself: `wb run` is never a free check.
  Keys in `workflowbench/.env` (gitignored). AutomationBench vendored at
  `workflowbench/vendor/automation-bench` (gitignored; re-clone if missing).

## What lives where

In this table and the references below, `workflowbench/` abbreviates
`monarch-benchmark/workflowbench/`; `specs/` and `docs/` otherwise start at the
repository root unless a full prefix is given. Historical feature statuses and
model examples are context; verify current status in `STATE-OF-THE-PROGRAM.md`
and actual configuration rather than treating those examples as runtime pins.

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
| `workflowbench/tasks/tier-simple/`, `tier-medium/`, `tier-complex/`, `random-10/` | The four frozen task sets, ten prompts each, drawn by `wb corpus tiers` with seed 20260904 on 4 Sep 2026; approval rules re-derived 6 Sep and again 9–10 Sep, so 23 of the 40 hashes moved. Round sheet: `monarch-benchmark/docs/rounds/tier-rounds.md`. |
| `workflowbench/tasks/achievable-50/` | The 50-task gauntlet set (ApplicationBench `achievable50` slate), frozen 8 Sep 2026 on corpus revision `1.0.6+evalrepair.10`. |
| `workflowbench/tasks/tiers-manifest.yaml` | How the four sets were chosen: the difficulty measure, the cut points, the seed and every drawn task's score, tier, domain and hash (feature 005). |
| `specs/006-html-report/` | Feature 006: the round's official report as an HTML page with real tables, and `wb summary` across rounds; `contracts/report.md` holds every table, column and formula. Documents only so far; design of record `docs/superpowers/specs/2026-09-04-html-report-design.md`. |
| `monarch-benchmark/PLAN.md` | Methodology, variables, deliverables, tasks, decisions, open questions. |
| `monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md` | Resume-here note: where things stand, what is blocked, what is next. Replaces the three handoffs of 2, 3 and 8 Sep. |
| `monarch-benchmark/docs/HOW-WORKFLOWBENCH-WORKS.md` | The guide to the machine: what an attempt is, the two judges, how a round reads. |
| `monarch-benchmark/docs/BOUNDARY-BENCH-AND-MONARCH.md` | Who describes what data, where the mock is the truth, what each side asks of the other (settled 9 Sep 2026). |
| `docs/AI-LABS-UNBLOCK-PLAN-2026-09-08.md` (repo root) | The milestone plan M0–M8 to the 50-task gauntlet; decisions D1–D11. |
| `monarch-benchmark/docs/ai-labs-context.html` | Onboarding dossier in plain language. |
| `monarch-benchmark/DESIGN.md`, `BUILD-SPEC.md`, `PROGRAM-SPEC.md` | Lucas's design of record. |
| `monarch-benchmark/workflowbench/` | The benchmark code (`wb` CLI). |
| `workflowbench/wb_orchestrator/cli.py` | The `wb` CLI (run, resume, status, doctor, grade, report, corpus — including `corpus import-ab --domains all` and `corpus tiers --seed N`, feature 005, and `corpus slate --ids FILE --out DIR --because TEXT`, which freezes a task set listed by id with its manifest, unblock plan M2; logic in `wb_orchestrator/slate.py`). |
| `workflowbench/config/` | Benchmark inputs as YAML; a run is one product × one plan (`wb run --product X --plan Y`). See `config/README.md`. |
| `workflowbench/config/products/` | What is under test: app set, data, supported test modes (`simulated-apps`); plus what Monarch was taught (`*.monarch-kb.yaml`) and, for run-only, the known-correct recipe per task (`*.monarch-recipes.yaml`). |
| `workflowbench/config/models/` | One language model per file: provider, prices, API key name. |
| `workflowbench/config/harnesses/` | How a competitor is driven: API loop, CLI agent, scripted check, Monarch. |
| `workflowbench/config/plans/` | Task set, test mode, repetitions, competitors, baseline, cost ceiling, `approved_by`. |
| `workflowbench/config/side-effects.yaml` | Reviewed per-service side-effect list used by `wb corpus declare`. |
| `workflowbench/wb_orchestrator/orchestrator.py` | Attempt state machine, config hash, resume. |
| `workflowbench/wb_orchestrator/declare.py` | Approval-rule derivation and the side-effect list. |
| `workflowbench/wb_arms/providers.py`, `api_loop.py` | Model catalog with prices; generic tool loop (OpenAI chat, OpenAI Responses, Gemini, Anthropic). |
| `workflowbench/wb_arms/monarch.py` | Monarch competitor (feature 002): create + run through Monarch's API; `observer` hook and the engine run stream feed the Studio's live view (feature 011). |
| `workflowbench/wb_studio/enterprise.py` | Stock Monarch Enterprise as a Studio comparison version: verification probe, readiness, frozen runtime manifest, the attempt arm that streams builder frames and recipe nodes and reserves its ceiling in the weekly ledger (feature 011, `specs/011-monarch-runtime-integration/checkpoint-3.md`). |
| `workflowbench/wb_studio/static/tokens.css`, `ui.css`, `report.css`, `charts.css` | The Studio's design system (redesigned 9 Sep night, design of record `docs/AI-LABS-STUDIO-DESIGN-SYSTEM-2026-09-09.md`): a Swiss technical manual. Paper and ink, one signal red for the current place, IBM Plex Sans for sentences, Newsreader (vendored, OFL) for report prose, IBM Plex Mono for values, rules instead of boxes, booktabs tables, a label column, numbered report sections; meaning colours (green passed, red failed) and one hue per model family only in results and figures. Component CSS uses tokens only; the CSS test in `tests/test_static_csp.py` fails on any hex colour, `!important`, inline style or external resource. |
| `workflowbench/wb_studio/static/vendor/` | Vendored Radix Colors, IBM Plex (woff2) and the Lucide icon sprite; licences in `THIRD_PARTY_LICENSES.md` at the repo root. |
| `docs/AI-LABS-DESIGN-AUDIT-2026-09-10.md` | The interaction audit of 10 Sep: every feature compared with named products, what was built the same day, what stays open (a free test on one task, the lanes graph, an attempt as a page, the editor at phone width). Read it before touching a view. |
| `workflowbench/wb_studio/usage.py` | Usage by model from stored results, and `ledger_lines`: the week's reservations as a person audits them (who, what, ceiling, settled, state) behind the read-only `GET /api/budget/ledger`; the Budget page shows it first (pass 7, 10 Sep). Genesis routes added the same day: `POST /api/genesis/cards/<id>/decline`, `POST /api/genesis/cards/<id>/work` (a person works a queued card now, under the watcher's allowances) and `POST /api/genesis/turns/<id>/stop`; feature 022 lane B added threads (`GET /api/genesis/threads`, `/threads/<id>`; `chat` takes `thread`) and `GET /api/genesis/cards/<id>/history`. |
| `workflowbench/wb_studio/measures.py`, `static/charts.js` | Measures computed once on the server from stored results and events (pass rate with Wilson interval, pass^k, objective share, violations, false completion, overlap, turns, paired delta, cost) and the chart kit that draws them as SVG styled by CSS classes. |
| `workflowbench/wb_studio/narrative.py` | The story of an attempt, written from the record by fixed rules (10 Sep): a turn-by-turn timeline with the provider's reasoning summary, what went right and wrong with the events each fact rests on, the turning point (earliest recorded step after which the outcome could not change), and one failure mode from a fixed list of nine; `run_story` says how each setup failed and which tasks every setup failed the same way (suspect the task first). Shown on the attempt sheet as What happened and in the run report as What went right and wrong; the paid Model reading follows the same shape. |
| `workflowbench/wb_studio/report_data.py`, `caveats.py`, `static/reports.js` | Reports, the Studio's front door: run and round reports that read verdict first, Standings in the round report, caveats written from data only, one report with no internal/public division (11 Sep 2026), print and single-file HTML export which refuse while a lab build is on the page. The narrative is written automatically for every finished run and reserved in the weekly ledger (`schedule_narrative` in `wb_studio/app.py`). |
| `workflowbench/wb_studio/live_graph.py` | The live Product Graph Monarch Enterprise uses, read from the Feature Discovery service (`fd_url` of the Monarch harness, `x-fd-api-key` gate) over GET only and cached for a minute; the Studio's Graph view in the product graph panel shows it, or any bench version, as products with their stored business actions. Nothing here can write to Monarch. |
| `workflowbench/wb_studio/scheduler.py` | Daily jobs for the owning Studio process: a module offers `DAILY = (name, hour, fn)`, the scheduler runs it once a day after its hour on the São Paulo clock and stamps it; `GET /api/genesis/schedule`, `POST /api/genesis/schedule/<name>/run`. |
| `workflowbench/wb_studio/code_index.py` | Genesis's code awareness (feature 019): a daily index of the Monarch checkout named by `MONARCH_REPO` (else `../monarch`) at the ref of the declared build, a change record since the previous commit filed in the library, Graphify when installed, a `MONARCH.md` of at most 2,500 characters written by code, and read-only tools `code_status`, `code_search`, `code_explain`, `code_read`, `code_changes` (internal-only facts). `wb genesis index` runs it by hand. |
| `workflowbench/wb_studio/memory.py`, `genesis_sleep.py` | Genesis's three-tier memory (feature 019): `SOUL.md`, the identity file (feature 020: voice, priorities, what Genesis never does; a starter text on first start, edited only by a person from the Memory tab, 2,500 characters, the first block of every prompt, no Genesis tool reaches it), `LAB.md` (2,500 characters, Pinned, Known, Recent, every entry tagged `[rec:kind:id]`), `MONARCH.md` from the code index, notes per card (4,000), an FTS5 record over turns, analyses, cards and sources; injection scan, seven-day probation, thirty-day decay, pinned entries never decay; the nightly job writes the Daily brief card and, when a model route and the ledger allow, one consolidation turn under `STUDIO_GENESIS_NIGHT_USD` (0.50). |
| `workflowbench/wb_studio/genesis_autonomy.py` | Genesis autonomy (feature 021): three dials (reading always on; cards act or off; runs smoke scale by itself, propose only, or off) and the Pause switch in `genesis/autonomy.json`, `may_launch` with the plain reason, `plan_lines` computed by the Studio, and the activity record `genesis/activity.jsonl`; in `genesis.py`, `propose_experiment` (a smoke plan within the allowances launches by itself, anything else waits in Approval), `ask_question` and `answer_question` (question cards in Your review with a suggested default; the blocked card resumes on the answer); routes `/api/genesis/autonomy`, `/api/genesis/activity`, `/api/genesis/cards/<id>/answer`; `genesis_skills.py` holds the procedures Genesis writes for itself (twelve at most, injected by card kind, `/api/genesis/skills`); a finished run that Genesis planned re-queues its card for the verdict (the debrief); the nightly brief is a fact list. Design of record `docs/superpowers/specs/2026-09-09-genesis-autonomy-reports-journeys-design.md`. |
| `workflowbench/wb_studio/genesis_access.py` | Feature 022, lane B: the people of the lab and their keys (`genesis/people.json`, sha256 of each key, member or admin), Genesis's weekly envelope, the brief hour and the digest day. A person's key travels as `X-Person-Key` beside the Studio token and names them (`by: human:<name>`) on every write; before anyone is listed the token alone opens writes. The configuration page under Settings › Genesis (`renderGenesisConfig` in `static/genesis.js`) and the digest page `#genesis/digest` read from it. |
| `workflowbench/wb_studio/genesis_config.py`, `genesis_plugins.py` | Feature 022 (design of record `docs/superpowers/specs/2026-09-10-genesis-team-scientist-design.md`): the model each step of Genesis's work uses (`genesis/config.json`, cheapest available route by default, `GET/POST /api/genesis/config`), and the seam through which new modules add tools, protocol text, prompt blocks, turn hooks and launch gates without editing the shared files. Review and patch default to the strongest keyed route, the rest to the cheapest (10 Sep). |
| `workflowbench/wb_studio/genesis_harness.py`, `genesis_schemas.py` | The Genesis loop (deep dive of 10 Sep 2026, `docs/AI-LABS-GENESIS-DEEP-DIVE-2026-09-10.md`): a turn is an in-process loop over the benchmark's four provider adapters (`wb_arms/api_loop.py`), one typed tool per lab action, SOUL.md first then the protocol as the system prompt, one ledger reservation per request at an output cap the turn can still pay, tool refusals returned as sentences, tool results and reasoning kept in the turn record, a landing two requests before the cap of 24, and a turn that runs out saves its last text to the card's notes. The Codex subprocess, its loopback broker and the MCP bridge are gone. |
| `workflowbench/wb_studio/static/genesis.js`, `genesis.css` | Genesis as a colleague (feature 022, lane B, 10 Sep): chat first in three columns, routes `#genesis`, `#genesis/t/<thread>`, `#genesis/board`, `/library`, `/memory`, `/activity`; the tracking pane (Cards, Sources, Trace); the card as a document; live tool steps from the turn's events. Lane briefs and receipts under `.tmp/genesis-lane-*.md`. |
| `workflowbench/wb_studio/genesis_watcher.py` | Cards as inputs (feature 019): `Genesis.drop` turns a link, a run id or a sentence into a card with a question; the watcher works queued cards one at a time under `STUDIO_GENESIS_CARD_USD` (2.00) per card and `STUDIO_GENESIS_DAILY_USD` (6.00) per day, only for runs and sources that arrive after it first ran, never launching anything; pause, stop and status routes under `/api/genesis/watcher`. |
| `workflowbench/wb_studio/genesis_engineer.py` | The daily engineer loop (feature 023, design of record `docs/superpowers/specs/2026-09-11-genesis-engineer-loop-design.md`): at 08:00 São Paulo it reads the runs it has not settled, computes their failure buckets for free, and asks Genesis for one typed spec on the worst bucket that points at code. A Codex agent implements the spec in a throwaway git worktree; **the Studio runs the verify command itself** (an allowlist, never a string a model chose) and files a `fix` (lab) or `patch` (monarch) card with the diff, the test result and the cost. Nothing is applied, merged or pushed. Money: `STUDIO_GENESIS_ENGINEER_USD` (3.00) for the spec turn, `STUDIO_GENESIS_CODEX_USD` (1.00) reserved before the agent starts and settled from its reported token usage — usage that cannot be read leaves the ceiling held. The `engineer` dial starts **off**. |
| `workflowbench/wb_studio/genesis_critic.py`, `rubrics/` | The weekly adversary (feature 023): on the lab's digest day a *different* model than the one that writes reviews what the lab publishes. It sees the rendered pages (`tests/browser/shot.cjs` — a full page, a crop, and a measured layout record: overflow, clipping, smallest text, WCAG contrast, tables, heading order), the newest run's report data, and the Studio's own source. It judges against rubric files a person edits — `prose.md` (Wikipedia's *Signs of AI writing*), `figures.md` (the design system as rules), `accuracy.md` (`PLAN.md` §1) — and may only cite a line id that exists in them. Output: one enhancement card per finding, six at most, with at most one carrying a Codex-written diff. The numeric rules are decided by the browser, not by the critic. |
| `workflowbench/wb_studio/figures.py` | Figures Genesis can put in a card (feature 023): it names a kind and a run, and nothing else. The Studio computes the figure from `report_data.run_report` — the same numbers the report shows — and `static/charts.js` draws it in the design system's own classes; a forged `chart`, `options` or `source` in the payload is dropped. Kinds: `pass_rate`, `failures`, `cost_against_pass_rate`, `tasks`, read from `figures.KINDS` so the tool's schema enum never drifts. `[figure:<id>]` in a card body is where it is drawn (`drawFigures` in `static/genesis.js`), and every figure carries its source line (rubric F6). Read-only over `GET /api/genesis/figures/<id>`. |
| `workflowbench/wb_studio/library.py` | Genesis research library: sources with publication and discovery dates, Saved or Analyzed only, one fixed topic list (`TOPICS`, keyword classification with Other as the fallback; Genesis or a person can reclassify), "Used in" as version metadata, import from `research/search-log.jsonl`; the hypothesis record (green, white, red) with its written rules. |
| `workflowbench/tests/browser/` | The browser suite: `node tests/browser/suite.cjs` starts the offline fixture Studio (`server.py`, three recorded runs by the scripted checks) and checks every view in both themes; `snapshots/` holds the screenshots for review, not for pixel diffing. `shot.cjs` is separate and single-purpose: one view, a full-page PNG, a crop and a measured layout record, for the weekly critic — it must never write into `snapshots/`. |
| `docs/AI-LABS-IMPLEMENTATION-PLAN-2026-09-09.md` | The Studio plan of 9 Sep: seven phases mapped to features 012 to 018, the design-system choice, and the decisions assumed. The design direction and the benchmark landscape research sit beside it under `docs/`. |
| `workflowbench/wb_world/openapi.py`, `wb_arms/http_shim.py` | OpenAPI documents + HTTP front door for Monarch. |
| `workflowbench/tasks/`, `workflowbench/corpus/` | 10 pilot tasks (manual rules); 200-task corpus (derived rules). |
| `workflowbench/deferred.md` | Deferred items of the bench: the sandbox for competitor harnesses (future), `wb doctor --record`, and smaller items carried from features 002 to 006. |
| `workflowbench/out/` | Run outputs and reports (gitignored where large). |
| `graphify-out/` | Knowledge graph (read before code questions; refresh after). |
| `.github/workflows/` | `ci.yml` (PRs to main or manual; free) and `smoke.yml` (manual; ~US$ 2). |
| `../monarch` | Sibling clone of Monarch; `feature-discovery/docs/public-api-seeds-runbook.md` for the OpenAPI path. |

## Key references

- **PLAN.md** — `monarch-benchmark/PLAN.md`. The single tracking surface.
- **State of the program** — `monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md`.
- **Smoke report** — `workflowbench/out/report-smoke-frontier-001-internal.md` (written before 11 Sep 2026, when reports carried the audience in the filename; `wb report` now writes `report-<run_id>.md`).
- **Monarch authoring endpoint** — `POST /api/workflows/recipe/runs {goal}`,
  session auth; knowledge base via Feature Discovery's `api_spec` handler.
- **Slack** — `#benchmarks` is the destination for round summaries; Langfuse the backend behind it.

## Open questions in flight

- Publication and pushes still require Carlos's explicit request; the repo is public.
- Replace the pilot tasks' manual approval rules with the derived ones. (Lucas)
- Adoption of the alternative AutomationBench dataset `1.0.6+evalrepair.10` is
  suspended by Carlos's final 10 September decision, with the question pending
  Lucas. Preserve its historical records; do not resume source acquisition or
  replacement without a new explicit decision.
- Service-account or API-key path for Monarch's authoring endpoint, or session login from the bench. (Deyton)
- Second product under test: real, mapped by Feature Discovery, legally clean. (Lucas + Carlos)
- Approval-rule gaps require simulator evidence and a recorded refreeze; the
  authorized corrections are limited to WorkflowBench's own rule translation,
  keeping AutomationBench's world, routes, seeds and assertions unchanged.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files, refresh the graph through the installed Graphify
  skill using its `uv`-managed environment; do not invoke bare `python3` or
  silently claim a refresh if Graphify is unavailable.
