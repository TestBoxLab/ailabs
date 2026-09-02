# WorkflowBench T0 — Synthetic Tools Ingestion Spec

v1 · Waki · 31 Aug 2026 · Reviewer: Deyton
Grounded in zapier/AutomationBench @ main (MIT), paths verified today.

## The finding that shapes everything

AutomationBench already ships **two tool surfaces over one world state**, and the second one is exactly what we need:

1. **Per-app tools** — ~52 app modules in `automationbench/tools/zapier/`, registered in `ALL_TOOLS` (`tools/__init__.py:1322`).
2. **A generic REST surface** — `automationbench/tools/api/`: `api_search` (BM25 over endpoint docs) + `api_fetch` (URL router → 48 app routes → the same underlying tool functions; "all WorldState mutations go through the Zapier tools") + `base64_encode`.

The REST surface is driven by **47 `.jsonc` schema files** (`tools/api/schemas/*.jsonc`), each declaring `api, version, baseUrl, notes, schemas, endpoints[]` with per-endpoint `id, path, method, description, parameters, response`.

**So T0 is not "wrap 600 tools in MCP." It is: one MCP server exposing 3 tools, and one graph ingester reading 47 schema files. Same source of truth for every arm — parity by construction.**

## Deliverable 1 — `wb-world` MCP server (bare arms)

- One MCP server, 3 tools: `api_search`, `api_fetch`, `base64_encode` — thin wrappers over the existing functions.
- **Per-episode instance**: server starts with `episode_id`, seeds a fresh `WorldState` (`automationbench/schema/world.py`) from the task's fixture, pins `WorldMeta.current_time` (frozen clock — the field exists), sets `WorldMeta.allowed_services` from the task (service gating already built in: `api_fetch` rejects out-of-scope services with a credentials error — `world.py:68-72`).
- Same server config handed to Claude Code / Codex / Gemini CLI and to the CUA arms' tool channel. Identical interface, no arm-specific extras.
- Snapshot API (not exposed to agents): `snapshot()` → canonical `WorldState.model_dump()` at episode start and end, for the grader.

## Deliverable 2 — graph ingester (Monarch arm)

- Reads the same 47 `.jsonc` files → product-graph actions: one node per endpoint (`id, method, path, description, parameters, response`), one service node per file (`api, baseUrl, notes`).
- The "what it does / what it doesn't do" metadata idea from the Aug 19 sync = the `description` + `notes` fields, ingested verbatim first; enrichment is a lab-arm experiment, not a T0 default.
- Monarch's engine executes workflows against the same `wb-world` server endpoint surface (via `api_fetch`-equivalent calls), so both arms mutate the identical world.

## Deliverable 3 — grader hookup

- Whole-state dual invariant on the snapshot pair: expected changes present, every observed change expected-or-allowed, over `model_dump()` diff with a small ignore-list (record ids, `created_at` autofields).
- Reuse the assertion registry (`automationbench/rubric/registry.py`, `rubric/assertions/`) for typed checks; add no-op validation (every check must fail on the start snapshot) as a corpus CI step.
- Runs out-of-process after the arm stops (nothing grades itself).

## Deliverable 4 — episode lifecycle

seed fixture → start `wb-world` (frozen clock, gated services) → snapshot₀ → run arm (`/goal` prompt + brief) → arm stops → snapshot₁ → grade → emit episode row (24-field schema from DESIGN.md) → teardown.

## Order of work

1. `wb-world` server + per-episode seeding/snapshot (the existing functions do the heavy lifting).
2. Graph ingester over the 47 schemas.
3. Grader hookup + no-op CI on 10 pilot tasks.
4. First paired pilot: 10 tasks × {Claude Code+wb-world, monarch/stock} × k=2. This smoke-tests every joint before any full run.

## Open questions for Deyton (review)

- Does Monarch's engine call tools over MCP today, or does it need an HTTP shim in front of `wb-world`?
- Where do episode rows land — the existing results store or the new one first?
- Pilot tasks: I propose 10 from `domains/simple/` before touching the six business domains.
