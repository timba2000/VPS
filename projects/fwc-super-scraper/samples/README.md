# Sample output

`sample_dataset.csv` is a 500-row slice of the dataset built by this
project — the 500 most recently published agreements as of
2026-05-13, one row per `(agreement, default-fund)` pair (some
agreements name more than one fund, which produces multiple rows).

All source data comes from the Fair Work Commission's public document
search (https://www.fwc.gov.au/document-search?search-ui=agreements);
nothing here is private. The full local dataset has ~4,500 agreements;
this is a representative cut for browsing.

## Columns

| Column              | Source                          |
|---------------------|---------------------------------|
| `ae_id`             | FWC approval identifier         |
| `matter_number`     | FWC matter number               |
| `title`             | Agreement title                 |
| `company_name`      | Primary employer party          |
| `abn`               | Employer ABN                    |
| `industry`          | FWC industry classification     |
| `published_date`    | Approval published date         |
| `expires`           | Nominal expiry                  |
| `date_signed`       | Extracted from PDF              |
| `term_start`        | Extracted from PDF              |
| `term_end`          | Extracted from PDF              |
| `confidence_super`  | `high` / `medium` / `low`       |
| `ocr`               | 1 if PDF needed OCR             |
| `no_default_named`  | 1 if EA explicitly names no default fund |
| `fund_name`         | Canonical super fund name       |
| `fund_abn`          | From APRA register backfill     |
| `fund_usi`          | From APRA register backfill     |
| `fund_source`       | `extract` / `rescan_*` / `ocr_*`|
| `detail_url`        | FWC detail page                 |
| `pdf_url`           | FWC canonical PDF download      |

## Regenerate

```bash
.venv/bin/fwc query --csv --limit 500 > samples/sample_dataset.csv
```

The richer variant in this file is produced by the helper SQL in
`scripts/` — see project `README.md` for the full pipeline.
