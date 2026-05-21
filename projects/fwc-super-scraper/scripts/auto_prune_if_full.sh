#!/usr/bin/env bash
# Run the PDF prune iff disk usage on / has crossed the threshold.
# Stdout/stderr is captured by systemd journal; keep messages compact.
set -euo pipefail

THRESHOLD_GIB="${THRESHOLD_GIB:-81}"
ROOT="/root/VPS/projects/fwc-super-scraper"

cd "$ROOT"

USED_KB=$(df --output=used / | tail -1)
THRESHOLD_KB=$((THRESHOLD_GIB * 1024 * 1024))
USED_GIB=$(( (USED_KB + 512*1024) / 1024 / 1024 ))

echo "$(date -u +%FT%TZ) used=${USED_GIB}GiB threshold=${THRESHOLD_GIB}GiB"

if [ "$USED_KB" -lt "$THRESHOLD_KB" ]; then
    echo "below threshold — no prune"
    exit 0
fi

echo "above threshold — running prune"
exec .venv/bin/python scripts/prune_extracted_pdfs.py --apply
