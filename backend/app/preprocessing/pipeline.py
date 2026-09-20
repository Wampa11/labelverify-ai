"""
Image preprocessing pipeline for display and OCR-prepared representations.

Architectural responsibility: orchestrate validation outputs into dual non-destructive
representations for UI preview and downstream OCR — without running OCR itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from app.core.config import Settings, get_settings
from app.models.image_analysis import (
    ImageQualityAssessment,
    PreprocessingOperation,
    PreprocessingSummary,
)
from app.preprocessing.geometry import maybe_deskew, plan_perspective_correction
from app.preprocessing.orientation import apply_exif_orientation
from app.preprocessing.quality import assess_image_quality
from app.preprocessing.transforms import (
    apply_clahe,
    encode_jpeg_base64,
    encode_png_gray_base64,
    mild_denoise,
    mild_unsharp,
    resize_max_edge,
    to_grayscale_array,
    to_rgb,
)


@dataclass
class PreprocessArtifacts:
    """In-memory outputs of preprocessing for one upload (never written to disk)."""

    display_rgb: Image.Image
    display_base64: str
    display_media_type: str
    ocr_gray: object  # np.ndarray; kept generic at boundary to avoid tight coupling in dataclass
    ocr_base64: str
    ocr_media_type: str
    exif_orientation_applied: bool
    preprocessing: PreprocessingSummary
    quality: ImageQualityAssessment
    display_width: int
    display_height: int


class ImagePreprocessPipeline:
    """Builds display + OCR representations and quality assessment from a Pillow image."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def run(self, image: Image.Image) -> PreprocessArtifacts:
        """
        Produce dual representations and quality assessment.

        The caller's original upload bytes are not modified; this works on a decoded image.
        Display path: EXIF orientation → RGB → optional max-edge resize for transfer.
        OCR path: copy of oriented RGB → resize → grayscale → CLAHE → mild denoise →
        optional deskew → mild unsharp.
        """
        operations: list[PreprocessingOperation] = []

        oriented, orientation_changed = apply_exif_orientation(image)
        operations.append(
            PreprocessingOperation(
                name="exif_orientation",
                applied=orientation_changed,
                detail=(
                    "Applied EXIF orientation tag"
                    if orientation_changed
                    else "No orientation correction needed"
                ),
            ),
        )

        rgb = to_rgb(oriented)
        operations.append(
            PreprocessingOperation(
                name="convert_rgb",
                applied=True,
                detail="Converted to RGB (alpha composited on white when present)",
            ),
        )

        display_rgb, display_resized = resize_max_edge(
            rgb,
            self._settings.display_max_edge_px,
        )
        operations.append(
            PreprocessingOperation(
                name="display_max_edge_resize",
                applied=display_resized,
                detail=(
                    f"Display image longest edge limited to "
                    f"{self._settings.display_max_edge_px}px for transfer"
                    if display_resized
                    else "Display image within max edge; no resize"
                ),
            ),
        )

        display_b64, display_media = encode_jpeg_base64(display_rgb)

        ocr_rgb, ocr_resized = resize_max_edge(rgb, self._settings.ocr_preview_max_edge_px)
        operations.append(
            PreprocessingOperation(
                name="ocr_max_edge_resize",
                applied=ocr_resized,
                detail=(
                    f"OCR image longest edge limited to {self._settings.ocr_preview_max_edge_px}px"
                    if ocr_resized
                    else "OCR image within max edge; no resize"
                ),
            ),
        )

        gray = to_grayscale_array(ocr_rgb)
        operations.append(
            PreprocessingOperation(
                name="grayscale",
                applied=True,
                detail="Converted OCR path to 8-bit grayscale",
            ),
        )

        # Quality on oriented, resized grayscale before enhancement — reflects capture quality.
        quality = assess_image_quality(
            gray,
            width_px=display_rgb.size[0],
            height_px=display_rgb.size[1],
        )

        gray = apply_clahe(gray)
        operations.append(
            PreprocessingOperation(
                name="clahe_contrast",
                applied=True,
                detail="Applied contrast-limited adaptive histogram equalization (clipLimit=2.0)",
            ),
        )

        gray = mild_denoise(gray)
        operations.append(
            PreprocessingOperation(
                name="mild_denoise",
                applied=True,
                detail="Applied light non-local means denoising (h=6)",
            ),
        )

        perspective = plan_perspective_correction()
        operations.append(
            PreprocessingOperation(
                name="perspective_correction",
                applied=False,
                detail=perspective.reason,
            ),
        )

        deskew = maybe_deskew(gray)
        if deskew.applied and deskew.corrected_gray is not None:
            gray = deskew.corrected_gray
            operations.append(
                PreprocessingOperation(
                    name="deskew",
                    applied=True,
                    detail=f"Rotated by {deskew.angle_degrees:.2f} degrees",
                ),
            )
        else:
            operations.append(
                PreprocessingOperation(
                    name="deskew",
                    applied=False,
                    detail=deskew.skipped_reason or "deskew_not_applied",
                ),
            )

        gray = mild_unsharp(gray)
        operations.append(
            PreprocessingOperation(
                name="mild_unsharp",
                applied=True,
                detail="Applied mild unsharp mask (amount=0.4)",
            ),
        )

        ocr_b64, ocr_media = encode_png_gray_base64(gray)

        summary = PreprocessingSummary(
            operations=operations,
            deskew_applied=deskew.applied,
            deskew_angle_degrees=deskew.angle_degrees,
            deskew_skipped_reason=None if deskew.applied else deskew.skipped_reason,
        )

        return PreprocessArtifacts(
            display_rgb=display_rgb,
            display_base64=display_b64,
            display_media_type=display_media,
            ocr_gray=gray,
            ocr_base64=ocr_b64,
            ocr_media_type=ocr_media,
            exif_orientation_applied=orientation_changed,
            preprocessing=summary,
            quality=quality,
            display_width=display_rgb.size[0],
            display_height=display_rgb.size[1],
        )
