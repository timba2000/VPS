"""Download PDFs for crawled agreements."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Iterator

from .db import connect
from .http import PoliteClient

DEFAULT_PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "pdfs"

# FWC stores approved-agreement PDFs in a predictable Azure blob path.
# The /document-view/media/download/<id> URL exposed in search rows redirects
# to a SharePoint URL with short-lived auth, so we use the canonical blob URL.
STATUS_FOLDER = {
    "Approved": "approved",
    "Expired": "approved",       # expired agreements are still in /approved
    "Terminated": "approved",
    "Superseded": "approved",
}


def blob_url_for(ae_id: str, status: str | None) -> str:
    folder = STATUS_FOLDER.get(status or "Approved", "approved")
    return f"https://www.fwc.gov.au/documents/agreements/{folder}/{ae_id.lower()}.pdf"


def download(
    db_path: str | None = None,
    *,
    pdf_dir: Path | str = DEFAULT_PDF_DIR,
    limit: int | None = None,
    delay: float = 1.0,
    redownload: bool = False,
) -> Iterator[tuple[str, str]]:
    pdf_dir = Path(pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path) if db_path else connect()

    sql = "SELECT ae_id, pdf_url, status, pdf_path FROM agreements"
    where = []
    if not redownload:
        where.append("pdf_path IS NULL")
    if where:
        sql += " WHERE " + " AND ".join(where)
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = list(conn.execute(sql))

    from urllib.parse import urlparse

    with PoliteClient(delay=delay) as client:
        for row in rows:
            ae_id = row["ae_id"]
            target = pdf_dir / f"{ae_id}.pdf"
            blob = blob_url_for(ae_id, row["status"])
            path = urlparse(blob).path
            try:
                resp = client.get(path)
                content = resp.content
                if not content or content[:4] != b"%PDF":
                    yield ae_id, "NOT_PDF"
                    continue
                target.write_bytes(content)
                sha = hashlib.sha256(content).hexdigest()
                size = len(content)
                now = dt.datetime.utcnow().isoformat(timespec="seconds")
                conn.execute(
                    """UPDATE agreements
                       SET pdf_path = ?, pdf_sha256 = ?, pdf_bytes = ?, pdf_url = ?, downloaded_at = ?
                       WHERE ae_id = ?""",
                    (str(target), sha, size, blob, now, ae_id),
                )
                yield ae_id, f"OK {size}B"
            except Exception as exc:  # noqa: BLE001
                yield ae_id, f"ERR {exc.__class__.__name__}"
    conn.close()
