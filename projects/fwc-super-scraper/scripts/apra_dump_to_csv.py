"""Convert the fixed-width SuperFundLookup dump to apra_register.csv.

Emits two CSV rows per source line — one keyed on the trustee FundName, one on
the ProductName — so the backfill matcher can hit either trustee-style names
("THE TRUSTEE FOR HESTA") or product brands ("Cbus", "REST") against our
canonical alias list.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "apra_register_raw.txt"
OUT = ROOT / "data" / "apra_register.csv"

ROW_RE = re.compile(
    r"^(\d{11})\s+(.+?)\s{2,}(\S+)\s{2,}(.+?)\s{2,}[NY]\s+\d{4}-\d{2}-\d{2}\s+\d{4}-\d{2}-\d{2}\s*$"
)


def main() -> int:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in RAW.read_text().splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        abn, fund_name, usi, product_name = m.groups()
        for name in (fund_name.strip(), product_name.strip()):
            key = (name.lower(), abn, usi)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"fund_name": name, "abn": abn, "usi": usi})
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["fund_name", "abn", "usi"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
