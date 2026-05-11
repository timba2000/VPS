"""SQLite schema and connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "fwc.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS agreements (
  ae_id           TEXT PRIMARY KEY,
  matter_number   TEXT,
  title           TEXT,
  company_name    TEXT,
  abn             TEXT,
  version         INTEGER,
  status          TEXT,
  industry        TEXT,
  expires         DATE,
  published_date  DATE,
  detail_url      TEXT,
  pdf_url         TEXT,
  pdf_path        TEXT,
  pdf_sha256      TEXT,
  pdf_bytes       INTEGER,
  crawled_at      DATETIME,
  enriched_at     DATETIME,
  downloaded_at   DATETIME
);

CREATE INDEX IF NOT EXISTS ix_agreements_company ON agreements(company_name);
CREATE INDEX IF NOT EXISTS ix_agreements_abn     ON agreements(abn);
CREATE INDEX IF NOT EXISTS ix_agreements_status  ON agreements(status);

-- multi-employer agreements may list several parties
CREATE TABLE IF NOT EXISTS parties (
  ae_id        TEXT NOT NULL,
  company_name TEXT NOT NULL,
  abn          TEXT,
  PRIMARY KEY (ae_id, company_name),
  FOREIGN KEY (ae_id) REFERENCES agreements(ae_id)
);

CREATE TABLE IF NOT EXISTS extraction (
  ae_id              TEXT PRIMARY KEY REFERENCES agreements(ae_id),
  date_signed        DATE,
  term_start         DATE,
  term_end           DATE,
  ocr                INTEGER,
  no_default_named   INTEGER DEFAULT 0,
  confidence_super   TEXT,
  confidence_signed  TEXT,
  confidence_term    TEXT,
  confidence_signer  TEXT,
  raw_super_excerpt  TEXT,
  raw_signed_excerpt TEXT,
  raw_signer_excerpt TEXT,
  extracted_at       DATETIME
);

-- One agreement → many signatories (employer + union side)
CREATE TABLE IF NOT EXISTS signatories (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ae_id     TEXT NOT NULL REFERENCES agreements(ae_id),
  name      TEXT,
  title     TEXT,
  side      TEXT,  -- 'employer' / 'employee' / 'unknown'
  excerpt   TEXT
);
CREATE INDEX IF NOT EXISTS ix_sig_ae ON signatories(ae_id);

CREATE TABLE IF NOT EXISTS default_super (
  ae_id          TEXT NOT NULL REFERENCES agreements(ae_id),
  fund_name      TEXT NOT NULL,
  fund_abn       TEXT,
  fund_usi       TEXT,
  source_excerpt TEXT,
  source         TEXT,
  PRIMARY KEY (ae_id, fund_name)
);
CREATE INDEX IF NOT EXISTS ix_default_super_fund ON default_super(fund_name);

-- Crawl progress: which list pages have been completed
CREATE TABLE IF NOT EXISTS crawl_state (
  status_code INTEGER NOT NULL,
  page        INTEGER NOT NULL,
  rows        INTEGER,
  fetched_at  DATETIME,
  PRIMARY KEY (status_code, page)
);
"""


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in have:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    _add_column_if_missing(conn, "extraction", "no_default_named", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "default_super", "source", "TEXT")
    return conn


@contextmanager
def cursor(conn: sqlite3.Connection):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def upsert_agreement(conn: sqlite3.Connection, row: dict) -> None:
    cols = ",".join(row)
    placeholders = ",".join(f":{k}" for k in row)
    updates = ",".join(f"{k}=excluded.{k}" for k in row if k != "ae_id")
    sql = (
        f"INSERT INTO agreements ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(ae_id) DO UPDATE SET {updates}"
    )
    conn.execute(sql, row)


def upsert_party(conn: sqlite3.Connection, ae_id: str, company_name: str, abn: str | None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO parties (ae_id, company_name, abn) VALUES (?,?,?)",
        (ae_id, company_name, abn),
    )
