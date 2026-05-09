#!/usr/bin/env bash
# 1,000-row pilot — crawl + enrich + download + extract.
# Idempotent: each stage skips work already done.
set -euo pipefail

cd "$(dirname "$0")/.."
LOG="data/pilot.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== pilot started: $(date -Iseconds) ==="

# 1. Crawl pages 0..19 (50 rows × 20 = 1000). Already-seen pages are upserted.
echo "[1/4] crawl pages 0..19"
.venv/bin/fwc crawl --pages 20 --start-page 0 --delay 0.8

# 2. Enrich any rows missing industry. Skips ones already enriched.
echo "[2/4] enrich"
.venv/bin/fwc enrich --delay 0.8

# 3. Download PDFs for any row that doesn't have one yet.
echo "[3/4] download"
.venv/bin/fwc download --delay 0.6

# 4. Extract default super / term / signed / signatories from new PDFs.
echo "[4/4] extract"
.venv/bin/fwc extract

echo "=== pilot finished: $(date -Iseconds) ==="
.venv/bin/fwc stats
