# Studio node editor cleanup — 9 September 2026

Product graphs are source-only knowledge plugins. The editor shows no input port and offers only compatible agent connections. Server validation independently refuses incoming knowledge links and links from knowledge to merges or Result Output. A knowledge source does not need a path from Task Input, but its agent must belong to the task-to-result flow. The informed template now has Task Input → Worker → Result Output, with Product graph → Worker alongside it. No historical files were migrated or overwritten.

The runtime gives product knowledge only to explicitly connected agents. Previous agent and merge outputs travel through normal flow connections. Task Input records the task brief as observable output. Stable instructions precede per-attempt predecessor text to preserve a reusable prompt prefix.

The editor uses a responsive canvas/inspector layout without capped inspector height. More contains Run latest version, Expand editor, and Back to runs. Escape exits expansion. Version choices contain only the version number; architecture and product graph choices contain their names. Preparation fields remain available in a disclosure. Incompatible drag insertion is refused before the graph changes. Fit to view can zoom below the previous 35% floor so wide graphs fit narrow screens.

A definite session-token rejection after a local server restart refreshes the token and retries once. Uncertain writes and server failures are never automatically replayed. Initialization holds the new-architecture button until the catalogs finish loading.

## Prompt caching audit

Anthropic already marks tool and system prefixes and sends request-level ephemeral cache control. Cached reads and cache writes are retained separately and used in cost accounting. Its offline request test now explicitly checks request-level cache control as well as the system breakpoint. OpenAI and Gemini retain their automatic caching behavior; no paid explicit cache storage or native harness changes were introduced. Actual cache hits are provider receipts, not a guarantee inferred from configuration. No paid model requests were made for this change.

Sources: [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Gemini context caching](https://ai.google.dev/gemini-api/docs/generate-content/caching), [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5).

## Verification

| Requirement | Evidence |
|---|---|
| Source-only agent plugin; reject incompatible edges | `test_product_knowledge_is_a_source_only_agent_plugin` |
| Explicit knowledge delivery; previous output retained; static prefix first | `test_connected_knowledge_and_previous_output_have_separate_delivery` |
| Published planner → worker → output runs end to end | `test_published_planner_worker_architecture_is_ready_and_executes_step_by_step` |
| Prepared knowledge delivered in scored attempt | `test_product_graph_is_prepared_once_and_its_records_flow_into_scored_attempts` |
| Stable cached tool prefix, system and request cache markers, receipt accounting | `test_tools_prefix_is_stable_and_cached`, `test_turn_normalizes_usage_and_echoes_thinking`, `test_cost_prices_cache_write_separately` |
| Offline validation | `.venv/Scripts/python.exe -m pytest tests/test_studio_execution.py tests/test_studio_blueprints.py tests/test_anthropic_adapter.py -q`: **63 passed** |
| Chrome desktop, tablet, mobile; expansion/Escape; concise selectors; token recovery | `artifacts/studio-refactor/node-cleanup-check.cjs`: passed, zero page errors, mobile document width 390/390 px |

CUA initialization failed in the Windows tool kernel; browser interaction and screenshot review used locally installed Chrome through Playwright. Screenshots: `node-cleanup-desktop.png`, `node-cleanup-expanded.png`, `node-cleanup-tablet.png`, `node-cleanup-mobile.png` in `artifacts/studio-refactor/`.

## Square visual direction — 9 September follow-up

User direction: every UI element should be square, retaining the light style with more technical character. Shared styles now enforce square corners (including SVG rectangles), stronger ink and border contrast, flat tabs, solid active navigation, and graph-paper canvas geometry. Product knowledge fields use a definition list: path, type, and description. Preparation timestamp/status/fingerprint have a separate disclosure; the colored metadata pile and inline "since v1" labels are removed.

Verified in Chrome with `artifacts/studio-refactor/square-check.cjs`: zero visible elements with rounded CSS corners, working field disclosure and navigation, no mobile horizontal overflow, no page errors. Visually reviewed `square-studio.png`, `square-budget.png`, and `square-mobile.png`. No runtime or stored-result changes in this follow-up.
