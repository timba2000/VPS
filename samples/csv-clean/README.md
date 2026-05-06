# csv-clean

A small CLI to clean messy CSV files. Trims whitespace, drops empty rows and columns, optionally dedupes, normalizes headers, and drops nuisance columns.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python csv_clean.py messy.csv cleaned.csv \
    --dedupe-on email \
    --snake-headers \
    --drop-cols notes
```

Run on the included example:

```bash
python csv_clean.py examples/messy.csv cleaned.csv --dedupe --snake-headers
```

## Flags

| Flag | Effect |
|---|---|
| `--dedupe` | Drop duplicate rows (after whitespace trim). |
| `--dedupe-on a,b` | Drop duplicates considering only the named columns. Implies `--dedupe`. |
| `--snake-headers` | Lowercase + replace non-alphanumeric runs with `_`. |
| `--drop-cols a,b` | Remove the listed columns by name. |

## Tests

```bash
PYTHONPATH=. pytest -q
```
