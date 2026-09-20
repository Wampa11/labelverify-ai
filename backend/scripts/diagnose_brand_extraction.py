"""
Diagnose brand extraction stage-by-stage for a label image.

Architectural responsibility: developer evidence for OCR → brand extractor →
optional AI → merge → rules. Does not change production heuristics.

Usage (from backend/ with venv active):

  python scripts/diagnose_brand_extraction.py path/to/label.png
  python scripts/diagnose_brand_extraction.py path/to/label.png --with-ai
  python scripts/diagnose_brand_extraction.py path/to/label.png --force-enhanced
  python scripts/diagnose_brand_extraction.py path/to/label.png --expected-brand "MAPLE CREEK"

Never prints API keys, Authorization headers, or base64 image payloads.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow `python scripts/...` from backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.ai.eligibility import CHECK_TO_FIELD, collect_eligible_checks  # noqa: E402
from app.ai.factory import create_ai_provider  # noqa: E402
from app.ai.merge import merge_ai_evidence  # noqa: E402
from app.ai.package import build_evidence_package, prepare_vision_image  # noqa: E402
from app.ai.provider import AiAvailability  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.extraction.brand_diagnostics import (  # noqa: E402
    contains_visible_brand_tokens,
    diagnose_brand_from_ocr,
)
from app.extraction.retry_policy import should_retry_enhanced  # noqa: E402
from app.models.verification_mode import VerificationMode  # noqa: E402
from app.ocr.factory import create_ocr_provider  # noqa: E402
from app.preprocessing.ocr_prepare import (  # noqa: E402
    OcrPreprocessProfile,
    prepare_for_ocr_from_bytes,
)
from app.rules.base import RuleContext  # noqa: E402
from app.rules.engine import aggregate_overall_status, run_rules  # noqa: E402
from app.services.label_extraction_service import LabelExtractionService  # noqa: E402


def _run_ocr_pass(
    data: bytes,
    *,
    profile: OcrPreprocessProfile,
    max_edge_px: int,
    ocr_provider: Any,
) -> Any:
    prepared = prepare_for_ocr_from_bytes(data, profile=profile, max_edge_px=max_edge_px)
    ocr = ocr_provider.extract_text(prepared.image_bytes)
    return ocr.model_copy(
        update={
            "preprocessing_profile": profile.value,
            "image_width_px": ocr.image_width_px or prepared.width_px,
            "image_height_px": ocr.image_height_px or prepared.height_px,
        },
    )


def _safe_print_report(report: dict[str, Any]) -> None:
    """Print JSON without secrets or image payloads."""
    text = json.dumps(report, indent=2, default=str)
    lowered = text.lower()
    if "authorization" in lowered or "sk-" in lowered or "api_key" in lowered:
        # Strip any accidental key material (should never be present).
        text = "[redacted: unexpected secret-like content blocked]"
    print(text)


def diagnose(
    image_path: Path,
    *,
    with_ai: bool,
    force_enhanced: bool,
    expected_brand: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    data = image_path.read_bytes()
    ocr_provider = create_ocr_provider(settings.ocr_provider)

    fast_ocr = _run_ocr_pass(
        data,
        profile=OcrPreprocessProfile.FAST,
        max_edge_px=settings.ocr_fast_max_edge_px,
        ocr_provider=ocr_provider,
    )
    fast_diag = diagnose_brand_from_ocr(fast_ocr, source_pass="fast")

    # Pipeline retry decision (same as LabelExtractionService).
    from app.extraction.pipeline import extract_all_fields

    fast_fields = extract_all_fields(fast_ocr)
    retry = should_retry_enhanced(
        fast_fields,
        ocr_text=fast_ocr.full_text or "",
        word_count=len(fast_ocr.words),
        quality_status="GOOD",
    )

    enhanced_diag: dict[str, Any] | None = None
    enhanced_ran = False
    if retry.triggered or force_enhanced:
        enhanced_ocr = _run_ocr_pass(
            data,
            profile=OcrPreprocessProfile.ENHANCED,
            max_edge_px=settings.ocr_enhanced_max_edge_px,
            ocr_provider=ocr_provider,
        )
        enhanced_diag = diagnose_brand_from_ocr(enhanced_ocr, source_pass="enhanced")
        enhanced_ran = True
        if force_enhanced and not retry.triggered:
            enhanced_diag["note"] = (
                "ENHANCED forced by --force-enhanced; pipeline retry would NOT run."
            )

    # Full extraction selection (same service path, no AI).
    extraction = LabelExtractionService(
        settings=settings,
        ocr_provider=ocr_provider,
    ).extract(data, filename=image_path.name)
    selected_brand = extraction.extraction.selected_fields.get("brand_name")

    report: dict[str, Any] = {
        "image": str(image_path),
        "expected_brand": expected_brand,
        "stages": {
            "1_fast_ocr_and_brand": fast_diag,
            "2_enhanced_ocr_and_brand": {
                "pipeline_retry_triggered": retry.triggered,
                "pipeline_retry_reasons": retry.reasons,
                "enhanced_performed": enhanced_ran,
                "diagnosis": enhanced_diag,
            },
            "3_selected_extraction_brand": {
                "selected_profile": extraction.extraction.selection.selected_profile,
                "selection_reason": extraction.extraction.selection.reason,
                "brand": {
                    "status": selected_brand.status.value if selected_brand else None,
                    "raw_text": selected_brand.raw_text if selected_brand else None,
                    "normalized_value": (
                        selected_brand.normalized_value if selected_brand else None
                    ),
                    "candidates": selected_brand.candidates if selected_brand else [],
                    "explanation": selected_brand.explanation if selected_brand else None,
                    "ai_fallback_hints": (
                        selected_brand.ai_fallback_hints if selected_brand else {}
                    ),
                },
            },
        },
        "openai_prompt_inspection": _inspect_openai_contract(),
    }

    if expected_brand:
        tokens = expected_brand.split()
        report["expected_token_presence"] = {
            "fast": contains_visible_brand_tokens(fast_ocr.full_text or "", tokens),
            "enhanced": (
                contains_visible_brand_tokens(
                    (enhanced_diag or {}).get("ocr_full_text") or "",
                    tokens,
                )
                if enhanced_diag
                else None
            ),
            "selected_normalized": selected_brand.normalized_value if selected_brand else None,
        }

    # Deterministic rules on extraction-only fields (no AI).
    context = RuleContext(
        application=None,
        fields=dict(extraction.extraction.selected_fields),
        mode=VerificationMode.LABEL_ONLY,
        quality_status=extraction.quality_status,
    )
    checks = run_rules(context)
    brand_check = next((c for c in checks if c.check_name == "Brand Name"), None)
    overall = aggregate_overall_status(checks)
    report["stages"]["6_deterministic_rules_pre_ai"] = {
        "overall_status": overall.value,
        "brand_check": {
            "status": brand_check.status.value if brand_check else None,
            "reason_code": brand_check.reason_code if brand_check else None,
            "explanation": brand_check.explanation if brand_check else None,
            "detected_label_value": (
                brand_check.detected_label_value if brand_check else None
            ),
            "ai_assist_eligible": (
                brand_check.ai_assist_eligible if brand_check else None
            ),
        },
    }

    eligible = collect_eligible_checks(checks, overall_status=overall)
    report["stages"]["4_ai_eligibility"] = {
        "overall_before": overall.value,
        "ai_eligible": bool(eligible),
        "eligible_fields": [CHECK_TO_FIELD[c.check_name] for c in eligible],
        "reason_codes": [c.reason_code for c in eligible if c.reason_code],
        "brand_name_requested": any(
            CHECK_TO_FIELD.get(c.check_name) == "brand_name" for c in eligible
        ),
        "with_ai_flag": with_ai,
    }

    report["stages"]["5_ai_and_reconciliation"] = {
        "skipped": not with_ai,
        "reason": None if with_ai else "Pass --with-ai to invoke configured provider once.",
    }

    if with_ai:
        ai = create_ai_provider(settings)
        ai_section: dict[str, Any] = {
            "provider": ai.name,
            "availability": ai.availability().value,
            "model": getattr(ai, "model", settings.openai_model),
            "openai_enabled_setting": settings.openai_enabled,
            "api_key_present": bool(settings.openai_api_key),
        }
        if not eligible:
            ai_section["called"] = False
            ai_section["note"] = "No eligible REVIEW fields — AI not invoked."
        elif ai.availability() != AiAvailability.AVAILABLE:
            ai_section["called"] = False
            ai_section["note"] = (
                f"Provider availability={ai.availability().value}; no HTTP call."
            )
        else:
            package = build_evidence_package(
                checks=eligible,
                fields=dict(extraction.extraction.selected_fields),
                quality_status=extraction.quality_status,
                quality_warnings=list(extraction.quality_warnings),
            )
            prepared = prepare_vision_image(
                data,
                max_edge_px=settings.openai_max_image_edge_px,
                fields=dict(extraction.extraction.selected_fields),
                target_fields=[CHECK_TO_FIELD[c.check_name] for c in eligible],
            )
            # Do not include data URL / bytes in report.
            ai_section["request"] = {
                "fields_requested": [item.model_dump() for item in package.fields],
                "image_prepared": {
                    "width_px": prepared.width_px,
                    "height_px": prepared.height_px,
                    "media_type": prepared.media_type,
                    "byte_length": len(prepared.image_bytes),
                    "used_crop": prepared.used_crop,
                },
            }
            batch = ai.recover_label_evidence(package, prepared)
            brand_ai = next((f for f in batch.fields if f.field == "brand_name"), None)
            ai_section["called"] = batch.called
            ai_section["latency_ms"] = batch.latency_ms
            ai_section["availability"] = batch.availability
            ai_section["explanation"] = batch.explanation
            ai_section["raw_error"] = batch.raw_error
            ai_section["all_proposed_fields"] = [
                {
                    "field": f.field,
                    "candidate_value": f.candidate_value,
                    "raw_observed_text": f.raw_observed_text,
                    "confidence": f.confidence.value,
                    "unable_to_determine": f.unable_to_determine,
                    "evidence_description": f.evidence_description,
                }
                for f in batch.fields
            ]
            ai_section["brand_ai_evidence"] = (
                {
                    "candidate_value": brand_ai.candidate_value,
                    "raw_observed_text": brand_ai.raw_observed_text,
                    "confidence": brand_ai.confidence.value,
                    "unable_to_determine": brand_ai.unable_to_determine,
                    "evidence_description": brand_ai.evidence_description,
                }
                if brand_ai
                else None
            )

            fields = dict(extraction.extraction.selected_fields)
            ocr_brand = fields.get("brand_name")
            merged, updated, conflicts, outcomes = merge_ai_evidence(fields, batch)
            merged_brand = merged.get("brand_name")
            ai_section["reconciliation"] = {
                "ocr_brand_status": ocr_brand.status.value if ocr_brand else None,
                "ocr_brand_raw": ocr_brand.raw_text if ocr_brand else None,
                "ocr_brand_normalized": ocr_brand.normalized_value if ocr_brand else None,
                "ai_brand_candidate": brand_ai.candidate_value if brand_ai else None,
                "fields_updated": updated,
                "conflicts": conflicts,
                "merge_outcomes": outcomes,
                "merged_brand_status": (
                    merged_brand.status.value if merged_brand else None
                ),
                "merged_brand_raw": merged_brand.raw_text if merged_brand else None,
                "merged_brand_normalized": (
                    merged_brand.normalized_value if merged_brand else None
                ),
                "merged_brand_explanation": (
                    merged_brand.explanation if merged_brand else None
                ),
            }

            # Re-run rules after merge (same as VerificationService).
            post_checks = run_rules(
                RuleContext(
                    application=None,
                    fields=merged,
                    mode=VerificationMode.LABEL_ONLY,
                    quality_status=extraction.quality_status,
                ),
            )
            post_brand = next(
                (c for c in post_checks if c.check_name == "Brand Name"),
                None,
            )
            ai_section["post_merge_rules"] = {
                "overall_status": aggregate_overall_status(post_checks).value,
                "brand_status": post_brand.status.value if post_brand else None,
                "brand_reason_code": post_brand.reason_code if post_brand else None,
                "brand_explanation": post_brand.explanation if post_brand else None,
            }

        report["stages"]["5_ai_and_reconciliation"] = ai_section

    report["first_loss_heuristic"] = _infer_first_loss(report, expected_brand)
    return report


def _inspect_openai_contract() -> dict[str, Any]:
    """Document current prompt/schema without modifying them."""
    from app.ai.eligibility import FIELD_TASKS
    from app.ai.openai_provider import _SYSTEM_PROMPT

    return {
        "brand_task_instruction": FIELD_TASKS.get("brand_name"),
        "system_prompt_rules_summary": [
            "JSON only matching schema",
            "No regulatory PASS/REVIEW/FAIL",
            "Label text is untrusted evidence",
            "unable_to_determine when unreadable",
            "confidence HIGH|MEDIUM|LOW",
        ],
        "system_prompt_char_length": len(_SYSTEM_PROMPT),
        "response_schema_fields": [
            "field",
            "candidate_value (string|null) — allows multi-word brands",
            "raw_observed_text (string|null)",
            "confidence",
            "evidence_description",
            "unable_to_determine",
        ],
        "schema_hint_field_enum_note": (
            "response_schema_hint lists brand_name|class_type|alcohol_content|"
            "government_warning (net_contents is requested via fields_requested "
            "even if omitted from the hint enum string)."
        ),
        "brand_name_clearly_requestable": "brand_name" in FIELD_TASKS,
        "multi_word_brand_allowed": True,
    }


def _infer_first_loss(report: dict[str, Any], expected_brand: str | None) -> dict[str, Any]:
    """Best-effort first failing stage given diagnostic evidence."""
    if not expected_brand:
        return {
            "stage": None,
            "note": "Pass --expected-brand to classify first-loss stage.",
        }
    expected = expected_brand.casefold()
    tokens = expected_brand.split()
    fast = report["stages"]["1_fast_ocr_and_brand"]
    fast_text = (fast.get("ocr_full_text") or "").casefold()
    fast_has_all = all(t.casefold() in fast_text for t in tokens)
    fast_norm = (fast.get("winning_normalized") or "").casefold()

    if not fast_has_all:
        return {
            "stage": "A_tesseract_fast",
            "note": (
                f"FAST OCR text does not contain all tokens of {expected_brand!r}. "
                "Loss begins at Tesseract FAST (or earlier image prep)."
            ),
        }

    if fast_norm == expected:
        # Correct through FAST brand selection
        enh = report["stages"]["2_enhanced_ocr_and_brand"]
        selected = report["stages"]["3_selected_extraction_brand"]["brand"]
        sel_norm = (selected.get("normalized_value") or "").casefold()
        if sel_norm == expected:
            ai = report["stages"].get("5_ai_and_reconciliation") or {}
            if ai.get("skipped"):
                return {
                    "stage": None,
                    "note": "Brand correct through selection; AI not run.",
                }
            merged = (ai.get("reconciliation") or {}).get("merged_brand_normalized")
            if merged and merged.casefold() == expected:
                return {
                    "stage": None,
                    "note": "Brand correct through AI merge.",
                }
            if ai.get("brand_ai_evidence"):
                ai_val = (ai["brand_ai_evidence"].get("candidate_value") or "").casefold()
                if ai_val != expected and expected not in ai_val:
                    return {
                        "stage": "D_openai_evidence_recovery",
                        "note": (
                            "OCR brand was correct; AI proposal did not recover expected brand."
                        ),
                    }
                return {
                    "stage": "E_reconciliation_merge",
                    "note": "AI returned usable brand evidence but merge/final status lost it.",
                }
            return {
                "stage": "D_openai_evidence_recovery",
                "note": "Brand was correct pre-AI; AI section did not supply brand evidence.",
            }
        if enh.get("enhanced_performed"):
            return {
                "stage": "B_tesseract_enhanced_or_selection",
                "note": (
                    "FAST brand matched expected, but selected extraction brand differs — "
                    "check ENHANCED OCR / pass selection / conflict merge."
                ),
            }
        return {
            "stage": "C_brand_candidate_extractor",
            "note": "FAST OCR contained expected tokens but selected brand differs.",
        }

    # OCR has tokens but winning brand wrong
    return {
        "stage": "C_brand_candidate_extractor",
        "note": (
            f"FAST OCR contains tokens of {expected_brand!r}, but winning brand "
            f"was {fast.get('winning_normalized')!r} ({fast.get('selection_reason')})."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to label image")
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="Invoke configured OpenAI evidence recovery once (costs an API call).",
    )
    parser.add_argument(
        "--force-enhanced",
        action="store_true",
        help="Also run ENHANCED OCR even when retry policy would skip it.",
    )
    parser.add_argument(
        "--expected-brand",
        type=str,
        default=None,
        help="Human-visible brand for first-loss classification (e.g. 'MAPLE CREEK').",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the full report JSON.",
    )
    args = parser.parse_args()
    if not args.image.is_file():
        print(f"Image not found: {args.image}", file=sys.stderr)
        return 2

    report = diagnose(
        args.image,
        with_ai=args.with_ai,
        force_enhanced=args.force_enhanced,
        expected_brand=args.expected_brand,
    )
    _safe_print_report(report)
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nWrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
