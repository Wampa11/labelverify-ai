"""
Verification orchestration service.

Architectural responsibility: extraction → deterministic rules → optional AI evidence
recovery → deterministic re-evaluation. AI never sets PASS/REVIEW/FAIL directly.
"""

from __future__ import annotations

import logging
import uuid

from app.ai.eligibility import CHECK_TO_FIELD, collect_eligible_checks
from app.ai.evidence import AiAssistSummary
from app.ai.factory import create_ai_provider
from app.ai.merge import merge_ai_evidence
from app.ai.package import build_evidence_package, prepare_vision_image
from app.ai.provider import AiAvailability, AiProvider
from app.core.config import Settings, get_settings
from app.core.timing import PipelineTimer
from app.models.verification import (
    ApplicationData,
    CheckStatus,
    DecisionMethod,
    FieldCheckResult,
    SingleReviewVerificationResponse,
    VerificationResult,
)
from app.models.verification_mode import VerificationMode
from app.ocr.base import OcrProvider
from app.rules.base import RuleContext
from app.rules.engine import build_verification_result, run_rules
from app.services.label_extraction_service import LabelExtractionService

logger = logging.getLogger(__name__)

INITIAL_CHECK_NAMES = (
    "Brand Name",
    "Class / Type",
    "Alcohol Content / ABV",
    "Net Contents",
    "Government Health Warning",
)


