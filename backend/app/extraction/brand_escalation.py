"""
Selective brand OCR escalation (region Tesseract, optional RapidOCR).

Architectural responsibility: escalate only on evidence-quality signals, reconcile
whole-label vs region OCR without dictionary correction or silent swaps.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.extraction.brand_name import extract_brand_name
from app.extraction.brand_region import BrandRegionCrop, select_brand_region, words_avg_height
from app.models.extraction import (
    ExtractedField,
    ExtractionMethod,
    ExtractionStatus,
    OcrRegionRef,
)
from app.normalization.comparison import comparison_normalize
from app.ocr.base import OcrProvider, OcrResult, OcrWord
from app.ocr.errors import OcrProviderError

logger = logging.getLogger(__name__)

# Soft FOUND suspicions that warrant region re-OCR without fixture strings.
_ESCALATE_FOUND_REASONS = frozenset(
    {
        "prominent_left_inset",
        "short_leading_token_tall_glyphs",
    },
)


@dataclass
class BrandEscalationResult:
    """Observable outcome of selective brand OCR escalation."""

    triggered: bool
    triggers: list[str] = field(default_factory=list)
    region_method: str | None = None
    tesseract_region_ran: bool = False
    tesseract_region_ms: float | None = None
    secondary_ran: bool = False
    secondary_provider: str | None = None
    secondary_ms: float | None = None
    secondary_skipped_reason: str | None = None
    reconcile_outcomes: list[str] = field(default_factory=list)
    evidence_method_suffix: str | None = None
    whole_brand_raw: str | None = None
    region_brand_raw: str | None = None
    secondary_brand_raw: str | None = None
    final_brand: ExtractedField | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "triggers": list(self.triggers),
            "region_method": self.region_method,
            "tesseract_region_ran": self.tesseract_region_ran,
            "tesseract_region_ms": self.tesseract_region_ms,
            "secondary_ran": self.secondary_ran,
            "secondary_provider": self.secondary_provider,
            "secondary_ms": self.secondary_ms,
            "secondary_skipped_reason": self.secondary_skipped_reason,
            "reconcile_outcomes": list(self.reconcile_outcomes),
            "evidence_method_suffix": self.evidence_method_suffix,
            "whole_brand_raw": self.whole_brand_raw,
            "region_brand_raw": self.region_brand_raw,
            "secondary_brand_raw": self.secondary_brand_raw,
        }


def collect_brand_escalation_triggers(
    brand: ExtractedField | None,
    ocr: OcrResult,
) -> list[str]:
    """
    Return trigger codes when brand evidence warrants region re-OCR.

    Clean high-confidence FOUND brands with no suspicion return [].
    """
    if brand is None:
        return ["brand_missing"]

    triggers: list[str] = []
    if brand.status == ExtractionStatus.NOT_FOUND:
        triggers.append("brand_not_found")
        if _has_prominent_upper_words(ocr):
            triggers.append("prominent_text_without_brand")
        return triggers

    if brand.status == ExtractionStatus.UNCERTAIN:
        reason = (brand.ai_fallback_hints or {}).get("reason") or "uncertain"
        triggers.append(f"brand_uncertain:{reason}")
        integrity = (brand.ai_fallback_hints or {}).get("integrity_issues") or []
        triggers.extend(f"integrity:{item}" for item in integrity)
        return triggers

    # FOUND — only escalate on soft geometric suspicions (no dictionary checks).
    soft = _found_suspicion_triggers(brand, ocr)
    triggers.extend(soft)
    return triggers


def should_escalate_brand(brand: ExtractedField | None, ocr: OcrResult) -> bool:
    """True when selective brand-region OCR should run."""
    return bool(collect_brand_escalation_triggers(brand, ocr))


def _has_prominent_upper_words(ocr: OcrResult) -> bool:
    height = float(ocr.image_height_px or 0)
    if height <= 0:
        return False
    for word in ocr.words:
        box = word.bounding_box or {}
        y_min = float(box.get("y_min") or 0)
        y_max = float(box.get("y_max") or 0)
        if y_min > height * 0.55:
            continue
        if (y_max - y_min) >= height * 0.06 and (word.text or "").strip():
            return True
    return False


def _found_suspicion_triggers(brand: ExtractedField, ocr: OcrResult) -> list[str]:
    triggers: list[str] = []
    line = (brand.raw_text or brand.normalized_value or "").strip()
    if not line:
        return ["found_empty_text"]

    words = _words_matching_line(ocr, line)
    width = float(ocr.image_width_px or 0)
    height = float(ocr.image_height_px or 0)
    if words and width > 0 and height > 0:
        avg_h = words_avg_height(words)
        leftmost = min(words, key=lambda w: float((w.bounding_box or {}).get("x_min") or 0))
        left = float((leftmost.bounding_box or {}).get("x_min") or 0)
        # Prominent brand glyphs that start well inset from the left often lost a
        # leading display character (general geometry — not a brand dictionary).
        if avg_h >= height * 0.06 and left >= width * 0.12:
            triggers.append("prominent_left_inset")
        tokens = line.split()
        if (
            len(tokens) >= 2
            and 3 <= len(tokens[0]) <= 4
            and tokens[0].isalpha()
            and avg_h >= height * 0.08
        ):
            triggers.append("short_leading_token_tall_glyphs")
    return triggers


def _words_matching_line(ocr: OcrResult, line: str) -> list[OcrWord]:
    tokens = {t.casefold() for t in line.split() if t}
    if not tokens:
        return []
    matched: list[OcrWord] = []
    for word in ocr.words:
        text = (word.text or "").strip()
        if text.casefold() in tokens:
            matched.append(word)
    return matched


def reconcile_brand_evidence(
    base: ExtractedField,
    challenger: ExtractedField,
    *,
    challenger_source: str,
    base_was_suspicious: bool,
) -> tuple[ExtractedField, str]:
    """
    Merge whole-label and region/secondary brand evidence.

    Returns (field, outcome_code). Never invents characters via dictionary.
    """
    base_norm = comparison_normalize(base.normalized_value or base.raw_text or "")
    chal_norm = comparison_normalize(
        challenger.normalized_value or challenger.raw_text or "",
    )

    if challenger.status == ExtractionStatus.NOT_FOUND:
        return base, f"{challenger_source}:no_text"

    if challenger.status == ExtractionStatus.UNCERTAIN and base.status == ExtractionStatus.FOUND:
        if not base_was_suspicious:
            return base, f"{challenger_source}:uncertain_kept_base"
        # Suspicious FOUND vs uncertain challenger — stay uncertain with both.
        merged = _as_uncertain_conflict(base, challenger, challenger_source)
        return merged, f"{challenger_source}:conflict_uncertain"

    if base.status in {ExtractionStatus.NOT_FOUND, ExtractionStatus.UNCERTAIN}:
        if challenger.status == ExtractionStatus.FOUND:
            chal_tokens = (
                (challenger.normalized_value or challenger.raw_text or "").split()
            )
            # Single-token FOUND after uncertain whole-label is often a partial
            # decorative recovery — keep UNCERTAIN so AI/review remain available.
            if len(chal_tokens) < 2 and base.status == ExtractionStatus.UNCERTAIN:
                partial = challenger.model_copy(
                    update={
                        "status": ExtractionStatus.UNCERTAIN,
                        "explanation": (
                            "Partial brand evidence was recovered from secondary OCR; "
                            "human review required."
                        ),
                        "ai_fallback_hints": {
                            **dict(challenger.ai_fallback_hints or {}),
                            "reason": "brand_partial_secondary",
                            "ocr_evidence_source": challenger_source,
                            "prior_whole_label_raw": base.raw_text,
                        },
                        "extraction_method": ExtractionMethod.COMBINED,
                    },
                )
                return partial, f"{challenger_source}:partial_uncertain"
            return (
                _annotate_source(challenger, challenger_source, base),
                f"{challenger_source}:replaced_weaker_base",
            )
        if challenger.status == ExtractionStatus.UNCERTAIN:
            # Prefer challenger text if base empty; else conflict packaging.
            if not (base.raw_text or base.normalized_value):
                return (
                    _annotate_source(challenger, challenger_source, base),
                    f"{challenger_source}:filled_empty_base",
                )
            if base_norm and chal_norm and base_norm == chal_norm:
                # Matching uncertain reads reinforce evidence but do not invent FOUND.
                hints = dict(base.ai_fallback_hints or {})
                hints["reinforced_by"] = challenger_source
                hints["ocr_evidence_source"] = challenger_source
                regions = list(base.ocr_regions or []) + list(challenger.ocr_regions or [])
                return (
                    base.model_copy(
                        update={
                            "ai_fallback_hints": hints,
                            "ocr_regions": regions,
                            "extraction_method": ExtractionMethod.COMBINED,
                        },
                    ),
                    f"{challenger_source}:reinforced_uncertain",
                )
            return (
                _as_uncertain_conflict(base, challenger, challenger_source),
                f"{challenger_source}:conflict_uncertain",
            )

    # Both FOUND
    if base_norm and chal_norm and base_norm == chal_norm:
        return (
            _strengthen(base, challenger, challenger_source),
            f"{challenger_source}:reinforced",
        )

    if _challenger_clearly_stronger(base, challenger, base_was_suspicious):
        return (
            _annotate_source(challenger, challenger_source, base),
            f"{challenger_source}:superseded_weaker",
        )

    return (
        _as_uncertain_conflict(base, challenger, challenger_source),
        f"{challenger_source}:conflict_uncertain",
    )


def _challenger_clearly_stronger(
    base: ExtractedField,
    challenger: ExtractedField,
    base_was_suspicious: bool,
) -> bool:
    """True when region/secondary evidence should replace whole-label FOUND."""
    if challenger.status != ExtractionStatus.FOUND:
        return False
    chal_issues = (challenger.ai_fallback_hints or {}).get("integrity_issues") or []
    if chal_issues:
        return False
    base_text = (base.normalized_value or base.raw_text or "").strip()
    chal_text = (challenger.normalized_value or challenger.raw_text or "").strip()
    if not chal_text:
        return False
    # Suspicious whole-label FOUND vs clean longer/different region FOUND.
    if base_was_suspicious and len(chal_text) >= len(base_text):
        return True
    # Region recovers additional leading characters on the same trailing tokens.
    base_tokens = base_text.split()
    chal_tokens = chal_text.split()
    if (
        len(base_tokens) >= 2
        and len(chal_tokens) >= 2
        and base_tokens[-1].casefold() == chal_tokens[-1].casefold()
        and base_tokens[0].casefold() != chal_tokens[0].casefold()
        and len(chal_tokens[0]) >= len(base_tokens[0])
        and base_was_suspicious
    ):
        return True
    return False


def _annotate_source(
    winner: ExtractedField,
    source: str,
    prior: ExtractedField,
) -> ExtractedField:
    hints = dict(winner.ai_fallback_hints or {})
    hints["ocr_evidence_source"] = source
    hints["prior_whole_label_raw"] = prior.raw_text
    hints["prior_whole_label_status"] = prior.status.value
    method = (
        ExtractionMethod.COMBINED
        if prior.raw_text and prior.raw_text != winner.raw_text
        else winner.extraction_method
    )
    return winner.model_copy(
        update={
            "ai_fallback_hints": hints,
            "extraction_method": method,
            "explanation": (
                f"Brand name was recovered as {winner.normalized_value or winner.raw_text} "
                f"via {source.replace('_', ' ')}."
            ),
        },
    )


def _strengthen(
    base: ExtractedField,
    challenger: ExtractedField,
    source: str,
) -> ExtractedField:
    hints = dict(base.ai_fallback_hints or {})
    hints["ocr_evidence_source"] = source
    hints["reinforced_by"] = source
    regions = list(base.ocr_regions or []) + list(challenger.ocr_regions or [])
    return base.model_copy(
        update={
            "status": ExtractionStatus.FOUND,
            "ai_fallback_hints": hints,
            "ocr_regions": regions,
            "extraction_method": ExtractionMethod.COMBINED,
            "explanation": (
                f"Brand name was recovered as {base.normalized_value or base.raw_text} "
                f"(reinforced by {source.replace('_', ' ')})."
            ),
        },
    )


def _as_uncertain_conflict(
    base: ExtractedField,
    challenger: ExtractedField,
    source: str,
) -> ExtractedField:
    candidates = []
    for value in (
        base.normalized_value or base.raw_text,
        challenger.normalized_value or challenger.raw_text,
    ):
        if value and value not in candidates:
            candidates.append(value)
    return ExtractedField(
        field_name="brand_name",
        status=ExtractionStatus.UNCERTAIN,
        raw_text=base.raw_text or challenger.raw_text,
        normalized_value=base.normalized_value or challenger.normalized_value,
        candidates=candidates,
        ocr_regions=list(base.ocr_regions or []) + list(challenger.ocr_regions or []),
        extraction_method=ExtractionMethod.COMBINED,
        explanation=(
            "Whole-label and region OCR brand candidates conflict; human review required."
        ),
        ai_fallback_hints={
            "reason": "brand_ocr_conflict",
            "reason_code_hint": "CONFLICTING_EVIDENCE",
            "candidates": candidates,
            "whole_label_raw": base.raw_text,
            "challenger_raw": challenger.raw_text,
            "challenger_source": source,
        },
    )


def run_brand_escalation(
    *,
    prepared_image_bytes: bytes,
    guide_ocr: OcrResult,
    brand: ExtractedField,
    primary_ocr: OcrProvider,
    secondary_ocr: OcrProvider | None,
    secondary_enabled: bool,
    brand_region_enabled: bool = True,
) -> BrandEscalationResult:
    """
    Run Tesseract brand-region OCR, optionally RapidOCR, and reconcile.

    ``prepared_image_bytes`` must be the OCR-prepared image matching ``guide_ocr`` boxes.
    """
    triggers = collect_brand_escalation_triggers(brand, guide_ocr)
    result = BrandEscalationResult(
        triggered=bool(triggers) and brand_region_enabled,
        triggers=triggers,
        whole_brand_raw=brand.raw_text,
        final_brand=brand,
    )
    if not result.triggered:
        return result

    base_suspicious = any(
        t in _ESCALATE_FOUND_REASONS
        or t.startswith("integrity:")
        or t.startswith("brand_uncertain")
        or t in {"brand_not_found", "prominent_text_without_brand", "found_empty_text"}
        for t in triggers
    )
    # FOUND-only soft triggers still count as suspicious for reconcile.
    if any(t in _ESCALATE_FOUND_REASONS for t in triggers):
        base_suspicious = True

    crop = select_brand_region(
        prepared_image_bytes,
        guide_ocr,
        prefer_upper=brand.status
        in {ExtractionStatus.UNCERTAIN, ExtractionStatus.NOT_FOUND},
    )
    result.region_method = crop.method

    # --- Tesseract region pass (measured Phase 8.8 strategy: default config) ---
    region_field, region_ms = _ocr_brand_on_crop(
        primary_ocr,
        crop,
        source_label="tesseract_brand_region",
    )
    result.tesseract_region_ran = True
    result.tesseract_region_ms = region_ms
    result.region_brand_raw = region_field.raw_text if region_field else None

    current = brand
    if region_field is not None:
        current, outcome = reconcile_brand_evidence(
            current,
            region_field,
            challenger_source="tesseract_brand_region",
            base_was_suspicious=base_suspicious,
        )
        result.reconcile_outcomes.append(outcome)
        result.evidence_method_suffix = "brand_region"
    result.final_brand = current

    needs_secondary = _still_needs_secondary(current)
    if not needs_secondary:
        result.secondary_skipped_reason = "brand_resolved_after_region"
        return result
    if not secondary_enabled:
        result.secondary_skipped_reason = "secondary_ocr_disabled"
        return result
    if secondary_ocr is None:
        result.secondary_skipped_reason = "secondary_provider_unavailable"
        return result

    # Prefer targeted region; if crop method was weak upper-only with no words, still use it.
    sec_field, sec_ms = _ocr_brand_on_crop(
        secondary_ocr,
        crop,
        source_label="rapidocr_brand_region",
    )
    result.secondary_ran = True
    result.secondary_provider = secondary_ocr.name
    result.secondary_ms = sec_ms
    result.secondary_brand_raw = sec_field.raw_text if sec_field else None

    # If region secondary remains weak, one whole-label RapidOCR attempt is allowed
    # (documented fallback when the crop is unreliable).
    def _secondary_weak(field: ExtractedField | None) -> bool:
        if field is None:
            return True
        if field.status != ExtractionStatus.FOUND:
            return True
        tokens = (field.normalized_value or field.raw_text or "").split()
        # Single-token FOUND on decorative script brands is often incomplete; allow
        # one whole-label secondary pass (no brand dictionary).
        return len(tokens) < 2

    if _secondary_weak(sec_field):
        whole_crop = BrandRegionCrop(
            image_bytes=prepared_image_bytes,
            method="whole_prepared_fallback",
            x_min=0.0,
            y_min=0.0,
            x_max=float(guide_ocr.image_width_px or 0),
            y_max=float(guide_ocr.image_height_px or 0),
            source_word_count=len(guide_ocr.words),
        )
        whole_field, whole_ms = _ocr_brand_on_crop(
            secondary_ocr,
            whole_crop,
            source_label="rapidocr_whole_fallback",
        )
        result.secondary_ms = (result.secondary_ms or 0.0) + whole_ms
        if whole_field is not None and not _secondary_weak(whole_field):
            sec_field = whole_field
            result.secondary_brand_raw = whole_field.raw_text
            result.reconcile_outcomes.append("secondary:whole_label_fallback")
        elif (
            whole_field is not None
            and sec_field is not None
            and whole_field.status == ExtractionStatus.FOUND
            and len((whole_field.normalized_value or "").split())
            > len((sec_field.normalized_value or "").split())
        ):
            sec_field = whole_field
            result.secondary_brand_raw = whole_field.raw_text
            result.reconcile_outcomes.append("secondary:whole_label_fallback")

    if sec_field is None:
        result.reconcile_outcomes.append("secondary:no_result")
        return result

    # After region attempt, treat remaining UNCERTAIN/NOT_FOUND as suspicious base.
    current, outcome = reconcile_brand_evidence(
        current,
        sec_field,
        challenger_source="rapidocr_brand_region",
        base_was_suspicious=True,
    )
    result.reconcile_outcomes.append(outcome)
    result.evidence_method_suffix = "brand_region_rapidocr"
    result.final_brand = current
    return result


def _still_needs_secondary(brand: ExtractedField) -> bool:
    if brand.status == ExtractionStatus.NOT_FOUND:
        return True
    if brand.status == ExtractionStatus.UNCERTAIN:
        return True
    return False


def _ocr_brand_on_crop(
    provider: OcrProvider,
    crop: BrandRegionCrop,
    *,
    source_label: str,
) -> tuple[ExtractedField | None, float]:
    start = time.perf_counter()
    try:
        ocr = provider.extract_text(crop.image_bytes)
        elapsed = (time.perf_counter() - start) * 1000
    except OcrProviderError as exc:
        logger.info("brand_region_ocr_failed source=%s err=%s", source_label, exc.message)
        return None, (time.perf_counter() - start) * 1000
    except Exception as exc:  # noqa: BLE001
        logger.info("brand_region_ocr_exception source=%s err=%s", source_label, exc)
        return None, (time.perf_counter() - start) * 1000

    ocr = ocr.model_copy(
        update={
            "image_width_px": ocr.image_width_px,
            "image_height_px": ocr.image_height_px,
            "preprocessing_profile": f"brand_region:{crop.method}",
        },
    )
    field = extract_brand_name(ocr)
    # Stamp region provenance on regions.
    stamped_regions = [
        OcrRegionRef(
            text=r.text,
            confidence=r.confidence,
            bounding_box=r.bounding_box,
            provider_name=provider.name,
            preprocessing_profile=f"brand_region:{crop.method}",
        )
        for r in (field.ocr_regions or [])
    ]
    hints = dict(field.ai_fallback_hints or {})
    hints["region_crop_method"] = crop.method
    hints["ocr_pass"] = source_label
    field = field.model_copy(
        update={"ocr_regions": stamped_regions, "ai_fallback_hints": hints},
    )
    return field, elapsed
