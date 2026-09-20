"""
PaddleOCR adapter.

Architectural responsibility: wrap PaddleOCR behind OcrProvider without leaking
Paddle APIs into business logic.
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


class PaddleOcrProvider(OcrProvider):
    """Local PaddleOCR engine (CPU by default for prototype evaluation)."""

    def __init__(self, *, use_angle_cls: bool = True, lang: str = "en") -> None:
        self._use_angle_cls = use_angle_cls
        self._lang = lang
        self._engine = None

    @property
    def name(self) -> str:
        return "paddleocr"

    def is_available(self) -> bool:
        try:
            self._ensure_engine()
            import numpy as np

            probe = np.zeros((64, 64, 3), dtype=np.uint8)
            probe[:] = 255
            # Smoke-test inference: init alone is insufficient on some Windows builds.
            try:
                self._engine.ocr(probe, cls=False)
            except TypeError:
                self._engine.ocr(probe)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("PaddleOCR unavailable: %s", exc)
            return False

    def _ensure_engine(self) -> object:
        if self._engine is not None:
            return self._engine
        try:
            import os

            # Windows + recent paddlepaddle can fail OneDNN fused_conv2d; disable MKLDNN.
            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrProviderError(
                "paddleocr is not installed. Install optional ocr-paddle extras.",
                provider_name=self.name,
                code="dependency_missing",
                details=str(exc),
            ) from exc
        try:
            self._engine = PaddleOCR(
                use_angle_cls=self._use_angle_cls,
                lang=self._lang,
                use_gpu=False,
                show_log=False,
                enable_mkldnn=False,
            )
        except TypeError:
            self._engine = PaddleOCR(lang=self._lang)
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(
                "Failed to initialize PaddleOCR",
                provider_name=self.name,
                code="init_failed",
                details=str(exc),
            ) from exc
        return self._engine

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        """Run PaddleOCR and map detections into the shared contract."""
        if not image_bytes:
            raise OcrProviderError(
                "Cannot run PaddleOCR on empty image bytes",
                provider_name=self.name,
                code="empty_image",
            )

        engine = self._ensure_engine()

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                width, height = image.size
                rgb = np.asarray(image.convert("RGB"))
            start = time.perf_counter()
            try:
                raw = engine.ocr(rgb, cls=self._use_angle_cls)
            except TypeError:
                raw = engine.ocr(rgb)
            elapsed_ms = (time.perf_counter() - start) * 1000
        except OcrProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(
                "PaddleOCR failed to process the image",
                provider_name=self.name,
                code="engine_error",
                details=str(exc),
            ) from exc

        words: list[OcrWord] = []
        lines: list[str] = []
        pages = raw if raw is not None else []
        for page in pages:
            if not page:
                continue
            for item in page:
                try:
                    box_points, text_info = item
                    text, score = text_info
                except (TypeError, ValueError):
                    continue
                text = (text or "").strip()
                if not text:
                    continue
                lines.append(text)
                polygon = [[float(p[0]), float(p[1])] for p in box_points]
                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                box = BoundingBox(
                    x_min=min(xs),
                    y_min=min(ys),
                    x_max=max(xs),
                    y_max=max(ys),
                )
                confidence = None
                if score is not None:
                    confidence = max(0.0, min(1.0, float(score)))
                words.append(
                    OcrWord(
                        text=text,
                        confidence=confidence,
                        bounding_box=box.as_dict(),
                        polygon=polygon,
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
                "PaddleOCR line/detection scores are engine-native probabilities. "
                "Not comparable to Tesseract confidence."
            ),
            raw_metadata={"lang": self._lang, "line_count": len(words)},
        )