class VerificationService:
    """Runs end-to-end verification for one label (label-only or application-comparison)."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        ai_provider: AiProvider | None = None,
        extraction_service: LabelExtractionService | None = None,
        ocr_provider: OcrProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._ai = ai_provider if ai_provider is not None else create_ai_provider(self._settings)
        self._extraction = extraction_service or LabelExtractionService(
            settings=self._settings,
            ocr_provider=ocr_provider,
        )

    def verify(
        self,
        data: bytes,
        application: ApplicationData | None = None,
        *,
        mode: VerificationMode | None = None,
        filename: str | None = None,
        declared_content_type: str | None = None,
    ) -> SingleReviewVerificationResponse:
        """
        Extract, deterministically verify, optionally recover AI evidence, re-verify.

        LABEL_ONLY (default when application is None): label evidence + label-only rules.
        APPLICATION_COMPARISON (when application provided): compare to application values.
        AI produces evidence only. Deterministic rules always produce status.
        """
        resolved_mode = mode or (
            VerificationMode.APPLICATION_COMPARISON
            if application is not None
            else VerificationMode.LABEL_ONLY
        )
        if (
            resolved_mode == VerificationMode.APPLICATION_COMPARISON
            and application is None
        ):
            raise ValueError("application_comparison mode requires ApplicationData")

        timer = PipelineTimer()
        timer.start()
        verification_id = str(uuid.uuid4())

        with timer.stage("extraction_pipeline"):
            extraction_response = self._extraction.extract(
                data,
                filename=filename,
                declared_content_type=declared_content_type,
            )

        fields = dict(extraction_response.extraction.selected_fields)
        context = self._rule_context(
            application,
            fields,
            extraction_response.quality_status,
            resolved_mode,
        )

        with timer.stage("verification_rules"):
            checks_before = run_rules(context)
        status_before = _overall(checks_before)

        checks = checks_before
        ai_used = False
        # Only mark degraded when AI was needed but unavailable/failed — not when disabled unused.
        ai_degraded = False

        ai_configured = (
            bool(self._settings.openai_enabled) and bool(self._settings.openai_api_key)
        )
        eligible = collect_eligible_checks(checks_before, overall_status=status_before)
        eligible_fields = [CHECK_TO_FIELD[c.check_name] for c in eligible]
        eligible_reasons = [c.reason_code for c in eligible if c.reason_code]

        # Evidence-method baseline from extraction passes + brand escalation.
        extraction_payload = extraction_response.extraction
        evidence_method = "ocr_only"
        if extraction_payload.enhanced_pass is not None:
            evidence_method = "ocr_plus_enhanced"
        esc = extraction_payload.brand_escalation
        if esc and esc.triggered and esc.evidence_method_suffix:
            if esc.evidence_method_suffix == "brand_region_rapidocr":
                evidence_method = f"{evidence_method}_plus_brand_region_rapidocr"
            elif esc.evidence_method_suffix == "brand_region":
                evidence_method = f"{evidence_method}_plus_brand_region"

        ai_summary = AiAssistSummary(
            status_before=status_before.value,
            provider_name=self._ai.name,
            ai_configured=ai_configured,
            ai_eligible=bool(eligible),
            eligible_fields=eligible_fields,
            trigger_reason_codes=eligible_reasons,
            evidence_method=evidence_method,
            model=self._settings.openai_model if ai_configured else None,
        )
        degradation_notes = [
            "Overall status is a prototype verification summary, not a final "
            "regulatory determination.",
        ]
        if resolved_mode == VerificationMode.LABEL_ONLY:
            degradation_notes.append(
                "Label-only review: application comparison checks were not evaluated.",
            )

        logger.info(
            "ai_fallback_triage verification_id=%s ai_configured=%s ai_eligible=%s "
            "eligible_fields=%s reason_codes=%s provider_availability=%s overall_before=%s",
            verification_id,
            ai_configured,
            bool(eligible),
            eligible_fields,
            eligible_reasons,
            self._ai.availability().value,
            status_before.value,
        )

        if eligible and self._settings.openai_max_calls_per_review > 0:
            ai_summary.attempted = True
            ai_summary.fields_requested = list(eligible_fields)

            if self._ai.availability() != AiAvailability.AVAILABLE:
                ai_degraded = True
                ai_summary.ai_succeeded = False
                ai_summary.failure_category = "provider_unavailable"
                ai_summary.outcome = "provider_unavailable"
                ai_summary.evidence_method = f"{evidence_method}_ai_unavailable"
                ai_summary.explanation = (
                    f"AI evidence recovery eligible but provider availability="
                    f"{self._ai.availability().value}; retaining deterministic REVIEW."
                )
                degradation_notes.append(ai_summary.explanation)
                logger.info(
                    "ai_fallback_skip verification_id=%s category=provider_unavailable "
                    "availability=%s",
                    verification_id,
                    self._ai.availability().value,
                )
            else:
                with timer.stage("ai_evidence_recovery"):
                    package = build_evidence_package(
                        checks=eligible,
                        fields=fields,
                        quality_status=extraction_response.quality_status,
                        quality_warnings=list(extraction_response.quality_warnings),
                    )
                    prepared = prepare_vision_image(
                        data,
                        max_edge_px=self._settings.openai_max_image_edge_px,
                        fields=fields,
                        target_fields=ai_summary.fields_requested,
                    )
                    if prepared.used_crop:
                        package = package.model_copy(
                            update={
                                "uses_full_image": False,
                                "crop_note": "Used union crop of OCR regions when available.",
                            },
                        )
                    try:
                        batch = self._ai.recover_label_evidence(package, prepared)
                    except Exception as exc:  # noqa: BLE001 — never fail the review on AI
                        logger.warning(
                            "ai_recovery_exception verification_id=%s provider=%s err=%s",
                            verification_id,
                            self._ai.name,
                            type(exc).__name__,
                        )
                        batch = None
                        ai_degraded = True
                        ai_summary.ai_succeeded = False
                        ai_summary.failure_category = "provider_exception"
                        ai_summary.outcome = "provider_exception"
                        ai_summary.evidence_method = f"{evidence_method}_ai_failed"
                        ai_summary.explanation = (
                            "AI provider raised an exception; retaining deterministic REVIEW."
                        )
                        degradation_notes.append(ai_summary.explanation)

                if batch is not None:
                    ai_used = batch.called
                    ai_summary.called = batch.called
                    ai_summary.model = batch.model or ai_summary.model
                    ai_summary.latency_ms = batch.latency_ms
                    ai_summary.explanation = batch.explanation
                    ai_summary.fields_proposed = [
                        f.field for f in batch.fields if f.field
                    ]
                    logger.info(
                        "ai_fallback_result verification_id=%s called=%s availability=%s "
                        "latency_ms=%s proposed_fields=%s model=%s",
                        verification_id,
                        batch.called,
                        batch.availability,
                        batch.latency_ms,
                        ai_summary.fields_proposed,
                        batch.model,
                    )
                    if batch.called and batch.availability == AiAvailability.AVAILABLE.value:
                        merged, updated, conflicts, outcomes = merge_ai_evidence(
                            fields,
                            batch,
                        )
                        ai_summary.merge_outcomes = outcomes
                        if conflicts:
                            degradation_notes.append(
                                "CONFLICTING_EVIDENCE: " + "; ".join(conflicts),
                            )
                        if updated:
                            fields = merged
                            ai_summary.fields_updated = updated
                            ai_summary.evidence_changed = True
                            ai_summary.ai_succeeded = True
                            ai_summary.evidence_method = "ocr_plus_ai"
                            # Re-run deterministic rules only — AI does not set status.
                            context = self._rule_context(
                                application,
                                fields,
                                extraction_response.quality_status,
                                resolved_mode,
                            )
                            with timer.stage("verification_rules_after_ai"):
                                checks = run_rules(context)
                            ai_summary.outcome = "evidence_merged"
                            if any(v == "conflict" for v in outcomes.values()):
                                ai_summary.evidence_method = "ocr_plus_ai_conflict"
                        else:
                            ai_summary.ai_succeeded = False
                            ai_summary.failure_category = "no_usable_evidence"
                            ai_summary.outcome = "no_usable_evidence"
                            ai_summary.evidence_method = f"{evidence_method}_ai_rejected"
                            ai_summary.explanation = (
                                batch.explanation
                                + " No validated AI evidence applied; retaining REVIEW."
                            )
                    elif batch.called:
                        ai_degraded = True
                        ai_summary.ai_succeeded = False
                        ai_summary.failure_category = "provider_failed"
                        ai_summary.outcome = "provider_failed"
                        ai_summary.evidence_method = f"{evidence_method}_ai_failed"
                        degradation_notes.append(batch.explanation)
                    else:
                        ai_summary.ai_succeeded = False
                        ai_summary.failure_category = "not_called"
                        ai_summary.outcome = "provider_not_called"
                        ai_summary.evidence_method = f"{evidence_method}_ai_unavailable"
        elif status_before == CheckStatus.PASS:
            ai_summary.outcome = "not_needed_pass"
            ai_summary.explanation = "Deterministic PASS — no AI calls."
        elif status_before == CheckStatus.FAIL:
            ai_summary.outcome = "not_needed_fail"
            ai_summary.explanation = (
                "Deterministic FAIL present — AI not invoked to avoid unnecessary calls."
            )
        else:
            ai_summary.outcome = "not_eligible"
            ai_summary.explanation = (
                "REVIEW present but no AI-eligible semantic reason codes "
                "(human-only / OCR_LOW_QUALITY alone without recoverable field state)."
            )

        status_after = _overall(checks)
        ai_summary.status_after = status_after.value

        # Annotate checks with evidence-method / AI outcome for Technical Details.
        esc = extraction_payload.brand_escalation
        checks = [
            c.model_copy(
                update={
                    "technical_details": {
                        **(c.technical_details or {}),
                        "evidence_method": ai_summary.evidence_method,
                        "ai_assist_outcome": ai_summary.outcome,
                        "ai_configured": ai_summary.ai_configured,
                        "ai_eligible_for_review": ai_summary.ai_eligible,
                        **(
                            {
                                "brand_escalation": esc.model_dump(exclude_none=True),
                            }
                            if esc is not None and c.check_name == "Brand Name"
                            else {}
                        ),
                        **(
                            {
                                "ai_assisted_evidence": True,
                                "ai_merge_outcome": (
                                    ai_summary.merge_outcomes.get(
                                        CHECK_TO_FIELD.get(c.check_name, ""),
                                    )
                                ),
                            }
                            if CHECK_TO_FIELD.get(c.check_name) in ai_summary.fields_updated
                            else {}
                        ),
                        **(
                            {
                                "ai_attempted_but_unavailable": True,
                                "ai_failure_category": ai_summary.failure_category,
                            }
                            if ai_summary.attempted
                            and not ai_summary.ai_succeeded
                            and ai_summary.failure_category
                            else {}
                        ),
                    },
                },
            )
            for c in checks
        ]

        # Mark AI-assisted checks with concise explanation note when evidence changed.
        if ai_summary.fields_updated:
            updated_checks = {
                check_name
                for check_name, field_name in CHECK_TO_FIELD.items()
                if field_name in ai_summary.fields_updated
            }
            checks = [
                (
                    c.model_copy(
                        update={
                            "explanation": c.explanation
                            + " (AI-assisted evidence was considered; status is deterministic.)",
                        },
                    )
                    if c.check_name in updated_checks
                    else c
                )
                for c in checks
            ]

        stage_timings = {item.label: item.elapsed_ms for item in timer.stages}
        for key, value in extraction_response.stage_timings_ms.items():
            stage_timings.setdefault(f"extraction_{key}", value)
        processing_time_ms = timer.stop_overall_ms()

        if ai_summary.attempted and ai_degraded:
            degradation_notes.append(
                f"AI provider {self._ai.name!r} availability={self._ai.availability().value}",
            )

        # Persist merged fields onto extraction payload for response transparency.
        extraction = extraction_response.extraction.model_copy(
            update={"selected_fields": fields},
        )

        verification = build_verification_result(
            verification_id=verification_id,
            checks=checks,
            processing_time_ms=processing_time_ms,
            stage_timings_ms=stage_timings,
            degradation_notes=degradation_notes,
            verification_mode=resolved_mode.value,
        )
        verification = verification.model_copy(
            update={
                "ai_used": ai_used,
                "ai_degraded": ai_degraded,
                "ai_assist": ai_summary.model_dump(),
            },
        )

        logger.info(
            "verification_complete verification_id=%s mode=%s overall=%s ai_used=%s "
            "ai_outcome=%s processing_time_ms=%.2f",
            verification_id,
            resolved_mode.value,
            verification.overall_status,
            ai_used,
            ai_summary.outcome,
            processing_time_ms,
        )

        return SingleReviewVerificationResponse(
            analysis_id=extraction_response.analysis_id,
            verification_id=verification_id,
            filename=filename,
            verification_mode=resolved_mode.value,
            application=application,
            display_image_base64=extraction_response.display_image_base64,
            display_media_type=extraction_response.display_media_type,
            metadata_width_px=extraction_response.metadata_width_px,
            metadata_height_px=extraction_response.metadata_height_px,
            quality_status=extraction_response.quality_status,
            quality_warnings=list(extraction_response.quality_warnings),
            extraction=extraction,
            verification=verification,
            processing_time_ms=processing_time_ms,
            stage_timings_ms=stage_timings,
        )

    def verify_stub(self, application: ApplicationData) -> VerificationResult:
        """Stub without image (smoke tests). Prefer `verify()` for Single Review."""
        timer = PipelineTimer()
        timer.start()
        checks = [
            FieldCheckResult(
                check_name=name,
                application_value=_application_value_for_check(name, application),
                detected_label_value=None,
                status=CheckStatus.REVIEW,
                confidence=None,
                explanation=(
                    "Not evaluated: stub path without label image. "
                    "Use POST /api/v1/verify with multipart image "
                    "(optional application JSON for comparison mode)."
                ),
                decision_method=DecisionMethod.PIPELINE_STUB,
                reason_code="PIPELINE_STUB",
                ai_assist_eligible=False,
            )
            for name in INITIAL_CHECK_NAMES
        ]
        processing_time_ms = timer.stop_overall_ms()
        return VerificationResult(
            overall_status=CheckStatus.REVIEW,
            verification_mode=VerificationMode.APPLICATION_COMPARISON.value,
            checks=checks,
            pass_count=0,
            review_count=len(checks),
            fail_count=0,
            processing_time_ms=processing_time_ms,
            ai_used=False,
            ai_degraded=True,
            ai_assist=AiAssistSummary(outcome="stub").model_dump(),
            degradation_notes=["Stub path: no image provided."],
        )

    def _rule_context(
        self,
        application: ApplicationData | None,
        fields: dict,
        quality_status: str,
        mode: VerificationMode,
    ) -> RuleContext:
        return RuleContext(
            application=application,
            fields=fields,
            mode=mode,
            quality_status=quality_status,
            brand_pass_ratio=self._settings.brand_pass_ratio,
            brand_review_ratio=self._settings.brand_review_ratio,
            class_pass_ratio=self._settings.class_pass_ratio,
            abv_epsilon=self._settings.abv_compare_epsilon,
            net_ml_epsilon=self._settings.net_contents_epsilon_ml,
        )


def _overall(checks: list[FieldCheckResult]) -> CheckStatus:
    from app.rules.engine import aggregate_overall_status

    return aggregate_overall_status(checks)


def _application_value_for_check(check_name: str, application: ApplicationData) -> str | None:
    mapping = {
        "Brand Name": application.brand_name,
        "Class / Type": application.class_type,
        "Alcohol Content / ABV": application.alcohol_content_abv,
        "Net Contents": application.net_contents,
        "Government Health Warning": None,
    }
    return mapping.get(check_name)
