# Phase 8.9 — Selective Brand OCR Escalation

**Status:** Implemented (prototype)  
**Date:** 2026-09-19  
**Related:** `docs/OCR_EVALUATION_PHASE88.md`, ADR-029

## Production path

```
Tesseract FAST whole-label
→ extraction
→ [optional ENHANCED whole-label retry — existing policy]
→ if brand evidence suspicious/uncertain:
      Tesseract on prominent brand region (Phase 8.8 strategy)
→ if still UNCERTAIN/NOT_FOUND and SECONDARY_OCR_ENABLED:
      RapidOCR on the same region (optional)
→ reconcile OCR evidence
→ rules → optional OpenAI fallback (unchanged safety)
```

Tesseract remains the primary provider. RapidOCR is never a readiness requirement.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `BRAND_REGION_OCR_ENABLED` | `true` | Tesseract brand-region retry |
| `SECONDARY_OCR_ENABLED` | `false` | Optional RapidOCR escalation |
| `SECONDARY_OCR_PROVIDER` | `rapidocr` | Secondary provider name |

Safe defaults: region retry on; secondary off until packaged/validated.

## Escalation triggers

Escalates when brand is `NOT_FOUND`, `UNCERTAIN`, or soft FOUND suspicions:

- `prominent_left_inset` — tall upper glyphs starting well right of the left edge
- `short_leading_token_tall_glyphs` — short first token on very tall glyphs
- integrity / ambiguous / weak-standalone UNCERTAIN reasons

Clean high-confidence FOUND brands with no suspicion skip region OCR.

## RapidOCR packaging (optional)

```bash
cd backend
pip install -e ".[ocr-secondary]"   # rapidocr + onnxruntime; pin numpy<2 if needed
```

| Topic | Notes |
|-------|-------|
| Models | Shipped inside the `rapidocr` wheel under `site-packages/rapidocr/models/*.onnx` (PP-OCRv6 small det/rec + cls). First import uses local files when present — **no runtime network required after install**. |
| Size | On the order of tens of MB for ONNX models + onnxruntime (platform-dependent). |
| License | RapidOCR Apache-2.0; check bundled model notices in the RapidOCR package. |
| Init | Lazy on first secondary call; failures → skip secondary, keep REVIEW, no HTTP 500. |
| Offline | Install wheels on an online machine / mirror; copy into air-gapped image. Do not rely on first-run download in locked-down networks. |
| Platforms | CPU onnxruntime wheels for Windows / Linux / macOS (incl. Apple Silicon variants). Validate per deploy target before enabling `SECONDARY_OCR_ENABLED`. |
| Whole-label fallback | If the brand-region RapidOCR crop is empty/uncertain **or** returns only a single token, one whole-label RapidOCR pass on the prepared image is permitted. |

**Do not** install EasyOCR/torch into production.

## Remaining limitations

- Whispering-style script brands may still yield partial secondary reads (e.g. `Whispering` without `Pine`); single-token secondary FOUND after UNCERTAIN whole-label stays **UNCERTAIN** for review/AI.
- Soft FOUND triggers (`prominent_left_inset`) are geometric heuristics — not regulatory certainty.
- Secondary OCR latency can approach ~2–3 s on CPU; keep disabled until packaging is validated.

## Evidence methods

Technical Details may show:

- `ocr_only` / `ocr_plus_enhanced`
- `…_plus_brand_region`
- `…_plus_brand_region_rapidocr`
- existing `…_ai_*` suffixes after OpenAI

Brand escalation payload is under Technical Details for the Brand Name check only.
