# Research and implementation basis

Read 2026-09-11:
- https://www.anthropic.com/engineering/multi-agent-research-system — explicit
  delegated tasks, synthesis and citation work. Transfer the separation of roles;
  do not claim its published gains for Genesis.
- https://www.anthropic.com/engineering/building-effective-agents — use a bounded
  evaluator/optimizer loop where criteria and feedback are concrete.
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents — retain
  trajectories and combine deterministic checks with calibrated interpretation.

Local findings: analysis.py hardcodes a one-shot Gemini route; empty findings and
omitted attempts pass. Genesis record_analysis writes a separate store that the
report never reads. The report tool removes narrative. Round reports have no
authored narrative. The run projection drops attempt analysis; the renderer drops
limitations. A fixed checker bucket chart cannot establish behavioral causes.

Additional writing/figure sources read 2026-09-11:
- https://github.com/blader/humanizer (SKILL.md, version 3.0.0): adapt concrete
  subjects, removal of vague authority and inflated significance, and an
  editorial pass that preserves facts and uncertainty. No global skill installed.
- https://service-manual.ons.gov.uk/content/writing-for-users/writing-main-points-and-analysis:
  organize result and supporting analysis for the reader's decision.
- https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-charts/
  and its publishing-charts guidance: shared scales, labels, accessible tables,
  denominators and readable sources.

Implementation review added fresh analysis batches, exact completion-bounded
repetition traces, frozen snapshot access, lossless long-event paging, native
startup-cost preflight and restart-only reconciliation. These close concrete
usability/recovery gaps; they do not establish live semantic quality.
