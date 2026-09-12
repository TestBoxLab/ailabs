# Tasks: Live workflows and metrics

Paths are relative to monarch-benchmark/workflowbench/ unless stated otherwise.

- [x] T001 Ground the feature, record spec/plan/contracts and inspect prior work.
- [x] T002 [P] [US2] Add failing metric checks in tests/test_studio_performance.py.
- [x] T003 [US2] Implement wb_studio/performance.py; integrate reports.py and
  report_data.py; correct missing-duration handling in measures.py.
- [x] T004 [P] [US1] Add failing stream projection checks in
  tests/browser/live-workflows-model.cjs.
- [x] T005 [US1] Build persistent lanes, data flow and output previews in
  static/observatory.js and static/observatory.css; wire index.html/app.js.
- [x] T006 [US2] Render shared performance data in Activity and static/reports.js.
- [x] T007 [US3] Add offline Playwright checks in tests/browser/live-workflows.cjs;
  verify streaming, inspection, focus, reconnect, terminal and reduced motion.
- [x] T008 Run focused regressions; inspect desktop/phone together, correct
  findings once, run design detector and request independent code review.
- [x] T009 Record runnable evidence and remaining limits in this feature's
  implementation.md; append status to monarch-benchmark/PLAN.md.

T002/T003 may run alongside T004/T005. T006 depends on their contract. T007/T008
follow integration. No paid benchmark or data mutation is part of verification.
