"""
EasyOCR adapter (evaluation / optional escalation only).

Architectural responsibility: wrap EasyOCR behind OcrProvider without leaking
torch/EasyOCR types into rules or VerificationService. Not wired as production default.
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


class EasyOcrProvider(OcrProvider):
    """Local EasyOCR (CPU). Heavy optional dependency for evaluation spikes."""

    def __init__(self, *, languages: list[str] | None = None, gpu: bool = False) -> None:
        self._languages = languages or ["en"]
        self._gpu = gpu
        self._reader = None
        self._init_time_ms: float | None = None

    @property
    def name(self) -> str:
        return "easyocr"

    @property
    def init_time_ms(self) -> float | None:
        """Wall-clock time of first engine construction, if measured."""
        return self._init_time_ms

    def is_available(self) -> bool:
        try:
            import easyocr  # noqa: F401

            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("EasyOCR unavailable: %s", exc)
            return False

    def _ensure_reader(self) -> object:
        if self._reader is not None:
            return self._reader
        try:
            import easyocr
        except ImportError as exc:
            raise OcrProviderError(
                "easyocr is not installed. Install optional ocr-easyocr extras.",
                provider_name=self.name,
                code="dependency_missing",
                details=str(exc),
            ) from exc
        start = time.perf_counter()
        try:
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu, verbose=False)
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(
                "Failed to initialize EasyOCR",
                provider_name=self.name,
                code="init_error",
                details=str(exc),
            ) from exc
        self._init_time_ms = (time.perf_counter() - start) * 1000
        return self._reader

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        if not image_bytes:
            raise OcrProviderError(
                "Cannot run EasyOCR on empty image bytes",
                provider_name=self.name,
                code="empty_image",
            )
        reader = self._ensure_reader()
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                rgb = image.convert("RGB")
                width, height = rgb.size
                array = np.asarray(rgb)
                start = time.perf_counter()
                raw = reader.readtext(array)
                elapsed_ms = (time.perf_counter() - start) * 1000
        except OcrProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(
                "EasyOCR failed to process the image",
                provider_name=self.name,
                code="engine_error",
                details=str(exc),
            ) from exc

        words: list[OcrWord] = []
        lines: list[str] = []
        for item in raw or []:
            if not item or len(item) < 2:
                continue
            box_pts, text, conf = item[0], item[1], item[2] if len(item) > 2 else None
            text = (text or "").strip()
            if not text:
                continue
            lines.append(text)
            xs = [float(p[0]) for p in box_pts]
            ys = [float(p[1]) for p in box_pts]
            box = BoundingBox(x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))
            confidence = None
            if conf is not None:
                confidence = max(0.0, min(1.0, float(conf)))
            words.append(
                OcrWord(
                    text=text,
                    confidence=confidence,
                    bounding_box=box.as_dict(),
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
                "EasyOCR confidence is engine-native [0,1]. Not comparable to Tesseract."
            ),
            raw_metadata={
                "languages": self._languages,
                "gpu": self._gpu,
                "init_time_ms": self._init_time_ms,
                "line_count": len(lines),
            },
        )
