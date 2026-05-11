"""Backfill default_super.fund_abn / fund_usi from an APRA register CSV.

Looks for data/apra_register.csv. If absent, exits 0 with a message — the file
isn't auto-fetchable (SuperFundLookup is reCAPTCHA-gated, APRA's RSE register
URLs are dated and rotate). Manual download once, then re-run.

Expected CSV columns (case-insensitive, any of these names):
  - fund_name / RSE name / Product name
  - abn / ABN
  - usi / USI

Match strategy:
  1. Exact case-insensitive match on canonical name (the value in
     default_super.fund_name).
  2. Fuzzy partial-ratio match against APRA fund names, using fwc_super.funds
     aliases as candidate strings, threshold 95.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

from fwc_super.db import connect
from fwc_super.funds import FUNDS

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "apra_register.csv"


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _load_register(path: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        # Normalise header names
        for row in reader:
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            name = (
                r.get("fund_name")
                or r.get("rse name")
                or r.get("rse_name")
                or r.get("product name")
                or r.get("product_name")
                or r.get("name")
            )
            abn = r.get("abn")
            usi = r.get("usi")
            if name and (abn or usi):
                out.append({"name": name, "abn": abn or "", "usi": usi or ""})
    return out


def _build_lookup(register: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
    """canonical fund_name -> (abn, usi). Match by exact + fuzzy alias hit."""
    lookup: dict[str, tuple[str, str]] = {}
    reg_names = [r["name"] for r in register]
    reg_norm = [_norm(n) for n in reg_names]
    for fund in FUNDS:
        # 1. Exact normalised match against canonical or any alias
        exact_keys = {_norm(fund.canonical)} | {_norm(a) for a in fund.aliases}
        for i, rn in enumerate(reg_norm):
            if rn in exact_keys:
                lookup[fund.canonical] = (register[i]["abn"], register[i]["usi"])
                break
        else:
            # 2. Fuzzy on aliases
            best: tuple[float, int] = (0, -1)
            for alias in (fund.canonical, *fund.aliases):
                m = process.extractOne(
                    _norm(alias), reg_norm, scorer=fuzz.partial_ratio,
                    score_cutoff=95,
                )
                if m and m[1] > best[0]:
                    best = (m[1], reg_norm.index(m[0]))
            if best[1] >= 0:
                r = register[best[1]]
                lookup[fund.canonical] = (r["abn"], r["usi"])
    return lookup


def main() -> int:
    if not CSV_PATH.exists():
        print(f"skipped: {CSV_PATH} not found")
        print("Manual download required:")
        print("  1. Visit https://superfundlookup.gov.au/Tools/DownloadUsiList")
        print("  2. Solve the reCAPTCHA, save the CSV as data/apra_register.csv")
        print("  3. Re-run this script.")
        return 0
    register = _load_register(CSV_PATH)
    print(f"loaded {len(register)} rows from {CSV_PATH.name}")
    lookup = _build_lookup(register)
    print(f"matched {len(lookup)}/{sum(1 for _ in FUNDS)} canonical funds to register entries")

    conn = connect()
    updated = 0
    for canonical, (abn, usi) in lookup.items():
        if not abn and not usi:
            continue
        cur = conn.execute(
            "UPDATE default_super SET fund_abn = COALESCE(fund_abn, ?), "
            "fund_usi = COALESCE(fund_usi, ?) "
            "WHERE fund_name = ? AND (fund_abn IS NULL OR fund_usi IS NULL)",
            (abn or None, usi or None, canonical),
        )
        updated += cur.rowcount
    print(f"backfilled {updated} default_super rows with ABN/USI")
    unmapped = sorted(f.canonical for f in FUNDS if f.canonical not in lookup)
    if unmapped:
        print(f"unmapped canonical funds ({len(unmapped)}):")
        for u in unmapped:
            print(f"  - {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
