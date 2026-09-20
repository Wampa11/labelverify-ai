"""
OCR evaluation runner: execute provider × preprocess × resolution matrix.

Architectural responsibility: collect measurable results for engine selection.
Never silently converts OCR failures into success.
"""

from __future__ import annotations

import platform
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.ocr.base import OcrProvider
from app.ocr.errors import OcrProviderError
from app.ocr.evaluate.ground_truth import FixtureGroundTruth, load_corpus_manifest
from app.ocr.evaluate.metrics import (
    character_error_rate,
    reference_full_text,
    score_compliance_fields,
)
from app.ocr.factory import create_ocr_provider
from app.preprocessing.ocr_prepare import OcrPreprocessProfile, prepare_for_ocr_from_bytes


@dataclass
class RunRecord:
    """One OCR evaluation trial."""

    fixture_id: str
    category: str
    provider: str
    preprocess_profile: str
    max_edge_px: int
    success: bool
    failure_kind: str | None
    failure_message: str | None
    preprocessing_time_ms: float
    ocr_time_ms: float | None
    total_pipeline_time_ms: float
    character_error_rate: float | None
    field_recovery: dict[str, bool]
    fields_recovered_count: int
    fields_total: int
    has_bounding_boxes: bool
    word_count: int
    ocr_text_preview: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class EvaluationReport:
    """Full evaluation output payload."""

    generated_at: str
    environment: dict[str, str]
    providers_requested: list[str]
    providers_available: list[str]
    providers_unavailable: dict[str, str]
    preprocess_profiles: list[str]
    max_edge_sizes: list[int]
    records: list[RunRecord]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "environment": self.environment,
            "providers_requested": self.providers_requested,
            "providers_available": self.providers_available,
            "providers_unavailable": self.providers_unavailable,
            "preprocess_profiles": self.preprocess_profiles,
            "max_edge_sizes": self.max_edge_sizes,
            "records": [asdict(r) for r in self.records],
        }


