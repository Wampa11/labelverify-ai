"""
Server-side validation of untrusted label image uploads.

Architectural responsibility: reject empty, oversized, unsupported, or unreadable images
before any preprocessing. Does not trust client-provided MIME types.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings, get_settings
from app.core.exceptions import ImageValidationError
from app.models.image_analysis import ImageFormat, ImageValidationResult
from app.preprocessing.formats import (
    DetectedContentKind,
    pillow_format_to_image_format,
    sniff_content_kind,
    to_supported_image_format,
)

logger = logging.getLogger(__name__)


def validate_image_bytes(
    data: bytes,
    *,
    declared_content_type: str | None = None,
    settings: Settings | None = None,
) -> tuple[ImageValidationResult, Image.Image, ImageFormat]:
    """
    Validate upload bytes and return an opened Pillow image (caller owns lifecycle).

    Raises ImageValidationError with a user-friendly message on failure.
    Logs internal diagnostics separately from the client-facing message.
    """
    cfg = settings or get_settings()

    if not data:
        raise ImageValidationError(
            "The uploaded file is empty. Please choose a JPEG, PNG, or WebP image.",
            code="empty_file",
        )

    size_bytes = len(data)
    if size_bytes > cfg.max_upload_bytes:
        limit_mb = cfg.max_upload_bytes / (1024 * 1024)
        raise ImageValidationError(
            f"This file is too large. Maximum size is {limit_mb:.0f} MB.",
            code="file_too_large",
            details=f"size_bytes={size_bytes} max={cfg.max_upload_bytes}",
        )

    kind = sniff_content_kind(data)
    if kind == DetectedContentKind.PDF:
        raise ImageValidationError(
            "PDF files are not supported yet. Please upload a JPEG, PNG, or WebP image.",
            code="pdf_not_supported",
        )
    sniffed_format = to_supported_image_format(kind)
    if sniffed_format is None:
        logger.info(
            "Rejected upload: unknown magic bytes; declared_content_type=%s size=%s",
            declared_content_type,
            size_bytes,
        )
        raise ImageValidationError(
            "This file type is not supported. Please upload a JPEG, PNG, or WebP image.",
            code="unsupported_format",
        )

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except UnidentifiedImageError as exc:
        logger.info("Rejected upload: Pillow UnidentifiedImageError: %s", exc)
        raise ImageValidationError(
            "This file could not be read as an image. It may be damaged.",
            code="corrupt_image",
            details=str(exc),
        ) from exc
    except OSError as exc:
        logger.info("Rejected upload: OSError while decoding image: %s", exc)
        raise ImageValidationError(
            "This file could not be read as an image. It may be damaged.",
            code="corrupt_image",
            details=str(exc),
        ) from exc

    decoded_format = pillow_format_to_image_format(image.format)
    if decoded_format is None:
        image.close()
        raise ImageValidationError(
            "This file type is not supported. Please upload a JPEG, PNG, or WebP image.",
            code="unsupported_format",
            details=f"pillow_format={image.format!r}",
        )

    if decoded_format != sniffed_format:
        logger.warning(
            "Magic/Pillow format mismatch: sniffed=%s decoded=%s",
            sniffed_format,
            decoded_format,
        )
        image.close()
        raise ImageValidationError(
            "This file's contents do not match a supported image type.",
            code="format_mismatch",
        )

    width, height = image.size
    if width < cfg.min_image_dimension_px or height < cfg.min_image_dimension_px:
        image.close()
        raise ImageValidationError(
            f"This image is too small. Each side must be at least "
            f"{cfg.min_image_dimension_px} pixels.",
            code="dimensions_too_small",
            details=f"width={width} height={height}",
        )
    if width > cfg.max_image_dimension_px or height > cfg.max_image_dimension_px:
        image.close()
        raise ImageValidationError(
            f"This image is too large. Each side must be at most "
            f"{cfg.max_image_dimension_px} pixels.",
            code="dimensions_too_large",
            details=f"width={width} height={height}",
        )

    validation = ImageValidationResult(
        accepted=True,
        detected_format=decoded_format,
        declared_content_type=declared_content_type,
        size_bytes=size_bytes,
        message="Image accepted.",
    )
    return validation, image, decoded_format
