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

## Current state (2026-05-06)

- No commits yet. No source files yet. The subject of work has not been introduced.
- Remote: `git@github.com:timba2000/VPS.git` (exists on GitHub, also empty).
- The local SSH key at `~/.ssh/id_ed25519.pub` is **not** registered with GitHub. Pushing will fail until the user adds it. Don't attempt `git push` without flagging this first.

## Conventions

None yet. When the user establishes one (file layout, naming, language choice, commit style), record it here so the next session inherits it.
