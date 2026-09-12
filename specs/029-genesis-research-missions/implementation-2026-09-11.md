# Genesis partner and durable missions: implementation evidence

Lucas requested Astra medium by default, a warm intelligent research partner, and durable research work with visible and spoken progress. These are implemented on existing cards, watcher, tools, and provider adapters. No new independent benchmark execution path was introduced.

## Requirement and evidence

| Requirement | Evidence |
|---|---|
| Astra medium partner | `test_genesis_astra_defaults.py`; explicit unavailable route stays unavailable, supported effort propagates to missions; custom identities preserved |
| Correct Astra billing | `test_genesis_astra_pricing.py`; whole-request long-context boundary at 272,000 input tokens |
| Durable bounded work | `test_genesis_missions.py`; owner and worker generation, checkpoints, stop/steer, interruption, child waits, turn limit |
| Clarification | Two regression tests first failed: question incorrectly blocked mission and answer after stop queued work. Both now pass |
| Real integration without paid providers | `test_genesis_mission_journey.py`; real chat/watcher/harness with fake adapter, persisted synthetic child job, successful read receipt, exactly one continuation after completion |
| Safe cancellation and evidence | Startup lease lock, provider-capacity cancellation recheck, child cancellation, compact receipts surviving truncation, parent-owned debrief |
| Concurrent conversation | 4 mission browser scenarios preserve typed draft, focus, scroll and worker updates; no duplicate streams |
| Voice lifecycle | 13 browser scenarios; meaningful progress from recorded tools and mission states, owner/thread isolation, no false action receipts |

Focused shared-workspace Python suite: **614 passed in 47.59 seconds**. Source snapshot: **612 passed, 1 failed**; failure is the repository source-read check because the archive has no Git metadata. This also exposes an existing hosted source-inspection limitation, not evidence that code inspection works in the Docker image. UI detector returned no findings. Tests are offline unless explicitly recorded below.

Independent review corrected worker startup/cancellation races, lost child cancellation IDs, truncated evidence receipts, and duplicate paid debriefs. No paid benchmark or architecture performance claim follows from these tests.

## Model configuration sources

- [GPT-6 Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model)

The implementation uses the Responses adapter, medium reasoning, preserved continuation output, and current tiered pricing. Prompt improvements describe warmth, candor, persistence, scientific discipline and concise useful progress. They do not establish SOTA performance experimentally.

## Live acceptance remaining

The original scenario still requires a real voice session, available source/workspace access, architecture revisions, matched frozen development/evaluation tasks, paid-round approval and billing/reservations, measured comparison and evidence review. Cards/Runs controls are not silently enabled. A 50-task experiment was not run by this implementation task.

## Railway verification

Final observed deployment: `6320318b-a1d4-4c5b-ae07-8cabe86ede5d`, **SUCCESS**, service `ailabs-studio`, project `monarch-dev`, production. Public app: https://ailabs-studio-production.up.railway.app . The persistent `/data` volume remains attached.

Initial upload `cbed9654-bea9-4a4d-b658-8a97a315adaa` was superseded by concurrent report deployment `c2aa885f-625b-4dda-ba4f-3795c453cc02`. Read-back showed that release served older code (Gemini defaults, no effort field, voice endpoint 404). The final release restores the verified current snapshot. Coordination messages were sent to the active report task to avoid another stale release.

Authenticated browser: title AI Labs — Genesis, GPT-6 Astra, medium, zero page errors; desktop/mobile screenshots retained under `out/genesis-missions-browser/hosted-*.png`. Served JavaScript contains mission attribution, question waits and Astra labeling. Configuration was explicitly saved through the normal API for chat/reading; the requested identity was saved through the versioned memory API.

Voice readiness now responds correctly but reports unavailable: current-week provider billing verification is absent. No provider exports were found in the research/config file search, and no OpenAI/Anthropic billing admin credential is configured in the hosted service. The planned one-attempt $2 chat smoke was therefore not launched; no paid request was made by this task. Weekly capacity is available but is not invoice verification. Cards and Runs remain off. The full spoken 50-task research scenario remains unverified.

See `deployment-source.json` for source hashes and `hosted-verification.json` for the final safe API projection. The snapshot intentionally excludes concurrent unfinished report changes.
