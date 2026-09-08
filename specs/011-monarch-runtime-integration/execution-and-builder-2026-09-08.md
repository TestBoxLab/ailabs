# Executable architectures and the rebuilt builder

8 September 2026. Private local changes under `monarch-benchmark/workflowbench`; no push,
deployment or publication. Three bounded paid pilots (USD 0.21 in total) were run against
the real providers to prove the wiring; nothing else was spent.

## What executes now

| Piece | Before | Now |
|---|---|---|
| Runners | One Gemini loop hard-wired into the Studio | Every rate-carded model in `config/models` (Claude Opus 5/4.8, GPT-5.6 Sol/Terra, Gemini 3.7 Flash, Kimi K3 and GLM 5.3 on Fireworks, Moonshot, Z.ai) through one budget-admitted gateway per adapter family, each with the effort vocabulary its API accepts |
| Published node graphs | A stored JSON definition with a decorative "adapter required" flag | Compiled into steps and executed on the episode world: prompts inherit downstream, agents run in act (tools) or advise (text) mode, outputs flow to successors, merge/output join them |
| Product-graph enrichment | A node type with no behaviour | A preparation operation: the enrichment agent researches every corpus product once through `api_search`, the typed result is pinned as a knowledge artifact beside the version, and scored attempts inject it into downstream steps |
| Launcher | Without Monarch × Gemini | Without Monarch × any available control, plus any ready published version as its own arm; every cell refused before a job exists when unsupported; run budgets below a runner's first-request reservation refused with the amount |
| Builder | Click-two-ports canvas, free-text runner fields, no validation | Drag-to-connect with live preview and refusal reasons, pan/zoom/fit, marquee and multi-drag, undo/redo, duplicate, keyboard connect, per-step validation badges, typed inspectors (mode, runner catalog with prices, effort limited to the model, fields table, target-field checkboxes), templates, version diffs, knowledge viewer, prepare dialog, run-latest, live execution overlay |

Stock Monarch Enterprise did not execute at the time of this note (no adapter, services or
Bedrock billing); `checkpoint-3.md` records the adapter that followed. Native Claude Code and Codex remain blocked by
the isolation preflight (Docker daemon is not running on this machine; no verified
container boundary exists). Both are reported honestly in the picker rather than faked.

## Code

- `wb_studio/gateways.py`: `ProviderGateway` (Anthropic, OpenAI Responses, OpenAI-compatible chat) and `GeminiGateway` behind one `start/turn/append_tool_result` interface; reserve → claim → dispatch → settle per request; unknown usage keeps its hold; provider errors sanitized; `request_ceiling` gives the first-request reservation floor.
- `wb_studio/agents.py`: the single agent loop with step-tagged events and journaled system prompts.
- `wb_studio/execution.py`: `compile_version`, `prepare_version` (knowledge artifact, single-dispatch claim, failure recorded), `ArchitectureArm`, `execution_manifest` binding a run to graph hash + knowledge hash.
- `wb_studio/runtime_registry.py`: API-control catalog from the provider registry, runner resolution, readiness with `preparation_required` and `ready`, `check_launch` returning version records.
- `wb_studio/blueprints.py`: `problems()` collects every defect per node, `diff_versions()`, published versions carry readiness, capabilities and a runtime manifest.
- `wb_studio/app.py`: arms (runner or version) in job settings, `gateway_for`, endpoints `/api/blueprints/validate`, `/prepare`, `/{id}/versions/{n}/{knowledge,diff,events}`, `/api/capabilities`; execution tracebacks kept in the job directory.
- `wb_studio/static/graph.js`, `graph.css`, `index.html`, `app.js`: the builder, launcher groups, step lanes in Activity.

## Evidence

Offline: Studio, manifest, registry, provenance, execution, blueprint, paid and sandbox
suites: 241 passed. Whole `tests/` directory: 1049 passed, 3 skipped in 909 s.

Live (task `simple.email_sf_contact_city_update`, one attempt each, all passed the
deterministic checks):

| Run | Arms | Cost | Tool calls |
|---|---|---|---|
| Single Gemini worker / v1 | Gemini 3.7 Flash, low, act | 0.051 | 15 |
| Opus planner, Gemini worker / v1 | Claude Opus 5 medium (advise) → Gemini worker | 0.113 | 18 |
| Enriched Gemini worker / v1 | knowledge prepared over 42 products (0.014, 15 s) then Gemini worker | 0.027 | 8 |

Events carry `step` ids, so the Activity view groups tool calls under the step that made
them and the builder lights up the step that is running. Evidence journals record the
composed system prompt (ground rules, planner output, pinned knowledge) with the first
request of every step.

Browser: headless review at 1600×1000 and 390×844 (`.impeccable/review/builder-*.png`), no
page errors, no horizontal overflow. One defect found and fixed during review: node
positions were emitted as inline `style` attributes, which the page's CSP strips; they now
go through the CSSOM. A second: builder node lookups matched Activity-view nodes with the
same data attribute; lookups are scoped to the canvas.

## Not done

- Native isolated runtime (checkpoint 2). The stock Enterprise adapter landed later the same day: see `checkpoint-3.md`.
- The BRIDGE v2 + v9.12 preset remains `source_required` until the missing artifacts are recovered.
- Paired analysis with Sol medium (checkpoint 6) is not connected; the Gemini review remains.
- The three pilots are single attempts on one easy task: wiring proof, not a quality measurement.
