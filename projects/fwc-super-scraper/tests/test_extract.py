import datetime as dt
import re
from pathlib import Path

import pytest

from fwc_super.extract import _needs_ocr, _no_default_named, _section, extract_pdf

PDF_DIR = Path(__file__).resolve().parents[1] / "data" / "pdfs"

# Hand-verified expectations against real PDFs in data/pdfs/
# These rows were sampled from the first crawled page on 2026-05-09.
CASES = [
    # (ae_id, expected_funds_subset, expected_term_end)
    ("AE525841", {"AustralianSuper"}, dt.date(2027, 8, 20)),
    ("AE532166", {"Mercer Super Trust"}, dt.date(2028, 6, 30)),
    ("AE532546", {"HESTA"}, dt.date(2029, 3, 31)),
]


@pytest.mark.parametrize("ae_id,expected_funds,fallback_end", CASES)
def test_extract_super_fund(ae_id, expected_funds, fallback_end):
    pdf = PDF_DIR / f"{ae_id}.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf} missing — run `fwc download --limit 50` first")
    e = extract_pdf(pdf, fallback_end=fallback_end)
    found = {c for c, _ in e.default_super}
    assert expected_funds.issubset(found), f"expected {expected_funds} ⊆ {found}"
    assert e.super_confidence == "high"
    assert e.term_end == fallback_end


# Synthetic doc: TOC at the top mentions Superannuation, real clause much later.
TOC_DOC = (
    "TABLE OF CONTENTS\n"
    "1. PARTIES\n"
    "2. APPLICATION\n"
    "3. WAGES\n"
    "Superannuation\n"
    "4. LEAVE\n"
    "5. TERMINATION\n"
    "6. DISPUTE RESOLUTION\n"
    "7. SIGNATORIES\n"
    "8. APPENDIX A\n"
    "9. APPENDIX B\n"
    + ("PARTIES\nThis agreement is between Acme and its employees.\n" * 60)
    + "Superannuation\n"
    "Contributions will be paid into AustralianSuper as the default fund.\n"
)


@pytest.mark.parametrize("page_lengths,expected", [
    # Healthy text PDF: every page has lots of text.
    ([2000] * 30, False),
    # Scanned PDF: every page extracts almost nothing.
    ([20, 30, 15, 10, 0, 25, 18], True),
    # Mixed: TOC + numbered pages have text but body pages are scanned.
    # Old global guard would have passed this through (~3000 chars total).
    ([800, 600, 400, 5, 8, 3, 2, 6, 4, 7, 5, 0, 4, 6], True),
    # Empty (corrupt): treat as needs OCR rather than crashing.
    ([], True),
    # Borderline-thin but readable: median ~410, < 80% near-empty -> no OCR.
    ([410] * 20, False),
])
def test_needs_ocr_heuristic(page_lengths, expected):
    assert _needs_ocr(page_lengths) is expected


@pytest.mark.parametrize("text,expected", [
    ("Contributions will be paid into the employee's stapled fund.", True),
    ("The Employer will contribute to a complying fund of the employee's choice.", True),
    ("The fund nominated by the employee will receive contributions.", True),
    ("The default fund is AustralianSuper.", False),
    ("Contributions to Cbus will be made monthly.", False),
])
def test_no_default_named_detection(text, expected):
    assert _no_default_named(text) is expected


def test_section_skips_toc_match():
    # The TOC has a 'Superannuation' line in the first ~10% of the doc, but
    # the real clause is much later. _section should skip the TOC hit.
    pat = re.compile(r"(?im)^\s*(?:\d+\.?\d*\.?\s+)?Superannuation\s*$")
    section = _section(TOC_DOC, pat, length=400)
    assert section is not None
    assert "AustralianSuper" in section
    assert "LEAVE" not in section
