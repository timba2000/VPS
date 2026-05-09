"""Augment crawled rows with detail-page fields (industry, blob path).

The search-results page already gives us status, expiry, approval date, ABN, and a
working download URL — so this step is optional. It enriches each row with:
- Industry classification
- Agreement type (Single-/Multi-enterprise/Greenfields)
- Canonical blob URL (predictable: /documents/agreements/approved/<ae_id>.pdf)
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Iterator
from urllib.parse import urlparse

from .db import connect
from .http import PoliteClient

ICON_PATTERN = re.compile(
    r'<span class="material-icons[^"]*">([a-z_]+)</span>\s*<[^>]+>([^<]+)<', re.I
)
BLOB_PATTERN = re.compile(
    r"blob\|\\?/\$web\\?/(documents\\?/agreements\\?/[a-z0-9_/\\-]+\.pdf)", re.I
)


def parse_detail_page(html: str) -> dict:
    """Pull industry/type/blob-path/published-date from a /document-view page."""
    out: dict[str, object] = {}

    for icon, value in ICON_PATTERN.findall(html):
        v = value.strip()
        if v.startswith("Industry:"):
            out["industry"] = v[len("Industry:"):].strip()
        elif v.startswith("Type:"):
            out["agreement_type"] = v[len("Type:"):].strip()
        elif v.startswith("Status:"):
            out.setdefault("status", v[len("Status:"):].strip())
        elif v.startswith("Expires:"):
            out.setdefault("expires_str", v[len("Expires:"):].strip())

    m = BLOB_PATTERN.search(html)
    if m:
        path = m.group(1).replace("\\/", "/").replace("\\", "/")
        out["pdf_blob_url"] = f"https://www.fwc.gov.au/{path}"

    return out


def _pdf_blob_url_from_ae(ae_id: str) -> str:
    """Predictable blob URL pattern for approved agreements."""
    return f"https://www.fwc.gov.au/documents/agreements/approved/{ae_id.lower()}.pdf"


def enrich(
    db_path: str | None = None,
    *,
    limit: int | None = None,
    delay: float = 1.0,
    only_missing: bool = True,
) -> Iterator[str]:
    conn = connect(db_path) if db_path else connect()
    sql = "SELECT ae_id, detail_url, pdf_url FROM agreements"
    if only_missing:
        sql += " WHERE industry IS NULL OR pdf_url IS NULL"
    if limit:
        sql += f" LIMIT {int(limit)}"

    rows = list(conn.execute(sql))
    with PoliteClient(delay=delay) as client:
        for row in rows:
            ae_id = row["ae_id"]
            detail_path = (
                urlparse(row["detail_url"]).path if row["detail_url"] else None
            )
            if not detail_path:
                continue
            try:
                resp = client.get(detail_path)
            except Exception:
                yield f"{ae_id}\tERR"
                continue
            data = parse_detail_page(resp.text)
            blob = data.get("pdf_blob_url") or _pdf_blob_url_from_ae(ae_id)
            now = dt.datetime.utcnow().isoformat(timespec="seconds")
            conn.execute(
                """UPDATE agreements
                   SET industry = COALESCE(?, industry),
                       pdf_url = COALESCE(pdf_url, ?),
                       enriched_at = ?
                   WHERE ae_id = ?""",
                (data.get("industry"), blob, now, ae_id),
            )
            yield f"{ae_id}\tOK"
    conn.close()
