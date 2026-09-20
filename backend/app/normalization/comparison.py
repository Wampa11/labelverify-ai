"""
Text and quantity comparison helpers for deterministic verification.

Architectural responsibility: engineering normalization and fuzzy bands —
not regulatory equivalence determinations.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.normalization.field_parsers import parse_alcohol_content, parse_net_contents

# Engineering heuristics (ADR-019). Configurable via Settings; defaults documented.
DEFAULT_BRAND_PASS_RATIO = 95.0
DEFAULT_BRAND_REVIEW_RATIO = 85.0
DEFAULT_CLASS_PASS_RATIO = 97.0
DEFAULT_ABV_EPSILON = 0.05
DEFAULT_NET_ML_EPSILON = 0.5


def comparison_normalize(text: str | None) -> str | None:
    """
    Conservative comparison key: NFKC, casefold, collapse whitespace,
    unify common apostrophes. Preserves letters/digits; strips most punctuation
    except internal apostrophes used in brand names (normalized to ').
    """
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("'", "'").replace("'", "'").replace("`", "'")
    normalized = normalized.casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    # Keep letters, digits, spaces, and apostrophes for brand/class comparison.
    normalized = re.sub(r"[^a-z0-9'\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def text_candidates_agree(left: str | None, right: str | None) -> bool:
    """
    True when two text candidates agree after normalization (exact, containment,
    or shared significant tokens). Used for OCR-pass and OCR↔AI reinforcement —
    not regulatory equivalence.
    """
    a = comparison_normalize(left) or ""
    b = comparison_normalize(right) or ""
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    a_clean = re.sub(r"[.|…]+", " ", a)
    a_clean = re.sub(r"\s+", " ", a_clean).strip()
    if a_clean and (a_clean in b or b.startswith(a_clean)):
        return True
    a_tokens = [t for t in a_clean.split() if len(t) >= 4]
    b_tokens = list(b.split())
    if not a_tokens:
        return False

    def _token_matches(partial: str) -> bool:
        return any(
            bt == partial or bt.startswith(partial) or partial.startswith(bt)
            for bt in b_tokens
            if len(bt) >= 4
        )

    return all(_token_matches(t) for t in a_tokens)


def prefer_cleaner_text(left: str | None, right: str | None) -> str | None:
    """Prefer the shorter agreeing candidate when one is a noisy superset."""
    if not left:
        return right
    if not right:
        return left
    if text_candidates_agree(left, right):
        return left if len(left.strip()) <= len(right.strip()) else right
    return left


def prefer_agreeing_text(left: str | None, right: str | None) -> str | None:
    """
    When candidates agree, prefer the more complete reading.

    Prefer longer when it adds significant tokens; prefer shorter when the longer
    form only adds short junk prefixes (e.g. 'di BOURBON WHISKEY').
    """
    if not left:
        return right
    if not right:
        return left
    if not text_candidates_agree(left, right):
        return left
    a = comparison_normalize(left) or ""
    b = comparison_normalize(right) or ""

    def _junk_superset(longer: str, shorter: str) -> bool:
        """True when longer only adds short/noise tokens beyond shorter's content."""
        short_tokens = shorter.split()
        long_tokens = longer.split()
        short_sig = [t for t in short_tokens if len(t) >= 4]
        long_sig = [t for t in long_tokens if len(t) >= 4]
        if len(long_sig) > len(short_sig):
            return False
        extras = [t for t in long_tokens if t not in short_tokens]
        if not extras:
            return False
        return all(len(t) < 4 for t in extras)

    if a in b and len(b) > len(a) + 1:
        if _junk_superset(b, a):
            return left
        return right
    if b in a and len(a) > len(b) + 1:
        if _junk_superset(a, b):
            return right
        return left
    a_sig = [t for t in a.split() if len(t) >= 4]
    b_sig = [t for t in b.split() if len(t) >= 4]
    if len(b_sig) > len(a_sig):
        return right
    if len(a_sig) > len(b_sig):
        return left
    return left if len(left.strip()) <= len(right.strip()) else right


def warning_wording_normalize(text: str | None) -> str | None:
    """Collapse whitespace/case for statutory warning wording comparison."""
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized or None


@dataclass(frozen=True)
class TextSimilarity:
    """Fuzzy comparison outcome with transparent score."""

    ratio: float
    normalized_a: str | None
    normalized_b: str | None
    exact_normalized: bool


def text_similarity(a: str | None, b: str | None) -> TextSimilarity:
    """RapidFuzz token_sort_ratio on comparison-normalized strings (0–100)."""
    na = comparison_normalize(a)
    nb = comparison_normalize(b)
    if na is None or nb is None:
        return TextSimilarity(ratio=0.0, normalized_a=na, normalized_b=nb, exact_normalized=False)
    if na == nb:
        return TextSimilarity(ratio=100.0, normalized_a=na, normalized_b=nb, exact_normalized=True)
    ratio = float(fuzz.token_sort_ratio(na, nb))
    return TextSimilarity(ratio=ratio, normalized_a=na, normalized_b=nb, exact_normalized=False)


def volumes_equal_ml(
    a_ml: float,
    b_ml: float,
    *,
    epsilon_ml: float = DEFAULT_NET_ML_EPSILON,
) -> bool:
    """True when volumes match within absolute epsilon in milliliters."""
    return abs(a_ml - b_ml) <= epsilon_ml


def to_milliliters(value: float, unit: str) -> float:
    """Convert mL or L to milliliters."""
    if unit == "L":
        return value * 1000.0
    return value


def parse_application_abv(text: str) -> float | None:
    """Parse application ABV from common forms (45, 45%, 45% Alc./Vol.)."""
    parsed = parse_alcohol_content(text)
    if parsed and parsed.abv_percent is not None:
        return parsed.abv_percent
    match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%?", text.strip())
    if match:
        return float(match.group(1))
    return None


def parse_application_net_ml(text: str) -> float | None:
    """Parse application net contents to milliliters."""
    parsed = parse_net_contents(text)
    if parsed is None:
        return None
    return to_milliliters(parsed.value, parsed.unit)


_AUTHORIZED_ABV_FORMAT = re.compile(
    r"(\d{1,2}(?:\.\d+)?)\s*%\s*(alc\.?/?\s*vol\.?|alcohol\s+by\s+volume)"
    r"|(alc\.?/?\s*vol\.?|alcohol\s+by\s+volume)\s*[:=]?\s*(\d{1,2}(?:\.\d+)?)\s*%?"
    r"|(\d{1,2}(?:\.\d+)?)\s*%?\s*alcohol\s+by\s+volume"
    r"|alcohol\s+(\d{1,2}(?:\.\d+)?)\s*(percent|%)\s*(by\s+)?vol",
    re.IGNORECASE,
)


def has_authorized_percent_abv_statement(raw_text: str | None) -> bool:
    """
    True when OCR evidence resembles an authorized § 5.65 percent ABV statement.

    Proof-only text returns False. Bare 'ABV' without alc/vol pattern returns False.
    """
    if not raw_text:
        return False
    if _AUTHORIZED_ABV_FORMAT.search(raw_text):
        return True
    # Also accept compact forms already parsed as source=abv/both by field parser.
    parsed = parse_alcohol_content(raw_text)
    return parsed is not None and parsed.source in {"abv", "both"}
