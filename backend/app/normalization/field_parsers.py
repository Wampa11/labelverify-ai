"""
Normalization helpers for extracted numeric label fields.

Architectural responsibility: structured ABV/net values while preserving raw OCR text.
Not regulatory equivalence decisions. Does not invent missing characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedAlcohol:
    """Parsed alcohol strength from OCR text."""

    raw_text: str
    abv_percent: float | None
    proof: float | None
    source: str  # "abv" | "proof" | "both"
    abv_span: str | None = None
    proof_span: str | None = None


@dataclass(frozen=True)
class ParsedNetContents:
    """Parsed net contents from OCR text."""

    raw_text: str
    value: float
    unit: str  # canonical "mL" or "L"
    match_span: str = ""


_ABV_PATTERNS = [
    re.compile(
        r"(?P<span>(?P<value>\d{1,2}(?:\.\d+)?)\s*%\s*(?:alc\.?/?\s*vol\.?|alcohol\s+by\s+volume|abv)\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<span>(?P<value>\d{1,2}(?:\.\d+)?)\s*%?\s*(?:alc\.?/?\s*vol\.?|alcohol\s+by\s+volume)\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<span>(?:alc\.?/?\s*vol\.?|alcohol\s+by\s+volume|abv)\s*[:=]?\s*"
        r"(?P<value>\d{1,2}(?:\.\d+)?)\s*%?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<span>alc\.?\s*(?P<value>\d{1,2}(?:\.\d+)?)\s*%?\s*by\s*vol\.?\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<span>(?P<value>\d{1,2}(?:\.\d+)?)\s*%\s*(?:alc|alcohol|abv)\b)",
        re.IGNORECASE,
    ),
]

_PROOF_PATTERN = re.compile(
    r"(?P<span>\(?\s*(?P<value>\d{1,3}(?:\.\d+)?)\s*proof\s*\)?)",
    re.IGNORECASE,
)

_NET_PATTERN = re.compile(
    r"(?P<span>(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>m\.?\s*l\.?|ml|l\.?|liter|litre|liters|litres)\b)",
    re.IGNORECASE,
)

# Characters/tokens that commonly appear beside a clean net match without implying noise.
_NET_BENIGN_CONTEXT = re.compile(
    r"[\s()\[\]{},;:/\\\-–—·•]|"
    r"\d{1,3}(?:\.\d+)?\s*proof|"
    r"net\s*contents?|"
    r"volume|"
    r"contains?",
    re.IGNORECASE,
)


def parse_alcohol_content(text: str) -> ParsedAlcohol | None:
    """
    Parse ABV and/or proof from a text snippet.

    Prefer the mandatory % Alc./Vol. span when present. Proof → ABV uses the
    documented engineering relation ABV = proof / 2 (extraction only).
    Does not invent characters that are not present in the text.
    """
    if not text or not text.strip():
        return None
    abv: float | None = None
    proof: float | None = None
    abv_span: str | None = None
    proof_span: str | None = None

    for pattern in _ABV_PATTERNS:
        match = pattern.search(text)
        if match:
            abv = float(match.group("value"))
            abv_span = match.group("span").strip()
            break

    proof_match = _PROOF_PATTERN.search(text)
    if proof_match:
        proof = float(proof_match.group("value"))
        proof_span = proof_match.group("span").strip()

    if abv is None and proof is None:
        return None

    if abv is not None and proof is not None:
        return ParsedAlcohol(
            raw_text=text.strip(),
            abv_percent=abv,
            proof=proof,
            source="both",
            abv_span=abv_span,
            proof_span=proof_span,
        )

    if proof is not None and abv is None:
        # Engineering extraction transform: US proof ≈ 2 × ABV.
        return ParsedAlcohol(
            raw_text=proof_span or text.strip(),
            abv_percent=proof / 2.0,
            proof=proof,
            source="proof",
            abv_span=None,
            proof_span=proof_span,
        )

    return ParsedAlcohol(
        raw_text=abv_span or text.strip(),
        abv_percent=abv,
        proof=None,
        source="abv",
        abv_span=abv_span,
        proof_span=None,
    )


def alcohol_normalized_display(parsed: ParsedAlcohol) -> str:
    """Human-facing normalized alcohol string centered on ABV when available."""
    if parsed.source == "proof":
        return f"proof={parsed.proof:g}" if parsed.proof is not None else "proof"
    if parsed.abv_percent is None:
        return parsed.raw_text
    if parsed.proof is not None:
        return f"{parsed.abv_percent:g}% Alc./Vol. (proof={parsed.proof:g})"
    return f"{parsed.abv_percent:g}% Alc./Vol."


def parse_net_contents(text: str) -> ParsedNetContents | None:
    """Parse net contents value and canonicalize unit to mL or L."""
    if not text or not text.strip():
        return None
    match = _NET_PATTERN.search(text)
    if not match:
        return None
    value = float(match.group("value"))
    unit_raw = re.sub(r"[\s.]", "", match.group("unit").lower())
    if unit_raw in {"ml"}:
        unit = "mL"
    elif unit_raw in {"l", "liter", "litre", "liters", "litres"}:
        unit = "L"
    else:
        unit = "mL"
    span = match.group("span").strip()
    # Canonical display: "750 mL" / "1 L" — never include proof or other OCR noise.
    display = f"{value:g} {unit}"
    return ParsedNetContents(raw_text=display, value=value, unit=unit, match_span=span)


def net_contents_evidence_is_reliable(line: str, parsed: ParsedNetContents) -> bool:
    """
    True when the net match is supported by sufficiently clean surrounding OCR.

    A regex hit alone is not enough when the line is dominated by unrelated noise
    (e.g. 'ge | 750mL'). Benign neighbors such as proof in parentheses are allowed.
    """
    if not line or not parsed.match_span:
        return False
    # Remove the matched span and known-benign tokens; residual alphanumeric junk → unreliable.
    residual = line
    residual = re.sub(re.escape(parsed.match_span), " ", residual, count=1, flags=re.IGNORECASE)
    residual = _NET_BENIGN_CONTEXT.sub(" ", residual)
    residual = re.sub(r"\s+", "", residual)
    # Allow a few leftover punctuation/digits; reject letter junk (OCR garbage prefixes).
    if not residual:
        return True
    letters = sum(1 for ch in residual if ch.isalpha())
    return letters == 0


def comparison_key(text: str | None) -> str | None:
    """Lowercase collapsed key for later comparison (not equivalence decision)."""
    if text is None:
        return None
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return collapsed or None
