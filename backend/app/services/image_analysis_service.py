"""
Image analysis orchestration for upload → validate → preprocess → quality.

Architectural responsibility: coordinate preprocessing package stages for the API
without OCR, rules, or persistence of uploaded bytes.
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import Settings, get_settings
from app.core.timing import PipelineTimer
from app.models.image_analysis import ImageAnalysisResponse, ImageMetadata
from app.preprocessing.pipeline import ImagePreprocessPipeline
from app.preprocessing.validation import validate_image_bytes

logger = logging.getLogger(__name__)


class ImageAnalysisService:
    """Analyzes a single uploaded label image in memory for the current request."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        pipeline: ImagePreprocessPipeline | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._pipeline = pipeline or ImagePreprocessPipeline(self._settings)

    def analyze(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        declared_content_type: str | None = None,
    ) -> ImageAnalysisResponse:
        """
        Validate and preprocess upload bytes; return analysis without filesystem paths.

        Uploaded content is not written to disk. analysis_id is ephemeral for the workflow.
        """
        timer = PipelineTimer()
        timer.start()
        analysis_id = str(uuid.uuid4())

        with timer.stage("validation"):
            validation, image, detected_format = validate_image_bytes(
                data,
                declared_content_type=declared_content_type,
                settings=self._settings,
            )

        try:
            with timer.stage("preprocessing"):
                artifacts = self._pipeline.run(image)
        finally:
            image.close()

        stage_timings = {item.label: item.elapsed_ms for item in timer.stages}
        processing_time_ms = timer.stop_overall_ms()

        logger.info(
            "image_analysis_complete analysis_id=%s format=%s size_bytes=%s "
            "quality=%s processing_time_ms=%.2f",
            analysis_id,
            detected_format,
            validation.size_bytes,
            artifacts.quality.status,
            processing_time_ms,
        )

        metadata = ImageMetadata(
            original_filename=filename,
            format=detected_format,
            width_px=artifacts.display_width,
            height_px=artifacts.display_height,
            mode="RGB",
            size_bytes=validation.size_bytes,
            exif_orientation_applied=artifacts.exif_orientation_applied,
        )

        return ImageAnalysisResponse(
            analysis_id=analysis_id,
            validation=validation,
            metadata=metadata,
            quality=artifacts.quality,
            preprocessing=artifacts.preprocessing,
            display_image_base64=artifacts.display_base64,
            display_media_type=artifacts.display_media_type,
            ocr_image_base64=artifacts.ocr_base64,
            ocr_media_type=artifacts.ocr_media_type,
            processing_time_ms=processing_time_ms,
            stage_timings_ms=stage_timings,
        )
