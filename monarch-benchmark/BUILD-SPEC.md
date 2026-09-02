# WorkflowBench — Build Spec v1

Waki · 31 Aug 2026 · Reviewer: Deyton · Builds on: DESIGN.md v2.1, T0-INGESTION-SPEC.md, and the shipped T0 code (`workflowbench-t0.zip`, 9/9 tests green, pilot-001 run)

**Scope:** everything from the working T0 to the full internal instrument (Rung 1) plus the Rung-2 public trajectory pipeline. **Non-goals in this spec:** Rung-3 neutral governance (Sam's call), REAL-mode CRM tranche (behind the vendor question), minimal-scaffold control arm (open decision — one config file if accepted).

## 0. Repo layout (monorepo, lands in TestBoxLab/monarch or sibling)

```
workflowbench/
  wb_world/        # DONE (T0): MCP server, episode, snapshot diff
  grader/          # DONE (T0): assertions + dual invariant + no-op CI
  ingester/        # DONE (T0): 47 schemas -> product_graph.json
  runner/          # DONE (T0): EpisodeRow, scripted arms, pilot
  wb_arms/         # M1/M2: real arm launchers (claude-code, codex, gemini, cua, monarch)
  wb_orchestrator/ # M1: run matrix, state machine, resume, retry, concurrency
  wb_results/      # M1: SQLite store + jsonl export + query API
  wb_stats/        # M4: McNemar, Pass^k, clustered SEs
  wb_report/       # M4: report builder + publication gates
  wb_tenants/      # M5: tenant pool manager + per-vendor normalizers
  legacy/          # M3: AutomationBench adapter (subprocess) + row importer
  corpus/          # task files, oracles, templates; CI jobs
```

## 1. Milestones

Each milestone ends in a demo + tests, not a document.

| M | Deliverable | Acceptance (demo) | Est | Owner |
|---|---|---|---|---|
| **M0** | T0 core | DONE — oracle 1.00 / sloppy caught by invariant / null 0.00; MCP stdio graded out-of-process | — | Waki |
| **M1** | First real bare arm + orchestrator + results store | `wb run --suite pilot10 --arm bare/cli/claude-code --k 4` completes unattended incl. one induced crash + resume; rows in SQLite; tokens/cost captured | ~5d | Waki |
| **M2** | Monarch arm (stock + lab) + telemetry | Paired pilot: claude-code vs monarch/stock on the 10 tasks, k=4; authoring/execution phases split in every row; lab arm runs under a config-hash | ~5d + engine hookup | Waki + Deyton |
| **M3** | Legacy adapter + import | v9.12 fork re-runs under `suite=automationbench-legacy` in a subprocess; the 5,427 historical rows imported, flagged, queryable next to new rows | ~4d | Owner A |
| **M4** | Stats + report builder + gates | One command renders the internal report (paired deltas, McNemar, Pass^k, SEM, W/L, source line on every figure) and the Rung-2 public variant with bare/* and monarch/lab@* structurally stripped | ~4d | Owner A |
| **M5** | REAL mode, Google tranche + CUA arms | 20 bridge tasks run synthetic AND live (Gmail/Drive/Calendar/Sheets tenants); scoped-diff grading with normalizers; per-arm synthetic↔live gap reported | ~10d | Waki + Owner B |
| **M6** | Release-pipeline artifact + corpus scale | Every Monarch release emits a bench report (report-only, no gate); corpus at 60+ tasks with contract hashes, no-op CI and oracle CI green in Actions | ~5d | Owner B + Deyton |

Sequencing: M1→M2 serial (M2 needs the orchestrator); M3 parallel from M1; M4 needs M1 rows; M5 after M2; M6 after M4. Maps to plan weeks: M1–M2 = W2–4, M3–M4 = W4–6, M5 = W6–10, M6 = W10–12 — all pre-leave.

## 2. Component specs

### 2.1 Orchestrator (`wb_orchestrator`) — M1
- **Episode state machine:** `PROVISION → SNAPSHOT0 → ARM_RUN(timeout) → SNAPSHOT1 → GRADE → RECORD`. Grade and record always run, whatever ARM_RUN did.
- **Run matrix:** tasks × arms × trials; checkpoint identity `(run_id, task_id, arm, trial)` (tau2's scheme); `--resume` skips completed identities, refuses on config drift (config hash stored per run).
- **Termination taxonomy** (P7): `completed | agent_error | timeout | infra:rate_limit | infra:model_unavailable | infra:tenant_reset_failed | infra:harness_crash`. Only `infra:*` auto-retries (max 2, logged); infra rate is a reported metric.
- **Concurrency:** per-provider semaphores (API limits) + per-tenant locks (M5). Synthetic default 8 parallel episodes.
- CLI: `wb run`, `wb resume <run_id>`, `wb status`, `wb grade <run_id>` (re-grade from stored snapshots — grading is always reproducible after the fact).

### 2.2 Arm launchers (`wb_arms`) — M1/M2
Common contract: `launch(episode) -> ArmResult{termination, tokens_in/out, cost_usd, turns, raw_log_uri}`.
- **`bare/cli/claude-code`:** per-episode workdir with generated `.mcp.json` pointing at `wb_world.server` (env: task file, episode id, snapshot dir); invoke pinned `claude -p "<goal>" --output-format json` headless; parse usage/cost from the JSON result; version recorded from `claude --version`. Permission config documented in the row (non-default flags named — "stock" policy from DESIGN §3).
- **`bare/cli/codex`, `bare/cli/gemini`:** same pattern, `codex exec` / `gemini` non-interactive; vendor Harbor's parsers where they save time (keep their file layout for upstream sync).
- **`bare/cua/<vendor>`:** M5 only (synthetic needs no browser). Vendor computer-use API in the vendor reference loop against a hosted Chrome + the live tenant. Sessions recorded (video/trace URI in `artifacts_uri`).
- **`monarch/stock@release`, `monarch/lab@cfg-hash`:** two integration points (M2):
  1. *Authoring:* drive Monarch's workflow-authoring agent with the same goal brief (API/headless path — Deyton names it).
  2. *Execution:* Monarch's engine calls tools against the episode's world. **Option A** engine speaks MCP → point it at `wb_world.server`. **Option B** it speaks HTTP → 50-line FastAPI shim exposing `POST /fetch {method,url,params,body}` over the same `Episode`. Build B only if A is false. *(Open question #1 to Deyton — blocks M2, nothing else.)*
  - Lab arm = stock code + config bundle; `cfg-hash = sha256(config)`; hash printed in every row; report builder refuses `monarch/lab@*` outside internal audience (DESIGN §3 quarantine).

### 2.3 Telemetry (M2)
Event stream per episode (`events.jsonl`): `{episode_id, phase: authoring|execution, event, ts, tokens?, cost?, meta}`. Minimum events: `turn_start/turn_end` (authoring), `workflow_saved | workflow_abandoned`, `engine_run_start/end`, `step_dispatch`, `gate_decision{allowed|refused, reason}`, `retry`. Collector folds into `EpisodeRow.phases.{authoring,execution}` + `gate_refusals`. This event list is simultaneously the product feature request from the RFC — the bench is its first consumer, the release pipeline its second.

### 2.4 Results store (`wb_results`) — M1
SQLite, orchestrator is the single writer. Tables: `runs(run_id, config_hash, suite, started, finished)`, `episodes(24-field row, FK run_id)`, `artifacts(episode_id, kind, uri)`. Export: `episodes.jsonl` per run (unchanged from T0). Query API used by stats/report: `store.episodes(suite=, arm=, run=)`. **Source line = a stored view**, not prose: every figure the report builder renders carries `{suite, suite_version, denominator, arm, run_id}` from the query itself — the August reconciliation failure made structurally impossible.

### 2.5 Stats (`wb_stats`) — M4
- Paired: McNemar (continuity-corrected) from per-task W/L on the identical task set; report b and c alongside p.
- Reliability: `pass_hat_k = comb(s,k)/comb(n,k)` per task, k ≤ 4, infra episodes excluded (tau2 verbatim).
- Uncertainty: SEM beside every mean; cluster bootstrap over `task_template × tenant` for REAL mode.
- Already validated: the T0-adjacent implementation reproduced the posted Kimi p = 0.040 to four decimals.

### 2.6 Report builder (`wb_report`) — M4
Input: queries only (no hand-entered numbers). Templates: `internal` (everything), `public-rung2` (arm allowlist `monarch/stock@*` only — bare/* and lab/* stripped at query level, not by editing). Every rendered figure: value ± SEM, W/L where paired, source line, contract hash. Output: md + html. **The gate is code:** `audiences.yaml` maps audience → arm allowlist; rendering a disallowed arm raises, never warns.

### 2.7 Tenants (`wb_tenants`) — M5
- Google-stack first (clean legally; Workspace dev tenant + Admin SDK). API: `lease(task) -> Tenant`, `provision(tenant, template)`, `verify_clean(tenant) -> ok|dirty`, `teardown(tenant)`.
- Provisioning = template import via vendor APIs (MCPMark pattern; no UI automation in the load-bearing path). Per-episode ephemeral users via Admin SDK (WorkArena pattern), tracked-resource teardown, orphan sweep job.
- `verify_clean` gates token spend: an episode never starts on a dirty tenant (reset failure = `infra:tenant_reset_failed`).
- **Normalizers:** per-vendor modules stripping housekeeping fields from readback before diffing (T0's `IGNORE_FIELDS` generalized; Drive activity metadata, Gmail read markers, Calendar updated stamps). Owner A owns the list + a vendor-release regression job re-running golden oracles.
- Capacity model (episodes/day = tenants × resets/hour) is M5's first deliverable, with Deyton, before any full run is scheduled.

### 2.8 Corpus (`corpus/`) — M1 onward
- Task files: T0 format + `contract_sha256` (full hash) embedded; converter from AB task functions (exists in T0 export script — promote to `wb corpus import-ab`).
- CI (GitHub Actions): **no-op job** (every assertion fails on the pristine world) + **oracle job** (every task's scripted oracle passes) on every corpus change. Both exist in T0 code; CI wiring is ~½ day.
- Growth: 10 (done) → 60 (M5 bridge set: 20 tasks × both modes + 40 synthetic-only, sampled across the 6 AB domains) → full 576/600 legacy-parallel corpus (M6). Effort-tier naming normalized (`low|medium|high` canonical; `max/xhigh` mapped in the legacy importer).

### 2.9 Legacy (`legacy/`) — M3
- Pinned v9.12 fork ran via subprocess in its own venv (quarantined deps); stdout/exports translated row-for-row into `episodes` with `suite=automationbench-legacy@9.12`, `tokens.estimated` flag preserved.
- One-time import of the 5,427 historical rows; nulls + flags where fields can't populate, never guesses.
- Acceptance: a single query returns legacy and new rows side by side with suite labels, and the report builder refuses to pool them into one headline.

## 3. Dependencies & risks

| Blocker | Blocks | Path |
|---|---|---|
| Monarch engine: MCP or HTTP? (Deyton) | M2 | Option B shim is half a day if the answer is HTTP |
| Monarch authoring headless entrypoint (Deyton) | M2 | — |
| Google Workspace dev tenant + Admin SDK access | M5 | request this week; zero cost blocker per Waki |
| Claude Code / Codex API-key billing configured | M1 | subscription-auth automation is the gray zone — API keys only |
| Owner A / Owner B named (due 2 Oct) | M3/M4, M6 owner columns | Waki runs M1–M2 solo meanwhile |

Biggest technical risk: harness output parsing drift (CLI updates break usage capture). Mitigation: pinned versions per run + vendored Harbor parsers + `wb doctor` smoke command that validates each arm launcher against one known task before a run starts.

## 4. Definition of done (Rung 1, pre-leave)

A single command reruns the full synthetic suite across `bare/cli/claude-code`, `bare/cli/codex`, `monarch/stock` at k=4, resumes through failures, grades out-of-process, and renders the internal report with paired stats and source lines — with Sam able to read the public-rung2 variant knowing nothing in it could have leaked from a lab arm. That is the instrument; everything after it is corpus growth and REAL-mode reach.
