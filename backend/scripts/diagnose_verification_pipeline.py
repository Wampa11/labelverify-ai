"""
Diagnose full verification evidence-recovery pipeline for one label image.

Architectural responsibility: developer observability across FAST / ENHANCED /
brand-region / optional RapidOCR / optional OpenAI / reconcile / rules.
Does not change production OCR, extraction, reconciliation, prompts, or rules.

Usage (from backend/ with venv active):

  python scripts/diagnose_verification_pipeline.py path/to/label.png
  python scripts/diagnose_verification_pipeline.py path/to/label.png --with-secondary-ocr
  python scripts/diagnose_verification_pipeline.py path/to/label.png --with-ai
  python scripts/diagnose_verification_pipeline.py path/to/label.png --with-secondary-ocr --with-ai

Never prints API keys, Authorization headers, base64 image payloads, or
hidden model chain-of-thought.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.ai.eligibility import CHECK_TO_FIELD, collect_eligible_checks  # noqa: E402
from app.ai.factory import create_ai_provider  # noqa: E402
from app.ai.merge import merge_ai_evidence, validate_field_evidence  # noqa: E402
from app.ai.package import build_evidence_package, prepare_vision_image  # noqa: E402
from app.ai.provider import AiAvailability  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.models.extraction import ExtractedField  # noqa: E402
from app.models.verification_mode import VerificationMode  # noqa: E402
from app.ocr.factory import create_ocr_provider  # noqa: E402
from app.rules.base import RuleContext  # noqa: E402
from app.rules.engine import aggregate_overall_status, run_rules  # noqa: E402
from app.services.label_extraction_service import LabelExtractionService  # noqa: E402

FIELD_KEYS = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "government_warning",
)

CHECK_NAMES = {
    "brand_name": "Brand Name",
    "class_type": "Class / Type",
    "alcohol_content": "Alcohol Content / ABV",
    "net_contents": "Net Contents",
    "government_warning": "Government Health Warning",
}


def _field_snap(field: ExtractedField | None) -> dict[str, Any]:
    if field is None:
        return {
            "raw": None,
            "normalized": None,
            "status": "MISSING",
            "confidence_notes": None,
            "explanation": None,
        }
    confidences = [
        r.confidence
        for r in (field.ocr_regions or [])
        if r.confidence is not None
    ]
    conf_note = None
    if confidences:
        conf_note = (
            f"region_conf mean={sum(confidences) / len(confidences):.2f} "
            f"n={len(confidences)}"
        )
    hints = field.ai_fallback_hints or {}
    if hints.get("integrity_issues"):
        conf_note = (conf_note or "") + f" integrity={hints.get('integrity_issues')}"
    return {
        "raw": field.raw_text,
        "normalized": field.normalized_value,
        "status": field.status.value,
        "confidence_notes": (conf_note or "").strip() or None,
        "explanation": field.explanation,
        "method": field.extraction_method.value,
        "hints_reason": hints.get("reason"),
    }


def _trunc(value: Any, limit: int = 120) -> str:
    if value is None:
        return "n/a"
    text = str(value).replace("\n", " | ")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _print_field_table(field_key: str, stages: dict[str, Any]) -> None:
    title = CHECK_NAMES.get(field_key, field_key)
    print()
    print("=" * 88)
    print(f"FIELD: {title} ({field_key})")
    print("=" * 88)
    rows = [
        ("1. Tesseract FAST", stages.get("fast")),
        ("2. Tesseract ENHANCED / region", stages.get("tesseract_retry")),
        ("3. RapidOCR", stages.get("rapidocr")),
        ("4. OpenAI fallback", stages.get("openai")),
        ("5. Reconciliation", stages.get("reconciliation")),
        ("6. Final rule", stages.get("final_rule")),
    ]
    for label, payload in rows:
        print(f"\n{label}")
        print("-" * len(label))
        if not payload:
            print("  (not run / not applicable)")
            continue
        for key, value in payload.items():
            print(f"  {key}: {_trunc(value, 160)}")


def diagnose(
    image_path: Path,
    *,
    with_secondary_ocr: bool,
    with_ai: bool,
) -> dict[str, Any]:
    base_settings = get_settings()
    # Diagnostic overrides only — does not mutate production defaults on disk.
    settings = base_settings.model_copy(
        update={
            "secondary_ocr_enabled": with_secondary_ocr,
            "brand_region_ocr_enabled": True,
            # AI only when explicitly requested; disable otherwise so no accidental call.
            "openai_enabled": with_ai and bool(base_settings.openai_enabled),
            "openai_api_key": base_settings.openai_api_key if with_ai else None,
        },
    )

    data = image_path.read_bytes()
    timings: dict[str, float | None] = {
        "preprocessing_display_ms": None,
        "tesseract_fast_ms": None,
        "tesseract_enhanced_ms": None,
        "tesseract_brand_region_ms": None,
        "rapidocr_init_ms": None,
        "rapidocr_inference_ms": None,
        "openai_request_ms": None,
        "reconciliation_rules_ms": None,
        "total_ms": None,
    }

    ocr_provider = create_ocr_provider(settings.ocr_provider)
    secondary_provider = None
    if with_secondary_ocr:
        try:
            secondary_provider = create_ocr_provider(settings.secondary_ocr_provider)
            if not secondary_provider.is_available():
                secondary_provider = None
            else:
                # Distinguish init cost when provider reports it.
                init_start = time.perf_counter()
                # Force lazy engine construction via tiny blank if supported.
                from io import BytesIO

                from PIL import Image

                buf = BytesIO()
                Image.new("RGB", (32, 32), color=(255, 255, 255)).save(buf, format="PNG")
                try:
                    secondary_provider.extract_text(buf.getvalue())
                except Exception:  # noqa: BLE001 — diagnostic warm-up only
                    pass
                reported = getattr(secondary_provider, "init_time_ms", None)
                timings["rapidocr_init_ms"] = (
                    float(reported)
                    if reported is not None
                    else (time.perf_counter() - init_start) * 1000
                )
        except Exception as exc:  # noqa: BLE001
            secondary_provider = None
            timings["rapidocr_init_ms"] = None
            secondary_note = f"unavailable: {exc}"
        else:
            secondary_note = None
    else:
        secondary_note = "skipped (--with-secondary-ocr not set)"

    extraction_service = LabelExtractionService(
        settings=settings,
        ocr_provider=ocr_provider,
        secondary_ocr_provider=secondary_provider,
    )

    t0 = time.perf_counter()
    extraction_response = extraction_service.extract(
        data,
        filename=image_path.name,
    )
    extraction_wall_ms = (time.perf_counter() - t0) * 1000
    extraction = extraction_response.extraction
    stage_timings = dict(extraction.stage_timings_ms or {})

    timings["preprocessing_display_ms"] = stage_timings.get("display_analysis")
    timings["tesseract_fast_ms"] = stage_timings.get("fast_ocr")
    if extraction.enhanced_pass is not None:
        timings["tesseract_enhanced_ms"] = extraction.enhanced_pass.ocr_time_ms
    esc = extraction.brand_escalation
    if esc and esc.tesseract_region_ms is not None:
        timings["tesseract_brand_region_ms"] = esc.tesseract_region_ms
    if esc and esc.secondary_ms is not None:
        timings["rapidocr_inference_ms"] = esc.secondary_ms

    fast_fields = extraction.fast_pass.fields
    enhanced_fields = (
        extraction.enhanced_pass.fields if extraction.enhanced_pass else None
    )
    selected_fields = dict(extraction.selected_fields)

    # Pre-AI rules (deterministic).
    t_rules = time.perf_counter()
    context = RuleContext(
        application=None,
        fields=selected_fields,
        mode=VerificationMode.LABEL_ONLY,
        quality_status=extraction_response.quality_status,
    )
    checks_before = run_rules(context)
    overall_before = aggregate_overall_status(checks_before)
    rules_ms = (time.perf_counter() - t_rules) * 1000

    field_reports: dict[str, dict[str, Any]] = {}
    for key in FIELD_KEYS:
        fast = _field_snap(fast_fields.get(key))
        retry_payload: dict[str, Any] | None = None
        if key == "brand_name" and esc and esc.triggered:
            retry_payload = {
                "ran": esc.tesseract_region_ran,
                "region_method": esc.region_method,
                "triggers": esc.triggers,
                "raw": esc.region_brand_raw,
                "normalized": (
                    selected_fields.get(key).normalized_value
                    if esc.secondary_ran is False
                    and selected_fields.get(key)
                    and "tesseract_brand_region" in " ".join(esc.reconcile_outcomes)
                    else esc.region_brand_raw
                ),
                "status_after_region_reconcile_hint": (
                    selected_fields.get(key).status.value
                    if selected_fields.get(key) and not esc.secondary_ran
                    else "see reconciliation"
                ),
                "reason_retry": (
                    f"brand escalation triggers: {', '.join(esc.triggers)}"
                ),
            }
        elif enhanced_fields is not None:
            snap = _field_snap(enhanced_fields.get(key))
            retry_payload = {
                "ran": True,
                "kind": "whole_label_ENHANCED",
                "reasons": list(extraction.retry.reasons),
                **snap,
            }
        else:
            retry_payload = {
                "ran": False,
                "note": (
                    "ENHANCED not triggered; brand-region N/A for non-brand fields"
                    if key != "brand_name"
                    else "brand-region not triggered"
                ),
            }

        rapid_payload: dict[str, Any] | None
        if key != "brand_name":
            rapid_payload = {
                "ran": False,
                "note": "RapidOCR escalation is brand-only in current architecture",
            }
        elif not with_secondary_ocr:
            rapid_payload = {"ran": False, "note": secondary_note}
        elif esc is None or not esc.secondary_ran:
            rapid_payload = {
                "ran": False,
                "note": (
                    esc.secondary_skipped_reason
                    if esc
                    else secondary_note or "secondary not run"
                ),
            }
        else:
            rapid_payload = {
                "ran": True,
                "provider": esc.secondary_provider,
                "raw": esc.secondary_brand_raw,
                "region_or_whole": (
                    "region (+ optional whole fallback if recorded in outcomes)"
                ),
                "reconcile_outcomes_including_secondary": [
                    o for o in esc.reconcile_outcomes if "rapidocr" in o or "secondary" in o
                ],
                "inference_ms": esc.secondary_ms,
            }

        field_reports[key] = {
            "fast": fast,
            "tesseract_retry": retry_payload,
            "rapidocr": rapid_payload,
            "openai": None,  # filled below
            "reconciliation": None,
            "final_rule": None,
        }

    # OpenAI path (explicit flag only).
    ai_section: dict[str, Any] = {
        "requested": with_ai,
        "called": False,
    }
    checks_after = checks_before
    overall_after = overall_before
    merge_outcomes: dict[str, str] = {}
    fields_updated: list[str] = []
    conflicts: list[str] = []
    ai_by_field: dict[str, Any] = {}

    eligible = collect_eligible_checks(checks_before, overall_status=overall_before)
    eligible_fields = [CHECK_TO_FIELD[c.check_name] for c in eligible]

    if with_ai:
        ai = create_ai_provider(
            Settings(
                openai_enabled=bool(base_settings.openai_enabled),
                openai_api_key=base_settings.openai_api_key,
                openai_model=base_settings.openai_model,
                openai_timeout_seconds=base_settings.openai_timeout_seconds,
                openai_max_image_edge_px=base_settings.openai_max_image_edge_px,
            ),
        )
        ai_section["availability"] = ai.availability().value
        ai_section["eligible_fields"] = eligible_fields
        if not eligible:
            ai_section["note"] = "No AI-eligible REVIEW fields"
        elif ai.availability() != AiAvailability.AVAILABLE:
            ai_section["note"] = f"Provider unavailable: {ai.availability().value}"
        else:
            package = build_evidence_package(
                checks=eligible,
                fields=selected_fields,
                quality_status=extraction_response.quality_status,
                quality_warnings=list(extraction_response.quality_warnings),
            )
            prepared = prepare_vision_image(
                data,
                max_edge_px=settings.openai_max_image_edge_px,
                fields=selected_fields,
                target_fields=eligible_fields,
            )
            ai_start = time.perf_counter()
            batch = ai.recover_label_evidence(package, prepared)
            timings["openai_request_ms"] = (time.perf_counter() - ai_start) * 1000
            ai_section["called"] = batch.called
            ai_section["latency_ms"] = batch.latency_ms
            ai_section["explanation"] = batch.explanation
            # Never include image bytes / headers.
            for item in batch.fields:
                ok, reason = validate_field_evidence(item)
                ai_by_field[item.field] = {
                    "requested": True,
                    "candidate_value": item.candidate_value,
                    "raw_observed_text": item.raw_observed_text,
                    "confidence": item.confidence.value,
                    "unable_to_determine": item.unable_to_determine,
                    "complete_or_partial": (
                        "unable_to_determine"
                        if item.unable_to_determine
                        else (
                            "partial"
                            if item.confidence.value == "LOW"
                            else "complete_candidate"
                        )
                    ),
                    "evidence_description": item.evidence_description,
                    "validation_ok": ok,
                    "validation_reason": reason,
                }
            merged, fields_updated, conflicts, merge_outcomes = merge_ai_evidence(
                selected_fields,
                batch,
            )
            t_post = time.perf_counter()
            checks_after = run_rules(
                RuleContext(
                    application=None,
                    fields=merged,
                    mode=VerificationMode.LABEL_ONLY,
                    quality_status=extraction_response.quality_status,
                ),
            )
            overall_after = aggregate_overall_status(checks_after)
            rules_ms += (time.perf_counter() - t_post) * 1000
            selected_fields = merged
    else:
        ai_section["note"] = "skipped (--with-ai not set)"
        ai_section["eligible_fields_if_ai_were_enabled"] = eligible_fields

    timings["reconciliation_rules_ms"] = rules_ms
    timings["total_ms"] = (
        extraction_wall_ms + rules_ms + (timings["openai_request_ms"] or 0.0)
    )

    checks_by_field = {
        CHECK_TO_FIELD.get(c.check_name): c
        for c in checks_after
        if c.check_name in CHECK_TO_FIELD
    }

    for key in FIELD_KEYS:
        # OpenAI row
        if not with_ai:
            field_reports[key]["openai"] = {
                "requested_in_call": False,
                "note": "AI not invoked (pass --with-ai)",
                "would_be_eligible": key in eligible_fields,
            }
        else:
            if key in ai_by_field:
                field_reports[key]["openai"] = ai_by_field[key]
            else:
                field_reports[key]["openai"] = {
                    "requested_in_call": key in eligible_fields,
                    "note": (
                        "eligible but no structured row returned"
                        if key in eligible_fields
                        else "not requested (not AI-eligible)"
                    ),
                }

        # Reconciliation row (OCR escalation + AI merge)
        recon: dict[str, Any] = {
            "ocr_sources": ["tesseract_fast"],
        }
        if extraction.enhanced_pass is not None:
            recon["ocr_sources"].append("tesseract_enhanced")
        if key == "brand_name" and esc and esc.triggered:
            recon["ocr_sources"].append(f"tesseract_region:{esc.region_method}")
            recon["brand_escalation_outcomes"] = list(esc.reconcile_outcomes)
            recon["whole_brand_raw"] = esc.whole_brand_raw
            recon["region_brand_raw"] = esc.region_brand_raw
            recon["secondary_brand_raw"] = esc.secondary_brand_raw
        if with_ai:
            recon["ai_merge_outcome"] = merge_outcomes.get(key)
            recon["ai_updated"] = key in fields_updated
            recon["ai_conflicts"] = [c for c in conflicts if c.startswith(f"{key}:")]
            if key in ai_by_field and not ai_by_field[key].get("validation_ok", True):
                recon["ai_rejected_reason"] = ai_by_field[key].get("validation_reason")
        final_field = selected_fields.get(key)
        recon["resulting_normalized"] = (
            final_field.normalized_value if final_field else None
        )
        recon["resulting_raw"] = final_field.raw_text if final_field else None
        recon["resulting_extraction_status"] = (
            final_field.status.value if final_field else None
        )
        field_reports[key]["reconciliation"] = recon

        check = checks_by_field.get(key)
        field_reports[key]["final_rule"] = {
            "status": check.status.value if check else None,
            "reason_code": check.reason_code if check else None,
            "explanation": check.explanation if check else None,
        }

    report = {
        "image": str(image_path),
        "flags": {
            "with_secondary_ocr": with_secondary_ocr,
            "with_ai": with_ai,
        },
        "overall_before_ai": overall_before.value,
        "overall_after": overall_after.value,
        "quality_status": extraction_response.quality_status,
        "enhanced_retry": {
            "triggered": extraction.retry.triggered,
            "performed": extraction.retry.performed,
            "reasons": list(extraction.retry.reasons),
        },
        "brand_escalation": esc.model_dump() if esc else None,
        "timings_ms": timings,
        "extraction_stage_timings_ms": stage_timings,
        "fields": field_reports,
        "ai_summary": ai_section,
    }
    return report


def _print_report(report: dict[str, Any]) -> None:
    print("LabelVerify verification pipeline diagnostic")
    print(f"image: {report['image']}")
    print(f"flags: {report['flags']}")
    print(f"quality: {report['quality_status']}")
    print(
        f"overall: before_ai={report['overall_before_ai']} "
        f"after={report['overall_after']}",
    )
    print(f"enhanced_retry: {report['enhanced_retry']}")
    if report.get("brand_escalation"):
        esc = report["brand_escalation"]
        print(
            "brand_escalation: "
            f"triggered={esc.get('triggered')} "
            f"region={esc.get('region_method')} "
            f"secondary_ran={esc.get('secondary_ran')} "
            f"outcomes={esc.get('reconcile_outcomes')}",
        )

    for key in FIELD_KEYS:
        _print_field_table(key, report["fields"][key])

    print()
    print("=" * 88)
    print("TIMING BREAKDOWN (ms)")
    print("=" * 88)
    timings = report["timings_ms"]
    order = [
        ("preprocessing (display analysis)", "preprocessing_display_ms"),
        ("Tesseract FAST", "tesseract_fast_ms"),
        ("Tesseract ENHANCED (whole-label)", "tesseract_enhanced_ms"),
        ("Tesseract brand region", "tesseract_brand_region_ms"),
        ("RapidOCR initialization", "rapidocr_init_ms"),
        ("RapidOCR inference", "rapidocr_inference_ms"),
        ("OpenAI request", "openai_request_ms"),
        ("reconciliation / rules", "reconciliation_rules_ms"),
        ("TOTAL (approx wall)", "total_ms"),
    ]
    for label, key in order:
        value = timings.get(key)
        print(f"  {label:40s} {value if value is not None else 'n/a'}")
    print()
    print("extraction stage_timings_ms (raw):")
    for key, value in sorted((report.get("extraction_stage_timings_ms") or {}).items()):
        print(f"  {key}: {value:.1f}" if isinstance(value, (int, float)) else f"  {key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose full verification evidence pipeline (read-only)",
    )
    parser.add_argument("image", type=Path, help="Path to label image")
    parser.add_argument(
        "--with-secondary-ocr",
        action="store_true",
        help="Enable optional RapidOCR brand escalation for this diagnostic run",
    )
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="Invoke configured OpenAI evidence recovery once (explicit opt-in)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also emit machine-readable JSON after the human tables",
    )
    args = parser.parse_args(argv)

    if not args.image.is_file():
        print(f"Image not found: {args.image}", file=sys.stderr)
        return 2

    report = diagnose(
        args.image,
        with_secondary_ocr=args.with_secondary_ocr,
        with_ai=args.with_ai,
    )
    # Safety: never print secret-like blobs
    blob = str(report).lower()
    if "authorization" in blob or "sk-" in blob or "api_key" in blob:
        print("[redacted: unexpected secret-like content blocked]", file=sys.stderr)
        return 3

    _print_report(report)
    if args.json:
        import json

        print()
        print("--- JSON ---")
        print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
