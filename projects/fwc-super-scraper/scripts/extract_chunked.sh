#!/usr/bin/env bash
# Chunked extract: runs `fwc extract --limit N` repeatedly until no
# unextracted PDFs remain. Each batch is a fresh process, so pdfplumber
# memory growth gets released between chunks.
#
# Watchdog: each batch is wrapped in `timeout $BATCH_TIMEOUT`. On timeout
# (rc=124), the in-flight ae_id is parsed from $LOG_FILE and quarantined
# via `extraction.too_large=1`, so the next batch skips it. $LOG_FILE
# must point at the file the wrapper writes the script's stdout to.
set -u
cd "$(dirname "$0")/.."

BATCH="${BATCH:-10}"
BATCH_TIMEOUT="${BATCH_TIMEOUT:-1200}"
LOG_FILE="${LOG_FILE:-}"
PY=".venv/bin/python"
FWC=".venv/bin/fwc"

quarantine_in_flight() {
    if [[ -z "$LOG_FILE" || ! -r "$LOG_FILE" ]]; then
        echo "QUARANTINE_SKIP no readable LOG_FILE; in-flight ae_id unknown"
        return
    fi
    local ae_id
    ae_id=$(awk '
        /^\[extract\] start / { in_flight = $3; next }
        /^AE[0-9]+\t/         { in_flight = "" }
        END                   { print in_flight }
    ' "$LOG_FILE")
    if [[ -z "$ae_id" ]]; then
        echo "QUARANTINE_SKIP no in-flight ae_id found in $LOG_FILE"
        return
    fi
    echo "QUARANTINE $ae_id (batch exceeded ${BATCH_TIMEOUT}s)"
    $PY - "$ae_id" <<'PYEOF'
import sys
from fwc_super.db import connect
ae_id = sys.argv[1]
c = connect()
c.execute(
    "INSERT INTO extraction(ae_id, too_large) VALUES(?, 1) "
    "ON CONFLICT(ae_id) DO UPDATE SET too_large=1",
    (ae_id,),
)
c.commit()
PYEOF
}

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
    PYTHONUNBUFFERED=1 timeout "$BATCH_TIMEOUT" $FWC extract --limit "$BATCH"
    rc=$?
    if [[ $rc -eq 124 ]]; then
        echo "BATCH_TIMEOUT batch=$batch_no after ${BATCH_TIMEOUT}s"
        quarantine_in_flight
    elif [[ $rc -ne 0 ]]; then
        echo "BATCH_FAIL rc=$rc batch=$batch_no; continuing"
    fi
done
