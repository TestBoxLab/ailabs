# Cumulative research

Working status: https://trello.com/b/ntJfbkLx/ai-labs-research-experiments
Scientific direction: ../docs/AI-LABS-DIRECTION.md

Append source discoveries and queries to search-log.jsonl. Use stable source
URLs/DOIs and distinguish discovered, abstract-read, full-text-read and verified.
Record date, query, motivation, source identity, access status and next question.
Do not label a paper deeply read because a search snippet was returned.

Use experiments.jsonl as the append-only experiment index, with a stable id,
mechanism, affected failure class, parent ids, development/evaluation split,
control, treatment, preregistration path, status, Trello URL, run ids, cost and
decision. Start with hypotheses, never invent completed experiments.

Each experiment gets a directory with preregistration.md, analysis.md and evidence
links. Use EXPERIMENT-TEMPLATE.md. Analysis labels exploratory versus confirmatory
findings, and cites exact trace/check IDs. Store favorable, unfavorable and
inconclusive outcomes. Read previous entries before proposing work.

The source ledger contains initial reading records; the experiment ledger is empty. These are scaffolding, not imported historical evidence.
Historical context remains in ApplicationBench and must be indexed with lineage
before claiming a proposal is new.

Weekly outputs go in digests/YYYY-MM-DD.md with source/access records, a synthesis
matrix update, contradictions, relevance to observed Monarch behavior and at most
three proposed next investigations. Report unknowns plainly and keep the task
update under 140 words.

Weekly research is scheduled for Mondays at 09:00 America/Sao_Paulo in the current Codex task. Automation id: ai-labs-weekly-research. The computer and app must be running for local access; the first scheduled execution has not yet been observed. Mapping: trello.json. Paid execution remains gated on the foundation prerequisites.


Budget implementation: `wb_orchestrator/budget.py`; local unversioned ledger:
`research/budget.sqlite3`. Inspect it with `uv run --frozen wb budget status`
from `monarch-benchmark/workflowbench`. Reservations/claims/settlement are tested,
but provider dispatch and actual billing reconciliation remain disabled. Weekly
capacity liabilities are conservative across settlement delays and are not
provider invoice totals. Do not release an unknown-cost hold merely because an
attempt crashed or the week changed.

Current engineering evidence: ../specs/007-lab-foundation/implementation.md.
Dependency candidate validation is engineering validation, not a measured model
improvement or a completed scientific hypothesis experiment.
