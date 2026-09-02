# Prompt for Claude Code — build the WorkflowBench run mechanism (M1)

Copy everything below the line into Claude Code, run from `Monarch_Main\APPLICATIONBENCH\`.

---

Build the WorkflowBench run mechanism on top of the existing T0 code. Everything you need is in this folder: `workflowbench-t0.zip` (working code, 9/9 tests green — unzip it, it is the starting codebase), `BUILD-SPEC.md` (component contracts — follow §2 exactly), `DESIGN.md`, `T0-INGESTION-SPEC.md`.

## Goal

One command runs any benchmark suite across any set of models, resumably, with prompt caching working and measured:

```
wb run --suite corpus/ --arms glm-5.3,gemini-3.7-flash,kimi-k3,oracle --k 4
wb resume <run_id>
wb status <run_id>
wb doctor            # validates every configured provider + cache behavior with one cheap call each
wb grade <run_id>    # re-grade offline from stored snapshots
```

## What exists (do not rebuild)

`wb_world/` (episode seeding, 3-tool surface, snapshots), `grader/` (assertions + dual invariant + no-op), `runner/` (EpisodeRow schema, scripted arms, pilot), `tasks/` (10 tasks), `tests/` (keep green). AutomationBench installs from the pinned clone as a sibling (`pip install -e ../ab`, python 3.13).

## Build 1 — `wb_arms/api_loop.py`: one generic tool-loop arm for all API models

OpenAI-compatible chat-completions loop with `tools` = the three wb-world tools (api_search, api_fetch, base64_encode), called in-process against the `Episode` object (no MCP hop needed for API arms). Max 50 tool turns (the AB budget), then stop.

**Provider registry (`wb_arms/providers.py`) — verified 31 Aug 2026 against vendor docs:**

| key | model id | base_url | key env | cached-tokens usage field | prices in/cached/out $/Mtok |
|---|---|---|---|---|---|
| `glm-5.3` | `glm-5.3` | `https://api.z.ai/api/paas/v4` | `ZAI_API_KEY` | `prompt_tokens_details.cached_tokens` | 1.40 / 0.26 / 4.40 |
| `kimi-k3` | `kimi-k3` | `https://api.moonshot.ai/v1` | `MOONSHOT_API_KEY` | `usage.cached_tokens` (top level) | 3.00 / 0.30 / 15.00 |
| `kimi-k3-fireworks` | `accounts/fireworks/models/kimi-k3` | `https://api.fireworks.ai/inference/v1` | `FIREWORKS_API_KEY` | `prompt_tokens_details.cached_tokens`, fallback header `fireworks-cached-prompt-tokens` | 3.00 / 0.30 / 15.00 |
| `gemini-3.7-flash` | `gemini-3.7-flash` | native GenAI SDK (`google-genai`), NOT the OpenAI-compat endpoint | `GEMINI_API_KEY` | `usageMetadata.cachedContentTokenCount` | 0.75 / 0.075 / 3.75 (doubles Jan 1 2027) |

Gemini gets a thin native adapter because implicit-cache reporting through its OpenAI-compat endpoint is undocumented; the other three share the OpenAI-SDK path. Registry entries carry prices so cost is computed per episode, split cached/uncached.

**Prompt-cache discipline (all providers cache automatically on prefix match — the code's job is to never break the prefix):**
- Byte-stable prefix order: system prompt → tools array (fixed serialization, sorted keys, built once per run) → task brief → append-only history. Never mutate or re-order earlier messages.
- No timestamps, run ids, or episode ids anywhere in the system prompt or tool schemas; per-task variables live in the first user message only.
- Schedule same-model episodes back-to-back (cache TTLs are minutes-scale); the orchestrator groups the matrix by arm.
- Normalize cached-token reporting across the four field shapes into `EpisodeRow.tokens.cached`; missing field → 0 plus a `cache_reporting=absent` flag, never silence.
- Cache minimums: Gemini needs ≥4,096 prompt tokens, Kimi ≥256 — the tool schemas alone clear both; assert in doctor.
- **Regression assertion:** within an episode, from turn 3 on, `cached_tokens ≥ 0.8 × previous turn's prompt_tokens`, else log `cache_degraded` with the first divergent message index. This is the check that catches prefix breakage forever.

## Build 2 — `wb_orchestrator/` per BUILD-SPEC §2.1

Episode state machine PROVISION → SNAPSHOT0 → ARM_RUN(timeout, default 10 min) → SNAPSHOT1 → GRADE → RECORD (grade+record always run). Checkpoint identity `(run_id, task_id, arm, trial)`; `resume` skips completed, refuses on config-hash drift. Termination taxonomy: `completed | agent_error | timeout | infra:rate_limit | infra:model_unavailable | infra:harness_crash`; only `infra:*` auto-retries (max 2, exponential backoff honoring `Retry-After`). Concurrency: per-provider semaphore (default 4), grouped by arm for cache warmth.

## Build 3 — `wb_results/store.py` per BUILD-SPEC §2.4

SQLite, single writer. Tables `runs`, `episodes` (the 24-field row + tokens split cached/uncached + cost), `artifacts`. `episodes.jsonl` export unchanged. Every query result carries suite/version/denominator/arm/run — that view is the only path the report builder may read.

## Build 4 — `wb doctor`

For each configured provider: one tiny completion, then the same prefix again; report model reachable, tool call works, `cached_tokens > 0` on the second call, and the usage field it found them in. Fail loud per provider, never abort the others. This runs before any paid sweep.

## Acceptance (all must pass)

1. Existing 9 T0 tests stay green; new tests for: prefix stability (serialize tools twice → identical bytes), cache-field normalization (4 fixture shapes), resume-after-kill (kill mid-run, resume completes without re-running finished episodes), retry-on-429 (mock), timeout termination.
2. A mock OpenAI-compatible server (in tests) runs the full loop end-to-end: 10 tasks × mock arm × k=2, graded, stored, `wb status` correct.
3. `wb doctor` against real keys shows cache hits on every configured provider. If a provider reports no cached tokens, doctor says so explicitly — do not paper over it.
4. `wb run --suite tasks/ --arms glm-5.3,kimi-k3,gemini-3.7-flash --k 2` completes on the 10-task pilot; the report shows per-arm strict pass, cost, and **cache hit rate** (cached ÷ total prompt tokens — print it beside cost; it is the number that proves the money isn't being wasted).

## Rules

- Real keys come from env; never write keys to disk or logs. API-key billing only.
- Don't invent numbers or models; if a provider call fails, that's a finding, not something to mock away in the real path.
- No new frameworks. OpenAI SDK + google-genai + stdlib + sqlite3 + pydantic.
- Keep prose in code minimal; no banner comments.
- When done: run the full test suite, run doctor, run the k=2 pilot, and print the three outputs verbatim.
