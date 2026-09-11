# Implementation plan: Live workflows and metrics

Date: 2026-09-11. Spec: [spec.md](spec.md).

## Summary
Extend the current Activity surface into a live comparison canvas with persistent
node lanes and exact outputs. Add a pure server-side performance projection to
both the job report and permanent report, then render updated charts as results
arrive. Preserve every existing unrelated working-tree change.

## Technical context
Python 3.13 through uv; vanilla JavaScript, CSS tokens and SVG. Existing durable
SSE journal and results store; no new dependencies. Pytest, Node assertions and
an offline Playwright fixture cover aggregation, stream behavior and layout.
Target: desktop and phone browser, light/dark, keyboard and reduced motion.

## Constitution check
Pass before and after design: fixed grading and upstream data stay unchanged;
no paid runs; original result rows stay immutable; tests precede implementation;
no publishing or deployment. Shared harness procedures replace unavailable
Superpowers. CLAUDE.md explicitly calls for task-scoped agents and review.
Graphify is not installed; code is the source of architecture truth.

## Structure and ownership
- wb_studio/performance.py and tests/test_studio_performance.py: pure metric
  projection with coverage, success/failure times, cost, tools and source rows.
- wb_studio/reports.py and report_data.py: additive performance report member.
- wb_studio/measures.py: missing durations remain unknown in existing timing.
- wb_studio/static/observatory.js and new observatory.css: persistent live UI,
  small SVG metrics and node lanes, streamed previews and evidence selection.
- wb_studio/static/app.js/index.html: only narrow live-report refresh/layout hooks.
- wb_studio/static/reports.js: performance section in permanent run reports.
- tests/browser/live-workflows.cjs: offline stream transitions and viewport checks.
- tests/browser/live-workflows-model.cjs: deterministic stream projection checks.

Paths above are relative to monarch-benchmark/workflowbench/.

## Motion thesis
Focal moment: an observed result lights its connection and resolves its node;
the corresponding recorded outcome adds to the shared chart. Continuity:
keyed nodes, preserved focus and scroll during streaming. Feedback: controls
act immediately and show state. Budget: bounded per-event animation, no full
canvas remount per delta, no motion when hidden, paused or reduced; exact
figures update without fabricated intermediate numbers. No animation dependency.

## Execution
Delegate the independent metrics task while implementing the live surface.
After integration, perform a separate code review and one batched desktop/phone
visual pass, one corrective pass if needed. Run focused offline regressions.
Work in this checkout because required concurrent uncommitted integrations are
already here; do not reset, stash, switch branches, or commit others' work.
