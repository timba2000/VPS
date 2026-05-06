"""Clean a messy CSV: trim whitespace, drop empty rows/columns, dedupe, normalize headers."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


def normalize_header(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^\w]+", "_", name)
    return name.strip("_")


def clean(
    df: pd.DataFrame,
    *,
    dedupe: bool = False,
    dedupe_on: list[str] | None = None,
    snake_headers: bool = False,
    drop_cols: list[str] | None = None,
) -> pd.DataFrame:
    df = df.copy()

    # Trim whitespace in string columns and treat empty strings as NaN.
    obj_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in obj_cols:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)

    # Drop fully-empty columns, then fully-empty rows.
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")

    if drop_cols:
        df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    if snake_headers:
        df.columns = [normalize_header(c) for c in df.columns]

    if dedupe:
        df = df.drop_duplicates(subset=dedupe_on, keep="first")

    df = df.reset_index(drop=True)
    return df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="Path to messy CSV")
    p.add_argument("output", type=Path, help="Path to write cleaned CSV")
    p.add_argument("--dedupe", action="store_true", help="Drop duplicate rows")
    p.add_argument(
        "--dedupe-on",
        help="Comma-separated columns to dedupe on (implies --dedupe)",
    )
    p.add_argument("--snake-headers", action="store_true", help="Convert headers to snake_case")
    p.add_argument("--drop-cols", help="Comma-separated column names to drop")
    args = p.parse_args(argv)

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2

    df = pd.read_csv(args.input)
    rows_in, cols_in = df.shape

    cleaned = clean(
        df,
        dedupe=args.dedupe or bool(args.dedupe_on),
        dedupe_on=args.dedupe_on.split(",") if args.dedupe_on else None,
        snake_headers=args.snake_headers,
        drop_cols=args.drop_cols.split(",") if args.drop_cols else None,
    )
    cleaned.to_csv(args.output, index=False)

    rows_out, cols_out = cleaned.shape
    print(
        f"{args.input} -> {args.output}: "
        f"{rows_in} rows, {cols_in} cols -> {rows_out} rows, {cols_out} cols",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
