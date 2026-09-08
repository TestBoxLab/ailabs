#!/bin/sh
# Start the AI Labs Studio on a host with a persistent volume (Railway).
# STUDIO_DATA_DIR (default /data) keeps the Studio jobs, product graphs, blueprints and the
# weekly budget ledger across deploys. On the first boot the image's out/studio folder seeds it,
# so the runs made before hosting stay visible. PORT comes from the platform.
set -eu
DATA="${STUDIO_DATA_DIR:-/data}"
mkdir -p "$DATA/studio" "$DATA/research"
if [ -z "$(ls -A "$DATA/studio" 2>/dev/null)" ] && [ -d out/studio ]; then
  echo "seeding $DATA/studio from the image"
  cp -R out/studio/. "$DATA/studio/"
fi
if [ ! -f "$DATA/research/budget.sqlite3" ] && [ -f /app/research/budget.sqlite3 ]; then
  cp /app/research/budget.sqlite3 "$DATA/research/budget.sqlite3"
fi
exec uv run --frozen --no-dev python -m wb_studio.app --host "${STUDIO_HOST:-0.0.0.0}" --port "${PORT:-8765}"
