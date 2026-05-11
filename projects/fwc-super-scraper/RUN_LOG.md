# fwc-super-scraper — backlog run 2026-05-11T10:43:02+00:00

Triggered by timba2000. Orchestrator: `scripts/finish_backlog.sh`.

## Outcome

| Metric                            | Before | After  | Δ      |
|-----------------------------------|--------|--------|--------|
| Agreements with default_super     | 1196 | 1342 | +146 |

```
agreements:   3633    with pdf:   3171    extracted:   2107    with super:   
1342
no-default-named (excluded from recall): 4
recall on eligible: 1342/2103 = 63.8%
Super-fund confidence:
  high      1213
  low       888
  medium    6
default_super by source:
  extract                   1466
  rescan_2026-05-11         165
  ocr_2026-05-11            35
Top default funds:
  Cbus                              614
  AustralianSuper                   259
  ESSSuper                          163
  REST                              152
  HESTA                             93
  Hostplus                          57
  Australian Retirement Trust       32
  NGS Super                         31
  Mercer Super Trust                28
  BUSSQ                             25
  Team Super                        25
  Aware Super                       24
  Maritime Super                    20
  Vision Super                      20
  MediaSuper                        18
```

## Items run

1. **OCR pipeline** — `scripts/ocr_pipeline.py --limit 50` — proof-of-concept cap; per-page heuristic replaces 200-char global guard.
2. **TOC-aware section finder** — `_section()` skips first match if it looks like a TOC heading list.
3. **no_default_named flag** — new column in `extraction`; surfaced in `fwc stats` and excluded from recall denominator.
4. **Rescan back-populate** — `scripts/back_populate_rescan.py` inserted matches from `data/empirical_recall.jsonl` with `source='rescan_2026-05-11'`.
5. **APRA register backfill** — `scripts/apra_backfill.py` reads `data/apra_register.csv` if present (manual download — SuperFundLookup is reCAPTCHA-gated).

Logs: `data/backlog_run.log`.
