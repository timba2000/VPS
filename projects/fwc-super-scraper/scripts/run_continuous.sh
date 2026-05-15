#!/usr/bin/env bash
# Continuous loop: keep cycling crawl → enrich → download → extract → backfill
# until one of two stop conditions hits:
#   1. extraction row count >= $TARGET_EXTRACTED   (primary)
#   2. $MAX_EMPTY_CYCLES consecutive cycles with no new agreements AND no new
#      extractions                                  (safety net)
#
# Each phase is idempotent; failures are logged and the loop continues so a
# single transient error doesn't kill the service. State (page cursor, empty
# counter) lives in data/continuous_state.env so a systemd restart resumes
# where it left off.
set -uo pipefail
cd "$(dirname "$0")/.."

TARGET_EXTRACTED="${TARGET_EXTRACTED:-8000}"
PAGES_PER_CYCLE="${PAGES_PER_CYCLE:-20}"
CATCHUP_PAGES="${CATCHUP_PAGES:-10}"
MAX_EMPTY_CYCLES="${MAX_EMPTY_CYCLES:-3}"
CYCLE_DELAY="${CYCLE_DELAY:-180}"
BATCH="${BATCH:-10}"
BATCH_TIMEOUT="${BATCH_TIMEOUT:-1200}"

STATE_FILE="data/continuous_state.env"
LOG="data/continuous.log"
export LOG_FILE="$LOG"
exec > >(tee -a "$LOG") 2>&1

PAGE_CURSOR="${START_PAGE:-140}"
EMPTY_CYCLES=0
CYCLE_NO=0
if [[ -r "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
fi

save_state() {
    cat > "$STATE_FILE" <<EOF
PAGE_CURSOR=$PAGE_CURSOR
EMPTY_CYCLES=$EMPTY_CYCLES
CYCLE_NO=$CYCLE_NO
EOF
}

PY=".venv/bin/python3"
FWC=".venv/bin/fwc"

count_sql() {
    $PY -c "
from fwc_super.db import connect
print(connect().execute('''$1''').fetchone()[0])
"
}

echo
echo "=== continuous started: $(date -Iseconds)  target=$TARGET_EXTRACTED  page_cursor=$PAGE_CURSOR  empty=$EMPTY_CYCLES ==="

while true; do
    CYCLE_NO=$((CYCLE_NO + 1))
    echo
    echo "=== cycle $CYCLE_NO  page_cursor=$PAGE_CURSOR  empty=$EMPTY_CYCLES  $(date -Iseconds) ==="

    EXT_NOW=$(count_sql "SELECT COUNT(*) FROM extraction")
    if (( EXT_NOW >= TARGET_EXTRACTED )); then
        echo "[target reached] extraction=$EXT_NOW >= $TARGET_EXTRACTED  stopping"
        break
    fi
    echo "[progress] extraction=$EXT_NOW / $TARGET_EXTRACTED"

    BEFORE_AGS=$(count_sql "SELECT COUNT(*) FROM agreements")

    echo "[crawl] pages $PAGE_CURSOR..$((PAGE_CURSOR + PAGES_PER_CYCLE - 1))"
    $FWC crawl --pages "$PAGES_PER_CYCLE" --start-page "$PAGE_CURSOR" --delay 0.8 \
        || echo "[crawl] failed rc=$?"

    echo "[catch-up crawl] pages 0..$((CATCHUP_PAGES - 1))"
    $FWC crawl --pages "$CATCHUP_PAGES" --start-page 0 --delay 0.8 \
        || echo "[catch-up crawl] failed rc=$?"

    echo "[enrich]"
    $FWC enrich --delay 0.8 || echo "[enrich] failed rc=$?"

    echo "[download]"
    $FWC download --delay 0.6 || echo "[download] failed rc=$?"

    echo "[extract chunked]  BATCH=$BATCH timeout=${BATCH_TIMEOUT}s"
    BATCH="$BATCH" BATCH_TIMEOUT="$BATCH_TIMEOUT" bash scripts/extract_chunked.sh \
        || echo "[extract] failed rc=$?"

    echo "[apra backfill]"
    $PY scripts/apra_backfill.py || echo "[apra] failed rc=$?"

    AFTER_AGS=$(count_sql "SELECT COUNT(*) FROM agreements")
    AFTER_EXT=$(count_sql "SELECT COUNT(*) FROM extraction")
    NEW_AGS=$((AFTER_AGS - BEFORE_AGS))
    NEW_EXT=$((AFTER_EXT - EXT_NOW))
    echo "[delta] new_agreements=$NEW_AGS new_extractions=$NEW_EXT total_extracted=$AFTER_EXT"

    if (( NEW_AGS == 0 && NEW_EXT == 0 )); then
        EMPTY_CYCLES=$((EMPTY_CYCLES + 1))
        echo "[empty cycle] streak=$EMPTY_CYCLES/$MAX_EMPTY_CYCLES"
    else
        EMPTY_CYCLES=0
    fi

    PAGE_CURSOR=$((PAGE_CURSOR + PAGES_PER_CYCLE))
    save_state

    if (( EMPTY_CYCLES >= MAX_EMPTY_CYCLES )); then
        echo "=== stopping: $EMPTY_CYCLES empty cycles (corpus appears exhausted) ==="
        break
    fi

    if (( AFTER_EXT >= TARGET_EXTRACTED )); then
        echo "=== stopping: extraction=$AFTER_EXT >= target=$TARGET_EXTRACTED ==="
        break
    fi

    echo "[sleep] ${CYCLE_DELAY}s before next cycle"
    sleep "$CYCLE_DELAY"
done

echo
echo "[final stats]"
$FWC stats || true
echo "=== continuous finished: $(date -Iseconds)  cycles=$CYCLE_NO ==="
