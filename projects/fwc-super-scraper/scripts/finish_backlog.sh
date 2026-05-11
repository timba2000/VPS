#!/usr/bin/env bash
# Orchestrator: runs the five backlog items in order, stops on first failure.
# Designed to run under systemd-run so it survives the parent shell exiting.
#
# Commits and pushes the code changes once at the start, then runs the data
# work (which writes to gitignored DB / logs). At the end, commits a stats
# snapshot to a tracked file.
#
# Logs to data/backlog_run.log. Status string in data/backlog_status.txt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REPO="$(cd ../.. && pwd)"

LOG="$ROOT/data/backlog_run.log"
STATUS="$ROOT/data/backlog_status.txt"
PY="$ROOT/.venv/bin/python"
PYTEST="$ROOT/.venv/bin/pytest"
RUN_LOG="$ROOT/RUN_LOG.md"

mkdir -p "$ROOT/data"
exec >>"$LOG" 2>&1

say() { printf '\n[%s] %s\n' "$(date -Iseconds)" "$*"; }
fail() { say "FAIL: $*"; printf 'FAILED at %s\n%s\n' "$(date -Iseconds)" "$*" > "$STATUS"; exit 1; }

git_commit_push() {
  local msg="$1"; shift
  ( cd "$REPO"
    git add "$@" || fail "git add failed"
    if git diff --cached --quiet; then
      say "no staged changes for: $msg"
      return 0
    fi
    git commit -m "$(cat <<EOF
$msg

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)" || fail "git commit failed"
    git push origin main || fail "git push failed"
  )
}

say "=== finish_backlog start ==="
printf 'RUNNING since %s\n' "$(date -Iseconds)" > "$STATUS"

say "step 0a: pytest baseline"
"$PYTEST" -q || fail "pytest baseline failed"

say "step 0b: commit + push code changes"
git_commit_push "fwc-super: backlog items — TOC-aware finder, no_default_named flag, OCR pipeline, rescan + APRA scripts" \
  projects/fwc-super-scraper/src \
  projects/fwc-super-scraper/tests \
  projects/fwc-super-scraper/scripts \
  projects/fwc-super-scraper/BACKLOG.md

PRE_SUPER=$("$PY" -c "import sqlite3; c=sqlite3.connect('$ROOT/data/fwc.sqlite'); print(c.execute('SELECT COUNT(DISTINCT ae_id) FROM default_super').fetchone()[0])")
say "pre-run: distinct ae_ids with default_super = $PRE_SUPER"

# --------------------------------------------------------------------- item 4
say "step 1: back-populate default_super from rescan jsonl (item 4)"
"$PY" scripts/back_populate_rescan.py || fail "item 4: back_populate_rescan.py failed"

# --------------------------------------------------------------------- item 5
say "step 2: APRA register backfill (item 5)"
"$PY" scripts/apra_backfill.py || fail "item 5: apra_backfill.py failed"

# --------------------------------------------------------------------- item 1
say "step 3: OCR pipeline, capped at 50 PDFs (item 1)"
"$PY" scripts/ocr_pipeline.py --limit 50 || fail "item 1: ocr_pipeline.py failed"

# --------------------------------------------------------------------- summary
say "step 4: capture final stats"
"$ROOT/.venv/bin/fwc" stats > "$ROOT/data/backlog_final_stats.txt" 2>&1 || true
cat "$ROOT/data/backlog_final_stats.txt"

POST_SUPER=$("$PY" -c "import sqlite3; c=sqlite3.connect('$ROOT/data/fwc.sqlite'); print(c.execute('SELECT COUNT(DISTINCT ae_id) FROM default_super').fetchone()[0])")
DELTA=$((POST_SUPER - PRE_SUPER))

say "step 5: write RUN_LOG.md and commit"
cat > "$RUN_LOG" <<EOF
# fwc-super-scraper — backlog run $(date -Iseconds)

Triggered by timba2000. Orchestrator: \`scripts/finish_backlog.sh\`.

## Outcome

| Metric                            | Before | After  | Δ      |
|-----------------------------------|--------|--------|--------|
| Agreements with default_super     | $PRE_SUPER | $POST_SUPER | +$DELTA |

\`\`\`
$(cat "$ROOT/data/backlog_final_stats.txt")
\`\`\`

## Items run

1. **OCR pipeline** — \`scripts/ocr_pipeline.py --limit 50\` — proof-of-concept cap; per-page heuristic replaces 200-char global guard.
2. **TOC-aware section finder** — \`_section()\` skips first match if it looks like a TOC heading list.
3. **no_default_named flag** — new column in \`extraction\`; surfaced in \`fwc stats\` and excluded from recall denominator.
4. **Rescan back-populate** — \`scripts/back_populate_rescan.py\` inserted matches from \`data/empirical_recall.jsonl\` with \`source='rescan_2026-05-11'\`.
5. **APRA register backfill** — \`scripts/apra_backfill.py\` reads \`data/apra_register.csv\` if present (manual download — SuperFundLookup is reCAPTCHA-gated).

Logs: \`data/backlog_run.log\`.
EOF

git_commit_push "fwc-super: backlog run results ($(date +%Y-%m-%d))" \
  projects/fwc-super-scraper/RUN_LOG.md

printf 'COMPLETED at %s (default_super distinct ae_ids: %s -> %s, +%s)\n' \
  "$(date -Iseconds)" "$PRE_SUPER" "$POST_SUPER" "$DELTA" > "$STATUS"
say "=== finish_backlog complete: +$DELTA agreements with default_super ==="
