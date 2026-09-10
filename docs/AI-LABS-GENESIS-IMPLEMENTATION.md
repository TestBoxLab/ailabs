# Genesis implementation and acceptance

Date: 2026-09-09. Local preview: http://127.0.0.1:8766/#genesis

## Implemented

- Genesis conversation routes the selected provider through installed Codex 0.153.4. A stable scientist wire alias prevents model-specific host tool expansion; the upstream model remains the selected actual model. GPT Responses, Anthropic, Gemini, and compatible chat adapters support public output streams and tool continuation. Gemini signed tool parts are retained privately between requests.
- Isolated Codex home, host skill discovery disabled, shell/image/subagent tools disabled, scoped MCP lab tools. Scientist instructions live in `wb_studio/GENESIS.md`; this is instruction-based behavior, not fine-tuning. Benchmark harnesses retain their existing native identities.
- Persistent research cards, revisions and history; research, hypotheses, review, experiments, findings and decisions stages. Completed experiments can record decisions without rewriting the approved proposal.
- Exact revision/digest approval for runs, product-graph preparation and paid analysis. The scientist has no approve or launch tool. Changes invalidate unlaunched approval; Studio still validates configuration and reserves capacity.
- Scientist tools inspect prior research, page through task evidence, record cited analyses, discover paper metadata, create graph drafts and publish architecture versions. Unchanged analyzed evidence is reused. Metadata discovery is explicitly not a full-paper review.
- Interrupted conversation/preparation records move to an honest attention state on server restart; no automatic paid replay. Unknown charges remain reserved.
- Square light research desk and conversation; operation-specific approval review. Real run workstreams show public output, task state and knowledge delivery. Keyed cards retain scroll and stop transfer motion after delivery. Historical output is labeled recorded.
- Server-derived model/thinking Bare eligibility, explicit use of published architecture models, delayed-script startup fix, browser Back and reloadable run URLs. Outcome summaries show a failed requirement instead of only a count.

## Verification

243 focused offline tests passed in 24.97 seconds. Coverage includes approval/idempotence/recovery, actual installed Codex SSE-to-MCP round trips for four provider selections, provider continuation, streamed tool fragments, cache receipts, precision rounding, complete-run leaderboard eligibility, node execution and budget controls.

`artifacts/genesis-check/final-browser-check.cjs` passed in actual Chrome: desktop/mobile no overflow or JavaScript errors, Back navigation, run reload, saved-model mode, preparation review, and one-shot delivery animation retaining its DOM through a text update. Screenshots named `proposal-fixture` and `mobile-final` contain clearly labeled synthetic UI data; `recorded-workstreams` shows existing historical evidence. No benchmark runs were launched for these checks.

## Live acceptance remains pending

Two minimal Gemini routing checks reached actual provider output. The second completed the lab tool round trip and returned ROUTE_OK, but settlement failed because floating-point cost exceeded the ledger's six-decimal precision. The existing conservative rounding helper now fixes this; an offline regression asserts 0.012345678 settles as 0.012346, with the receipt recorded before settlement. It has not been reverified live.

Those checks added $0.005328 in verified cost. $0.664268 remains held for requests whose receipt was not retained before the failure. It is not claimed as actual spend and has not been released without billing evidence.

Automatic approval review rejected further live provider validation, including after the synthetic tool interception was proved offline. The requested next check is GPT, Claude, Gemini and Kimi through the same Codex bridge, using only a hard-coded synthetic tool result, capped at $1 per route ($4 total), with no workspace research data or benchmark launches. User approval is required before retrying that rejected action. Available routes remain labeled live-unverified in the UI.

Remaining limits: paid full-run analysis retains its existing context ceiling; Genesis can inspect paginated evidence instead. Paper discovery currently provides Crossref metadata, not full-text retrieval. The board is local, not a new Trello synchronization. Conversation history is bounded to eight preceding exchanges plus persisted notebook/evidence tools. This work does not establish live acceptance for every provider/model in the catalog.


## Chat cleanup — 2026-09-09

Removed the chat spend field, analyzed-runs display, route disclaimers and empty-column filler. Backend budget admission and analysis deduplication remain active. The composer has model-family colors, readable model names, keyboard selection, Enter-to-send, Shift+Enter newlines and safe basic Markdown formatting. Thinking choices use the existing provider vocabulary, are validated before reservation, persisted with each turn and forwarded to the provider. Providers without an effort control show disabled Default.

Verification: chat-cleanup.cjs exercises desktop/mobile rendering and an intercepted chat request, asserting Gemini/high and no client maximum_usd field. Its response screenshots use synthetic UI content. Focused Genesis/protocol/streaming suite: 62 passed. No paid calls during this cleanup.

| Requirement | Evidence |
|---|---|
| Selected thinking stored; spend field optional | test_chat_persists_selected_thinking_without_client_spend_field |
| Unsupported effort refused before reservation | test_chat_rejects_unsupported_thinking_before_spending |
| Selected thinking reaches provider body | test_broker_rounds_cost_and_settles_receipt_before_turn_outcome |
