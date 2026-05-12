"""Extract default-super, term, signed date, signatory from agreement PDFs."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pdfplumber

from .db import connect
from .funds import find_funds

# ---------- Date utilities ----------------------------------------------------

MONTHS = (
    "January|February|March|April|May|June|July|"
    "August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({MONTHS})\.?\s+(\d{{4}})\b",
    re.I,
)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _parse_one(text: str) -> dt.date | None:
    if (m := DATE_RE.search(text)):
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return dt.datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt
                ).date()
            except ValueError:
                continue
    if (m := ISO_DATE_RE.search(text)):
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    if (m := SLASH_DATE_RE.search(text)):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(y, mo, d)
        except ValueError:
            pass
    return None


# ---------- Section locators -------------------------------------------------

SUPER_HEADING = re.compile(
    r"(?im)^\s*(?:\d+\.?\d*\.?\s+)?Superannuation\s*$"
)
SIGNATURE_MARKER = re.compile(
    r"(?i)(SIGNATURE\s+PROVISIONS|Signed\s+(?:for\s+and\s+)?on\s+behalf\s+of|"
    r"Part\s+\d+\s*[-–]\s*Signatories|EXECUTION|Signatures?)"
)
TERM_PHRASES = re.compile(
    r"(?i)(nominal\s+expiry\s+date|operates?\s+from|commences?\s+(?:on|seven\s+days)|"
    r"nominal\s+term)"
)


_HEADING_LIKE = re.compile(r"(?m)^[A-Z0-9][A-Z0-9 \-,&/().]{4,80}$")


def _looks_like_toc(window: str) -> bool:
    lines = [l for l in window.splitlines() if l.strip()]
    if len(lines) < 6:
        return False
    headings = sum(1 for l in lines if _HEADING_LIKE.match(l.strip()))
    return headings / len(lines) >= 0.5


def _section(text: str, start: re.Pattern, *, length: int = 1500) -> str | None:
    """Return text following the first match of `start`, up to `length` chars.

    If the first match falls in the first ~10% of the document and the captured
    window looks like a table of contents (mostly heading-style ALL-CAPS lines),
    advance to the next match — the real clause is later in the body.
    """
    matches = list(start.finditer(text))
    if not matches:
        return None
    first = matches[0]
    early_cutoff = max(2000, len(text) // 10)
    if (
        first.start() < early_cutoff
        and len(matches) > 1
        and _looks_like_toc(text[first.start(): first.start() + length])
    ):
        chosen = matches[1]
    else:
        chosen = first
    return text[chosen.start(): chosen.start() + length]


# ---------- Heuristic extractors ---------------------------------------------


@dataclass
class Extracted:
    default_super: list[tuple[str, str]] = field(default_factory=list)  # (canonical, excerpt)
    super_excerpt: str | None = None
    super_confidence: str = "low"
    date_signed: dt.date | None = None
    signed_excerpt: str | None = None
    signed_confidence: str = "low"
    term_start: dt.date | None = None
    term_end: dt.date | None = None
    term_excerpt: str | None = None
    term_confidence: str = "low"
    signatories: list[tuple[str, str | None, str | None, str]] = field(default_factory=list)
    # (name, title, side, excerpt)
    signer_confidence: str = "low"
    ocr: bool = False
    no_default_named: bool = False


# Phrases used in stapling-era / employee-choice EAs that legitimately do not
# name a default fund. Case-insensitive substring match.
NO_DEFAULT_PHRASES = (
    "stapled fund",
    "stapled super",
    "fund nominated by the employee",
    "fund nominated by the employer",
    "fund of the employee's choice",
    "fund of the employees' choice",
    "complying fund of the employee",
    "complying superannuation fund nominated",
    "in accordance with the choice of fund",
    "in accordance with the superannuation guarantee",
)


def _no_default_named(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in NO_DEFAULT_PHRASES)


def _extract_super(text: str) -> tuple[list[tuple[str, str]], str | None, str]:
    section = _section(text, SUPER_HEADING, length=2500) or ""
    if not section:
        # Fallback: any paragraph mentioning "default fund"
        m = re.search(r"(?i)default\s+(?:super(?:annuation)?\s+)?fund.{0,400}", text)
        section = text[m.start(): m.start() + 600] if m else ""
    if not section:
        return [], None, "low"
    funds = find_funds(section)
    if not funds:
        return [], section[:600] or None, "low"
    excerpt = section[:600]
    confidence = "high" if any(s == 100 for _, _, s in funds) else "medium"
    return [(canonical, excerpt) for canonical, _, _ in funds], excerpt, confidence


def _extract_term(
    text: str, *, fallback_end: dt.date | None
) -> tuple[dt.date | None, dt.date | None, str | None, str]:
    """Find term_start in body text. End date comes from FWC metadata (passed
    in via fallback_end) — body text often quotes a previous agreement's expiry,
    so the metadata is more reliable.
    """
    excerpt = None
    start = None
    # Body text typically has "commences seven days after approval" or
    # "operates from <date>" — useful for term_start only.
    for pattern in (
        r"(?i)commenc\w+\s+(?:on\s+|seven\s+days\s+after\s+)?[^\n]{0,80}",
        r"(?i)operates?\s+from\s+[^\n]{0,80}",
    ):
        m = re.search(pattern, text)
        if m:
            d = _parse_one(m.group(0))
            if d:
                start = d
                excerpt = m.group(0)
                break
    end = fallback_end  # trust search/detail-page metadata
    confidence = "high" if start and end else ("medium" if end else "low")
    return start, end, excerpt, confidence


def _extract_signed(text: str) -> tuple[dt.date | None, str | None, str]:
    # Try the signature section first
    sig_section = _section(text, SIGNATURE_MARKER, length=3000)
    candidates: list[tuple[dt.date, str]] = []
    pool = sig_section or text[-4000:]
    for m in DATE_RE.finditer(pool):
        d = _parse_one(m.group(0))
        if d and 1990 <= d.year <= dt.date.today().year + 1:
            s = max(0, m.start() - 120)
            e = min(len(pool), m.end() + 80)
            candidates.append((d, pool[s:e]))
    if not candidates:
        # widen to slashes
        for m in SLASH_DATE_RE.finditer(pool):
            d = _parse_one(m.group(0))
            if d and 1990 <= d.year <= dt.date.today().year + 1:
                s = max(0, m.start() - 120)
                e = min(len(pool), m.end() + 80)
                candidates.append((d, pool[s:e]))
    if not candidates:
        return None, None, "low"
    # Latest date in the signature region is most likely the signing date.
    candidates.sort(key=lambda t: t[0])
    chosen, excerpt = candidates[-1]
    confidence = "medium" if sig_section else "low"
    return chosen, excerpt, confidence


SIGNATORY_LINE = re.compile(
    r"(?im)^\s*(?<!of\s)(Name|Print(?:ed)?\s+Name|Full\s+Name)\s*[:\-]?\s*(.+?)$"
)
WITNESS_PREFIX = re.compile(r"(?i)^\s*(of\s+witness|witness|witnessed)")
TITLE_LINE = re.compile(
    r"(?im)^\s*(Title|Position|Capacity|Capacity\s+to\s+Sign)\s*[:\-]?\s*(.+?)$"
)


def _extract_signatories(text: str) -> tuple[list[tuple[str, str | None, str | None, str]], str]:
    sig_section = _section(text, SIGNATURE_MARKER, length=4000)
    if not sig_section:
        return [], "low"
    out: list[tuple[str, str | None, str | None, str]] = []
    side = "unknown"
    for line in sig_section.splitlines():
        l = line.strip()
        ll = l.lower()
        if "behalf of employer" in ll or "for and on behalf of the employer" in ll:
            side = "employer"
        elif "on behalf of the employees" in ll or "behalf of employee" in ll:
            side = "employee"
        elif "union" in ll and "secretary" in ll:
            side = "employee"
        if WITNESS_PREFIX.match(l):
            continue
        m = SIGNATORY_LINE.match(line)
        if m:
            name = m.group(2).strip(" .:-")
            # Strip OCR garbage (long runs of non-alpha)
            if re.search(r"[^A-Za-z\s\.\-']", name) and len(re.findall(r"[A-Za-z]", name)) < 3:
                continue
            if 2 <= len(name) <= 80 and re.search(r"[A-Za-z]", name):
                out.append((name, None, side, line.strip()[:200]))
    # Try to pair titles to most recent name
    if out:
        title_matches = list(TITLE_LINE.finditer(sig_section))
        for i, (name, _, side, exc) in enumerate(out):
            # Find a title line after the name's position
            try:
                idx = sig_section.index(name)
            except ValueError:
                continue
            for tm in title_matches:
                if tm.start() > idx and tm.start() - idx < 300:
                    out[i] = (name, tm.group(2).strip(" .:-")[:120], side, exc)
                    break
    confidence = "medium" if out else "low"
    return out, confidence


def _needs_ocr(per_page_lengths: list[int]) -> bool:
    """Per-page heuristic: an EA looks scanned when most pages have very little
    extractable text. Beats the old global 200-char guard, which let multi-page
    scans through if their TOC + page numbers totalled enough chars.
    """
    if not per_page_lengths:
        return True
    n = len(per_page_lengths)
    sorted_lens = sorted(per_page_lengths)
    median = sorted_lens[n // 2]
    near_empty = sum(1 for x in per_page_lengths if x < 50)
    return median < 400 or near_empty / n > 0.8


def extract_pdf(pdf_path: Path | str, *, fallback_end: dt.date | None = None) -> Extracted:
    pdf_path = Path(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        page_texts = [(p.extract_text() or "") for p in pdf.pages]
    text = "\n".join(page_texts)
    page_lengths = [len(t) for t in page_texts]
    e = Extracted(ocr=False)
    if _needs_ocr(page_lengths):
        e.ocr = True  # caller may invoke OCR; see scripts/ocr_pipeline.py
        return e
    e.default_super, e.super_excerpt, e.super_confidence = _extract_super(text)
    if not e.default_super:
        # Look in the super section first (if any), then the whole doc
        scan = e.super_excerpt or text
        e.no_default_named = _no_default_named(scan)
    e.term_start, e.term_end, e.term_excerpt, e.term_confidence = _extract_term(
        text, fallback_end=fallback_end
    )
    e.date_signed, e.signed_excerpt, e.signed_confidence = _extract_signed(text)
    e.signatories, e.signer_confidence = _extract_signatories(text)
    return e


def extract(db_path: str | None = None, *, limit: int | None = None) -> Iterator[tuple[str, str]]:
    conn = connect(db_path) if db_path else connect()
    sql = (
        "SELECT a.ae_id, a.pdf_path, a.expires "
        "FROM agreements a "
        "LEFT JOIN extraction e ON a.ae_id = e.ae_id "
        "WHERE a.pdf_path IS NOT NULL AND e.ae_id IS NULL"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = list(conn.execute(sql))
    for row in rows:
        ae_id = row["ae_id"]
        path = Path(row["pdf_path"])
        # Pre-process breadcrumb so a hang/OOM names the offending PDF.
        size_mb = path.stat().st_size / 1_048_576 if path.exists() else -1
        print(f"[extract] start {ae_id} {path.name} ({size_mb:.1f} MB)", flush=True)
        fallback_end = (
            dt.date.fromisoformat(row["expires"]) if row["expires"] else None
        )
        try:
            e = extract_pdf(path, fallback_end=fallback_end)
        except Exception as exc:  # noqa: BLE001
            yield ae_id, f"ERR {exc.__class__.__name__}"
            continue
        now = dt.datetime.utcnow().isoformat(timespec="seconds")
        conn.execute(
            """INSERT OR REPLACE INTO extraction
               (ae_id, date_signed, term_start, term_end, ocr, no_default_named,
                confidence_super, confidence_signed, confidence_term, confidence_signer,
                raw_super_excerpt, raw_signed_excerpt, raw_signer_excerpt, extracted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ae_id,
                e.date_signed.isoformat() if e.date_signed else None,
                e.term_start.isoformat() if e.term_start else None,
                e.term_end.isoformat() if e.term_end else None,
                int(e.ocr),
                int(e.no_default_named),
                e.super_confidence,
                e.signed_confidence,
                e.term_confidence,
                e.signer_confidence,
                e.super_excerpt,
                e.signed_excerpt,
                (e.signatories[0][3] if e.signatories else None),
                now,
            ),
        )
        # default_super rows
        conn.execute("DELETE FROM default_super WHERE ae_id = ?", (ae_id,))
        for canonical, excerpt in e.default_super:
            conn.execute(
                """INSERT OR IGNORE INTO default_super
                   (ae_id, fund_name, source_excerpt) VALUES (?,?,?)""",
                (ae_id, canonical, excerpt),
            )
        # signatories
        conn.execute("DELETE FROM signatories WHERE ae_id = ?", (ae_id,))
        for name, title, side, excerpt in e.signatories:
            conn.execute(
                """INSERT INTO signatories (ae_id, name, title, side, excerpt)
                   VALUES (?,?,?,?,?)""",
                (ae_id, name, title, side, excerpt),
            )
        funds_str = ",".join(c for c, _ in e.default_super) or "-"
        yield ae_id, (
            f"super={funds_str}/{e.super_confidence} "
            f"signed={e.date_signed or '-'}/{e.signed_confidence} "
            f"term={e.term_start or '-'}..{e.term_end or '-'}/{e.term_confidence} "
            f"sigs={len(e.signatories)}/{e.signer_confidence}"
        )
    conn.close()
