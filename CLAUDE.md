# ailabs

Start with `monarch-benchmark/docs/HANDOFF-2026-09-02.md`, then `monarch-benchmark/PLAN.md`.

## Working method

- Conversation with Carlos is in Portuguese; every file in the repo is in English, plain language.
- Design before code: `superpowers:brainstorming`, then `/speckit-specify` -> `/speckit-plan` -> `/speckit-tasks`
  (artifacts in `specs/<id>/`), then Superpowers `executing-plans` / `subagent-driven-development`.
- Never run a full benchmark round without explicit approval of that specific run. Smoke scale
  (10 tasks, k=2) and `wb doctor` are fine. State episode count and cost band before any `wb run`.
- Do not edit task contracts after seeing results without Lucas's sign-off (pre-registration).
- Nothing is pushed to `TestBoxLab/ailabs` until Carlos decides on repo visibility.
- Environment: `cd monarch-benchmark/workflowbench && uv sync && uv run python -m pytest tests -q`.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
