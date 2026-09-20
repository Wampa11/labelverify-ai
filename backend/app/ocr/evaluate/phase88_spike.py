"""
Phase 8.8 decorative typography OCR evaluation spike.

Architectural responsibility: measure local OCR alternatives, Tesseract PSM
variants, and region-based OCR without changing production VerificationService.

Usage (from backend/ with .venv-ocr):

    python -m app.ocr.evaluate.phase88_spike
"""

from __future__ import annotations

import io
import json
import platform
import statistics
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from app.ocr.base import OcrProvider, OcrResult
from app.ocr.evaluate.corpus import default_corpus_root
from app.ocr.evaluate.ground_truth import FixtureGroundTruth, load_corpus_manifest
from app.ocr.evaluate.metrics import (
    brand_exact_recovered,
    brand_normalized_recovered,
    character_error_rate,
    reference_full_text,
    score_compliance_fields,
)
from app.ocr.factory import create_ocr_provider
from app.ocr.tesseract_provider import TesseractOcrProvider
from app.preprocessing.ocr_prepare import OcrPreprocessProfile, prepare_for_ocr_from_bytes

DECORATIVE_IDS = ("decorative_maple_creek", "decorative_whispering_pine")

# Limited Tesseract layout variants (production config remains empty/default).
TESSERACT_CONFIG_VARIANTS: list[tuple[str, str]] = [
    ("default", ""),
    ("psm3_auto", "--psm 3"),
    ("psm6_block", "--psm 6"),
    ("psm7_line", "--psm 7"),
    ("psm11_sparse", "--psm 11"),
    ("psm12_sparse_osd", "--psm 12"),
]


@dataclass
class SpikeTrial:
    """One measured OCR trial for the Phase 8.8 spike."""

    experiment: str
    fixture_id: str
    category: str
    provider: str
    variant: str
    preprocess_profile: str
    max_edge_px: int
    success: bool
    failure_kind: str | None
    failure_message: str | None
    preprocess_ms: float
    ocr_ms: float | None
    total_ms: float
    brand_exact: bool
    brand_normalized: bool
    field_recovery: dict[str, bool]
    fields_recovered_count: int
    character_error_rate: float | None
    word_count: int
    ocr_full_text: str
    brand_region_preview: str
    init_time_ms: float | None = None
    rss_mb_after: float | None = None
    notes: list[str] = field(default_factory=list)


def _rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def _brand_region_preview(ocr: OcrResult, expected_brand: str, *, max_chars: int = 400) -> str:
    """Heuristic excerpt: lines overlapping expected tokens or top/large words."""
    text = ocr.full_text or ""
    tokens = [t for t in expected_brand.split() if t]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = [
        ln
        for ln in lines
        if any(tok.casefold() in ln.casefold() for tok in tokens)
        or any(tok[:4].casefold() in ln.casefold() for tok in tokens if len(tok) >= 4)
    ]
    if hits:
        return "\n".join(hits)[:max_chars]
    # Fall back to top-of-image words by bbox.
    topped = []
    for word in ocr.words:
        box = word.bounding_box or {}
        topped.append((float(box.get("y_min") or 0), float(box.get("x_min") or 0), word.text))
    topped.sort()
    preview = " ".join(t for _, __, t in topped[:12])
    return (preview or text[:max_chars])[:max_chars]


