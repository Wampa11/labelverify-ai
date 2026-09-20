"""
Orchestrate Single Review OCR + structured field extraction.

Architectural responsibility: FAST OCR → extraction → optional one ENHANCED retry →
selective brand-region escalation → observable selection.
No regulatory PASS/FAIL and no OpenAI calls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.timing import PipelineTimer
from app.extraction.brand_escalation import run_brand_escalation
from app.extraction.pipeline import extract_all_fields
from app.extraction.retry_policy import (
    merge_conflicts_as_uncertain,
    select_pass,
    should_retry_enhanced,
)
from app.models.extraction import (
    BrandEscalationSummary,
    ExtractedField,
    ExtractedLabelResult,
    ExtractionStatus,
    LabelExtractionResponse,
    OcrPassSummary,
    RetryDecision,
)
from app.ocr.base import OcrProvider, OcrResult
from app.ocr.errors import OcrProviderError
from app.ocr.factory import create_ocr_provider
from app.preprocessing.ocr_prepare import OcrPreprocessProfile, prepare_for_ocr_from_bytes
from app.services.image_analysis_service import ImageAnalysisService

logger = logging.getLogger(__name__)


@dataclass
class _PassBundle:
    """Internal OCR pass with prepared image bytes for region crops."""

    summary: OcrPassSummary
    ocr: OcrResult
    prepared_bytes: bytes


class LabelExtractionService:
    """Runs production Tesseract OCR and structured extraction for one upload."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        ocr_provider: OcrProvider | None = None,
        image_service: ImageAnalysisService | None = None,
        secondary_ocr_provider: OcrProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._ocr = ocr_provider or create_ocr_provider(self._settings.ocr_provider)
        self._image_service = image_service or ImageAnalysisService(settings=self._settings)
        self._secondary_ocr = secondary_ocr_provider

    def extract(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        declared_content_type: str | None = None,
    ) -> LabelExtractionResponse:
        """
        Validate/preprocess for display, run FAST OCR+extraction, optionally one
        ENHANCED retry, selective brand escalation, then return structured fields.
        """
        timer = PipelineTimer()
        timer.start()

        with timer.stage("display_analysis"):
            analysis = self._image_service.analyze(
                data,
                filename=filename,
                declared_content_type=declared_content_type,
            )
        analysis_id = analysis.analysis_id
        quality_status = analysis.quality.status

        fast_bundle = self._run_pass(
            data,
            profile=OcrPreprocessProfile.FAST,
            max_edge_px=self._settings.ocr_fast_max_edge_px,
            timer=timer,
            stage_prefix="fast",
        )
        fast_pass = fast_bundle.summary

        retry = should_retry_enhanced(
            fast_pass.fields,
            ocr_text=fast_pass.ocr_text_preview,
            word_count=fast_pass.word_count,
            quality_status=quality_status,
        )

        enhanced_bundle: _PassBundle | None = None
        enhanced_pass: OcrPassSummary | None = None
        if retry.triggered:
            enhanced_bundle = self._run_pass(
                data,
                profile=OcrPreprocessProfile.ENHANCED,
                max_edge_px=self._settings.ocr_enhanced_max_edge_px,
                timer=timer,
                stage_prefix="enhanced",
            )
            enhanced_pass = enhanced_bundle.summary
            retry = RetryDecision(
                triggered=True,
                reasons=retry.reasons,
                performed=True,
            )

        selection = select_pass(fast_pass, enhanced_pass)
        if (
            selection.selected_profile == OcrPreprocessProfile.ENHANCED.value
            and enhanced_pass is not None
            and enhanced_bundle is not None
        ):
            selected_fields = merge_conflicts_as_uncertain(
                enhanced_pass.fields,
                fast_pass.fields,
            )
            guide = enhanced_bundle
            ocr_w = enhanced_pass.image_width_px
            ocr_h = enhanced_pass.image_height_px
        else:
            selected_fields = merge_conflicts_as_uncertain(
                fast_pass.fields,
                enhanced_pass.fields if enhanced_pass else None,
            )
            guide = fast_bundle
            ocr_w = fast_pass.image_width_px
            ocr_h = fast_pass.image_height_px

        brand_escalation_summary: BrandEscalationSummary | None = None
        with timer.stage("brand_escalation"):
            brand_escalation_summary = self._maybe_escalate_brand(
                selected_fields,
                guide_ocr=guide.ocr,
                prepared_bytes=guide.prepared_bytes,
            )

        stage_timings = {item.label: item.elapsed_ms for item in timer.stages}
        for key, value in analysis.stage_timings_ms.items():
            stage_timings.setdefault(f"display_{key}", value)
        if brand_escalation_summary and brand_escalation_summary.tesseract_region_ms is not None:
            stage_timings["brand_region_tesseract_ms"] = (
                brand_escalation_summary.tesseract_region_ms
            )
        if brand_escalation_summary and brand_escalation_summary.secondary_ms is not None:
            stage_timings["brand_region_secondary_ms"] = brand_escalation_summary.secondary_ms
        processing_time_ms = timer.stop_overall_ms()

        extraction = ExtractedLabelResult(
            analysis_id=analysis_id,
            selected_fields=selected_fields,
            fast_pass=fast_pass,
            enhanced_pass=enhanced_pass,
            retry=retry,
            selection=selection,
            brand_escalation=brand_escalation_summary,
            ocr_image_width_px=ocr_w,
            ocr_image_height_px=ocr_h,
            display_image_width_px=analysis.metadata.width_px,
            display_image_height_px=analysis.metadata.height_px,
            stage_timings_ms=stage_timings,
            processing_time_ms=processing_time_ms,
        )

        logger.info(
            "label_extraction_complete analysis_id=%s selected=%s retry=%s "
            "brand_escalation=%s found=%s uncertain=%s not_found=%s "
            "processing_time_ms=%.2f",
            analysis_id,
            selection.selected_profile,
            retry.performed,
            bool(brand_escalation_summary and brand_escalation_summary.triggered),
            _count_status(selected_fields, ExtractionStatus.FOUND),
            _count_status(selected_fields, ExtractionStatus.UNCERTAIN),
            _count_status(selected_fields, ExtractionStatus.NOT_FOUND),
            processing_time_ms,
        )

        return LabelExtractionResponse(
            analysis_id=analysis_id,
            filename=filename,
            display_image_base64=analysis.display_image_base64,
            display_media_type=analysis.display_media_type,
            metadata_width_px=analysis.metadata.width_px,
            metadata_height_px=analysis.metadata.height_px,
            quality_status=str(quality_status),
            quality_warnings=list(analysis.quality.warnings),
            extraction=extraction,
            processing_time_ms=processing_time_ms,
            stage_timings_ms=stage_timings,
        )

    def _maybe_escalate_brand(
        self,
        selected_fields: dict[str, ExtractedField],
        *,
        guide_ocr: OcrResult,
        prepared_bytes: bytes,
    ) -> BrandEscalationSummary | None:
        """Selective brand-region OCR; mutates selected_fields['brand_name'] when updated."""
        brand = selected_fields.get("brand_name")
        if brand is None:
            return None
        if not self._settings.brand_region_ocr_enabled:
            return BrandEscalationSummary(
                triggered=False,
                triggers=["brand_region_ocr_disabled"],
            )

        secondary = None
        secondary_enabled = bool(self._settings.secondary_ocr_enabled)
        if secondary_enabled:
            secondary = self._resolve_secondary_provider()

        escalation = run_brand_escalation(
            prepared_image_bytes=prepared_bytes,
            guide_ocr=guide_ocr,
            brand=brand,
            primary_ocr=self._ocr,
            secondary_ocr=secondary,
            secondary_enabled=secondary_enabled,
            brand_region_enabled=True,
        )
        if not escalation.triggered:
            return BrandEscalationSummary(**escalation.as_dict())

        if escalation.final_brand is not None:
            selected_fields["brand_name"] = escalation.final_brand
            # Preserve both evidence sources under Technical Details via hints.
            hints = dict(escalation.final_brand.ai_fallback_hints or {})
            hints["brand_escalation"] = escalation.as_dict()
            selected_fields["brand_name"] = escalation.final_brand.model_copy(
                update={"ai_fallback_hints": hints},
            )

        logger.info(
            "brand_escalation triggered=%s triggers=%s outcomes=%s secondary=%s",
            escalation.triggered,
            escalation.triggers,
            escalation.reconcile_outcomes,
            escalation.secondary_ran,
        )
        return BrandEscalationSummary(**escalation.as_dict())

    def _resolve_secondary_provider(self) -> OcrProvider | None:
        if self._secondary_ocr is not None:
            if self._secondary_ocr.is_available():
                return self._secondary_ocr
            return None
        name = (self._settings.secondary_ocr_provider or "rapidocr").strip().lower()
        try:
            provider = create_ocr_provider(name)
        except ValueError:
            logger.info("secondary_ocr_unknown_provider name=%s", name)
            return None
        try:
            if provider.is_available():
                return provider
        except Exception as exc:  # noqa: BLE001
            logger.info("secondary_ocr_unavailable name=%s err=%s", name, exc)
            return None
        logger.info("secondary_ocr_not_available name=%s", name)
        return None

    def _run_pass(
        self,
        data: bytes,
        *,
        profile: OcrPreprocessProfile,
        max_edge_px: int,
        timer: PipelineTimer,
        stage_prefix: str,
    ) -> _PassBundle:
        """Prepare image, OCR, and extract fields for one profile."""
        with timer.stage(f"{stage_prefix}_preprocess"):
            t0 = time.perf_counter()
            prepared = prepare_for_ocr_from_bytes(
                data,
                profile=profile,
                max_edge_px=max_edge_px,
            )
            preprocess_ms = (time.perf_counter() - t0) * 1000

        with timer.stage(f"{stage_prefix}_ocr"):
            try:
                ocr = self._ocr.extract_text(prepared.image_bytes)
            except OcrProviderError:
                raise
            ocr = ocr.model_copy(
                update={
                    "preprocessing_profile": profile.value,
                    "image_width_px": ocr.image_width_px or prepared.width_px,
                    "image_height_px": ocr.image_height_px or prepared.height_px,
                },
            )
            ocr_ms = float(ocr.processing_time_ms or 0.0)

        with timer.stage(f"{stage_prefix}_extraction"):
            t1 = time.perf_counter()
            fields = extract_all_fields(ocr)
            extraction_ms = (time.perf_counter() - t1) * 1000

        summary = _build_pass_summary(
            profile=profile.value,
            max_edge_px=max_edge_px,
            ocr=ocr,
            fields=fields,
            preprocessing_time_ms=preprocess_ms,
            ocr_time_ms=ocr_ms,
            extraction_time_ms=extraction_ms,
        )
        return _PassBundle(
            summary=summary,
            ocr=ocr,
            prepared_bytes=prepared.image_bytes,
        )


