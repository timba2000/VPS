#!/usr/bin/env python
"""Live terminal dashboard for the fwc extract pipeline.

Refreshes every 2s. Reads from the SQLite DB, `systemctl show` for the
currently active `fwc-extract-chunked-*` unit, and tails the unit's log
file for the most recent batch boundaries and watchdog signals.

Run from the project root:

    .venv/bin/python scripts/dashboard.py

Press Ctrl-C to quit.
"""
from __future__ import annotations

import re
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fwc_super.db import connect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
UNIT_PREFIX = "fwc-extract-chunked-"
REFRESH_SECONDS = 2.0
RATE_WINDOW_SECONDS = 300  # 5-min rolling rate

BATCH_LINE_RE = re.compile(r"^--- batch (\d+)\s+remaining=(\d+)\s+(\S+)")
START_LINE_RE = re.compile(r"^\[extract\] start (\S+) (\S+) \(([\d.]+) MB\)")
RESULT_LINE_RE = re.compile(r"^(AE\d+)\t(.+)")


def active_unit() -> str | None:
    out = subprocess.run(
        ["systemctl", "list-units", "--type=service", "--state=active",
         "--no-legend", f"{UNIT_PREFIX}*.service"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        name = line.strip().split()[0] if line.strip() else ""
        if name.startswith(UNIT_PREFIX):
            return name
    return None


def unit_props(unit: str) -> dict:
    out = subprocess.run(
        ["systemctl", "show", unit, "-p",
         "ActiveState,SubState,MainPID,MemoryCurrent,MemoryHigh,MemoryMax,"
         "ExecMainStartTimestamp,Result,ExecMainStatus"],
        capture_output=True, text=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}P"


def fmt_duration(secs: float) -> str:
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60:02d}s"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"


def parse_systemd_timestamp(s: str) -> float | None:
    # e.g. "Tue 2026-05-12 06:21:58 UTC"
    parts = s.split()
    if len(parts) < 4:
        return None
    try:
        dt = datetime.strptime(" ".join(parts[1:3]), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def log_path_for(unit: str) -> Path:
    # fwc-extract-chunked-v4.service -> data/extract_chunked_v4.log
    name = unit.removeprefix(UNIT_PREFIX).removesuffix(".service")
    return DATA_DIR / f"extract_chunked_{name}.log"


def tail_lines(path: Path, max_lines: int = 4000) -> list[str]:
    if not path.exists():
        return []
    # Cheap tail: read whole file (typical run logs are KB-scale).
    with path.open() as f:
        return f.read().splitlines()[-max_lines:]


def parse_log(lines: list[str]) -> dict:
    batches: list[tuple[int, int, str]] = []
    in_flight_ae: str | None = None
    in_flight_pdf: str | None = None
    in_flight_mb: float | None = None
    quarantines: list[str] = []
    timeouts = 0
    batch_fails = 0
    all_done: str | None = None

    for line in lines:
        m = BATCH_LINE_RE.match(line)
        if m:
            batches.append((int(m.group(1)), int(m.group(2)), m.group(3)))
            continue
        m = START_LINE_RE.match(line)
        if m:
            in_flight_ae = m.group(1)
            in_flight_pdf = m.group(2)
            in_flight_mb = float(m.group(3))
            continue
        m = RESULT_LINE_RE.match(line)
        if m and m.group(1) == in_flight_ae:
            in_flight_ae = None
            in_flight_pdf = None
            in_flight_mb = None
            continue
        if line.startswith("QUARANTINE "):
            quarantines.append(line)
            in_flight_ae = None
            in_flight_pdf = None
            in_flight_mb = None
        elif line.startswith("BATCH_TIMEOUT"):
            timeouts += 1
        elif line.startswith("BATCH_FAIL"):
            batch_fails += 1
        elif line.startswith("ALL_DONE"):
            all_done = line

    return {
        "batches": batches,
        "in_flight_ae": in_flight_ae,
        "in_flight_pdf": in_flight_pdf,
        "in_flight_mb": in_flight_mb,
        "quarantines": quarantines,
        "timeouts": timeouts,
        "batch_fails": batch_fails,
        "all_done": all_done,
    }


def db_stats(conn) -> dict:
    rows = {
        "agreements": conn.execute("SELECT COUNT(*) FROM agreements").fetchone()[0],
        "with_pdf": conn.execute(
            "SELECT COUNT(*) FROM agreements WHERE pdf_path IS NOT NULL"
        ).fetchone()[0],
        "extracted": conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0],
        "too_large": conn.execute(
            "SELECT COUNT(*) FROM extraction WHERE too_large=1"
        ).fetchone()[0],
        "no_default_named": conn.execute(
            "SELECT COUNT(*) FROM extraction WHERE no_default_named=1"
        ).fetchone()[0],
        "remaining": conn.execute(
            "SELECT COUNT(*) FROM agreements a "
            "LEFT JOIN extraction e ON a.ae_id=e.ae_id "
            "WHERE e.ae_id IS NULL AND a.pdf_path IS NOT NULL"
        ).fetchone()[0],
    }
    return rows


def render(conn, history: deque) -> Panel:
    now = time.time()
    stats = db_stats(conn)
    history.append((now, stats["extracted"]))
    while history and now - history[0][0] > RATE_WINDOW_SECONDS:
        history.popleft()

    rate_per_min = 0.0
    eta_text = "-"
    if len(history) >= 2:
        t0, c0 = history[0]
        dt = now - t0
        dc = stats["extracted"] - c0
        if dt > 0:
            rate_per_min = dc / dt * 60.0
            if rate_per_min > 0 and stats["remaining"] > 0:
                eta_text = fmt_duration(stats["remaining"] / rate_per_min * 60.0)

    unit = active_unit()
    props = unit_props(unit) if unit else {}
    pid = props.get("MainPID")
    mem_current = int(props["MemoryCurrent"]) if props.get("MemoryCurrent", "").isdigit() else None
    mem_high = int(props["MemoryHigh"]) if props.get("MemoryHigh", "").isdigit() else None
    mem_max = int(props["MemoryMax"]) if props.get("MemoryMax", "").isdigit() else None
    start_ts = parse_systemd_timestamp(props.get("ExecMainStartTimestamp", ""))
    uptime = fmt_duration(now - start_ts) if start_ts else "-"

    log_info = parse_log(tail_lines(log_path_for(unit))) if unit else None

    db_table = Table.grid(padding=(0, 2))
    db_table.add_column(justify="right", style="dim")
    db_table.add_column()
    db_table.add_row("agreements", f"{stats['agreements']:>6,}")
    db_table.add_row("with pdf", f"{stats['with_pdf']:>6,}")
    db_table.add_row("extracted", f"[green]{stats['extracted']:>6,}[/green]")
    db_table.add_row("remaining", f"[yellow]{stats['remaining']:>6,}[/yellow]")
    db_table.add_row("too_large", f"{stats['too_large']:>6,}")
    db_table.add_row("no_default_named", f"{stats['no_default_named']:>6,}")
    pct = (stats["extracted"] / stats["with_pdf"] * 100) if stats["with_pdf"] else 0
    db_table.add_row("progress", f"{pct:5.1f}% of downloaded PDFs")
    db_table.add_row("rate (5m)", f"{rate_per_min:5.1f} PDFs/min")
    db_table.add_row("ETA", eta_text)

    svc_table = Table.grid(padding=(0, 2))
    svc_table.add_column(justify="right", style="dim")
    svc_table.add_column()
    if unit:
        state_color = "green" if props.get("ActiveState") == "active" else "red"
        svc_table.add_row(
            "unit",
            f"[{state_color}]{unit}[/{state_color}] "
            f"({props.get('ActiveState', '?')}/{props.get('SubState', '?')})",
        )
        svc_table.add_row("uptime", uptime)
        svc_table.add_row("PID", pid or "-")
        mem_str = fmt_bytes(mem_current)
        if mem_high:
            mem_str += f" / high {fmt_bytes(mem_high)}"
        if mem_max:
            mem_str += f" / max {fmt_bytes(mem_max)}"
        svc_table.add_row("memory", mem_str)
        if log_info and log_info["batches"]:
            last = log_info["batches"][-1]
            svc_table.add_row("current batch", f"#{last[0]} (remaining at start: {last[1]:,})")
        if log_info and log_info["in_flight_ae"]:
            svc_table.add_row(
                "in flight",
                f"{log_info['in_flight_ae']} ({log_info['in_flight_mb']:.1f} MB)",
            )
        if log_info and log_info["all_done"]:
            svc_table.add_row("status", f"[bold green]{log_info['all_done']}[/bold green]")
    else:
        svc_table.add_row("unit", "[red]no active fwc-extract-chunked-* service[/red]")

    wd_table = Table.grid(padding=(0, 2))
    wd_table.add_column(justify="right", style="dim")
    wd_table.add_column()
    if log_info:
        q_color = "yellow" if log_info["quarantines"] else "dim"
        wd_table.add_row("quarantines", f"[{q_color}]{len(log_info['quarantines'])}[/{q_color}]")
        wd_table.add_row("timeouts", str(log_info["timeouts"]))
        wd_table.add_row("batch fails", str(log_info["batch_fails"]))
        if log_info["quarantines"]:
            recent = log_info["quarantines"][-3:]
            wd_table.add_row("recent", "\n".join(recent))
    else:
        wd_table.add_row("watchdog", "no log available")

    header = Text(
        f"  fwc extract pipeline — {datetime.now().strftime('%H:%M:%S')}",
        style="bold",
    )

    return Panel(
        Group(
            header,
            Panel(db_table, title="database", border_style="cyan"),
            Panel(svc_table, title="service",  border_style="green"),
            Panel(wd_table, title="watchdog", border_style="magenta"),
        ),
        border_style="white",
    )


def main() -> None:
    console = Console()
    conn = connect()
    history: deque = deque()
    try:
        with Live(render(conn, history), console=console, refresh_per_second=2) as live:
            while True:
                time.sleep(REFRESH_SECONDS)
                live.update(render(conn, history))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