def _crop_upper_region(image_bytes: bytes, *, top_fraction: float = 0.45) -> bytes:
    """Crop the upper portion of the label (general heuristic, no fixture coords)."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        width, height = image.size
        crop = image.crop((0, 0, width, max(1, int(height * top_fraction))))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        return buf.getvalue()


def _crop_prominent_band(image_bytes: bytes, ocr: OcrResult) -> bytes | None:
    """
    Crop a band around the tallest OCR words in the upper half.

    Uses first-pass boxes only — no fixture-specific coordinates.
    """
    if not ocr.words or not ocr.image_height_px:
        return None
    height = float(ocr.image_height_px)
    width = float(ocr.image_width_px or 1)
    candidates = []
    for word in ocr.words:
        box = word.bounding_box
        if not box:
            continue
        y_min = float(box["y_min"])
        y_max = float(box["y_max"])
        x_min = float(box["x_min"])
        x_max = float(box["x_max"])
        if y_min > height * 0.55:
            continue
        h = max(1.0, y_max - y_min)
        candidates.append((h, x_min, y_min, x_max, y_max, word.text))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    top = candidates[: min(4, len(candidates))]
    x0 = max(0.0, min(t[1] for t in top) - 12)
    y0 = max(0.0, min(t[2] for t in top) - 12)
    x1 = min(width, max(t[3] for t in top) + 12)
    y1 = min(height, max(t[4] for t in top) + 12)
    if x1 - x0 < 20 or y1 - y0 < 12:
        return None
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        crop = image.crop((int(x0), int(y0), int(x1), int(y1)))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        return buf.getvalue()


def _run_trial(
    *,
    experiment: str,
    fixture: FixtureGroundTruth,
    image_bytes: bytes,
    provider: OcrProvider,
    variant: str,
    profile: OcrPreprocessProfile,
    max_edge: int,
) -> SpikeTrial:
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
        prep_ms = (time.perf_counter() - prep_start) * 1000
        result = provider.extract_text(prepared.image_bytes)
        result = result.model_copy(
            update={
                "preprocessing_profile": profile.value,
                "image_width_px": result.image_width_px or prepared.width_px,
                "image_height_px": result.image_height_px or prepared.height_px,
            },
        )
        ocr_ms = float(result.processing_time_ms or 0.0)
        total_ms = prep_ms + ocr_ms
        if not result.has_text:
            return SpikeTrial(
                experiment=experiment,
                fixture_id=fixture.fixture_id,
                category=fixture.category,
                provider=provider.name,
                variant=variant,
                preprocess_profile=profile.value,
                max_edge_px=max_edge,
                success=False,
                failure_kind="no_text",
                failure_message="OCR returned no text",
                preprocess_ms=prep_ms,
                ocr_ms=ocr_ms,
                total_ms=total_ms,
                brand_exact=False,
                brand_normalized=False,
                field_recovery=empty_fields,
                fields_recovered_count=0,
                character_error_rate=1.0,
                word_count=0,
                ocr_full_text="",
                brand_region_preview="",
                init_time_ms=getattr(provider, "init_time_ms", None),
                rss_mb_after=_rss_mb(),
            )
        fields = score_compliance_fields(result.full_text, fixture)
        return SpikeTrial(
            experiment=experiment,
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            provider=provider.name,
            variant=variant,
            preprocess_profile=profile.value,
            max_edge_px=max_edge,
            success=True,
            failure_kind=None,
            failure_message=None,
            preprocess_ms=prep_ms,
            ocr_ms=ocr_ms,
            total_ms=total_ms,
            brand_exact=brand_exact_recovered(result.full_text, fixture.brand_name),
            brand_normalized=brand_normalized_recovered(result.full_text, fixture.brand_name),
            field_recovery=fields,
            fields_recovered_count=sum(1 for ok in fields.values() if ok),
            character_error_rate=character_error_rate(
                reference_full_text(fixture),
                result.full_text,
            ),
            word_count=len(result.words),
            ocr_full_text=result.full_text,
            brand_region_preview=_brand_region_preview(
                result,
                fixture.brand_name.exact_text,
            ),
            init_time_ms=getattr(provider, "init_time_ms", None),
            rss_mb_after=_rss_mb(),
        )
    except Exception as exc:  # noqa: BLE001
        prep_ms = (time.perf_counter() - prep_start) * 1000
        return SpikeTrial(
            experiment=experiment,
            fixture_id=fixture.fixture_id,
            category=fixture.category,
            provider=getattr(provider, "name", "unknown"),
            variant=variant,
            preprocess_profile=profile.value,
            max_edge_px=max_edge,
            success=False,
            failure_kind="engine_exception",
            failure_message=f"{exc}\n{traceback.format_exc(limit=2)}",
            preprocess_ms=prep_ms,
            ocr_ms=None,
            total_ms=prep_ms,
            brand_exact=False,
            brand_normalized=False,
            field_recovery=empty_fields,
            fields_recovered_count=0,
            character_error_rate=None,
            word_count=0,
            ocr_full_text="",
            brand_region_preview="",
            init_time_ms=getattr(provider, "init_time_ms", None),
            rss_mb_after=_rss_mb(),
            notes=[type(exc).__name__],
        )


def _probe_providers(names: list[str]) -> tuple[dict[str, OcrProvider], dict[str, str]]:
    available: dict[str, OcrProvider] = {}
    unavailable: dict[str, str] = {}
    for name in names:
        try:
            provider = create_ocr_provider(name)
            if provider.is_available():
                available[provider.name] = provider
            else:
                unavailable[name] = "is_available() returned False"
        except Exception as exc:  # noqa: BLE001
            unavailable[name] = str(exc)
    return available, unavailable


def run_phase88_spike(
    corpus_dir: Path | None = None,
    *,
    providers: list[str] | None = None,
    max_edge: int = 1600,
) -> dict[str, Any]:
    """Run corpus + decorative + PSM + region experiments; return structured report."""
    root = corpus_dir or default_corpus_root()
    fixtures = load_corpus_manifest(root)
    by_id = {f.fixture_id: f for f in fixtures}
    provider_names = providers or ["tesseract", "easyocr", "rapidocr"]
    available, unavailable = _probe_providers(provider_names)

    # Warm engines once and record init cost.
    init_costs: dict[str, float | None] = {}
    for name, provider in list(available.items()):
        try:
            blank = Image.new("RGB", (64, 64), color=(255, 255, 255))
            buf = io.BytesIO()
            blank.save(buf, format="PNG")
            start = time.perf_counter()
            provider.extract_text(buf.getvalue())
            init_costs[name] = getattr(provider, "init_time_ms", None)
            if init_costs[name] is None:
                init_costs[name] = (time.perf_counter() - start) * 1000
        except Exception as exc:  # noqa: BLE001
            unavailable[name] = f"warm-up failed: {exc}"
            init_costs[name] = None
            available.pop(name, None)

    trials: list[SpikeTrial] = []
    profile = OcrPreprocessProfile.FAST

    # 1) Full corpus matrix (FAST/1600) for available engines.
    for fixture in fixtures:
        image_path = root / "fixtures" / fixture.image_file
        if not image_path.is_file():
            continue
        image_bytes = image_path.read_bytes()
        for provider in available.values():
            trials.append(
                _run_trial(
                    experiment="corpus_fast",
                    fixture=fixture,
                    image_bytes=image_bytes,
                    provider=provider,
                    variant="production_default",
                    profile=profile,
                    max_edge=max_edge,
                ),
            )

    # 2) Decorative ENHANCED control for Tesseract only.
    for fixture_id in DECORATIVE_IDS:
        fixture = by_id.get(fixture_id)
        if not fixture:
            continue
        image_bytes = (root / "fixtures" / fixture.image_file).read_bytes()
        if "tesseract" in available:
            trials.append(
                _run_trial(
                    experiment="decorative_enhanced",
                    fixture=fixture,
                    image_bytes=image_bytes,
                    provider=available["tesseract"],
                    variant="enhanced_control",
                    profile=OcrPreprocessProfile.ENHANCED,
                    max_edge=1200,
                ),
            )

    # 3) Tesseract PSM variants on decorative fixtures only.
    for fixture_id in DECORATIVE_IDS:
        fixture = by_id.get(fixture_id)
        if not fixture:
            continue
        image_bytes = (root / "fixtures" / fixture.image_file).read_bytes()
        for variant_name, config in TESSERACT_CONFIG_VARIANTS:
            provider = TesseractOcrProvider(
                config=config,
                provider_name=f"tesseract[{variant_name}]",
            )
            if not provider.is_available():
                continue
            trials.append(
                _run_trial(
                    experiment="tesseract_psm",
                    fixture=fixture,
                    image_bytes=image_bytes,
                    provider=provider,
                    variant=variant_name,
                    profile=profile,
                    max_edge=max_edge,
                ),
            )

    # 4) Region-based OCR (upper crop + prominent band) for decorative fixtures.
    for fixture_id in DECORATIVE_IDS:
        fixture = by_id.get(fixture_id)
        if not fixture:
            continue
        image_bytes = (root / "fixtures" / fixture.image_file).read_bytes()
        for provider in available.values():
            upper = _crop_upper_region(image_bytes, top_fraction=0.45)
            trials.append(
                _run_trial(
                    experiment="region_upper45",
                    fixture=fixture,
                    image_bytes=upper,
                    provider=provider,
                    variant="upper_45pct",
                    profile=profile,
                    max_edge=max_edge,
                ),
            )
            # First-pass whole image to guide prominent band (same provider).
            first = _run_trial(
                experiment="region_guide_pass",
                fixture=fixture,
                image_bytes=image_bytes,
                provider=provider,
                variant="guide",
                profile=profile,
                max_edge=max_edge,
            )
            # Rebuild OcrResult-like crop using provider directly for band.
            try:
                prepared = prepare_for_ocr_from_bytes(
                    image_bytes,
                    profile=profile,
                    max_edge_px=max_edge,
                )
                guide_ocr = provider.extract_text(prepared.image_bytes)
                guide_ocr = guide_ocr.model_copy(
                    update={
                        "image_width_px": guide_ocr.image_width_px or prepared.width_px,
                        "image_height_px": guide_ocr.image_height_px or prepared.height_px,
                    },
                )
                band = _crop_prominent_band(prepared.image_bytes, guide_ocr)
                if band is not None:
                    trials.append(
                        _run_trial(
                            experiment="region_prominent_band",
                            fixture=fixture,
                            image_bytes=band,
                            provider=provider,
                            variant="prominent_upper_words",
                            profile=OcrPreprocessProfile.FAST,
                            max_edge=max_edge,
                        ),
                    )
                else:
                    trials.append(
                        SpikeTrial(
                            experiment="region_prominent_band",
                            fixture_id=fixture.fixture_id,
                            category=fixture.category,
                            provider=provider.name,
                            variant="prominent_upper_words",
                            preprocess_profile=profile.value,
                            max_edge_px=max_edge,
                            success=False,
                            failure_kind="no_band",
                            failure_message="No prominent upper word band found",
                            preprocess_ms=0.0,
                            ocr_ms=None,
                            total_ms=0.0,
                            brand_exact=False,
                            brand_normalized=False,
                            field_recovery=first.field_recovery,
                            fields_recovered_count=0,
                            character_error_rate=None,
                            word_count=0,
                            ocr_full_text="",
                            brand_region_preview="",
                            notes=["skipped_no_band"],
                        ),
                    )
            except Exception as exc:  # noqa: BLE001
                trials.append(
                    SpikeTrial(
                        experiment="region_prominent_band",
                        fixture_id=fixture.fixture_id,
                        category=fixture.category,
                        provider=provider.name,
                        variant="prominent_upper_words",
                        preprocess_profile=profile.value,
                        max_edge_px=max_edge,
                        success=False,
                        failure_kind="region_error",
                        failure_message=str(exc),
                        preprocess_ms=0.0,
                        ocr_ms=None,
                        total_ms=0.0,
                        brand_exact=False,
                        brand_normalized=False,
                        field_recovery={
                            "brand_name": False,
                            "class_type": False,
                            "alcohol_content_abv": False,
                            "net_contents": False,
                            "government_health_warning": False,
                        },
                        fields_recovered_count=0,
                        character_error_rate=None,
                        word_count=0,
                        ocr_full_text="",
                        brand_region_preview="",
                    ),
                )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "phase": "8.8",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "providers_requested": provider_names,
        "providers_available": list(available.keys()),
        "providers_unavailable": unavailable,
        "init_time_ms": init_costs,
        "rss_mb_after_warmup": _rss_mb(),
        "candidate_rationale": {
            "easyocr": (
                "Actively maintained PyTorch OCR; strong on irregular/display fonts; "
                "CPU path; Win/Linux/macOS; offline after model cache; no cloud API."
            ),
            "rapidocr": (
                "ONNX Runtime packaging of Paddle-family detectors/recognizers without "
                "full PaddlePaddle/OneDNN stack; lighter deploy story; CPU; offline after "
                "model cache."
            ),
            "paddleocr_skipped": (
                "Phase 3 Windows OneDNN fused_conv2d inference failure; no materially "
                "different install path attempted in this spike."
            ),
        },
        "trials": [asdict(t) for t in trials],
        "aggregates": _aggregate(trials),
    }
    return report


def _aggregate(trials: list[SpikeTrial]) -> dict[str, Any]:
    by_provider: dict[str, list[SpikeTrial]] = defaultdict(list)
    for trial in trials:
        if trial.experiment == "corpus_fast":
            by_provider[trial.provider].append(trial)

    corpus = {}
    for provider, rows in by_provider.items():
        totals = [r.total_ms for r in rows if r.success]
        brand_exact = [r.brand_exact for r in rows]
        brand_norm = [r.brand_normalized for r in rows]
        field_rates = defaultdict(list)
        for row in rows:
            for key, ok in row.field_recovery.items():
                field_rates[key].append(bool(ok))
        corpus[provider] = {
            "n": len(rows),
            "success_rate": sum(1 for r in rows if r.success) / max(1, len(rows)),
            "brand_exact_rate": sum(brand_exact) / max(1, len(brand_exact)),
            "brand_normalized_rate": sum(brand_norm) / max(1, len(brand_norm)),
            "mean_fields": statistics.mean(r.fields_recovered_count for r in rows),
            "field_rates": {
                k: sum(v) / max(1, len(v)) for k, v in field_rates.items()
            },
            "median_total_ms": statistics.median(totals) if totals else None,
            "p95_total_ms": _percentile(totals, 95),
            "max_total_ms": max(totals) if totals else None,
        }

    decorative = [
        t
        for t in trials
        if t.fixture_id in DECORATIVE_IDS
        and t.experiment
        in {
            "corpus_fast",
            "decorative_enhanced",
            "tesseract_psm",
            "region_upper45",
            "region_prominent_band",
        }
    ]
    return {"corpus_fast": corpus, "decorative_trial_count": len(decorative)}


def write_phase88_artifacts(report: dict[str, Any], results_dir: Path) -> Path:
    """Write JSON + Markdown summary under results_dir."""
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "phase88_decorative_ocr_spike.json"
    md_path = results_dir / "phase88_decorative_ocr_spike.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return md_path


def _markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Phase 8.8 — Decorative Typography OCR Evaluation Spike")
    lines.append("")
    lines.append(f"Generated: `{report['generated_at']}`")
    lines.append("")
    lines.append("## Environment")
    for k, v in report["environment"].items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    lines.append("## Providers")
    lines.append(f"- Requested: {', '.join(report['providers_requested'])}")
    lines.append(f"- Available: {', '.join(report['providers_available']) or '(none)'}")
    if report["providers_unavailable"]:
        lines.append("- Unavailable:")
        for name, reason in report["providers_unavailable"].items():
            lines.append(f"  - `{name}`: {reason}")
    lines.append("")
    lines.append("## Init / memory")
    lines.append(f"- RSS after warmup: `{report.get('rss_mb_after_warmup')}` MB")
    for name, ms in (report.get("init_time_ms") or {}).items():
        lines.append(f"- `{name}` init: `{ms}` ms")
    lines.append("")
    lines.append("## Corpus FAST/1600 aggregates")
    lines.append("")
    lines.append(
        "| Provider | Brand exact | Brand norm | Mean fields/5 | "
        "Median ms | p95 ms | Max ms | Success |",
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for provider, agg in (report.get("aggregates") or {}).get("corpus_fast", {}).items():
        med = agg.get("median_total_ms")
        p95 = agg.get("p95_total_ms")
        mx = agg.get("max_total_ms")
        med_s = f"{med:.0f}" if med is not None else "n/a"
        p95_s = f"{p95:.0f}" if p95 is not None else "n/a"
        mx_s = f"{mx:.0f}" if mx is not None else "n/a"
        lines.append(
            f"| {provider} | {agg['brand_exact_rate']:.2f} | "
            f"{agg['brand_normalized_rate']:.2f} | {agg['mean_fields']:.2f} | "
            f"{med_s} | {p95_s} | {mx_s} | {agg['success_rate']:.2f} |",
        )
    lines.append("")
    lines.append("### Per-field recovery (corpus FAST)")
    lines.append("")
    for provider, agg in (report.get("aggregates") or {}).get("corpus_fast", {}).items():
        rates = agg.get("field_rates") or {}
        lines.append(
            f"- **{provider}:** brand={rates.get('brand_name', 0):.2f}, "
            f"class={rates.get('class_type', 0):.2f}, "
            f"abv={rates.get('alcohol_content_abv', 0):.2f}, "
            f"net={rates.get('net_contents', 0):.2f}, "
            f"warning={rates.get('government_health_warning', 0):.2f}",
        )
    lines.append("")
    lines.append("## Decorative label raw brand region previews")
    lines.append("")
    for trial in report.get("trials") or []:
        if trial["fixture_id"] not in DECORATIVE_IDS:
            continue
        if trial["experiment"] not in {
            "corpus_fast",
            "decorative_enhanced",
            "tesseract_psm",
            "region_upper45",
            "region_prominent_band",
        }:
            continue
        lines.append(
            f"### {trial['fixture_id']} — {trial['experiment']} / "
            f"{trial['provider']} / {trial['variant']}",
        )
        lines.append(
            f"- brand_exact={trial['brand_exact']} brand_norm={trial['brand_normalized']} "
            f"fields={trial['fields_recovered_count']}/5 total_ms={trial['total_ms']:.0f}",
        )
        preview = (trial.get("brand_region_preview") or "").replace("\n", " | ")
        lines.append(f"- brand_region: `{preview[:300]}`")
        lines.append("")
    lines.append("See JSON artifact for full OCR text.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry for Phase 8.8 spike."""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 8.8 decorative OCR spike")
    parser.add_argument("--corpus-dir", type=Path, default=None)
    parser.add_argument("--results-dir", type=Path, default=None)
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["tesseract", "easyocr", "rapidocr"],
    )
    parser.add_argument("--max-edge", type=int, default=1600)
    args = parser.parse_args(argv)

    corpus = args.corpus_dir or default_corpus_root()
    results = args.results_dir or (corpus / "results")
    report = run_phase88_spike(
        corpus,
        providers=list(args.providers),
        max_edge=args.max_edge,
    )
    md_path = write_phase88_artifacts(report, results)
    print(md_path.read_text(encoding="utf-8").encode("ascii", errors="replace").decode("ascii"))
    print(f"Wrote {results / 'phase88_decorative_ocr_spike.json'}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
