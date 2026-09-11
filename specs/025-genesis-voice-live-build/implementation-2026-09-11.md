# GPT-Live-1 connection: implementation and evidence

Date: 11 September 2026. Lucas explicitly selected GPT-Live-1 for Genesis voice.
This record covers the local connection slice; the full feature specification is
not complete. Existing live architecture edits and unrelated working-tree changes
were preserved. No benchmark tasks, simulator assertions or historical results
were changed by this slice.

## Behavior

The persistent **Talk to Genesis** control opens a GPT-Live-1 WebRTC session.
Browser microphone audio goes to OpenAI; the API key stays on the server. An
authenticated server sideband delegates lab work to ordinary Genesis turns,
which retain tool access, memory, autonomy checks, person attribution and their
own request reservations. Voice and typing share thread and parent identifiers.
The current route, selected architecture nodes, draft state and selected run are
available through the bounded `workspace_context` tool. Browser context contains
identifiers and structural state, not scraped page text or unsaved prompt bodies.

Existing `show`, `edit_architecture`, `save_architecture`, research, report and
lab source tools remain the operations surface. Voice turns enter the real turn
stream: navigation follows the person's Follow preference, edits remain
provisional until saved, and source changes retain the existing review gates.
A navigation receipt means the server prepared a route, not proof a browser moved.
Voice cannot bypass paid-round approval, project budget, deployment or write gates.

Captions, local playback pause, acknowledged microphone mute/unmute, explicit end,
connection failure handling and late microphone-permission cleanup are implemented.
A newer delegated request supersedes older work; persisted cancellation is checked
before model requests and each action. Cancellation cannot undo an action that has
already committed. Repeated delegation events cannot dispatch the same turn twice.
Delayed transcript fragments are associated using the provider audio timeline.

## Runtime and accounting

Install the existing Python environment with `uv sync`; `websockets>=15` is now an
explicit dependency. Use the existing server-side `OPENAI_API_KEY` and an available
Genesis chat route. Voice uses `gpt-live-1`; the reasoning/tool route remains the
lab's configured Genesis route. An HTTPS or localhost browser origin and microphone
permission are required. Restart the Studio process to load the Python changes.

`WB_GENESIS_VOICE_ENABLED=0` disables live voice. `WB_GENESIS_VOICE_MAX_SECONDS`
accepts 30 through 600 seconds, default 300. The default reservation is US$0.275:
300 seconds plus 15 seconds of closing and 15 seconds of initialization headroom,
at US$0.05/minute. Backend reasoning is billed separately. Initialization time is
credited toward live duration by OpenAI; it is not added to the final usage receipt.

Admission requires the existing current-week billing reconciliation flag, Genesis
allowance and shared ledger capacity. Only authenticated provider final
`session.closed.usage.seconds` settles actual voice spend. Interim usage is a
cumulative snapshot. Unknown finalization retains liability and blocks another
voice session until the existing ledger reconciliation resolves it. On restart,
interrupted records are recovered and the provider hangup is attempted again.
The server timer is best effort, not a provider-enforced hard dollar ceiling.

Session records and append-only transcript evidence live under the Genesis
runtime directory's `voice/` folder. Prompt context is bounded independently of
that evidence. Raw audio is not written locally, and provider session recording
is not enabled.

## Verification

All verification in this task uses temporary fixtures and scripted providers.
No paid model session or benchmark round was launched. Focused backend tests cover
ownership, admission, reservations, cumulative/final usage, interruption, orphan
recovery, duplicate and delayed delegation, cancellation, context and receipts.
HTTP route tests exercise the actual server's person gate, including dictation.
Browser checks exercise controls, microphone races, disconnects and the actual
Genesis conversation, navigation and open editor context. See the final command
results below.

The current ledger reported `historical_billing_verified: false` for the week of
7 September. Therefore live provider access, real microphone/speaker quality,
latency, interruption quality and production deployment remain unverified. No
repository push or deployment was performed. A paid smoke session requires the
existing billing verification to be resolved first and an explicit attempt/cost
statement; do not bypass that gate or create a replacement ledger.

The broader numeric truth registry, strict pre-playback verification, source
preview, long-term memory/calibration acceptance and full voice quality criteria
in feature 025 remain outside this slice. Recorded structured tool facts and
successful operation receipts can be spoken; arbitrary generated answer prose is
not promoted to verified evidence. This is not evidence of state-of-the-art
performance or complete autonomous operation of every lab capability.

## Protocol references checked

- [GPT-Live model](https://developers.openai.com/api/docs/models/gpt-live-1)
- [Live delegation](https://developers.openai.com/api/docs/guides/live-delegation)
- [Live conversation events](https://developers.openai.com/api/docs/guides/live-conversations)
- [WebRTC transport](https://developers.openai.com/api/docs/guides/voice-webrtc)
- [Authenticated server controls](https://developers.openai.com/api/docs/guides/voice-server-controls)
- [Voice cost and latency](https://developers.openai.com/api/docs/guides/voice-latency-cost)

## Final local results

- `uv run python -m pytest tests/test_genesis_voice.py tests/test_genesis_voice_routes.py tests/test_genesis_workspace.py tests/test_genesis_voice_cancel.py tests/test_genesis_loop.py tests/test_genesis_threads.py tests/test_genesis_access.py tests/test_genesis_stream.py tests/test_genesis_stream_contract.py tests/test_genesis_show.py tests/test_genesis_build.py tests/test_voice_stt.py tests/test_static_csp.py -q`: **152 passed**, 11.76 seconds.
- `node tests/browser/genesis-voice.cjs`: **11 scenarios passed**.
- `node tests/browser/suite.cjs --only 'genesis voice'`: **2 scenarios passed**.
- `node tests/browser/suite.cjs --only 'studio: Genesis'`: **1 scenario passed**.
- Earlier existing `node tests/browser/suite.cjs --only genesis` checks passed.
- `node --check` passed for `genesis.js`, `voice-live.js` and `voice.js`.
- Scoped `git diff --check` passed; only existing Windows line-ending notices.
- Desktop (1440px) and mobile (390px) voice screenshots were visually inspected.
  Fixture evidence: `monarch-benchmark/workflowbench/.tmp/genesis-voice-browser/`.
- Final independent scoped review found no remaining material issues after the
  mute acknowledgment, stale delegation, fast navigation, pre-truncation facts
  and final saved-state fixes.

A useful-answer regression first failed because the harness omitted `voice_facts`.
The harness now projects actual complete tool results before its normal trace
truncation. Tests confirm the resulting spoken pass count keeps its evaluated
denominator, preserves unknown costs and respects per-setup comparison eligibility.
No free-form model answer is treated as a verified result.

The repository-wide suite was not run; these are focused connection and shared
Genesis regressions, not a certification of unrelated work in the dirty tree.
