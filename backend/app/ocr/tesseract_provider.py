"""
Tesseract OCR adapter.

Architectural responsibility: wrap pytesseract behind OcrProvider without leaking
Tesseract APIs into business logic.
"""

from __future__ import annotations

import io
import logging
import time

from PIL import Image

from app.ocr.base import BoundingBox, OcrProvider, OcrResult, OcrWord
from app.ocr.errors import OcrProviderError

logger = logging.getLogger(__name__)


class TesseractOcrProvider(OcrProvider):
    """Local Tesseract OCR via pytesseract."""

    def __init__(
        self,
        *,
        language: str = "eng",
        tesseract_cmd: str | None = None,
        config: str = "",
        provider_name: str | None = None,
    ) -> None:
        self._language = language
        self._tesseract_cmd = tesseract_cmd or self._detect_tesseract_cmd()
        # Production uses empty config (Tesseract defaults). Eval may pass --psm etc.
        self._config = config
        self._provider_name = provider_name or "tesseract"

    @staticmethod
    def _detect_tesseract_cmd() -> str | None:
        """Locate tesseract on PATH or common Windows install locations."""
        import os
        import shutil

        found = shutil.which("tesseract")
        if found:
            return found
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    @property
    def name(self) -> str:
        return self._provider_name

    def is_available(self) -> bool:
        try:
            import pytesseract

            if self._tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
            pytesseract.get_tesseract_version()
            return True
        except Exception as exc:  # noqa: BLE001 — availability probe must not raise
            logger.info("Tesseract unavailable: %s", exc)
            return False

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        """Run Tesseract and map word boxes/confidences into the shared contract."""
        if not image_bytes:
            raise OcrProviderError(
                "Cannot run Tesseract on empty image bytes",
                provider_name=self.name,
                code="empty_image",
            )
        try:
            import pytesseract
        except ImportError as exc:
            raise OcrProviderError(
                "pytesseract is not installed. Install optional ocr-tesseract extras.",
                provider_name=self.name,
                code="dependency_missing",
                details=str(exc),
            ) from exc

        if self._tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                width, height = image.size
                start = time.perf_counter()
                data = pytesseract.image_to_data(
                    image,
                    lang=self._language,
                    config=self._config,
                    output_type=pytesseract.Output.DICT,
                )
                full_text = pytesseract.image_to_string(
                    image,
                    lang=self._language,
                    config=self._config,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrProviderError(
                "Tesseract binary not found. Install Tesseract OCR on the host.",
                provider_name=self.name,
                code="binary_missing",
                details=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001 — wrap engine failures observably
            raise OcrProviderError(
                "Tesseract failed to process the image",
                provider_name=self.name,
                code="engine_error",
                details=str(exc),
            ) from exc

        words: list[OcrWord] = []
        n_boxes = len(data.get("text", []))
        for index in range(n_boxes):
            text = (data["text"][index] or "").strip()
            if not text:
                continue
            conf_raw = float(data["conf"][index])
            # Tesseract uses -1 for non-word rows; omit rather than invent.
            confidence = None if conf_raw < 0 else max(0.0, min(1.0, conf_raw / 100.0))
            left = float(data["left"][index])
            top = float(data["top"][index])
            width_box = float(data["width"][index])
            height_box = float(data["height"][index])
            box = BoundingBox(
                x_min=left,
                y_min=top,
                x_max=left + width_box,
                y_max=top + height_box,
            )
            words.append(
                OcrWord(
                    text=text,
                    confidence=confidence,
                    bounding_box=box.as_dict(),
                ),
            )

        return OcrResult(
            full_text=full_text.strip(),
            words=words,
            provider_name=self.name,
            image_width_px=width,
            image_height_px=height,
            processing_time_ms=elapsed_ms,
            confidence_scale_notes=(
                "Tesseract word confidence is engine-native 0–100 scaled to 0–1. "
                "Not comparable to PaddleOCR confidence."
            ),
            raw_metadata={
                "language": self._language,
                "word_count": len(words),
                "tesseract_config": self._config or "(default)",
            },
        )
