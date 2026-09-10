# Feature 007: trustworthy experiments and evidence-driven reports

Status: partially implemented; offline foundation increment, paid execution blocked. See implementation.md. Direction: ../../docs/AI-LABS-DIRECTION.md.

## Acceptance criteria

1. A clean checkout reproduces an identified offline baseline. The dependency
   revision, patches and environment are explicit; no silent upstream updates.
2. Native Claude Code and Codex adapters execute in isolated environments.
   Adversarial checks prove agents cannot read task answers, grader code,
   snapshots, another attempt's data, or unrelated provider credentials.
3. Two first-class tracks: one-off agentic requests and create-plus-run.
   Results and user-assistance policies cannot be silently mixed.
4. Every attempt persists an ordered event stream, workflow artifacts,
   snapshots, check results, usage and a manifest with hashes and availability.
   Reports explicitly disclose missing or truncated events.
5. Budget reservations across simultaneous experiments enforce USD 300/week
   before dispatch. Retries, analysis, interrupted and unknown-cost work remain
   accounted for. Resuming and restarting cannot reset spend.
6. Scientific records retain hypothesis identity, predecessor relationships,
   controls, splits, pre-registration, actual runs and decisions. A duplicate
   check finds exact repeats and prompts semantic review of related mechanisms.
7. Difficulty classification has versioned, outcome-independent rationale,
   reviewed examples and domain coverage. Existing task sets remain frozen.
8. Reports provide overview → task comparison → exact events and state changes.
   Numbers reconcile with stored records; uncertainty and denominators are visible.
   Analysis covers both wins and losses and distinguishes facts from hypotheses.
9. Weekly research uses prior query/source history and the experiment ledger,
   creates a synthesis update and a concise actionable readout, and updates Trello.
   Repeated investigations require a reason. Negative findings remain retrievable.
10. Budget, trace and grading integrity failures block claims of measured
    improvement. Paid evaluation is enabled only after the foundation is verified.

## Open decisions

- Workflow clarification: bounded scripted answers versus unattended behavior.
  Compare as separate policies before declaring a standard.
- Current Monarch stock release and its one-off agent API need inspection.
- Additional model-family harnesses require capability verification.
- Shared hosting, report UI implementation and engineering promotion remain
  implementation choices to resolve against the actual product repositories.

## Non-goals for the first release

Public leaderboard; migrating every historical run into one comparable suite;
execution-only results as the main comparison; arbitrary LLM grading as truth;
an automatic claim that a single winning run is a product improvement.