def run_evaluation(
    corpus_dir: Path,
    *,
    providers: list[str] | None = None,
    profiles: list[OcrPreprocessProfile] | None = None,
    max_edges: list[int] | None = None,
) -> EvaluationReport:
    """Run the evaluation matrix and return a structured report."""
    fixtures = load_corpus_manifest(corpus_dir)
    provider_names = providers or ["tesseract", "paddleocr"]
    profiles = profiles or [OcrPreprocessProfile.FAST, OcrPreprocessProfile.ENHANCED]
    max_edges = max_edges or [1200, 1600, 2200]

    available: list[str] = []
    unavailable: dict[str, str] = {}
    provider_map: dict[str, OcrProvider] = {}
    for name in provider_names:
        try:
            provider = create_ocr_provider(name)
            if provider.is_available():
                available.append(provider.name)
                provider_map[provider.name] = provider
            else:
                unavailable[name] = "is_available() returned False"
        except Exception as exc:  # noqa: BLE001
            unavailable[name] = str(exc)

    records: list[RunRecord] = []
    for fixture in fixtures:
        image_path = corpus_dir / "fixtures" / fixture.image_file
        image_bytes = image_path.read_bytes()
        for _provider_name, provider in provider_map.items():
            for profile in profiles:
                for max_edge in max_edges:
                    records.append(
                        _run_one(
                            fixture,
                            image_bytes,
                            provider,
                            profile,
                            max_edge,
                        ),
                    )

    return EvaluationReport(
        generated_at=datetime.now(UTC).isoformat(),
        environment={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        providers_requested=provider_names,
        providers_available=available,
        providers_unavailable=unavailable,
        preprocess_profiles=[p.value for p in profiles],
        max_edge_sizes=max_edges,
        records=records,
    )


def _run_one(
    fixture: FixtureGroundTruth,
    image_bytes: bytes,
    provider: OcrProvider,
    profile: OcrPreprocessProfile,
    max_edge: int,
) -> RunRecord:
    fields_total = 5
    empty_fields = {
        "brand_name": False,
        "class_type": False,
        "alcohol_content_abv": False,
        "net_contents": False,
        "government_health_warning": False,
    }

    prep_start = time.perf_counter()
    try:
        prepared = prepare_for_ocr_from_bytes(
            image_bytes,
            profile=profile,
            max_edge_px=max_edge,
        )
    except Exception as exc:  # noqa: BLE001
        prep_ms = (time.perf_counter() - prep_start) * 1000
        return RunRecord(
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            provider=provider.name,
            preprocess_profile=profile.value,
            max_edge_px=max_edge,
            success=False,
            failure_kind="preprocess_error",
            failure_message=str(exc),
            preprocessing_time_ms=prep_ms,
            ocr_time_ms=None,
            total_pipeline_time_ms=prep_ms,
            character_error_rate=None,
            field_recovery=empty_fields,
            fields_recovered_count=0,
            fields_total=fields_total,
            has_bounding_boxes=False,
            word_count=0,
            ocr_text_preview="",
            warnings=[],
        )
    prep_ms = (time.perf_counter() - prep_start) * 1000

    try:
        result = provider.extract_text(prepared.image_bytes)
        result.preprocessing_profile = profile.value
        ocr_ms = float(result.processing_time_ms or 0.0)
        total_ms = prep_ms + ocr_ms
        if not result.has_text:
            return RunRecord(
                fixture_id=fixture.fixture_id,
                category=fixture.category,
                provider=provider.name,
                preprocess_profile=profile.value,
                max_edge_px=max_edge,
                success=False,
                failure_kind="no_text",
                failure_message="OCR returned no text",
                preprocessing_time_ms=prep_ms,
                ocr_time_ms=ocr_ms,
                total_pipeline_time_ms=total_ms,
                character_error_rate=1.0,
                field_recovery=empty_fields,
                fields_recovered_count=0,
                fields_total=fields_total,
                has_bounding_boxes=result.has_bounding_boxes,
                word_count=len(result.words),
                ocr_text_preview="",
                warnings=list(result.warnings),
            )

        field_recovery = score_compliance_fields(result.full_text, fixture)
        recovered = sum(1 for ok in field_recovery.values() if ok)
        cer = character_error_rate(reference_full_text(fixture), result.full_text)
        return RunRecord(
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            provider=provider.name,
            preprocess_profile=profile.value,
            max_edge_px=max_edge,
            success=True,
            failure_kind=None,
            failure_message=None,
            preprocessing_time_ms=prep_ms,
            ocr_time_ms=ocr_ms,
            total_pipeline_time_ms=total_ms,
            character_error_rate=cer,
            field_recovery=field_recovery,
            fields_recovered_count=recovered,
            fields_total=fields_total,
            has_bounding_boxes=result.has_bounding_boxes,
            word_count=len(result.words),
            ocr_text_preview=result.full_text[:500],
            warnings=list(result.warnings),
        )
    except OcrProviderError as exc:
        ocr_ms = None
        total_ms = prep_ms
        return RunRecord(
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            provider=provider.name,
            preprocess_profile=profile.value,
            max_edge_px=max_edge,
            success=False,
            failure_kind=exc.code,
            failure_message=exc.message,
            preprocessing_time_ms=prep_ms,
            ocr_time_ms=ocr_ms,
            total_pipeline_time_ms=total_ms,
            character_error_rate=None,
            field_recovery=empty_fields,
            fields_recovered_count=0,
            fields_total=fields_total,
            has_bounding_boxes=False,
            word_count=0,
            ocr_text_preview="",
            warnings=[],
        )
    except Exception as exc:  # noqa: BLE001
        return RunRecord(
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            provider=provider.name,
            preprocess_profile=profile.value,
            max_edge_px=max_edge,
            success=False,
            failure_kind="engine_exception",
            failure_message=f"{exc}\n{traceback.format_exc(limit=2)}",
            preprocessing_time_ms=prep_ms,
            ocr_time_ms=None,
            total_pipeline_time_ms=prep_ms,
            character_error_rate=None,
            field_recovery=empty_fields,
            fields_recovered_count=0,
            fields_total=fields_total,
            has_bounding_boxes=False,
            word_count=0,
            ocr_text_preview="",
            warnings=[],
        )
