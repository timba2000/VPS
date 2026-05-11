"""Insert rows into default_super from the empirical-recall audit log.

Reads data/empirical_recall.jsonl produced by scripts/empirical_recall_scan.py
and writes one row per (ae_id, fund) it discovered, tagged with
source='rescan_2026-05-11'. Idempotent — uses INSERT OR IGNORE on the
(ae_id, fund_name) primary key, so re-running adds nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fwc_super.db import connect

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "empirical_recall.jsonl"
SOURCE_TAG = "rescan_2026-05-11"


def main() -> int:
    if not LOG.exists():
        print(f"missing {LOG}", file=sys.stderr)
        return 1
    conn = connect()
    inserted = 0
    skipped_existing = 0
    rows = 0
    with LOG.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            funds = row.get("funds")
            ae_id = row.get("ae_id")
            if not funds or not ae_id or row.get("error"):
                continue
            rows += 1
            for fund in funds:
                cur = conn.execute(
                    "SELECT 1 FROM default_super WHERE ae_id = ? AND fund_name = ?",
                    (ae_id, fund),
                )
                if cur.fetchone():
                    skipped_existing += 1
                    continue
                conn.execute(
                    "INSERT INTO default_super (ae_id, fund_name, source_excerpt, source) "
                    "VALUES (?, ?, ?, ?)",
                    (ae_id, fund, None, SOURCE_TAG),
                )
                inserted += 1
    print(f"jsonl rows scanned:    {rows}")
    print(f"default_super inserts: {inserted}  (source={SOURCE_TAG})")
    print(f"skipped (already had): {skipped_existing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
