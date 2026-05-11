"""Command-line entrypoints."""

from __future__ import annotations

import sys
from typing import Iterable

import click
from rich.console import Console
from rich.table import Table

from .crawl import STATUS_APPROVED, crawl as crawl_iter
from .download import download as download_iter
from .enrich import enrich as enrich_iter
from .extract import extract as extract_iter
from .db import connect

console = Console()


@click.group()
def main() -> None:
    """fwc — Fair Work Commission default-super scraper."""


@main.command("crawl")
@click.option("--pages", type=int, default=None, help="Stop after N pages (default: until empty).")
@click.option("--start-page", type=int, default=0)
@click.option("--status", "status_code", type=int, default=STATUS_APPROVED)
@click.option("--items-per-page", type=int, default=50)
@click.option("--delay", type=float, default=1.0)
def cmd_crawl(pages: int | None, start_page: int, status_code: int, items_per_page: int, delay: float) -> None:
    """Walk the FWC search results into the local DB."""
    total = 0
    for n in crawl_iter(
        pages=pages,
        start_page=start_page,
        status_code=status_code,
        items_per_page=items_per_page,
        delay=delay,
    ):
        total += n
        console.print(f"[green]+{n}[/green]  total: {total}")
    console.print(f"[bold]Done. {total} rows added/updated.[/bold]")


@main.command("enrich")
@click.option("--limit", type=int, default=None)
@click.option("--delay", type=float, default=1.0)
def cmd_enrich(limit: int | None, delay: float) -> None:
    """Fetch detail pages to fill industry + canonical PDF URL."""
    n = 0
    for line in enrich_iter(limit=limit, delay=delay):
        n += 1
        console.print(line)
    console.print(f"[bold]Enriched {n}.[/bold]")


@main.command("download")
@click.option("--limit", type=int, default=None)
@click.option("--delay", type=float, default=1.0)
@click.option("--redownload/--no-redownload", default=False)
def cmd_download(limit: int | None, delay: float, redownload: bool) -> None:
    """Download PDFs into data/pdfs/."""
    n = 0
    for ae, msg in download_iter(limit=limit, delay=delay, redownload=redownload):
        n += 1
        console.print(f"{ae}\t{msg}")
    console.print(f"[bold]Processed {n}.[/bold]")


@main.command("extract")
@click.option("--limit", type=int, default=None)
def cmd_extract(limit: int | None) -> None:
    """Parse downloaded PDFs and populate the extraction tables."""
    n = 0
    for ae, msg in extract_iter(limit=limit):
        n += 1
        console.print(f"{ae}\t{msg}")
    console.print(f"[bold]Extracted {n}.[/bold]")