def _build_pass_summary(
    *,
    profile: str,
    max_edge_px: int,
    ocr: OcrResult,
    fields: dict[str, ExtractedField],
    preprocessing_time_ms: float,
    ocr_time_ms: float,
    extraction_time_ms: float,
) -> OcrPassSummary:
    """Assemble an observable OCR+extraction pass summary."""
    return OcrPassSummary(
        profile=profile,
        max_edge_px=max_edge_px,
        provider_name=ocr.provider_name,
        preprocessing_time_ms=preprocessing_time_ms,
        ocr_time_ms=ocr_time_ms,
        extraction_time_ms=extraction_time_ms,
        total_pass_time_ms=preprocessing_time_ms + ocr_time_ms + extraction_time_ms,
        ocr_text_preview=(ocr.full_text or "")[:500],
        word_count=len(ocr.words),
        image_width_px=ocr.image_width_px,
        image_height_px=ocr.image_height_px,
        fields=fields,
        found_count=_count_status(fields, ExtractionStatus.FOUND),
        uncertain_count=_count_status(fields, ExtractionStatus.UNCERTAIN),
        not_found_count=_count_status(fields, ExtractionStatus.NOT_FOUND),
    )


def _count_status(fields: dict[str, ExtractedField], status: ExtractionStatus) -> int:
    return sum(1 for field in fields.values() if field.status == status)
