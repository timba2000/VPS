# fwc-super-scraper backlog

Improvements to fund-coverage recall, drawn from the 2026-05-11 failure
analysis (911 / 2,107 extracted rows had no `default_super` row — 43%).

## Done (2026-05-11)

- Extended `FUNDS` alias list: AMP Super, Commonwealth Super Corp
  (PSSap / MilitarySuper / ADF Super), Team Super (+ `TEAMSUPER` no-space),
  MLC Super, Plum Super, Brighter Super, Energy Super, Transport Workers
  (Union) Super no-apostrophe variants for TWUSUPER.
- `funds._punctuation_variants()` — aliases containing `+` or `-` auto-generate
  the other-punctuation and space-separated forms (catches `C+BUS` → Cbus).
- `funds._normalise()` — intra-word rejoin: `Hostp lus` → `Hostplus`, only when
  the merged form is a known alias (safe).
- Empirical recall scan (`scripts/empirical_recall_scan.py`) — dry-run, writes
  `data/empirical_recall_summary.txt` and per-row audit `data/empirical_recall.jsonl`.

## Done (2026-05-11, follow-up run)

- **Item 2 — TOC-aware section finder.** `_section()` skips the first match
  if it falls in the first ~10% of the document and the captured window looks
  like a table of contents. Unit-tested.
- **Item 3 — `no_default_named` flag.** New `extraction.no_default_named`
  column, populated when the super clause matches stapling / employee-choice
  phrases. Surfaced in `fwc stats` and excluded from the recall denominator.
- **Item 4 — Rescan back-populate.** `scripts/back_populate_rescan.py` reads
  `data/empirical_recall.jsonl` and inserts matches with
  `source='rescan_2026-05-11'` (new `default_super.source` column).
- **Item 5 — APRA backfill (scaffolded only).** `scripts/apra_backfill.py`
  reads `data/apra_register.csv` if present. Auto-fetch isn't viable:
  SuperFundLookup is reCAPTCHA-gated, APRA's RSE register URLs rotate.
  **Manual step:** download the USI list from
  https://superfundlookup.gov.au/Tools/DownloadUsiList, drop the CSV at
  `data/apra_register.csv`, re-run the script.
- **Item 1 — OCR pipeline.** Per-page heuristic in `extract._needs_ocr`
  replaces the global 200-char guard; `scripts/ocr_pipeline.py` runs
  ocrmypdf in-place (keeping `.pre-ocr.pdf` backup) on candidates the
  heuristic flags. First pass capped at 50 PDFs as a proof of concept.

## Open

### 1. OCR pipeline for scanned PDFs  (highest expected recall lift)
**Why:** ~33% of the 911 failures are image-PDFs slipping past the 200-char
guard at `src/fwc_super/extract.py:225` — multi-page scans with page
numbers/TOC clear the global threshold but have no body text. Only 1 of 911
failures was correctly flagged `ocr=1`.

**Tasks:**
- Replace the global 200-char guard with a per-page heuristic (e.g. flag
  OCR-needed when median page text < ~400 chars or > 80% of pages are < 50 chars).
- Wire up the OCR step that's currently stubbed `# not implemented in v0`.
  Candidates: `ocrmypdf` (preferred — preserves PDF structure, idempotent) or
  raw `pytesseract`. Tesseract is already installed; `ocrmypdf` isn't.
- Persist `ocr=1` and re-run `find_funds` over the OCR'd text.
- Add a test fixture with a scanned PDF excerpt.

### 2. TOC-aware section finder
**Why:** When the first `Superannuation` heading hit lands in the table of
contents, the 2,500-char window captures other heading titles instead of the
real clause (confirmed: AE532198, others).

**Tasks:**
- In `extract._section`, if the first match is in the first ~10% of the
  document AND the captured window contains many ALL-CAPS heading-style lines,
  advance to the next heading match.
- Test with a known TOC-stealing AE ID.

### 3. `no_default_named` status flag
**Why:** ~13% of "failures" are post-2021 stapling EAs and "fund nominated by
Company" agreements that legitimately don't name a default. They inflate the
miss rate and aren't actually a recall problem — they're a data-shape one.

**Tasks:**
- Add column `extraction.no_default_named INTEGER` (or
  `default_super.fund_name = 'NONE_NAMED'` sentinel).
- Detect phrases like "stapled fund", "fund nominated by the employee",
  "complying fund of the employee's choice" and set the flag.
- Exclude flagged rows from the recall denominator in `fwc stats`.

### 4. Back-populate `default_super` for this session's new matches
**Why:** The 44 (Pass A) + ~N (Pass B) newly-matched rows from this session's
alias work are currently dry-run only — no DB writes happened.

**Tasks:**
- Wait for `fwc-recall-scan.service` to finish; read final counts from
  `data/empirical_recall.jsonl`.
- Insert rows into `default_super` from that audit log (fund_name + canonical;
  fund_abn / fund_usi remain NULL unless a directory lookup is also added).
- Decide whether to also add a `source = "rescan_2026-05-11"` column so these
  are distinguishable from the original extraction pass.

### 5. Fund-directory ABN/USI lookup
**Why:** `default_super` has `fund_abn` and `fund_usi` columns that the
current pipeline doesn't populate for re-discovered matches. APRA publishes a
fund register; populating this would make the dataset much more queryable
(e.g. join by ABN to other corporate datasets).

**Tasks:**
- Pull APRA's fund/RSE register CSV.
- Build a canonical-name → ABN/USI lookup keyed off the `FUNDS` table.
- Backfill existing `default_super` rows.

---

*This file is the durable backlog — survives terminal exit and new sessions.*
*The session-scoped task store under `/root/.claude/tasks/<session-id>/` is
unreliable across sessions; don't rely on it for cross-session continuity.*
