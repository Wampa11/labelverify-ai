"""
Phase 8.7.1 service-level AI fallback + brand integrity tests.

Architectural responsibility: prove eligibility → one combined call → merge → re-rules,
and that malformed brand OCR cannot PASS.
"""

from __future__ import annotations

from app.ai.evidence import AiEvidenceConfidence, AiFieldEvidence
from app.ai.null_provider import NullAiProvider
from app.ai.scripted_provider import ScriptedAiProvider
from app.core.config import Settings
from app.extraction.brand_name import extract_brand_name
from app.models.extraction import ExtractionStatus
from app.models.verification import CheckStatus
from app.models.verification_mode import VerificationMode
from app.ocr.base import OcrProvider, OcrResult, OcrWord
from app.rules.regulatory_sources import STATUTORY_GOVERNMENT_WARNING
from app.services.verification_service import VerificationService
from tests.image_fixtures import jpeg_bytes


class ScriptedOcrProvider(OcrProvider):
    def __init__(self, text: str, words: list[OcrWord] | None = None) -> None:
        self._text = text
        self._words = words or []

    @property
    def name(self) -> str:
        return "scripted"

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        assert image_bytes
        return OcrResult(
            full_text=self._text,
            words=list(self._words),
            provider_name=self.name,
            image_width_px=800,
            image_height_px=600,
            preprocessing_profile="fast",
        )


# Artistic-label shaped OCR: partial brand artifact, proof-only, noisy net, missing warning.
DIFFICULT_LABEL = """hispering =
KENTUCKY STRAIGHT BOURBON WHIS...
90 PROOF
ge | 750mL
"""


def test_malformed_brand_with_equals_is_uncertain() -> None:
    words = [
        OcrWord(
            text="hispering",
            confidence=0.7,
            bounding_box={"x_min": 40, "y_min": 20, "x_max": 180, "y_max": 60},
        ),
        OcrWord(
            text="=",
            confidence=0.4,
            bounding_box={"x_min": 185, "y_min": 25, "x_max": 200, "y_max": 55},
        ),
    ]
    field = extract_brand_name(
        OcrResult(
            full_text=DIFFICULT_LABEL,
            words=words,
            provider_name="test",
            image_width_px=800,
            image_height_px=600,
        ),
    )
    assert field.status == ExtractionStatus.UNCERTAIN
    assert "integrity" in (field.ai_fallback_hints.get("reason") or "")


def test_difficult_label_ai_eligible_and_one_combined_call() -> None:
    """Whispering-Pine-shaped extraction must be AI-eligible and invoke one call."""
    ai = ScriptedAiProvider(
        results=[
            AiFieldEvidence(
                field="brand_name",
                candidate_value="CEDAR RIDGE",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Brand line visible",
            ),
            AiFieldEvidence(
                field="class_type",
                candidate_value="KENTUCKY STRAIGHT BOURBON WHISKEY",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Full class line",
            ),
            AiFieldEvidence(
                field="alcohol_content",
                candidate_value="45% ALC./VOL. (90 PROOF)",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="ABV with proof",
            ),
            AiFieldEvidence(
                field="net_contents",
                candidate_value="750 mL",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Volume",
            ),
            AiFieldEvidence(
                field="government_warning",
                candidate_value=STATUTORY_GOVERNMENT_WARNING[:60],
                raw_observed_text=STATUTORY_GOVERNMENT_WARNING,
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="Warning block",
            ),
        ],
    )
    service = VerificationService(
        ocr_provider=ScriptedOcrProvider(DIFFICULT_LABEL),
        ai_provider=ai,
        settings=Settings(
            openai_enabled=True,
            openai_api_key="test-key",
            openai_max_calls_per_review=1,
        ),
    )
    result = service.verify(jpeg_bytes(), application=None, mode=VerificationMode.LABEL_ONLY)
    assist = result.verification.ai_assist or {}

    assert assist.get("ai_eligible") is True
    assert ai.calls == 1
    assert set(assist.get("fields_requested") or []) >= {
        "brand_name",
        "class_type",
        "alcohol_content",
        "net_contents",
        "government_warning",
    }
    assert assist.get("called") is True
    assert assist.get("ai_succeeded") is True
    assert assist.get("outcome") == "evidence_merged"
    assert assist.get("evidence_method") in {"ocr_plus_ai", "ocr_plus_ai_conflict"}
    # AI never directly sets overall — deterministic re-eval after merge.
    assert result.verification.overall_status in {CheckStatus.PASS, CheckStatus.REVIEW}
    brand = next(c for c in result.verification.checks if c.check_name == "Brand Name")
    # Brand should not have PASS'd on "hispering =" before AI; after merge may PASS/REVIEW.
    assert brand.technical_details.get("evidence_method")
    assert "ai_assist_outcome" in (brand.technical_details or {})


def test_difficult_label_ai_disabled_safe_review() -> None:
    ai = NullAiProvider()
    service = VerificationService(
        ocr_provider=ScriptedOcrProvider(DIFFICULT_LABEL),
        ai_provider=ai,
        settings=Settings(openai_enabled=False, openai_api_key=None),
    )
    result = service.verify(jpeg_bytes(), application=None, mode=VerificationMode.LABEL_ONLY)
    assist = result.verification.ai_assist or {}
    assert assist.get("ai_eligible") is True
    assert assist.get("attempted") is True
    assert assist.get("called") is False
    assert assist.get("ai_succeeded") is False
    assert assist.get("failure_category") == "provider_unavailable"
    assert result.verification.overall_status == CheckStatus.REVIEW
    assert result.verification.ai_used is False
    brand = next(c for c in result.verification.checks if c.check_name == "Brand Name")
    assert brand.status == CheckStatus.REVIEW


def test_ai_conflict_remains_review() -> None:
    ai = ScriptedAiProvider(
        results=[
            AiFieldEvidence(
                field="brand_name",
                candidate_value="IRON PEAK",
                confidence=AiEvidenceConfidence.HIGH,
                evidence_description="conflicting brand",
            ),
        ],
    )
    # Warning missing keeps overall REVIEW so AI can run; brand FOUND may conflict if requested.
    label_review = """CEDAR HILLS
Straight Bourbon Whiskey
45% Alc./Vol.
750 mL
"""
    service = VerificationService(
        ocr_provider=ScriptedOcrProvider(label_review),
        ai_provider=ai,
        settings=Settings(openai_enabled=True, openai_api_key="test-key"),
    )
    result = service.verify(jpeg_bytes(), application=None, mode=VerificationMode.LABEL_ONLY)
    assert result.verification.overall_status == CheckStatus.REVIEW
    assist = result.verification.ai_assist or {}
    assert assist.get("ai_eligible") is True
    if "brand_name" in (assist.get("fields_updated") or []):
        brand = next(c for c in result.verification.checks if c.check_name == "Brand Name")
        assert brand.status == CheckStatus.REVIEW


def test_openai_health_exposes_fallback_without_key() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    payload = client.get("/health").json()
    assert "openai_fallback" in payload
    assert "openai_configured" in payload
    assert "api_key" not in str(payload).lower() or "api_key_present" in payload.get(
        "openai_fallback",
        "",
    )
    # Key material must never appear.
    assert "sk-" not in str(payload)
