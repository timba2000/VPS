from fwc_super.funds import find_funds


def _names(matches):
    return sorted(c for c, _, _ in matches)


def test_substring_match_australian_super():
    assert _names(find_funds("The default fund will be Australian Super.")) == ["AustralianSuper"]


def test_bare_art_not_an_alias():
    # The bare "ART" alias was dropped because legal-style "Art." (Article)
    # abbreviations and bare "art" produced false positives. ART must only be
    # reachable via the long aliases (Australian Retirement Trust / Sunsuper /
    # QSuper).
    assert find_funds("Art. 36 covers superannuation.") == []
    assert find_funds("the art of negotiation") == []
    assert "Australian Retirement Trust" in {
        c for c, _, _ in find_funds("Default fund: Sunsuper.")
    }


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


def test_amp_signature_super_matches():
    matches = find_funds("Contributions will be paid to AMP SignatureSuper.")
    assert "AMP Super" in _names(matches)


def test_pssap_matches_csc():
    matches = find_funds("The default fund is PSSap.")
    assert "Commonwealth Superannuation Corporation" in _names(matches)


def test_military_super_matches_csc():
    matches = find_funds("Defence personnel are members of MilitarySuper.")
    assert "Commonwealth Superannuation Corporation" in _names(matches)


def test_cbus_punctuation_variant_plus():
    # OCR / typesetting sometimes renders Cbus as "C+BUS"
    matches = find_funds("The default fund will be C+BUS Super.")
    assert "Cbus" in _names(matches)


def test_cbus_punctuation_variant_space():
    matches = find_funds("Default fund: C BUS Superannuation.")
    assert "Cbus" in _names(matches)


def test_intra_word_split_rejoined_when_alias():
    # "MyS uper" isn't a fund itself, but the rejoin logic should be safe — pick
    # a real one: "Australian Super" already matches as-is. Use a fund alias that
    # gets mid-word-split: "Hostp lus" should rejoin to "Hostplus".
    matches = find_funds("Default fund: Hostp lus.")
    assert "Hostplus" in _names(matches)


def test_intra_word_split_does_not_weld_random_words():
    # Two adjacent words whose concatenation is not a known alias must stay split.
    assert find_funds("hello world is not a fund.") == []


def test_team_super_with_and_without_space():
    assert "Team Super" in _names(find_funds("Default fund is Team Super."))
    # "TEAMSUPER" as one word appears in some EAs.
    assert "Team Super" in _names(find_funds("Industry fund is TEAMSUPER."))


def test_mlc_super_matches():
    assert "MLC Super" in _names(find_funds("Contributions paid to the MLC Superannuation Fund."))


def test_plum_super_matches():
    # Sub-plan phrasing common in EAs.
    matches = find_funds("Boral Super, a sub-plan of the Plum Superannuation Fund.")
    assert "Plum Super" in _names(matches)


def test_brighter_super_matches():
    assert "Brighter Super" in _names(
        find_funds("Brighter Super will be the Company's default superannuation fund.")
    )


def test_transport_workers_no_apostrophe():
    # "Transport Workers Super" / "Transport Workers Union Super" (no apostrophe)
    # are common variants — confirm they all map back to TWUSUPER.
    assert "TWUSUPER" in _names(find_funds("Default fund: Transport Workers Super."))
    assert "TWUSUPER" in _names(
        find_funds("Contributions to the Transport Workers Union Super fund.")
    )
