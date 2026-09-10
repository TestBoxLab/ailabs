# Streaming Studio test research

Scope: new paid request gateway, local Studio job manager/API, graph streaming and rich output UI. Existing pytest style, temporary SQLite and mocked provider transports.

Requirements: bounded paid admission before every request; unknown billing retains hold; credentials never emitted; model comparison with task drilldowns; restart-safe job history; cancellation; SSE reconnect; rich outputs escape untrusted content; native unavailability disclosed.
