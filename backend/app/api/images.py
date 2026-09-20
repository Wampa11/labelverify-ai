"""
HTTP endpoints for label image upload and analysis.

Architectural responsibility: multipart intake and error mapping — no OCR or regulatory logic.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import ImageValidationError
from app.models.image_analysis import ImageAnalysisResponse
from app.services.image_analysis_service import ImageAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter()

LabelImageUpload = Annotated[
    UploadFile,
    File(description="Label image file (JPEG, PNG, or WebP)"),
]


@router.post(
    "/images/analyze",
    response_model=ImageAnalysisResponse,
    summary="Validate and preprocess a single label image",
    description=(
        "Accepts one JPEG, PNG, or WebP label image. Returns display and OCR-prepared "
        "representations, quality assessment, and processing time. Does not run OCR or "
        "regulatory checks. Uploads are not stored on disk."
    ),
)
async def analyze_image(file: LabelImageUpload) -> ImageAnalysisResponse:
    """Analyze an uploaded label image for Single Review preprocessing."""
    raw = await file.read()
    service = ImageAnalysisService()
    try:
        return service.analyze(
            raw,
            filename=file.filename,
            declared_content_type=file.content_type,
        )
    except ImageValidationError as exc:
        logger.info(
            "image_validation_rejected code=%s details=%s",
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
    except Exception as exc:
        logger.exception("Unexpected failure during image analysis")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Something went wrong while analyzing this image. Please try again.",
                "code": "internal_error",
            },
        ) from exc
