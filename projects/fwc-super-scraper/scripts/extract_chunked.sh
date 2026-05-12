#!/usr/bin/env bash
# Chunked extract: runs `fwc extract --limit N` repeatedly until no
# unextracted PDFs remain. Each batch is a fresh process, so pdfplumber
# memory growth gets released between chunks.
set -u
cd "$(dirname "$0")/.."

BATCH="${BATCH:-50}"
PY=".venv/bin/python"
FWC=".venv/bin/fwc"

start=$(date +%s)
batch_no=0
while true; do
    remaining=$($PY -c "
from fwc_super.db import connect
c = connect()
print(c.execute(\"select count(*) from agreements a left join extraction e on a.ae_id=e.ae_id where e.ae_id is null and a.pdf_path is not null\").fetchone()[0])
")
    if [[ "$remaining" -le 0 ]]; then
        echo "ALL_DONE remaining=$remaining batches=$batch_no elapsed=$(( $(date +%s) - start ))s"
        break
    fi
    batch_no=$((batch_no + 1))
    echo "--- batch $batch_no  remaining=$remaining  $(date -u +%H:%M:%S) ---"
    PYTHONUNBUFFERED=1 $FWC extract --limit "$BATCH"
    rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "BATCH_FAIL rc=$rc batch=$batch_no; continuing"
    fi
done
