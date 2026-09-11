# Implementation Plan: Genesis report authoring

Python 3.13 through uv, stdlib JSON persistence, existing Genesis provider loop,
pytest and Studio browser fixtures. No new dependencies. Local edits preserve
the many unrelated changes already present in this shared checkout.

Use a dedicated genesis_reports plugin for evidence packets, persisted stages,
analysis per attempt, draft submission, separate review and internal publication.
Preallocate bounded Genesis turn reservations before dispatch; pass an internal
reservation flag to chat, never a model-controlled payload flag. Allow report
turns only scoped report tools. The plugin installs procedural prompt blocks and
handles completion idempotently. Finish unused reservations after completion or
failure, retain drafts and never replay an interrupted paid turn automatically.

Report projections prefer a reviewed publication, retain historical one-shot
analyses with their original provenance, expose working status and round links.
The run scheduler and explicit analyze action start the new workflow. Keep the
old analysis reader available for historical API consumers.

Add code-owned outcome slices in a separate report_patterns module, integrated
into run and round projections. Update reports.js using existing table, chart,
typography and evidence controls; no design-system changes.

Constitution: inputs/graders/world unchanged; evidence preserved; no paid round,
push, deployment or external publication. Tests first, independent implementation
of chart/projection work and final review, then relevant offline/browser checks.

Research: Anthropic's evaluator-optimizer and multi-agent research descriptions
support distinct work assignments, feedback and citations. These are engineering
patterns, not proof of improved Genesis report quality. Existing one-shot analysis
is a historical baseline for future blinded editorial comparison.

Final local implementation and validation: see validation.md. Native analysis
uses bounded fresh contexts, upfront startup-cost admission and startup-only
reconciliation. Both actor and reviewer receive versioned editorial/figure
guidance inspired by Humanizer and public statistical-writing guidance.
