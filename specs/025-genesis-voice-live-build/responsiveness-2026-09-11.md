# Genesis voice responsiveness investigation — 11 September 2026

## Observed production evidence

Read-only Railway inspection found ailabs-studio deployment
351a703d-195f-455e-a58b-fcf495058449 successful. Its runtime logs contained startup
messages, not per-delegation or provider timing. A bounded 1,000-row HTTP sample
included four voice sessions. The busiest session had 181 status requests,
averaging 10.7 ms server duration and 48.4 KiB responses, peaking at 101.5 KiB.
98 GET /api/genesis requests averaged 60.3 ms and 288.3 KiB. Turn event streams
lasted roughly 9–51 seconds; these durations do not isolate model inference,
tool time, queue time, or browser playback. Payload churn is demonstrated;
its contribution to perceived latency has not been measured.

The local configured default is gpt-6-astra at medium effort. The live environment
has an OpenAI key, but SSH was unavailable because no SSH key is registered.
The persisted live model override, turn traces, transcripts and detailed provider
timings could not be inspected. No model switch is justified by these observations.
Raw audio was not available. The bounded HTTP sample is in the ignored
.tmp/railway-genesis-http.jsonl and includes request metadata; do not publish it.

## Local corrections

- Voice GET status accepts at most twelve known turn IDs. It keeps ownership
  checks and returns full new turns, omitting turns already accepted by the
  browser's existing event stream. The browser acknowledges a turn only after
  successful acceptance, so failed acceptance can retry.
- Narration now notices completed tool receipts even when a tool starts and
  finishes between sideband ticks. It delivers the first validated fact while
  the overall task remains running, with existing rate limiting.
- A model_started phase still pending after five observed seconds gets one
  factual waiting update. Generated answer text is never substituted for a
  verified receipt, and no repeating filler heartbeat was added.
- Current voice, model routing, orb art, idle policy and paid admission policy
  were not changed by this correction.

The shared-root weekly billing check differs from the separately deployed
release's reported authorized policy. Do not deploy the shared root wholesale.
The separate panel-art task reports isolated commit 714b8c4 and subsequent work;
its integration and deployment are outside this change.

## Verification

74 focused voice/progress/route/cancellation tests passed (6.31 seconds).
17 offline browser scenarios passed. Scoped git diff --check passed.

Exact regression names:
- test_fast_tool_receipt_is_spoken_while_next_model_request_runs
- test_model_wait_is_delayed_and_announced_once_without_generated_text
- test_known_voice_turns_are_omitted_without_hiding_new_delegations

No live deployment, paid model call or benchmark round was launched.
Remaining work: obtain authorized persisted session timing access and perform a
live acceptance run after the scoped changes are integrated into the current
release. Local checks do not prove improved deployed latency or speech delivery.

## Extended responsiveness and durability implementation

Local changes now also include:

- Exact, standalone navigation requests use the validated `show` tool immediately,
  before any model request. Compound, conditional and ambiguous requests still go
  through the reasoning harness. The receipt says the link is ready; browser Follow
  controls whether the page actually moves.
- `person_remember` appends or corrects one bounded profile entry without overwriting
  unrelated facts. Duplicate writes are idempotent; capacity and credential rules
  remain enforced. Profile replacement uses atomic file replacement. Voice loads
  the current person's profile, and confirms memory only from successful receipts.
- Voice delegations send the newly requested transcript instead of repeating all
  earlier user speech on every turn; durable thread history supplies prior context.
- Browser session storage remembers the active conversation and authenticated owner.
  Refresh restores its persisted turns and parent without replaying page navigation
  or automatically activating the microphone. Stale thread reads cannot replace a
  newly selected conversation.
- Page detach closes the media session with a keepalive request while preserving
  accepted backend work. Transport failure and the media hard lifetime likewise
  preserve accepted tasks. Explicit stop/pause still cancels. Unknown provider usage
  remains unknown; a detached task is not considered completed merely by surviving.
- `read_web` returns paged public-source text with citation URL and retrieval time,
  without starting an extraction model or creating a card. Existing scholarly search
  and durable source extraction remain available. Public-address checks now cover
  each derived fetch and redirect, and credential-bearing URLs are refused. This
  retains the existing DNS check/connect race; it is not a pinned-IP network sandbox.

### Verification of the extended changes

- 102 focused responsiveness, voice, routing, loop, profile and cancellation checks
  passed in 8.30 seconds before the additional web changes.
- 52 responsiveness, source-fetch guard and ingest checks passed in 2.10 seconds
  after web changes. These groups overlap; their counts must not be added.
- Three real Chrome integration checks passed, including an actual page reload that
  restores the same conversation and parent while preserving the current page.
- 17 standalone voice browser scenarios passed, with desktop/mobile screenshots.
- Runtime tool inventory: 72 registered actions, none lacking an explicit schema.
- GitHub metadata reads verified local access to TestBoxLab/ailabs and
  TestBoxLab/monarch. This does not establish deployed service credentials.

Key additional regressions:
`test_remember_survives_restart_and_enters_new_conversation`,
`test_memory_correction_and_refusal_preserve_other_entries`,
`test_direct_navigation_emits_receipt_without_model_request`,
`test_media_detach_keeps_accepted_work_running_through_final_usage`,
`test_media_transport_loss_preserves_task_but_retains_unknown_billing`,
`test_direct_web_read_pages_evidence_without_starting_another_turn`, and
`test_source_redirect_refuses_private_destination_before_following`.

These changes are local. General web discovery, separately hosted repair execution,
GitHub App provisioning and live deployment acceptance remain unfinished.


## Spoken memory recall checkpoint

A `person_read` receipt can now project up to two complete saved profile entries
into spoken context. Empty profiles are stated explicitly. Failed reads, rejected
profile content and entries too long for one bounded append do not become invented
or clipped memories. Generated answer text is not substituted for a stored entry.
The model can paraphrase the verified receipt naturally under the existing Live
commentary handoff; this does not validate arbitrary model speech before playback.

`uv run python -m pytest tests/test_genesis_voice_progress.py tests/test_genesis_responsiveness.py -q`
passed **36 tests in 1.69 seconds**. Added exact checks:
`test_saved_memory_is_spoken_from_profile_receipt_without_generated_answer` and
`test_empty_and_long_profile_receipts_do_not_invent_or_cut_memories`.

The [official client-delegation guide](https://developers.openai.com/api/docs/guides/live-delegation)
was rechecked: commentary appends carry useful results for speech, while their
acknowledgements do not prove playback. No live speech or latency result was claimed.
