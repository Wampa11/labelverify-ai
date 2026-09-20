"""
RapidOCR (ONNX Runtime) adapter (evaluation / optional escalation only).

Architectural responsibility: wrap RapidOCR behind OcrProvider without leaking
ONNX/RapidOCR types into rules or VerificationService. Not production default.
"""

from __future__ import annotations

import io
import logging
import time

import numpy as np
from PIL import Image

from app.ocr.base import BoundingBox, OcrProvider, OcrResult, OcrWord
from app.ocr.errors import OcrProviderError

logger = logging.getLogger(__name__)


class RapidOcrProvider(OcrProvider):
    """Local RapidOCR via ONNX Runtime (CPU). Optional evaluation dependency."""

    def __init__(self) -> None:
        self._engine = None
        self._init_time_ms: float | None = None

    @property
    def name(self) -> str:
        return "rapidocr"

    @property
    def init_time_ms(self) -> float | None:
        return self._init_time_ms

    def is_available(self) -> bool:
        try:
            import onnxruntime  # noqa: F401
            import rapidocr  # noqa: F401

            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("RapidOCR unavailable: %s", exc)
            return False

    def _ensure_engine(self) -> object:
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise OcrProviderError(
                "rapidocr is not installed. Install optional ocr-rapidocr extras.",
                provider_name=self.name,
                code="dependency_missing",
                details=str(exc),
            ) from exc
        start = time.perf_counter()
        try:
            self._engine = RapidOCR()
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(
                "Failed to initialize RapidOCR",
                provider_name=self.name,
                code="init_error",
                details=str(exc),
            ) from exc
        self._init_time_ms = (time.perf_counter() - start) * 1000
        return self._engine

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        if not image_bytes:
            raise OcrProviderError(
                "Cannot run RapidOCR on empty image bytes",
                provider_name=self.name,
                code="empty_image",
            )
        engine = self._ensure_engine()
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                # RapidOCR ONNX detectors expect 3-channel input; FAST prep is grayscale.
                rgb = image.convert("RGB")
                width, height = rgb.size
                array = np.asarray(rgb)
                start = time.perf_counter()
                result = engine(array)
                elapsed_ms = (time.perf_counter() - start) * 1000
        except OcrProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(
                "RapidOCR failed to process the image",
                provider_name=self.name,
                code="engine_error",
                details=str(exc),
            ) from exc

        words: list[OcrWord] = []
        lines: list[str] = []
        # rapidocr>=3 returns an object with .boxes/.txts/.scores; older returns list.
        boxes, texts, scores = _unpack_rapidocr_result(result)
        for box_pts, text, score in zip(boxes, texts, scores, strict=False):
            text = (text or "").strip()
            if not text:
                continue
            lines.append(text)
            xs = [float(p[0]) for p in box_pts]
            ys = [float(p[1]) for p in box_pts]
            bbox = BoundingBox(x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))
            confidence = None if score is None else max(0.0, min(1.0, float(score)))
            words.append(
                OcrWord(
                    text=text,
                    confidence=confidence,
                    bounding_box=bbox.as_dict(),
                    polygon=[[float(p[0]), float(p[1])] for p in box_pts],
                ),
            )

        return OcrResult(
            full_text="\n".join(lines).strip(),
            words=words,
            provider_name=self.name,
            image_width_px=width,
            image_height_px=height,
            processing_time_ms=elapsed_ms,
            confidence_scale_notes=(
                "RapidOCR confidence is engine-native [0,1]. Not comparable to Tesseract."
            ),
            raw_metadata={
                "init_time_ms": self._init_time_ms,
                "line_count": len(lines),
            },
        )


def _unpack_rapidocr_result(result: object) -> tuple[list, list, list]:
    """Normalize RapidOCR v2 list results and v3 object results."""
    if result is None:
        return [], [], []
    if hasattr(result, "txts") and hasattr(result, "boxes"):
        texts_raw = getattr(result, "txts", None)
        boxes_raw = getattr(result, "boxes", None)
        scores_raw = getattr(result, "scores", None)
        texts = list(texts_raw) if texts_raw is not None else []
        if boxes_raw is None:
            boxes = []
        elif hasattr(boxes_raw, "tolist"):
            boxes = list(boxes_raw)
        else:
            boxes = list(boxes_raw)
        if scores_raw is None:
            scores = [None] * len(texts)
        elif hasattr(scores_raw, "tolist"):
            scores = list(scores_raw)
        else:
            scores = list(scores_raw)
        return boxes, texts, scores
    # Legacy: list of [box, text, score]
    if isinstance(result, (list, tuple)):
        # Some versions return (result, elapse) where result is list-like.
        if (
            len(result) >= 1
            and not isinstance(result[0], (list, tuple))
            and hasattr(result[0], "txts")
        ):
            return _unpack_rapidocr_result(result[0])
        boxes, texts, scores = [], [], []
        for item in result:
            if not item or len(item) < 2:
                continue
            boxes.append(item[0])
            texts.append(item[1])
            scores.append(item[2] if len(item) > 2 else None)
        return boxes, texts, scores
    return [], [], []
