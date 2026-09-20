"""
Build minimal AI evidence packages from verification REVIEW checks.

Architectural responsibility: package OCR/extraction context + image bytes for AiProvider.
Does not call OpenAI.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from PIL import Image

from app.ai.eligibility import CHECK_TO_FIELD, FIELD_TASKS, underlying_eligible_reason
from app.ai.evidence import AiEvidencePackage, AiEvidenceRequestItem
from app.models.extraction import ExtractedField
from app.models.verification import FieldCheckResult
from app.preprocessing.transforms import resize_max_edge


@dataclass
class PreparedAiImage:
    """JPEG bytes prepared for vision input (resized, no secrets)."""

    image_bytes: bytes
    media_type: str = "image/jpeg"
    width_px: int = 0
    height_px: int = 0
    used_crop: bool = False


def build_evidence_package(
    *,
    checks: list[FieldCheckResult],
    fields: dict[str, ExtractedField],
    quality_status: str | None,
    quality_warnings: list[str],
) -> AiEvidencePackage:
    """Assemble request items for eligible checks (no image bytes in the model)."""
    items: list[AiEvidenceRequestItem] = []
    for check in checks:
        field_name = CHECK_TO_FIELD[check.check_name]
        extracted = fields.get(field_name)
        semantic_reason = underlying_eligible_reason(check) or check.reason_code or ""
        items.append(
            AiEvidenceRequestItem(
                field=field_name,
                reason_code=semantic_reason,
                task_instruction=FIELD_TASKS[field_name],
                ocr_text=extracted.raw_text if extracted else check.detected_label_value,
                candidates=list(extracted.candidates) if extracted else [],
                application_value=check.application_value,
                extraction_status=extracted.status.value if extracted else None,
                extraction_explanation=extracted.explanation if extracted else None,
            ),
        )
    return AiEvidencePackage(
        fields=items,
        quality_status=quality_status,
        quality_warnings=quality_warnings,
        uses_full_image=True,
        crop_note="Full label image used when localization is uncertain or multi-field.",
    )


def prepare_vision_image(
    image_bytes: bytes,
    *,
    max_edge_px: int,
    fields: dict[str, ExtractedField] | None = None,
    target_fields: list[str] | None = None,
) -> PreparedAiImage:
    """
    Resize (and optionally crop) the upload for vision cost/latency control.

    Uses a union crop of OCR boxes when all target fields have geometry; otherwise full image.
    """
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        rgb = image.convert("RGB")
        used_crop = False
        working = rgb
        if fields and target_fields:
            crop = _union_crop(rgb, fields, target_fields)
            if crop is not None:
                working = crop
                used_crop = True
        resized, _ = resize_max_edge(working, max_edge_px)
        buffer = io.BytesIO()
        resized.save(buffer, format="JPEG", quality=85, optimize=True)
        return PreparedAiImage(
            image_bytes=buffer.getvalue(),
            media_type="image/jpeg",
            width_px=resized.width,
            height_px=resized.height,
            used_crop=used_crop,
        )


def image_to_data_url(prepared: PreparedAiImage) -> str:
    """Encode prepared image as a data URL for the OpenAI vision API."""
    b64 = base64.b64encode(prepared.image_bytes).decode("ascii")
    return f"data:{prepared.media_type};base64,{b64}"


def _union_crop(
    image: Image.Image,
    fields: dict[str, ExtractedField],
    target_fields: list[str],
) -> Image.Image | None:
    boxes: list[tuple[float, float, float, float]] = []
    for name in target_fields:
        field = fields.get(name)
        if field is None:
            return None
        for region in field.ocr_regions:
            box = region.bounding_box
            if not box:
                continue
            try:
                boxes.append(
                    (
                        float(box["x_min"]),
                        float(box["y_min"]),
                        float(box["x_max"]),
                        float(box["y_max"]),
                    ),
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not any(region.bounding_box for region in field.ocr_regions):
            return None
    if not boxes:
        return None
    pad = 24
    x0 = max(0, int(min(b[0] for b in boxes) - pad))
    y0 = max(0, int(min(b[1] for b in boxes) - pad))
    x1 = min(image.width, int(max(b[2] for b in boxes) + pad))
    y1 = min(image.height, int(max(b[3] for b in boxes) + pad))
    if x1 - x0 < 40 or y1 - y0 < 40:
        return None
    return image.crop((x0, y0, x1, y1))
