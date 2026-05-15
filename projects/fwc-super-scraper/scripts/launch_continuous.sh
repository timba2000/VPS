#!/usr/bin/env bash
# Launch run_continuous.sh as a systemd-run transient unit with the same
# memory limits and slice used by CLAUDE.md's documented long-run pattern.
# Refuses to start if the unit is already active.
set -euo pipefail
cd "$(dirname "$0")/.."

UNIT="${UNIT:-fwc-continuous}"
TARGET_EXTRACTED="${TARGET_EXTRACTED:-8000}"
START_PAGE="${START_PAGE:-140}"

if systemctl is-active --quiet "$UNIT.service"; then
    echo "Unit $UNIT.service is already active." >&2
    echo "  status:  systemctl status $UNIT" >&2
    echo "  logs:    journalctl -u $UNIT -f   (or tail -f data/continuous.log)" >&2
    echo "  stop:    systemctl stop $UNIT" >&2
    exit 1
fi

echo "Launching $UNIT.service  target=$TARGET_EXTRACTED  start_page=$START_PAGE"
systemd-run \
    --slice=system.slice \
    --unit="$UNIT" \
    --property=MemoryHigh=5G \
    --property=MemoryMax=6G \
    --property=WorkingDirectory="$PWD" \
    --setenv=TARGET_EXTRACTED="$TARGET_EXTRACTED" \
    --setenv=START_PAGE="$START_PAGE" \
    /bin/bash scripts/run_continuous.sh

echo "Launched. Follow with: tail -f data/continuous.log"
