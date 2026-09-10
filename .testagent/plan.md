# Streaming Studio test plan

Gateway tests: reserve/claim ordering, max request cost, provider error/unknown usage holds, verified usage settlement, budget exhaustion, cancellation.
Server tests: same-origin write protection, task/provider allowlists, durable jobs and monotonic events, reconnect cursor, comparison task identity, no arbitrary file access.
UI validation: real streamed scripted task followed by bounded paid pilot if credentials available; desktop/mobile comparison and output interaction; HTML/script injection payload rendered as text.
