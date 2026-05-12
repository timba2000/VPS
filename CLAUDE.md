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

Active project: **`projects/fwc-super-scraper`** (Python). Builds a queryable SQLite dataset of default-super funds named in active Australian enterprise agreements, sourced from the Fair Work Commission. Pipeline is crawl → enrich → download → extract; each stage idempotent and resumable from `data/fwc.sqlite`. Entry point: `bash scripts/run_pilot.sh` (1,000-row pilot). Launch long runs via `systemd-run --slice=system.slice --unit=<name> --property=MemoryHigh=5G --property=MemoryMax=6G --property=WorkingDirectory=$PWD /bin/bash -c '…'` — `nohup setsid` does not survive on this VPS. The `extract` stage leaks memory across PDFs inside one Python process; keep `BATCH<=10` in `scripts/extract_chunked.sh` so the per-batch respawn reclaims it. See `projects/fwc-super-scraper/README.md` for full pipeline + schema.

Remote `git@github.com:timba2000/VPS.git` is working — SSH key is registered, `main` pushes cleanly.

## Conventions

None established yet. Record here when the user sets one (file layout, naming, commit style).
