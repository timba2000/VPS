"""Run OCR on PDFs that the per-page heuristic flagged as scanned, then
re-extract super-fund matches and write them to the DB.

Selects up to --limit candidates that have:
  - extraction.ocr = 1
  - no rows in default_super
  - the PDF still on disk

For each candidate:
  1. Save a sibling copy at <pdf>.pre-ocr.pdf if not already saved.
  2. Run `ocrmypdf --force-ocr --quiet` in place.
  3. Re-run extract_pdf to get fresh text.
  4. Re-set extraction.ocr = 1, refresh super_excerpt + no_default_named.
  5. INSERT new default_super rows tagged source='ocr_2026-05-11'.

Idempotent: skips PDFs that already have a .pre-ocr.pdf sibling.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pdfplumber

from fwc_super.db import connect
from fwc_super.extract import _needs_ocr, extract_pdf

OCR_TAG = "ocr_2026-05-11"


def _candidates(conn, limit: int) -> list[tuple[str, str]]:
    """Open each unmatched PDF and pick those where the per-page heuristic says
    OCR is needed. Stops once we have `limit` candidates."""
    sql = """
        SELECT a.ae_id, a.pdf_path FROM extraction e
        JOIN agreements a ON a.ae_id = e.ae_id
        LEFT JOIN default_super d ON d.ae_id = e.ae_id
        WHERE d.ae_id IS NULL AND a.pdf_path IS NOT NULL
    """
    chosen: list[tuple[str, str]] = []
    scanned = 0
    for row in conn.execute(sql):
        if len(chosen) >= limit:
            break
        scanned += 1
        path = Path(row["pdf_path"])
        if not path.exists():
            continue
        try:
            with pdfplumber.open(path) as pdf:
                lengths = [len(p.extract_text() or "") for p in pdf.pages]
        except Exception:
            continue
        if _needs_ocr(lengths):
            chosen.append((row["ae_id"], row["pdf_path"]))
        if scanned % 50 == 0:
            print(f"  …scanned {scanned}, found {len(chosen)} OCR candidates", flush=True)
    print(f"selected {len(chosen)} OCR candidates from {scanned} unmatched PDFs", flush=True)
    return chosen


def _ocr_inplace(pdf: Path) -> tuple[bool, str]:
    backup = pdf.with_suffix(pdf.suffix + ".pre-ocr.pdf")
    if not backup.exists():
        shutil.copy2(pdf, backup)
    cmd = [
        "ocrmypdf",
        "--force-ocr",  # ignore existing text on otherwise-blank pages
        "--quiet",
        "--output-type", "pdf",
        "--optimize", "0",
        str(pdf), str(pdf),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if proc.returncode != 0:
        return False, f"rc={proc.returncode} {(proc.stderr or '')[:200]}"
    return True, ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=50, help="Max PDFs to OCR.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print candidates only; don't run OCR or write DB.")
    args = p.parse_args()

    conn = connect()
    cands = _candidates(conn, args.limit)
    print(f"OCR candidates: {len(cands)} (limit {args.limit})", flush=True)
    if args.dry_run:
        for ae, path in cands[:20]:
            print(f"  {ae}\t{path}")
        return 0

    started = time.time()
    ok = ocr_failed = parse_failed = funds_added = 0
    for i, (ae_id, path_str) in enumerate(cands, 1):
        pdf = Path(path_str)
        if not pdf.exists():
            ocr_failed += 1
            print(f"[{i}/{len(cands)}] {ae_id}\tMISSING_PDF", flush=True)
            continue
        ok_ocr, msg = _ocr_inplace(pdf)
        if not ok_ocr:
            ocr_failed += 1
            print(f"[{i}/{len(cands)}] {ae_id}\tOCR_FAIL {msg}", flush=True)
            continue
        try:
            e = extract_pdf(pdf)
        except Exception as exc:  # noqa: BLE001
            parse_failed += 1
            print(f"[{i}/{len(cands)}] {ae_id}\tPARSE_FAIL {exc.__class__.__name__}", flush=True)
            continue
        ok += 1
        # Refresh extraction row's OCR-related fields
        conn.execute(
            "UPDATE extraction SET ocr = 1, no_default_named = ?, "
            "  raw_super_excerpt = COALESCE(?, raw_super_excerpt), "
            "  confidence_super = ? "
            "WHERE ae_id = ?",
            (int(e.no_default_named), e.super_excerpt, e.super_confidence, ae_id),
        )
        for canonical, excerpt in e.default_super:
            cur = conn.execute(
                "SELECT 1 FROM default_super WHERE ae_id = ? AND fund_name = ?",
                (ae_id, canonical),
            )
            if cur.fetchone():
                continue
            conn.execute(
                "INSERT INTO default_super (ae_id, fund_name, source_excerpt, source) "
                "VALUES (?, ?, ?, ?)",
                (ae_id, canonical, excerpt, OCR_TAG),
            )
            funds_added += 1
        funds_str = ",".join(c for c, _ in e.default_super) or "-"
        print(
            f"[{i}/{len(cands)}] {ae_id}\tok funds={funds_str} "
            f"no_default={int(e.no_default_named)}",
            flush=True,
        )

    elapsed = time.time() - started
    print(
        f"\nDone in {elapsed/60:.1f} min. "
        f"ok={ok} ocr_fail={ocr_failed} parse_fail={parse_failed} "
        f"funds_added={funds_added}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
