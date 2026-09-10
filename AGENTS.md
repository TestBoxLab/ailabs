# AI Labs working agreement

This is the entry point for every harness. Read these repository instructions
in order; following the links is required, not optional background:

1. [Current direction](docs/AI-LABS-DIRECTION.md). Lucas's September 7 decisions
   supersede conflicting historical assumptions.
2. [How WorkflowBench works](monarch-benchmark/docs/HOW-WORKFLOWBENCH-WORKS.md).
3. [State of the program](monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md),
   sections 12–13 for the September 9–10 investigation and final decisions.
4. [Bench/Monarch boundary](monarch-benchmark/docs/BOUNDARY-BENCH-AND-MONARCH.md).
5. [Shared project instructions](CLAUDE.md), **the entire file**: project facts,
   methodology, glossary, workflow, benchmark rules, file map and references
   apply to Codex as well as Claude. Its name does not limit its authority.
6. [Constitution](.specify/memory/constitution.md), governing every feature, and
   [harness-independent procedures](docs/HARNESS-PROCEDURES.md), the executable
   prose equivalent of all eleven local Claude skills.

Current explicit human decisions take precedence over historical documents and
skill defaults. Carlos's final September 10 decision supersedes the earlier
repair authorization: **AutomationBench's world, routes, seeds, task requests,
initial data and assertions are immutable**, including the ignored Airtable
filter and weak invoice assertion. Only WorkflowBench's own approval-rule
translation may be corrected. Reproduce that defect against the unchanged
simulator, preserve prior rules, and record old/new hashes and evidence in
`monarch-benchmark/docs/rounds/`; old rows must not be regraded against new hashes.
Bad tasks may be excluded with a recorded reason or reported upstream; never
silently edit them. Adoption of `1.0.6+evalrepair.10` remains suspended, with the
question pending Lucas; do not resume source acquisition or replacement without
a new explicit decision. This does not authorize a different methodology.

## Working agreement

- Two separate evaluations: one-off agentic requests; workflow creation plus execution.
- Native harnesses: Claude Code for Claude, Codex for GPT, verified suitable
  harnesses for other families. Raw API loops are separate controls.
- Comparable task briefs, business constraints and application access; preserve
  native harness behavior and record every version and non-default setting.
- No grader, expected answer, snapshot, other competitor trace or host secret
  may be accessible to an evaluated agent.
- Preserve observable trajectories and final world state. Distinguish observed
  facts, grader verdicts, causal hypotheses and experimentally supported findings.
- Lucas authorizes autonomous experiments within USD 300 weekly, subject to
  the paid-round approval rules below.
  Operating default: calendar week starting Monday 00:00 America/Sao_Paulo,
  no rollover. Reserve maximum spend before launch;
  count retries and paid analysis. The existing per-run ceiling does not enforce
  this shared limit. Paid launches wait until reservations and billing are verified.
- Search prior research and experiment records. Avoid accidental duplicates;
  deliberate replication and combinations require a stated purpose and parent links.
- Trello tracks status; repository records hold versioned scientific evidence.
- Conversation with Carlos in Brazilian Portuguese; every repository file,
  including comments and commit messages, in English. Use the plain names from
  `CLAUDE.md`. Short updates under 140 words, business outcomes first.
  Reports use readable charts and exact evidence drilldowns.
- Local setup, implementation, Trello and the research loop are authorized.
  Do not infer permission to post to Slack, publish results, push this repository
  or merge experimental changes into Monarch.
- Preserve frozen task sets, run configurations and historical results while
  preparing replacements. Run relevant offline checks. Do not equate a written
  design with working implementation.

## Before a round

- Work in `monarch-benchmark/workflowbench/`, Python 3.13 through `uv run`.
  `.env` is gitignored and loaded by `wb`; never print secret values.
- Read `monarch-benchmark/PLAN.md` section 1.1 and the resolved product, plan,
  competitors, task hashes and world revision. Same request for each competitor;
  nothing grades itself; pass requires the expected result, no unrequested
  change and normal finish; complete cost, API-key billing and version pins.
- Follow [round preparation](docs/HARNESS-PROCEDURES.md#prepare-and-run-a-round).
  **Before any `wb run`, state attempts (including retry scope) and a cost band.**
  `wb run` is paid execution, never a free validation command.
- Either Carlos or Lucas approves paid rounds. Attribute `WB_OPERATOR` and any
  approval record to the person who requested the round; an agent never approves
  its own round. Smoke scale (at most 20 attempts per competitor, retries
  included) needs no approval record. Above that, use the human approval flow
  (`wb approvals`, `wb approve`, `wb run ... --request`) when required; a plan's
  `approved_by` alone approves nothing. Existing explicit authorization suffices.
- Check `uv run wb budget status`, verified reservations and billing before
  paid launch. The ledger is `research/budget.sqlite3` at the repository root;
  retain unknown costs and count retries and paid analysis. Never bypass a
  spending, verification, revision, knowledge-base or front-door refusal.
- For Monarch, verify the deployed build, unchanged catalogue and live front
  door with `uv run wb monarch verify`. A CLI round needs ngrok forwarding to
  `127.0.0.1:9105`; the hosted Studio relays through `STUDIO_FRONT_DOOR_TARGET`.
  Use the [deployment runbook](monarch-benchmark/docs/rounds/2026-09-10-fdapi-deploy-runbook.md),
  checking changed-service ownership before deployment. `railway up` uploads
  the working tree; inspect uncommitted edits. Catalogue baseline: 47 products,
  686 actions, 47 in sync. A knowledge-base re-import moves dependent config hashes.
- Validate corrections with failing-then-passing simulator tests. Run relevant
  offline checks; the full `uv run python -m pytest tests -q` takes about 27
  minutes on Windows, so launch it detached with logs and wait for its exit.
  Verify UI changes with browser tooling before completion.
- Retain trajectories, final snapshots, terminations and billing; grade and
  report from stored evidence with source lines. Inspect every failed attempt.
  Do not infer a successful write from `completed` or final prose alone.
