import datetime as dt
from pathlib import Path

import pytest

from fwc_super.extract import extract_pdf

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
