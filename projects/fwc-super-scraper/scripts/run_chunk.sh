#!/usr/bin/env bash
# Parameterized chunk runner — crawl + enrich + download + extract.
# Usage: START_PAGE=20 PAGES=40 bash scripts/run_chunk.sh
# Idempotent: each stage skips work already done.
set -euo pipefail

START_PAGE="${START_PAGE:-0}"
PAGES="${PAGES:-20}"

cd "$(dirname "$0")/.."
LOG="data/chunk_${START_PAGE}_$((START_PAGE + PAGES - 1)).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== chunk started: $(date -Iseconds) start_page=${START_PAGE} pages=${PAGES} ==="

echo "[1/4] crawl pages ${START_PAGE}..$((START_PAGE + PAGES - 1))"
.venv/bin/fwc crawl --pages "${PAGES}" --start-page "${START_PAGE}" --delay 0.8

echo "[2/4] enrich"
.venv/bin/fwc enrich --delay 0.8

echo "[3/4] download"
.venv/bin/fwc download --delay 0.6

echo "[4/4] extract"
.venv/bin/fwc extract

echo "=== chunk finished: $(date -Iseconds) ==="
.venv/bin/fwc stats
