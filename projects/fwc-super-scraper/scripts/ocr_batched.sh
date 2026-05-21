#!/usr/bin/env bash
# Chunked OCR: runs `scripts/ocr_pipeline.py --limit N` repeatedly until
# the candidate set is empty. Each batch is a fresh process, so pdfplumber
# memory growth (from both _candidates() and the post-OCR extract_pdf())
# gets released between chunks.
#
# Watchdog: each batch is wrapped in `timeout $BATCH_TIMEOUT`. ocrmypdf
# itself has a 300s/PDF cap inside the script, so a runaway file kills
# only its own ocrmypdf subprocess, not the batch.
#
# Done condition: the script prints "selected 0 OCR candidates" when
# _candidates() finds nothing left.
set -u
cd "$(dirname "$0")/.."

BATCH="${BATCH:-10}"
BATCH_TIMEOUT="${BATCH_TIMEOUT:-1800}"
LOG_FILE="${LOG_FILE:-data/ocr_batched.log}"
PY=".venv/bin/python"

start=$(date +%s)
batch_no=0
mkdir -p "$(dirname "$LOG_FILE")"
echo "=== ocr-batched start $(date -u +%FT%TZ)  BATCH=$BATCH  TIMEOUT=${BATCH_TIMEOUT}s ===" | tee -a "$LOG_FILE"

while true; do
    batch_no=$((batch_no + 1))
    echo "--- batch $batch_no  $(date -u +%H:%M:%S) ---" | tee -a "$LOG_FILE"

    PYTHONUNBUFFERED=1 timeout "$BATCH_TIMEOUT" \
        "$PY" scripts/ocr_pipeline.py --limit "$BATCH" 2>&1 \
        | tee -a "$LOG_FILE"
    rc=${PIPESTATUS[0]}

    if [[ $rc -eq 124 ]]; then
        echo "BATCH_TIMEOUT batch=$batch_no after ${BATCH_TIMEOUT}s; continuing" | tee -a "$LOG_FILE"
    elif [[ $rc -ne 0 ]]; then
        echo "BATCH_FAIL rc=$rc batch=$batch_no; continuing" | tee -a "$LOG_FILE"
    fi

    # Done when the script reports an empty candidate set. Grep the tail of
    # this batch's output (last ~50 lines is plenty).
    if tail -n 50 "$LOG_FILE" | grep -q "selected 0 OCR candidates"; then
        echo "ALL_DONE batches=$batch_no elapsed=$(( $(date +%s) - start ))s" | tee -a "$LOG_FILE"
        break
    fi
done