@main.command("query")
@click.option("--fund", default=None, help="Canonical fund name e.g. AustralianSuper")
@click.option("--abn", default=None)
@click.option("--company", default=None, help="LIKE-match on company name")
@click.option("--industry", default=None, help="LIKE-match on industry")
@click.option("--signed-after", default=None)
@click.option("--signed-before", default=None)
@click.option("--expires-after", default=None)
@click.option("--confidence", default=None, help="Minimum super-fund confidence: high|medium|low")
@click.option("--limit", type=int, default=50)
@click.option("--csv", "as_csv", is_flag=True, default=False)
def cmd_query(
    fund: str | None,
    abn: str | None,
    company: str | None,
    industry: str | None,
    signed_after: str | None,
    signed_before: str | None,
    expires_after: str | None,
    confidence: str | None,
    limit: int,
    as_csv: bool,
) -> None:
    """Query the local DB."""
    sql = (
        "SELECT a.ae_id, a.company_name, a.abn, a.industry, "
        "       group_concat(d.fund_name, ', ') AS funds, "
        "       e.term_start, e.term_end, e.date_signed, "
        "       e.confidence_super, a.expires "
        "FROM agreements a "
        "LEFT JOIN default_super d ON a.ae_id = d.ae_id "
        "LEFT JOIN extraction e ON a.ae_id = e.ae_id "
    )
    where: list[str] = []
    params: list[object] = []
    if fund:
        where.append("a.ae_id IN (SELECT ae_id FROM default_super WHERE fund_name = ?)")
        params.append(fund)
    if abn:
        where.append("a.abn = ?"); params.append(abn)
    if company:
        where.append("a.company_name LIKE ?"); params.append(f"%{company}%")
    if industry:
        where.append("a.industry LIKE ?"); params.append(f"%{industry}%")
    if signed_after:
        where.append("e.date_signed >= ?"); params.append(signed_after)
    if signed_before:
        where.append("e.date_signed <= ?"); params.append(signed_before)
    if expires_after:
        where.append("a.expires >= ?"); params.append(expires_after)
    if confidence:
        levels = {"low": 0, "medium": 1, "high": 2}
        min_lvl = levels.get(confidence.lower(), 0)
        keep = [k for k, v in levels.items() if v >= min_lvl]
        placeholders = ",".join("?" * len(keep))
        where.append(f"e.confidence_super IN ({placeholders})")
        params.extend(keep)
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "GROUP BY a.ae_id ORDER BY a.published_date DESC LIMIT ?"
    params.append(limit)

    conn = connect()
    rows = list(conn.execute(sql, params))
    if as_csv:
        import csv as _csv
        w = _csv.writer(sys.stdout)
        w.writerow([d[0] for d in (rows[0].keys() if rows else [
            ("ae_id",), ("company_name",), ("abn",), ("industry",),
            ("funds",), ("term_start",), ("term_end",), ("date_signed",),
            ("confidence_super",), ("expires",),
        ])])
        for r in rows:
            w.writerow([r[k] for k in r.keys()])
        return
    table = Table(show_header=True, header_style="bold cyan")
    cols = ["ae_id", "company", "abn", "industry", "funds", "signed", "term", "conf"]
    for c in cols:
        table.add_column(c)
    for r in rows:
        term = f"{r['term_start'] or '-'}..{r['term_end'] or r['expires'] or '-'}"
        table.add_row(
            r["ae_id"] or "",
            (r["company_name"] or "")[:40],
            r["abn"] or "",
            (r["industry"] or "")[:40],
            r["funds"] or "-",
            r["date_signed"] or "-",
            term,
            r["confidence_super"] or "-",
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} rows[/dim]")


@main.command("stats")
def cmd_stats() -> None:
    """Print counts and confidence breakdown."""
    conn = connect()
    n = conn.execute("SELECT COUNT(*) FROM agreements").fetchone()[0]
    n_pdf = conn.execute("SELECT COUNT(*) FROM agreements WHERE pdf_path IS NOT NULL").fetchone()[0]
    n_ext = conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0]
    n_super = conn.execute("SELECT COUNT(DISTINCT ae_id) FROM default_super").fetchone()[0]
    n_no_default = conn.execute(
        "SELECT COUNT(*) FROM extraction WHERE no_default_named = 1"
    ).fetchone()[0]
    # Recall denominator excludes EAs that legitimately don't name a default fund.
    eligible = max(1, n_ext - n_no_default)
    recall = 100 * n_super / eligible
    by_conf = list(conn.execute(
        "SELECT confidence_super, COUNT(*) FROM extraction GROUP BY confidence_super"
    ))
    by_fund = list(conn.execute(
        "SELECT fund_name, COUNT(*) FROM default_super GROUP BY fund_name ORDER BY 2 DESC LIMIT 15"
    ))
    by_source = list(conn.execute(
        "SELECT COALESCE(source, 'extract'), COUNT(*) FROM default_super GROUP BY 1 ORDER BY 2 DESC"
    ))
    console.print(f"agreements: {n:>6}    with pdf: {n_pdf:>6}    extracted: {n_ext:>6}    with super: {n_super:>6}")
    console.print(f"no-default-named (excluded from recall): {n_no_default}")
    console.print(f"recall on eligible: {n_super}/{eligible} = {recall:.1f}%")
    console.print("[bold]Super-fund confidence:[/bold]")
    for conf, count in by_conf:
        console.print(f"  {conf or 'null':<8}  {count}")
    console.print("[bold]default_super by source:[/bold]")
    for src, count in by_source:
        console.print(f"  {src:<24}  {count}")
    console.print("[bold]Top default funds:[/bold]")
    for fund, count in by_fund:
        console.print(f"  {fund:<32}  {count}")


if __name__ == "__main__":
    main()
