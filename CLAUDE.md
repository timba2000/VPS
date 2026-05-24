# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A dual-purpose repo for timba2000:

1. **Public face**: a portfolio of TypeScript and Python code samples (`samples/`) that buyers on Fiverr/GitHub see when they click the GitHub profile.
2. **Workspace**: a place for ongoing collaboration with Claude Code on the freelance/bounty work itself.

Despite the `VPS` name, this is **not** infrastructure / server provisioning code — the name is incidental. Don't assume Bash/Ansible/Terraform conventions just because of the directory name.

**Stacks in scope:** TypeScript and Python only (see memory `feedback_languages.md`). Don't author Rust/Go/Scala/etc. work under this account.

When you start a new session here:

1. Read `git log` first — that's the authoritative record of what's been added since this file was written. Whatever is below this line was true on 2026-05-06 and may be stale.
2. Check `/root/.claude/projects/-root/memory/MEMORY.md` for accumulated context about the user and prior decisions.
3. If the repo's purpose has clearly evolved (a real subject has taken shape — a project, a script collection, notes, etc.), update this file rather than letting it drift.

## Current state (2026-05-10)

Layout:

- `samples/` — public portfolio. `csv-clean` (Python) and `ts-bug-fix` (TypeScript).
- `projects/` — active work.
- `ops/` — local-only, not tracked.

Active project: **`projects/fwc-super-scraper`** (Python). Builds a queryable SQLite dataset of default-super funds named in active Australian enterprise agreements, sourced from the Fair Work Commission. Pipeline is crawl → enrich → download → extract; each stage idempotent and resumable from `data/fwc.sqlite`. Entry point: `bash scripts/run_pilot.sh` (1,000-row pilot). The continuous crawl now runs as a **persistent, enabled** systemd unit: `/etc/systemd/system/fwc-continuous.service` (`Restart=on-failure`, memory limits, `system.slice`). To change the crawl target, edit `Environment=TARGET_AGREEMENTS=<n>` in that file, then `systemctl daemon-reload && systemctl restart fwc-continuous`. State (page cursor, empty-cycle counter) persists in `data/continuous_state.env`, so restarts resume rather than restart. NOTE: `scripts/launch_continuous.sh` (a `systemd-run` transient launcher) is superseded and will fail with a name collision while the unit file exists — don't use it. For other ad-hoc long runs, the `systemd-run --slice=system.slice ...` pattern still applies; `nohup setsid` does not survive on this VPS. The `extract` stage leaks memory across PDFs inside one Python process; keep `BATCH<=10` in `scripts/extract_chunked.sh` so the per-batch respawn reclaims it. A PDF that raises during parse is quarantined (`extraction.too_large=1`) so it is skipped, not re-selected forever. See `projects/fwc-super-scraper/README.md` for full pipeline + schema.

Remote `git@github.com:timba2000/VPS.git` is working — SSH key is registered, `main` pushes cleanly.

## Conventions

None established yet. Record here when the user sets one (file layout, naming, commit style).
