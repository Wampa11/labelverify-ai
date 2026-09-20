"""
Brand name extractor using conservative layout heuristics.

Architectural responsibility: propose a brand candidate without inventing one.
Does not hard-code brand strings. Suspicious or ambiguous evidence → UNCERTAIN.
"""

from __future__ import annotations

import re

from app.extraction.ocr_support import (
    bbox_height,
    bbox_top,
    lines_from_ocr,
    regions_for_snippet,
)
from app.extraction.terminology import CLASS_TYPE_KEYWORDS, CLASS_TYPE_PHRASES
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
)
from app.normalization.field_parsers import parse_alcohol_content, parse_net_contents
from app.ocr.base import OcrResult, OcrWord

_SKIP_LINE = re.compile(
    r"government\s+warning|surgeon\s+general|birth\s+defects|operate\s+machinery|"
    r"alcoholic\s+beverages|health\s+problems|pregnancy|"
    r"alc\.?/?\s*vol|abv|\bproof\b|\d+\s*m\.?\s*l|\d+\s*l(?:iter|itre)?s?\b",
    re.IGNORECASE,
)

# Weak when standing alone; may still appear inside a legitimate multi-word brand.
_WEAK_STANDALONE = re.compile(
    r"^(?:the\s+)?"
    r"(?:distillery|distilling\s+co\.?|distilling\s+company|brewing\s+co\.?|"
    r"brewing\s+company|brewery|winery|vineyards?|spirits|liqueurs?|"
    r"company|incorporated|llc|inc\.?|co\.?)$",
    re.IGNORECASE,
)

# OCR artifacts that are not normal brand punctuation (apostrophes / hyphens allowed).
_OCR_ARTIFACT = re.compile(r"[=|_~^`<>{}[\]\\]|/{2,}|\*{2,}")
_LEADING_TRAILING_JUNK = re.compile(r"^[^A-Za-z0-9\"']+|[^A-Za-z0-9\"'.!?-]+$")


def extract_brand_name(ocr: OcrResult) -> ExtractedField:
    """
    Extract brand using prominence, position, and continuity cues.

    Returns UNCERTAIN when candidates conflict, evidence looks clipped/malformed,
    or only weak standalone producer descriptors remain.
    """
    field_name = "brand_name"
    lines = lines_from_ocr(ocr)
    filtered = [
        line
        for line in lines
        if not _SKIP_LINE.search(line)
        and parse_alcohol_content(line) is None
        and parse_net_contents(line) is None
        and not _looks_like_class(line)
        and not _looks_like_warning_fragment(line)
        and 3 <= len(line) <= 60
    ]

    if not filtered:
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.NOT_FOUND,
            explanation="Brand name could not be reliably extracted.",
            extraction_method=ExtractionMethod.NOT_EXTRACTED,
            ai_fallback_hints={"reason": "brand_no_candidates", "lines": lines[:12]},
        )

    scored = _score_candidates(ocr, filtered)
    if not scored:
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.NOT_FOUND,
            explanation="Brand name could not be reliably extracted.",
            extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
            candidates=filtered[:5],
            ai_fallback_hints={"reason": "brand_unscored", "candidates": filtered[:5]},
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score, top_line = scored[0]
    # Material conflict: near-tied distinct candidates (not mere weak descriptors).
    close = [
        line
        for score, line in scored
        if score >= top_score * 0.88 and not _is_weak_standalone(line)
    ]
    close_unique = _dedupe_lines(close)
    # Also flag alternate candidates that share a later token but disagree on the lead
    # (possible truncated / conflicting OCR of the same brand line).
    suffix_conflict = _suffix_conflict_candidates(scored, top_line, top_score)

    integrity = _brand_integrity_issues(ocr, top_line)

    if len(close_unique) > 1 or suffix_conflict:
        conflict_list = close_unique if len(close_unique) > 1 else [top_line, *suffix_conflict]
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=top_line,
            normalized_value=_clean_display(top_line),
            candidates=[line for _, line in scored[:5]],
            ocr_regions=regions_for_snippet(ocr, top_line),
            extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
            explanation=(
                "Multiple plausible brand candidates conflict; human review required."
            ),
            ai_fallback_hints={
                "reason": "brand_ambiguous",
                "candidates": _dedupe_lines(conflict_list),
                "reason_code_hint": "CONFLICTING_EVIDENCE",
            },
        )

    if _is_weak_standalone(top_line):
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=top_line,
            normalized_value=_clean_display(top_line),
            candidates=[line for _, line in scored[:5]],
            ocr_regions=regions_for_snippet(ocr, top_line),
            extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
            explanation=(
                "Only a generic producer descriptor was recovered as a brand candidate."
            ),
            ai_fallback_hints={"reason": "brand_weak_standalone", "candidates": [top_line]},
        )

    if integrity:
        return ExtractedField(
            field_name=field_name,
            status=ExtractionStatus.UNCERTAIN,
            raw_text=top_line,
            normalized_value=_clean_display(top_line),
            candidates=[line for _, line in scored[:5]],
            ocr_regions=regions_for_snippet(ocr, top_line),
            extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
            explanation="Brand name could not be reliably extracted.",
            ai_fallback_hints={
                "reason": "brand_integrity",
                "integrity_issues": integrity,
                "candidates": [top_line],
            },
        )

    return ExtractedField(
        field_name=field_name,
        status=ExtractionStatus.FOUND,
        raw_text=top_line,
        normalized_value=_clean_display(top_line),
        candidates=[line for _, line in scored[:5]],
        ocr_regions=regions_for_snippet(ocr, top_line),
        extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
        explanation=f"Brand name was recovered as {_clean_display(top_line)}.",
    )


