"""Capture a live FWC search page snapshot into tests/fixtures/.

Useful when the FWC HTML changes and we need to refresh the parser fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fwc_super.crawl import page_url, STATUS_APPROVED
from fwc_super.http import PoliteClient

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "search_page0.html"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with PoliteClient(delay=1.0) as client:
        resp = client.get(page_url(STATUS_APPROVED, page=0))
    OUT.write_text(resp.text, encoding="utf-8")
    print(f"wrote {OUT} ({len(resp.text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
