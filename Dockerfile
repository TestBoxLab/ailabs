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

# Genesis runs its turns through the Codex CLI (wb_studio/genesis_harness.py); without it every
# model route reads as unavailable on the configuration page and no turn can start.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg     && curl -fsSL https://deb.nodesource.com/setup_22.x | bash -     && apt-get install -y --no-install-recommends nodejs     && npm install -g @openai/codex     && codex --version     && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY research /app/research
COPY monarch-benchmark/workflowbench /app/monarch-benchmark/workflowbench

WORKDIR /app/monarch-benchmark/workflowbench
RUN uv sync --frozen --no-dev \
    && chmod +x scripts/studio-entrypoint.sh

EXPOSE 8765
CMD ["sh", "scripts/studio-entrypoint.sh"]
