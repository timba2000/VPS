"""Australian default-superannuation fund alias table and matcher.

Each fund has a canonical name plus aliases (variations as commonly written in
enterprise agreements). The matcher uses rapidfuzz for token-set matching with a
high threshold to avoid false positives, and requires word-boundary matches so
short acronyms like "ART" don't fire on words like "depART-ment".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process


@dataclass(frozen=True)
class Fund:
    canonical: str
    aliases: tuple[str, ...]


# Largest AU super funds plus common industry funds frequently named in EAs.
# Order does not matter for matching, but the canonical name is what we store.
FUNDS: tuple[Fund, ...] = (
    Fund("AustralianSuper", ("AustralianSuper", "Australian Super", "ASUPER")),
    Fund("Australian Retirement Trust", (
        "Australian Retirement Trust", "ART", "Sunsuper", "QSuper",
    )),
    Fund("Aware Super", ("Aware Super", "First State Super", "FSS", "VicSuper")),
    Fund("Cbus", ("Cbus", "C-Bus", "Construction and Building Unions Super")),
    Fund("HESTA", ("HESTA", "Health Employees Superannuation Trust Australia")),
    Fund("Hostplus", ("Hostplus", "Host-Plus", "Host Plus")),
    Fund("REST", ("REST", "Rest Super", "Retail Employees Superannuation Trust")),
    Fund("UniSuper", ("UniSuper", "Uni Super")),
    Fund("CareSuper", ("CareSuper", "Care Super")),
    Fund("MediaSuper", ("MediaSuper", "Media Super")),
    Fund("Mine Super", ("Mine Super", "MineSuper", "AUSCOAL Super")),
    Fund("BUSSQ", ("BUSSQ", "Building Unions Superannuation Scheme Queensland")),
    Fund("legalsuper", ("legalsuper", "Legal Super")),
    Fund("Mercer Super Trust", ("Mercer Super", "Mercer Superannuation", "Mercer Super Trust")),
    Fund("Russell Investments Master Trust", ("Russell Investments Master Trust", "Russell Super")),
    Fund("NGS Super", ("NGS Super", "Non-Government Schools Super")),
    Fund("TWUSUPER", ("TWUSUPER", "TWU Super", "Transport Workers' Union Super")),
    Fund("AMIST Super", ("AMIST Super", "AMIST")),
    Fund("First Super", ("First Super",)),
    Fund("Spirit Super", ("Spirit Super", "Tasplan", "MTAA Super")),
    Fund("Vision Super", ("Vision Super",)),
    Fund("Equip Super", ("Equip Super", "Equipsuper")),
    Fund("Prime Super", ("Prime Super",)),
    Fund("Smartsave Member's Choice Super", ("Smartsave",)),
    Fund("Maritime Super", ("Maritime Super",)),
    Fund("ESSSuper", ("ESSSuper", "ESS Super", "Emergency Services Super")),
    Fund("GESB", ("GESB", "Government Employees Superannuation Board")),
    Fund("Catholic Super", ("Catholic Super", "CSF", "Catholic Superannuation Fund")),
)


# Build flat alias → canonical lookup. Keys preserve original casing; matching
# uses re.IGNORECASE in _word_boundary_re below.
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for f in FUNDS:
    for alias in f.aliases:
        _ALIAS_TO_CANONICAL[alias] = f.canonical


# Aliases shorter than this need a hard word-boundary match (no fuzzy).
_STRICT_ALIAS_MAX_LEN = 6


def _word_boundary_re(alias: str) -> re.Pattern[str]:
    # Pattern that requires non-alphanumeric on both sides, so "ART" won't match
    # "depART-ment". For aliases ending in a digit (none currently) \b is fine.
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", re.I)


_BOUNDARY_PATTERNS: dict[str, re.Pattern[str]] = {
    alias: _word_boundary_re(alias) for alias in _ALIAS_TO_CANONICAL
}


_OCR_SPLIT_TAIL = re.compile(r"\b([A-Z]{3,})\s+([A-Z])\b")


def _normalise(text: str) -> str:
    """Repair common OCR splits like "HEST A" -> "HESTA"."""
    return _OCR_SPLIT_TAIL.sub(r"\1\2", text)


def find_funds(text: str, *, threshold: int = 95) -> list[tuple[str, str, int]]:
    """Return (canonical_name, matched_alias, score) for every fund mentioned.

    Uses word-boundary substring matching first (reliable), then fuzzy partial
    matching only on longer aliases as a backup for OCR-mangled text.
    """
    if not text:
        return []
    text = _normalise(text)
    found: dict[str, tuple[str, int]] = {}

    # 1. Word-boundary substring hits — high confidence.
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if _BOUNDARY_PATTERNS[alias].search(text):
            existing = found.get(canonical)
            if existing is None or existing[1] < 100:
                found[canonical] = (alias, 100)

    # 2. Fuzzy fallback — only on aliases that are unambiguous (>= 7 chars or
    #    contain a space/digit). This guards against OCR artefacts without
    #    over-matching short acronyms.
    long_aliases = [
        a for a in _ALIAS_TO_CANONICAL
        if len(a) > _STRICT_ALIAS_MAX_LEN or " " in a
    ]
    lower = text.lower()
    for match in process.extract(
        lower, [a.lower() for a in long_aliases],
        scorer=fuzz.partial_ratio, score_cutoff=threshold, limit=10,
    ):
        alias_lc, score, _ = match
        # find the original cased alias to look up canonical
        for a in long_aliases:
            if a.lower() == alias_lc:
                canonical = _ALIAS_TO_CANONICAL[a]
                break
        else:
            continue
        existing = found.get(canonical)
        if existing is None or existing[1] < score:
            found[canonical] = (alias_lc, int(score))

    return [
        (canonical, alias, score)
        for canonical, (alias, score) in found.items()
    ]
