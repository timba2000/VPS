import pandas as pd

from csv_clean import clean, normalize_header


def test_normalize_header():
    assert normalize_header("First Name") == "first_name"
    assert normalize_header("  E-mail Address  ") == "e_mail_address"
    assert normalize_header("Total ($)") == "total"


def test_trims_whitespace_and_drops_empty_rows():
    df = pd.DataFrame({"name": ["  alice  ", "  ", "bob"], "age": [30, None, 25]})
    out = clean(df)
    assert list(out["name"]) == ["alice", "bob"]
    assert list(out["age"]) == [30, 25]


def test_drops_fully_empty_columns():
    df = pd.DataFrame({"name": ["a", "b"], "junk": [None, None]})
    out = clean(df)
    assert "junk" not in out.columns


def test_dedupe_default_keeps_first():
    df = pd.DataFrame({"id": [1, 1, 2], "v": ["a", "a", "c"]})
    out = clean(df, dedupe=True)
    assert list(out["v"]) == ["a", "c"]


def test_dedupe_on_subset():
    df = pd.DataFrame({"email": ["x@a", "x@a", "y@b"], "name": ["X1", "X2", "Y"]})
    out = clean(df, dedupe=True, dedupe_on=["email"])
    assert list(out["name"]) == ["X1", "Y"]


def test_snake_headers():
    df = pd.DataFrame({"First Name": ["a"], "E-mail": ["b"]})
    out = clean(df, snake_headers=True)
    assert list(out.columns) == ["first_name", "e_mail"]


def test_drop_cols():
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    out = clean(df, drop_cols=["b"])
    assert list(out.columns) == ["a", "c"]
