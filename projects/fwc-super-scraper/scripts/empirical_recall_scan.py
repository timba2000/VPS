"""Empirical recall scan for fwc-super-scraper.

Two passes:
  A. Stored excerpts (fast, in-memory): re-evaluate find_funds() over rows where
     extraction stored a super-clause excerpt but default_super has no row.
  B. Full PDF text (slow): for rows with NULL/empty stored excerpt, re-parse the
     whole PDF and run find_funds() against the full text — measures the
     upper-bound miss caused by the section-finder, not by the alias list.

Writes a JSONL audit log so individual matches can be inspected, plus a summary
to stdout. No DB writes — this is a dry-run measurement.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pdfplumber

from fwc_super.funds import find_funds


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fwc.sqlite"
LOG = ROOT / "data" / "empirical_recall.jsonl"
SUMMARY = ROOT / "data" / "empirical_recall_summary.txt"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    summary_lines: list[str] = []
    def say(s: str) -> None:
        print(s, flush=True)
        summary_lines.append(s)

    say(f"=== Empirical recall scan ===  db={DB}")

    # --- Pass A: stored excerpts ----------------------------------------------
    pass_a = con.execute("""
        SELECT e.ae_id, e.raw_super_excerpt FROM extraction e
        LEFT JOIN default_super d ON d.ae_id = e.ae_id
        WHERE d.ae_id IS NULL AND e.raw_super_excerpt IS NOT NULL
          AND length(e.raw_super_excerpt) > 0
    """).fetchall()

    a_funds: Counter[str] = Counter()
    a_hits = 0
    with LOG.open("w") as fh:
        for r in pass_a:
            matches = find_funds(r["raw_super_excerpt"])
            if matches:
                a_hits += 1
                for c, _, _ in matches:
                    a_funds[c] += 1
                fh.write(json.dumps({
                    "pass": "A", "ae_id": r["ae_id"],
                    "funds": [c for c, _, _ in matches],
                }) + "\n")

    say(f"\nPass A (stored excerpts):  {a_hits}/{len(pass_a)} newly match  ({100*a_hits/max(1,len(pass_a)):.1f}%)")
    for f, n in a_funds.most_common(20):
        say(f"  {n:4d}  {f}")

    # --- Pass B: full PDF text -----------------------------------------------
    pass_b = con.execute("""
        SELECT a.ae_id, a.pdf_path FROM extraction e
        JOIN agreements a ON a.ae_id = e.ae_id
        LEFT JOIN default_super d ON d.ae_id = e.ae_id
        WHERE d.ae_id IS NULL
          AND (e.raw_super_excerpt IS NULL OR length(e.raw_super_excerpt) = 0)
          AND a.pdf_path IS NOT NULL
    """).fetchall()

    say(f"\nPass B (full-PDF re-parse): {len(pass_b)} candidates")

    b_funds: Counter[str] = Counter()
    b_hits = 0
    errs = 0
    no_text = 0
    with LOG.open("a") as fh:
        for i, r in enumerate(pass_b, 1):
            p = Path(r["pdf_path"])
            if not p.exists():
                errs += 1
                continue
            try:
                with pdfplumber.open(p) as pdf:
                    text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
            except Exception as e:
                errs += 1
                fh.write(json.dumps({"pass": "B", "ae_id": r["ae_id"], "error": str(e)}) + "\n")
                continue
            if len(text) < 200:
                no_text += 1
                continue
            matches = find_funds(text)
            if matches:
                b_hits += 1
                for c, _, _ in matches:
                    b_funds[c] += 1
                fh.write(json.dumps({
                    "pass": "B", "ae_id": r["ae_id"],
                    "funds": [c for c, _, _ in matches],
                    "n_chars": len(text),
                }) + "\n")
            if i % 25 == 0:
                print(f"  …processed {i}/{len(pass_b)}  hits={b_hits}  errs={errs}", flush=True)

    say(f"\nPass B summary: {b_hits}/{len(pass_b)} hit a fund  errs={errs}  empty/scanned={no_text}")
    for f, n in b_funds.most_common(20):
        say(f"  {n:4d}  {f}")

    total_failing = con.execute("""
        SELECT COUNT(*) FROM extraction e
        LEFT JOIN default_super d ON d.ae_id = e.ae_id
        WHERE d.ae_id IS NULL
    """).fetchone()[0]
    say(f"\nTotal previously-failing rows: {total_failing}")
    say(f"Potential new matches:        A={a_hits}  B={b_hits}  total={a_hits + b_hits}")
    say(f"Projected new recall on this slice: {100*(a_hits + b_hits)/max(1, total_failing):.1f}%")

    SUMMARY.write_text("\n".join(summary_lines) + "\n")
    say(f"\nSummary written to: {SUMMARY}")
    say(f"Per-row audit log:  {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
