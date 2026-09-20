"""
Verification HTTP endpoints.

Architectural responsibility: accept label image (optional application JSON); delegate to
VerificationService — no rules/OCR logic in the handler.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.core.audit import (
    SINGLE_REVIEW_COMPLETED,
    SINGLE_REVIEW_STARTED,
    emit_application_error,
    emit_audit_event,
)
from app.core.exceptions import ImageValidationError
from app.models.verification import ApplicationData, SingleReviewVerificationResponse
from app.models.verification_mode import VerificationMode
from app.ocr.errors import OcrProviderError
from app.services.verification_service import VerificationService

logger = logging.getLogger(__name__)

router = APIRouter()

LabelImageUpload = Annotated[
    UploadFile,
    File(description="Label image file (JPEG, PNG, or WebP)"),
]


@router.post(
    "/verify",
    response_model=SingleReviewVerificationResponse,
    summary="Analyze a label image (label-only or application-comparison)",
    description=(
        "Accepts multipart `file` (label image). Optional form field `application` "
        "(JSON with brand_name, class_type, alcohol_content_abv, net_contents) enables "
        "application-comparison mode (Batch / future COLA). Without application, runs "
        "label-only review. OpenAI evidence recovery remains optional and never sets "
        "PASS/FAIL. Not a final regulatory determination."
    ),
)
async def verify_label(
    file: LabelImageUpload,
    application: Annotated[
        str | None,
        Form(description="Optional JSON ApplicationData for comparison mode"),
    ] = None,
) -> SingleReviewVerificationResponse:
    """Run verification for one label image; application JSON enables comparison mode."""
    app_model: ApplicationData | None = None
    mode = VerificationMode.LABEL_ONLY
    if application is not None and application.strip():
        try:
            app_model = ApplicationData.model_validate(json.loads(application))
            mode = VerificationMode.APPLICATION_COMPARISON
        except (json.JSONDecodeError, ValidationError) as exc:
            emit_application_error(
                operation="single_review",
                stage="application_parse",
                error_type=type(exc).__name__,
                message="Invalid application JSON for verification request.",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Application data is invalid. Check required fields and formats.",
                    "code": "invalid_application_data",
                    "details": str(exc),
                },
            ) from exc

    emit_audit_event(
        SINGLE_REVIEW_STARTED,
        verification_mode=mode.value,
    )

    raw = await file.read()
    service = VerificationService()
    try:
        result = service.verify(
            raw,
            app_model,
            mode=mode,
            filename=file.filename,
            declared_content_type=file.content_type,
        )
    except ImageValidationError as exc:
        emit_application_error(
            operation="single_review",
            stage="image_validation",
            error_type=type(exc).__name__,
            message=exc.message,
        )
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if exc.code == "file_too_large"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={"error": exc.message, "code": exc.code},
        ) from exc
    except OcrProviderError as exc:
        emit_application_error(
            operation="single_review",
            stage="ocr",
            error_type=type(exc).__name__,
            message="OCR provider unavailable during single review.",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": (
                    "Text reading is temporarily unavailable. "
                    "Please try again or check OCR installation."
                ),
                "code": exc.code or "ocr_unavailable",
            },
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected failure during verification")
        emit_application_error(
            operation="single_review",
            stage="verify",
            error_type=type(exc).__name__,
            message="Unexpected failure during single label verification.",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Something went wrong while analyzing this label. Please try again.",
                "code": "internal_error",
            },
        ) from None

    escalation = result.extraction.brand_escalation
    secondary_ocr = bool(escalation and escalation.secondary_ran)
    emit_audit_event(
        SINGLE_REVIEW_COMPLETED,
        overall_status=result.verification.overall_status.value,
        duration_ms=round(float(result.processing_time_ms or 0.0), 1),
        ai_used=bool(result.verification.ai_used),
        secondary_ocr_used=secondary_ocr,
        quality_status=result.quality_status,
        verification_mode=result.verification_mode,
    )
    return result
