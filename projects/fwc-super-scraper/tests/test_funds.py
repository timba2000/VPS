from fwc_super.funds import find_funds


def _names(matches):
    return sorted(c for c, _, _ in matches)


def test_substring_match_australian_super():
    assert _names(find_funds("The default fund will be Australian Super.")) == ["AustralianSuper"]


def test_no_false_positive_on_short_alias_art():
    # "ART" is an alias for Australian Retirement Trust — must not fire on
    # words like "department" or "smart".
    assert find_funds("The Department considers participation important.") == []


def test_word_boundary_blocks_partial_token():
    # "REST" must not fire on the substring "rest" inside "interest"
    assert find_funds("Members may earn interest on their balance.") == []


def test_ocr_split_repaired_for_hesta():
    # OCR commonly turns HESTA into HEST A
    matches = find_funds('default fund, HEST A ("Default Fund")')
    assert "HESTA" in _names(matches)


def test_multiple_funds_in_one_clause():
    matches = find_funds(
        "The default fund will be Cbus Super. Salary sacrifice is also available "
        "via the Mercer Super Trust."
    )
    assert "Cbus" in _names(matches)
    assert "Mercer Super Trust" in _names(matches)


def test_unknown_text_returns_empty():
    assert find_funds("This clause has nothing to do with funds.") == []