def _clean_display(line: str) -> str:
    """Strip obvious edge junk for display without inventing characters."""
    cleaned = line.strip()
    cleaned = re.sub(r"^[^\w\"']+", "", cleaned)
    cleaned = re.sub(r"[^\w\"'.!?-]+$", "", cleaned)
    return cleaned.strip() or line.strip()


def _dedupe_lines(lines: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key = line.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(line)
    return unique


def _looks_like_class(line: str) -> bool:
    lowered = line.lower()
    if any(phrase in lowered for phrase in CLASS_TYPE_PHRASES):
        return True
    return any(keyword in lowered for keyword in CLASS_TYPE_KEYWORDS) and len(line.split()) <= 6


def _looks_like_warning_fragment(line: str) -> bool:
    lowered = line.lower()
    return any(
        frag in lowered
        for frag in (
            "surgeon general",
            "birth defects",
            "operate machinery",
            "health problems",
            "alcoholic beverages",
        )
    )


def _is_weak_standalone(line: str) -> bool:
    return bool(_WEAK_STANDALONE.match(line.strip()))


def _score_candidates(ocr: OcrResult, lines: list[str]) -> list[tuple[float, str]]:
    """Score by visual prominence, upper position, continuity; penalize weak/malformed."""
    # Keep a single scoring implementation via brand_diagnostics (no outcome drift).
    from app.extraction.brand_diagnostics import score_candidates_detailed

    return [(item["score"], item["line"]) for item in score_candidates_detailed(ocr, lines)]


def _brand_integrity_issues(ocr: OcrResult, line: str) -> list[str]:
    """Return non-empty list of integrity problems that block deterministic PASS."""
    issues: list[str] = []
    stripped = line.strip()

    if _OCR_ARTIFACT.search(stripped):
        issues.append("ocr_artifact_symbol")
    if _LEADING_TRAILING_JUNK.search(stripped):
        issues.append("edge_punctuation")
    if stripped[:1].islower() and any(ch.isalpha() for ch in stripped[1:]):
        # Brands on spirits labels are typically title/upper case; leading lowercase
        # often indicates a clipped first character (e.g. missing leading capital).
        issues.append("leading_lowercase")
    if re.search(r"\s[=|_]\s*$", stripped) or stripped.endswith("="):
        issues.append("trailing_ocr_artifact")

    words = _words_for_line(ocr, line)
    if words:
        leftmost = min(words, key=_bbox_left)
        rightmost = max(words, key=lambda w: _bbox_left(w) + _bbox_width(w))
        if leftmost.confidence is not None and leftmost.confidence < 0.5:
            issues.append("low_confidence_leading_word")
        if rightmost.confidence is not None and rightmost.confidence < 0.5:
            issues.append("low_confidence_trailing_word")
        if _suggests_clipped_leading(ocr, line):
            issues.append("clipped_leading_edge")
        if _suggests_clipped_trailing(ocr, line):
            issues.append("clipped_trailing_edge")
        if _left_adjacent_orphan_fragment(ocr, line):
            issues.append("left_adjacent_orphan_fragment")
        if _suggests_truncated_box(ocr, line):
            issues.append("truncated_text_box")

    return issues


def _suffix_conflict_candidates(
    scored: list[tuple[float, str]],
    top_line: str,
    top_score: float,
) -> list[str]:
    """
    Detect alternate candidates that share a significant trailing token but differ
    on the leading token — a common OCR truncation / misread pattern.
    """
    top_tokens = top_line.split()
    if len(top_tokens) < 2:
        return []
    top_tail = top_tokens[-1].casefold()
    if len(top_tail) < 4:
        return []
    conflicts: list[str] = []
    for score, line in scored[1:]:
        if score < top_score * 0.72:
            continue
        if _is_weak_standalone(line):
            continue
        tokens = line.split()
        if len(tokens) < 2:
            continue
        if tokens[-1].casefold() != top_tail:
            continue
        if tokens[0].casefold() == top_tokens[0].casefold():
            continue
        conflicts.append(line)
    return conflicts


def _suggests_clipped_leading(ocr: OcrResult, line: str) -> bool:
    """Leading OCR word is low-confidence and flush against the left edge."""
    words = _words_for_line(ocr, line)
    if not words:
        return False
    leftmost = min(words, key=_bbox_left)
    left = _bbox_left(leftmost)
    conf = leftmost.confidence
    near_edge = left <= max(4.0, (ocr.image_width_px or 800) * 0.02)
    if conf is not None and conf < 0.55 and near_edge:
        return True
    if conf is not None and conf < 0.35:
        return True
    return False


def _suggests_clipped_trailing(ocr: OcrResult, line: str) -> bool:
    words = _words_for_line(ocr, line)
    if not words:
        return False
    rightmost = max(words, key=lambda w: _bbox_left(w) + _bbox_width(w))
    right = _bbox_left(rightmost) + _bbox_width(rightmost)
    width = float(ocr.image_width_px or 800)
    near_edge = right >= width * 0.98
    conf = rightmost.confidence
    return bool(near_edge and conf is not None and conf < 0.55)


def _suggests_truncated_box(ocr: OcrResult, line: str) -> bool:
    """True when a tall, narrow multi-token band suggests crop/truncation."""
    words = _words_for_line(ocr, line)
    if len(words) < 2:
        return False
    avg_h = sum(bbox_height(w) for w in words) / len(words)
    total_w = sum(_bbox_width(w) for w in words)
    # Very tall, narrow multi-token bands often indicate crop/truncation.
    return avg_h > 0 and total_w < avg_h * 1.2 * len(words) * 0.35


def _left_adjacent_orphan_fragment(ocr: OcrResult, line: str) -> bool:
    """
    A short OCR token sits immediately left of the brand on the same band —
    possible split/truncated leading character without inventing the letter.
    """
    words = _words_for_line(ocr, line)
    if not words:
        return False
    leftmost = min(words, key=_bbox_left)
    brand_left = _bbox_left(leftmost)
    brand_top = bbox_top(leftmost)
    brand_h = bbox_height(leftmost) or 10.0
    line_tokens = {t.lower() for t in line.split()}

    for word in ocr.words:
        token = word.text.strip()
        if not token or token.lower() in line_tokens:
            continue
        if len(token) > 2:
            continue
        if not any(ch.isalpha() for ch in token):
            continue
        w_left = _bbox_left(word)
        w_right = w_left + _bbox_width(word)
        w_top = bbox_top(word)
        # Same horizontal band and immediately left with a small gap.
        if abs(w_top - brand_top) > brand_h * 0.6:
            continue
        gap = brand_left - w_right
        if 0 <= gap <= brand_h * 1.2:
            return True
    return False


def _bbox_left(word: OcrWord) -> float:
    box = word.bounding_box or {}
    try:
        if "x_min" in box:
            return float(box["x_min"])
        if "x" in box:
            return float(box["x"])
        if "left" in box:
            return float(box["left"])
    except (TypeError, ValueError):
        return 0.0
    return 0.0


def _bbox_width(word: OcrWord) -> float:
    box = word.bounding_box or {}
    try:
        if "x_min" in box and "x_max" in box:
            return max(0.0, float(box["x_max"]) - float(box["x_min"]))
        if "width" in box:
            return float(box["width"])
        if "w" in box:
            return float(box["w"])
    except (TypeError, ValueError):
        return float(bbox_height(word) or 10.0)
    return float(bbox_height(word) or 10.0)


def _words_for_line(ocr: OcrResult, line: str) -> list[OcrWord]:
    # Match tokens after stripping common OCR edge junk from the line tokens.
    tokens = {re.sub(r"^[^\w]+|[^\w]+$", "", t).lower() for t in line.split()}
    tokens.discard("")
    matched: list[OcrWord] = []
    for word in ocr.words:
        cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", word.text).lower()
        if cleaned in tokens or word.text.lower() in tokens:
            matched.append(word)
    return matched
