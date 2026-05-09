"""Walk the FWC enterprise-agreement search results."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from selectolax.parser import HTMLParser, Node

from .db import connect, upsert_agreement, upsert_party
from .http import PoliteClient

SEARCH_PATH = "/document-search"
STATUS_APPROVED = 163803
DEFAULT_ITEMS_PER_PAGE = 50

# Map FWC status codes (used both in the URL and in the chip label)
STATUS_LABELS = {
    163803: "Approved",
    163804: "Terminated",
    163805: "Expired",
    163806: "Withdrawn",
    216455: "Ceased to operate – pre-2010 agreement",
    216456: "Title Changed",
    216463: "Other",
    216465: "Superseded",
}

DATE_FORMATS = ["%d %b %Y", "%d %B %Y"]


@dataclass
class ResultRow:
    ae_id: str
    matter_number: str | None
    title: str | None
    detail_url: str | None
    pdf_url: str | None
    parties: list[tuple[str, str | None]]  # (company_name, abn)
    version: int | None
    status: str | None
    approved_date: dt.date | None
    expires: dt.date | None


def _parse_date(s: str) -> dt.date | None:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _chip_text(node: Node, title: str) -> str | None:
    el = node.css_first(f'div.fwc-chip[title="{title}"]')
    if el is None:
        return None
    return el.text(strip=True) or None


def _all_chip_texts(node: Node, title: str) -> list[str]:
    return [
        (el.text(strip=True) or "")
        for el in node.css(f'div.fwc-chip[title="{title}"]')
        if (el.text(strip=True) or "")
    ]


def _chip_starting_with(node: Node, prefix: str) -> str | None:
    for el in node.css("div.fwc-chip"):
        text = el.text(strip=True) or ""
        if text.startswith(prefix):
            return text[len(prefix):].strip().lstrip(":").strip()
    return None


def _all_chip_starting_with(node: Node, prefix: str) -> list[str]:
    out = []
    for el in node.css("div.fwc-chip"):
        text = el.text(strip=True) or ""
        if text.startswith(prefix):
            out.append(text[len(prefix):].strip().lstrip(":").strip())
    return out


def parse_results_page(html: str) -> list[ResultRow]:
    """Parse a /document-search HTML page into ResultRow objects."""
    tree = HTMLParser(html)
    rows: list[ResultRow] = []
    for row in tree.css("div.views-row.faceted-search-item"):
        # Title and detail URL
        title_a = row.css_first("h3.result-title a.result-title-link")
        title = (title_a.text(strip=True) if title_a else None) or None
        detail_href = title_a.attributes.get("href") if title_a else None
        detail_url = f"https://www.fwc.gov.au{detail_href}" if detail_href else None

        # Download URL (absolute already)
        dl_a = row.css_first("div.document-actions a")
        pdf_url = dl_a.attributes.get("href") if dl_a else None

        # Chips
        ae_id = _chip_text(row, "Matter name")
        matter_number = _chip_text(row, "Matter number")
        version_str = _chip_text(row, "Agreement Version")  # "Version 1"
        version = None
        if version_str:
            m = re.search(r"\d+", version_str)
            if m:
                version = int(m.group(0))

        # Multi-party agreements: multiple Party chips and ABN chips, in order.
        parties_raw = _all_chip_texts(row, "Party")
        abns_raw = _all_chip_starting_with(row, "ABN")
        # ABNs are digit-only after stripping prefix and any whitespace
        abns = [re.sub(r"\D", "", a) or None for a in abns_raw]
        # If counts mismatch, still pair what we can
        parties: list[tuple[str, str | None]] = []
        for i, name in enumerate(parties_raw):
            abn = abns[i] if i < len(abns) else None
            parties.append((name, abn))

        approved_str = _chip_starting_with(row, "Approved")
        approved_date = _parse_date(approved_str) if approved_str else None
        expires_str = _chip_starting_with(row, "Nominal expiry")
        expires = _parse_date(expires_str) if expires_str else None

        # Status chip — title is "Click to filter by Agreement Status: <status>"
        status = None
        for el in row.css("div.chip-document-type.fwc-chip--clickable"):
            tt = el.attributes.get("title") or ""
            m = re.search(r"Agreement Status:\s*(.+)$", tt)
            if m:
                status = m.group(1).strip()
                break

        if not ae_id:
            continue  # skip non-result rows
        rows.append(
            ResultRow(
                ae_id=ae_id,
                matter_number=matter_number,
                title=title,
                detail_url=detail_url,
                pdf_url=pdf_url,
                parties=parties,
                version=version,
                status=status,
                approved_date=approved_date,
                expires=expires,
            )
        )
    return rows


def page_url(status_code: int, page: int, items_per_page: int = DEFAULT_ITEMS_PER_PAGE) -> str:
    return (
        f"{SEARCH_PATH}?search-ui=agreements"
        f"&f%5B0%5D=agreement-status%3A{status_code}"
        f"&items_per_page={items_per_page}"
        f"&page={page}"
    )


def crawl(
    db_path: str | None = None,
    status_code: int = STATUS_APPROVED,
    pages: int | None = None,
    start_page: int = 0,
    items_per_page: int = DEFAULT_ITEMS_PER_PAGE,
    delay: float = 1.0,
) -> Iterator[int]:
    """Yield rows-saved counts per page as the crawl progresses."""
    conn = connect(db_path) if db_path else connect()
    with PoliteClient(delay=delay) as client:
        page = start_page
        while True:
            if pages is not None and page - start_page >= pages:
                break
            url = page_url(status_code, page, items_per_page)
            resp = client.get(url)
            rows = parse_results_page(resp.text)
            if not rows:
                break  # past the end
            now = dt.datetime.utcnow().isoformat(timespec="seconds")
            for r in rows:
                # Lead party for the canonical agreement row
                lead_company, lead_abn = (r.parties[0] if r.parties else (None, None))
                upsert_agreement(
                    conn,
                    {
                        "ae_id": r.ae_id,
                        "matter_number": r.matter_number,
                        "title": r.title,
                        "company_name": lead_company,
                        "abn": lead_abn,
                        "version": r.version,
                        "status": r.status,
                        "expires": r.expires.isoformat() if r.expires else None,
                        "published_date": r.approved_date.isoformat() if r.approved_date else None,
                        "detail_url": r.detail_url,
                        "pdf_url": r.pdf_url,
                        "crawled_at": now,
                    },
                )
                for name, abn in r.parties:
                    upsert_party(conn, r.ae_id, name, abn)
            conn.execute(
                "INSERT OR REPLACE INTO crawl_state(status_code, page, rows, fetched_at) VALUES (?,?,?,?)",
                (status_code, page, len(rows), now),
            )
            yield len(rows)
            page += 1
    conn.close()
