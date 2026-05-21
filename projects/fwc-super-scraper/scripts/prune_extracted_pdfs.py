"""Delete PDFs whose extraction has succeeded.

A PDF is considered "correctly extracted" and safe to delete iff:
  - An extraction row exists for the ae_id
  - extraction.too_large = 0
  - Either at least one raw_*_excerpt is populated, OR no_default_named = 1

Files modified within the last 60s are skipped, to avoid racing with an
active downloader. After unlink, agreements.pdf_path is set to NULL;
pdf_sha256 and pdf_bytes are preserved as evidence the PDF existed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from fwc_super.db import connect

CANDIDATE_SQL = """
SELECT a.ae_id, a.pdf_path, a.pdf_bytes
FROM agreements a
JOIN extraction e ON e.ae_id = a.ae_id
WHERE a.pdf_path IS NOT NULL
  AND e.too_large = 0
  AND (
       e.raw_super_excerpt  IS NOT NULL
    OR e.raw_signed_excerpt IS NOT NULL
    OR e.raw_signer_excerpt IS NOT NULL
    OR e.no_default_named = 1
  )
"""

MTIME_GUARD_SECONDS = 60


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete files and update DB. Default is dry-run.")
    parser.add_argument("--limit", type=int, default=0, help="Cap candidates (0 = no cap).")
    args = parser.parse_args()

    dry_run = not args.apply
    now = time.time()

    conn = connect()
    rows = conn.execute(CANDIDATE_SQL).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    deleted = 0
    skipped_recent = 0
    skipped_missing = 0
    bytes_freed = 0

    for row in rows:
        path = Path(row["pdf_path"])
        if not path.exists():
            skipped_missing += 1
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            skipped_missing += 1
            continue
        if now - mtime < MTIME_GUARD_SECONDS:
            skipped_recent += 1
            continue

        size = row["pdf_bytes"] or path.stat().st_size
        if dry_run:
            deleted += 1
            bytes_freed += size
            continue

        try:
            path.unlink()
        except OSError as exc:
            print(f"unlink failed for {path}: {exc}", file=sys.stderr)
            continue
        conn.execute("UPDATE agreements SET pdf_path = NULL WHERE ae_id = ?", (row["ae_id"],))
        deleted += 1
        bytes_freed += size

    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"[{mode}] candidates={len(rows)} deleted={deleted} "
          f"skipped_recent={skipped_recent} skipped_missing={skipped_missing} "
          f"freed={bytes_freed/1024/1024/1024:.2f} GiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
