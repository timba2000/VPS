#!/usr/bin/env python3
"""Export the full extracted dataset to samples/dataset_full.csv.

One row per (agreement, default_fund). Agreements without a named default
fund still get one row with the fund_* fields blank.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fwc.sqlite"
OUT = ROOT / "samples" / "dataset_full.csv"

COLS = [
    "ae_id", "matter_number", "title", "company_name", "abn", "industry",
    "published_date", "expires",
    "date_signed", "term_start", "term_end",
    "confidence_super", "ocr", "no_default_named",
    "fund_name", "fund_abn", "fund_usi", "fund_source",
    "detail_url", "pdf_url",
]

SQL = """
SELECT
  a.ae_id, a.matter_number, a.title, a.company_name, a.abn, a.industry,
  a.published_date, a.expires,
  e.date_signed, e.term_start, e.term_end,
  e.confidence_super, e.ocr, e.no_default_named,
  d.fund_name, d.fund_abn, d.fund_usi, d.source AS fund_source,
  a.detail_url, a.pdf_url
FROM agreements a
JOIN extraction e ON e.ae_id = a.ae_id
LEFT JOIN default_super d ON d.ae_id = a.ae_id
ORDER BY a.ae_id, d.fund_name
"""


def main() -> int:
    if not DB.exists():
        print(f"db not found: {DB}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    try:
        rows = conn.execute(SQL).fetchall()
    finally:
        conn.close()
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
