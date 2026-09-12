# Streaming Studio test plan

Gateway tests: reserve/claim ordering, max request cost, provider error/unknown usage holds, verified usage settlement, budget exhaustion, cancellation.
Server tests: same-origin write protection, task/provider allowlists, durable jobs and monotonic events, reconnect cursor, comparison task identity, no arbitrary file access.
UI validation: real streamed scripted task followed by bounded paid pilot if credentials available; desktop/mobile comparison and output interaction; HTML/script injection payload rendered as text.


## Feature 027 report scope — 2026-09-11

Lifecycle/citation/coverage regressions precede implementation; pattern and
browser implementation delegated separately. Independent backend review checks
cost, paging and interruptions. Tests use deterministic model doubles, real
native loop and real ledger for integration; browser checks use scripted evidence.
Acceptance matrix, exact tests and final command are recorded in
specs/027-genesis-report-authoring/validation.md.
