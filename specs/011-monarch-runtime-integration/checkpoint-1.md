# Checkpoint 1: provenance/manifest inventory and capability matrix

8 September 2026. Private local changes under `monarch-benchmark/workflowbench`; no push,
deployment, publication or paid experiment. Implemented in this session after the Codex
"Sol medium" route was confirmed dead again (`codex doctor`: elevated Windows sandbox
provisioning failed, `helper_unknown_error`), so the plan was executed directly.

## What now actually executes

Nothing new executes an agent. Every comparison version except Without Monarch remains
non-launchable, and the launcher now says exactly why per version and per runner. The
deliverable of this checkpoint is identity and capability discovery, not execution.

## Delivered

**Runtime manifest** (`wb_arms/runtime_manifest.py`, schema `ailabs-runtime-manifest-v1`).
Source (repository, full commit, patch hash, lockfile blob, image digest), runtime
entrypoint and dependency closure, evaluation track/provider/model/effort/harness,
artifact hashes with present/missing/reconstructed status, public-surface hashes and
budget policy. `identity_sha256` covers only executable inputs: readiness, notes and
timestamps never move it; commit, lockfile, graph, prompt, effort or provider do.
`freeze` refuses a git source without a full SHA. Readiness has three axes (source,
publication, runtime); only `runtime == ready` is launchable and every other state must
carry reasons.

**Stock resolution** (`wb_studio/architectures.py`). Resolving Default Monarch Enterprise
now pins the `main` commit and the `pnpm-lock.yaml` blob through two `gh api` calls and
returns a frozen manifest. Either call failing fails resolution closed. `cached_default`
never contacts GitHub, so `/api/state` and the picker are offline. Refreshed live through
the Studio API: main is still `60faf2a238fc…`, lockfile blob `13305d43a698…`, no drift
from the pinned facts.

**Capability registry** (`wb_studio/runtime_registry.py`). Facts read from the pinned
Enterprise checkout (`.references/monarch-enterprise-60faf2a`, sparse, git-ignored) with
the eight source-file hashes recorded and re-checked by a test:

| Track | Stock product accepts | Refused |
|---|---|---|
| Agentic request (`POST /api/operator/runs`) | goal, productSlug, origin, threadId; model from `ANTHROPIC_MODEL` (default claude-opus-4-8) | any per-run model or effort; any non-Bedrock runner |
| Create and run (`POST …/recipes/runs`) | `brain` preset name: `opus-medium` (claude-opus-4-8) or `sonnet-high` (claude-sonnet-5); env default otherwise | free model/effort pairs |
| Provider | AWS Bedrock only; catalog of six keys; fable/mythos barred | direct Anthropic/OpenAI keys as billing |

Without Monarch: Gemini API control (low/medium/high) is the only launchable runner; Claude
Code and Codex are the right harnesses but carry the `native-isolation-v1` block with its
seven missing checks; Fireworks has no inference or billing adapter. The BRIDGE v2 + v9.12
identity accepts only Claude Opus 5 at medium as a reproduction setting; anything else is a
new variant. `check_launch` runs before a job, reservation or provider request exists.

**Publication** (`wb_studio/blueprints.py`). A published version now carries `readiness`,
per-node `capabilities` and a `runtime_manifest` bound to the graph hash, prompt hash and
pinned baseline. A Monarch node with a non-Bedrock runner publishes as `unsupported`
(editable, not launchable); a stock configuration publishes as `adapter_required`. The
default Monarch node in the editor now defaults to Bedrock `claude-opus-4-8` with no
effort override. Stored versions are never rewritten; `/api/blueprints` overlays live
readiness on versions that predate the field and marks them `readiness_computed_live`.

**Historical bundle** (`wb_studio/provenance.py`, output in
`research/architectures/bridge-v2-v9.12/`). The dependency closure of the v9.12 graph
producer was hashed in its original layout: 12 components present, 3 present but unpinned
(the repair checkout advanced to evalrepair.17; the current slack and recruitee sources
match none of the candidate commits before the evalrepair.11 cut), 4 missing. The four
missing components block regeneration and reproduction: the actor contract
(`.automationbench-local/suite-package-7a08b5047c89`), `source-provenance-evalrepair10.json`,
the generated `graph-inline-v6-evalrepair10.json`, and the 600-task run manifests. The
producer's project root (a sibling of `ATLAS` and `AutomationBench-repair` with
`config/monarch/`) no longer exists under `Monarch_Main`. `AB-5a0dea3-clean` at 5a0dea3
carries the `1.0.6+evalrepair.10` version string the producer names. Report claims
(361/600 vs 289/600) are transcribed as unverified. The preset stays `source_required`.

**Studio surfaces.** The launcher lists every version from `/api/capabilities` with its
readiness reason; the versions panel shows readiness and the graph hash;
`/api/architectures/bridge-v2-v9.12` exposes the provenance summary.

## Validation

- `pytest` on the Studio, manifest, registry, provenance, architecture, blueprint,
  comparison-mode, sandbox and app suites: 127 passed (3.4 s) after the last change;
  the earlier broader Studio pass was 157 passed.
- Whole `tests/` directory (`uv run --frozen python -m pytest tests`): 1030 passed,
  3 skipped in 914.7 s; the slowest cases are the pre-existing run-config drift tests
  (~100 s each), unrelated to this checkpoint.
- Browser (localhost:8765): `/api/capabilities` 200 with no console errors; the launch
  dialog renders Default Monarch Enterprise and the BRIDGE preset disabled with reasons,
  and flags the pre-existing "Product graph enrichment / v1" as unsupported; the
  Enterprise refresh through the API moved readiness from `unavailable` to `frozen`.

## Remaining blockers for later checkpoints

- No isolated native runtime (checkpoint 2); no Enterprise build/deploy recipe, adapter or
  Bedrock billing verification (checkpoint 3); no node executor (checkpoint 5).
- The v9.12 graph, its provenance JSON, the actor contract and the run manifests must be
  recovered from backups or deleted worktrees before any reproduction claim (checkpoint 4).
- Capability facts are pinned to `60faf2a`; a later main commit is flagged as drift and
  needs the catalog, presets and request shapes re-read.
