# AI Labs Studio on Railway (unblock plan, decision D4: the web app is a front door too).
#
# Build context: the repo root uploaded by `railway up --no-gitignore` (see .railwayignore for
# what stays out). The vendored AutomationBench package must be present at
# monarch-benchmark/workflowbench/vendor/automation-bench; it is gitignored, hence --no-gitignore.
# Runtime state (Studio jobs, product graphs, the weekly budget ledger) lives on the volume
# mounted at /data (STUDIO_DATA_DIR); the image's out/studio folder seeds it on first boot.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    STUDIO_DATA_DIR=/data \
    STUDIO_HOST=0.0.0.0

WORKDIR /app
COPY research /app/research
COPY monarch-benchmark/workflowbench /app/monarch-benchmark/workflowbench

WORKDIR /app/monarch-benchmark/workflowbench
RUN uv sync --frozen --no-dev \
    && chmod +x scripts/studio-entrypoint.sh

EXPOSE 8765
CMD ["sh", "scripts/studio-entrypoint.sh"]
