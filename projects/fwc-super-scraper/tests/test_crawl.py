from pathlib import Path

import pytest

from fwc_super.crawl import parse_results_page

FIXTURE = Path(__file__).parent / "fixtures" / "search_page0.html"


@pytest.fixture(scope="module")
def page_html():
    if not FIXTURE.exists():
        pytest.skip(
            "Search-results fixture missing. Run `python scripts/save_fixture.py` "
            "to capture a live page snapshot."
        )
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_results_page_yields_50_rows(page_html):
    rows = parse_results_page(page_html)
    assert 40 <= len(rows) <= 60
    assert all(r.ae_id and r.ae_id.startswith("AE") for r in rows)


def test_each_row_has_expected_fields(page_html):
    rows = parse_results_page(page_html)
    sample = rows[0]
    assert sample.matter_number and sample.matter_number.startswith("AG")
    assert sample.title
    assert sample.detail_url and sample.detail_url.startswith("https://www.fwc.gov.au")
    assert sample.parties  # at least one party
    assert sample.status == "Approved"
    assert sample.approved_date is not None
    assert sample.expires is not None


def test_multi_party_rows_capture_all_parties(page_html):
    rows = parse_results_page(page_html)
    counts = [len(r.parties) for r in rows]
    # Parser must support both single- and multi-party rows
    assert max(counts) >= 1
