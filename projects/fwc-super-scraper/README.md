# fwc-super-scraper

Build a queryable local dataset of default-superannuation funds named in active
Australian enterprise agreements, sourced from the
[Fair Work Commission's public document search](https://www.fwc.gov.au/document-search?search-ui=agreements).

For each agreement the pipeline captures:

| Field                       | Source                                  |
|-----------------------------|------------------------------------------|
| Company name + ABN          | Search-results chip (no PDF needed)     |
| Approval date, nominal expiry | Search-results chip                    |
| Status (Approved / Expired) | Search-results chip                      |
| Industry                    | Detail page (`fwc enrich`)               |
| **Default super fund(s)**   | PDF body text (heuristic + alias table) |
| Term start                  | PDF body text                            |
| Date signed                 | PDF signature block (best-effort)        |
| Signatory name + title      | PDF signature block (best-effort)        |

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Optional OCR support for scanned signature pages:

```bash
.venv/bin/pip install -e ".[ocr]"
sudo apt-get install tesseract-ocr poppler-utils
```

## Pipeline

Each stage is idempotent and resumable. The local SQLite DB
(`data/fwc.sqlite`) is the queue.

```bash
# 1. Walk the FWC search results and capture metadata
fwc crawl --pages 5            # ~250 rows; omit --pages to crawl all 89k

# 2. (Optional) fetch detail pages for industry classification
fwc enrich --limit 250

# 3. Download PDFs into data/pdfs/
fwc download --limit 250 --delay 0.6

# 4. Parse PDFs → super fund / term / signed date / signatories
fwc extract

# 5. Query
fwc stats
fwc query --fund AustralianSuper --confidence high
fwc query --industry construction --signed-after 2024-01-01
fwc query --abn 43062921126 --csv > takwood.csv
```

## How it works

The FWC search rows already publish `AE-id`, `AG-number`, party (company),
ABN, approval date, nominal expiry, and status. We pull all that without
opening any PDF — see `crawl.py`.

PDFs are stored in a predictable Azure blob path:

```
https://www.fwc.gov.au/documents/agreements/approved/<ae_id_lowercase>.pdf
```

The download URL exposed in search rows redirects to a short-lived SharePoint
URL, so we use the canonical blob URL directly (`download.py`).

PDF extraction (`extract.py`) is heuristic. Each field gets a confidence flag
(`high` / `medium` / `low`) plus a raw excerpt so low-confidence rows can be
hand-reviewed without re-opening the PDF.

The fund matcher (`funds.py`) uses a curated alias table for the ~28 largest
Australian super funds. It uses word-boundary substring matching first, with a
fuzzy fallback for OCR artefacts (e.g. `HEST A` → `HESTA`). Three-letter
acronyms like `ART` require strict word boundaries so they don't fire on
`depART-ment`.

## Schema

See `src/fwc_super/db.py`. Key tables:

- `agreements` — one row per AE-id (matter ID), with metadata + PDF path.
- `parties` — multi-employer agreements list multiple companies/ABNs.
- `default_super` — one row per (ae_id, fund_name); an agreement can name
  multiple funds.
- `extraction` — extraction outcomes + confidence flags + excerpts.
- `signatories` — extracted names + titles + employer/employee side.

## Tests

```bash
.venv/bin/pytest
```

Tests cover the fund matcher (exact / OCR / false-positive cases), the search
results parser (against a saved fixture), and the PDF extractor (against a
small set of real PDFs in `data/pdfs/`).

## Etiquette

The crawler runs at 1 req/s by default with retries and `Retry-After`
handling. The `User-Agent` identifies the project and a contact email so
fwc.gov.au admins can reach out. Don't lower `--delay` below ~0.5s.

Full crawl is ~89,000 PDFs (~45 GB at ~500 KB average). Run a 1,000-row
pilot first and check `fwc stats` before committing to the full archive.

## Open questions

These are flagged in the project plan and need a call before a full crawl:

1. "Active" = `status:Approved` only, or only those with `expires > today`?
2. PDF retention vs. extract-and-discard for the full crawl.
3. Multi-employer signatures — capture all parties' signatories or only the
   lead?
4. "Authorised director" — almost no EAs are signed by a formal Director;
   capture whoever signs as employer-side with their printed title.
