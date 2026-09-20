"""
HTTP endpoints for structured label field extraction (Single Review).

Architectural responsibility: multipart intake and error mapping — no field rules
and no regulatory decisions.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import ImageValidationError
from app.models.extraction import LabelExtractionResponse
from app.ocr.errors import OcrProviderError
from app.services.label_extraction_service import LabelExtractionService

logger = logging.getLogger(__name__)

router = APIRouter()

LabelImageUpload = Annotated[
    UploadFile,
    File(description="Label image file (JPEG, PNG, or WebP)"),
]


@router.post(
    "/labels/extract",
    response_model=LabelExtractionResponse,
    summary="Extract structured fields from a label image",
    description=(
        "Accepts one JPEG, PNG, or WebP label image. Runs Tesseract OCR (FAST/1600) "
        "and structured field extraction. May perform one observable ENHANCED/1200 "
        "OCR retry when extraction evidence is insufficient. Returns FOUND / "
        "UNCERTAIN / NOT_FOUND for each field — not regulatory PASS/REVIEW/FAIL. "
        "Does not call OpenAI. Uploads are not stored on disk."
    ),
)
async def extract_label_fields(file: LabelImageUpload) -> LabelExtractionResponse:
    """Extract structured alcohol-label fields for Single Review."""
    raw = await file.read()
    service = LabelExtractionService()
    try:
        return service.extract(
            raw,
            filename=file.filename,
            declared_content_type=file.content_type,
        )
    except ImageValidationError as exc:
        logger.info(
            "label_extraction_validation_rejected code=%s details=%s",
            exc.code,
            exc.details,
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
        logger.warning(
            "label_extraction_ocr_failed code=%s provider=%s",
            exc.code,
            exc.provider_name,
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
        logger.exception("Unexpected failure during label extraction")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Something went wrong while extracting label fields. Please try again.",
                "code": "internal_error",
            },
        ) from exc
