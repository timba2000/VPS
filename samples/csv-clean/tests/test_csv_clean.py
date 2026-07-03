import pandas as pd

from csv_clean import clean, main, normalize_header


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


def test_snake_headers_with_dedupe_on_uses_original_names():
    # Regression: snake_headers renamed columns before dedupe ran, so dedupe_on
    # (original-cased) referenced a column that no longer existed -> KeyError.
    df = pd.DataFrame(
        {"Email Address": ["x@a", "x@a", "y@b"], "Full Name": ["X1", "X2", "Y"]}
    )
    out = clean(df, dedupe=True, dedupe_on=["Email Address"], snake_headers=True)
    assert list(out.columns) == ["email_address", "full_name"]
    assert list(out["full_name"]) == ["X1", "Y"]


def test_snake_headers_with_drop_cols_uses_original_names():
    # Regression: drop_cols required original casing while dedupe_on required
    # snake_case. Both now consistently take the original header names.
    df = pd.DataFrame({"First Name": ["a"], "Notes": ["x"], "E-mail": ["b"]})
    out = clean(df, snake_headers=True, drop_cols=["Notes"])
    assert list(out.columns) == ["first_name", "e_mail"]


def test_main_dedupe_on_with_snake_headers_end_to_end(tmp_path):
    # End-to-end CLI: --dedupe-on implies --dedupe, combined with --snake-headers
    # (the flag combination that used to crash), plus the read_csv/to_csv round trip.
    src = tmp_path / "in.csv"
    src.write_text(
        "First Name,Email Address\n"
        "Alice,alice@example.com\n"
        "Alice,alice@example.com\n"
        "Bob,bob@example.com\n"
    )
    dst = tmp_path / "out.csv"
    rc = main([str(src), str(dst), "--dedupe-on", "Email Address", "--snake-headers"])
    assert rc == 0
    out = pd.read_csv(dst)
    assert list(out.columns) == ["first_name", "email_address"]
    assert list(out["email_address"]) == ["alice@example.com", "bob@example.com"]


def test_main_drop_cols_comma_split(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("a,b,c\n1,2,3\n")
    dst = tmp_path / "out.csv"
    rc = main([str(src), str(dst), "--drop-cols", "b,c"])
    assert rc == 0
    assert list(pd.read_csv(dst).columns) == ["a"]


def test_main_missing_input_returns_2(tmp_path):
    rc = main([str(tmp_path / "nope.csv"), str(tmp_path / "out.csv")])
    assert rc == 2
