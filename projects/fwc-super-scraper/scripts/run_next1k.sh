#!/usr/bin/env bash
# Next-1,000 run: extend the dataset by crawling 20 pages starting at
# $1 (default 120), then sweep pages 0..9 for any new approvals that
# landed since the prior run. Idempotent — already-known ae_ids are
# upserted, already-extracted PDFs are skipped.
set -euo pipefail

START_PAGE="${1:-120}"
END_PAGE=$((START_PAGE + 19))

cd "$(dirname "$0")/.."
LOG="data/next1k.log"
export LOG_FILE="$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "=== next1k started: $(date -Iseconds)  start_page=$START_PAGE ==="

# 1a. Crawl 20 pages — the next ~1,000 older Approved agreements.
echo "[1a/5] crawl pages $START_PAGE..$END_PAGE"
.venv/bin/fwc crawl --pages 20 --start-page "$START_PAGE" --delay 0.8

# 1b. Catch-up sweep at top (any approvals since 2026-05-10).
echo "[1b/5] catch-up crawl pages 0..9"
.venv/bin/fwc crawl --pages 10 --start-page 0 --delay 0.8

# 2. Enrich any rows missing industry / canonical pdf URL.
echo "[2/5] enrich"
.venv/bin/fwc enrich --delay 0.8

# 3. Download PDFs for any row that doesn't have one yet.
echo "[3/5] download"
.venv/bin/fwc download --delay 0.6

# 4. Extract via the chunked respawn wrapper (handles pdfplumber memory leak).
echo "[4/6] extract (chunked)"
BATCH=10 BATCH_TIMEOUT=1200 bash scripts/extract_chunked.sh

# 5. APRA ABN/USI backfill for any new default_super rows.
echo "[5/6] apra backfill"
.venv/bin/python3 scripts/apra_backfill.py

# 6. Final stats.
echo "[6/6] stats"
.venv/bin/fwc stats

echo "=== next1k finished: $(date -Iseconds) ==="
