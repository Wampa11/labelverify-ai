# OCR Evaluation Report

**Status:** Complete (Phase 3)  
**Date:** 2026-09-19  
**Raw artifacts:** `test-data/ocr-eval/results/ocr_evaluation.json`, `.csv`, `ocr_evaluation_summary.md`

This report selects an OCR strategy from **measured results**, not reputation.

Synthetic fixtures are **not** actual approved TTB labels.

## Recommendation (evidence-based)

| Decision | Choice |
|----------|--------|
| **Primary OCR engine** | **Tesseract** (`pytesseract` + host Tesseract 5.4) |
| **Default preprocessing** | **FAST** (orientation → RGB → resize → grayscale) |
| **Default working max-edge** | **1600 px** |
| **Optional harder path** | Tesseract **ENHANCED** at **1200 px** when capture quality is poor |
| **PaddleOCR** | **Not selected** for the prototype runtime (inference blocked on this Windows eval host; see below) |

### Why

1. **Tesseract recovered compliance fields** at ~4.2/5 mean across fixtures; best config **enhanced/1200** reached **4.27/5** with **100% success**.
2. **FAST/1600** was nearly as accurate (**4.18/5**) with **median ~427 ms** — much better headroom under the eventual **&lt;5 s** end-to-end budget than enhanced (~750 ms).
3. Larger edges (2200) did **not** improve Tesseract field recovery vs 1200/1600 on this corpus.
4. **ENHANCED** slightly improved CER / best field recovery but roughly **doubled** median latency vs FAST — not justified as the default.
5. **PaddleOCR** installed and initialized, but **every inference failed** on this Windows environment (OneDNN `fused_conv2d` / `OneDnnContext does not have the input Filter`). Downgrading paddle caused NumPy/SciPy/OpenCV ABI conflicts. Therefore Paddle could not be scored on accuracy here.

No primary/fallback dual-engine stack is justified until Paddle (or another engine) runs successfully on the target deploy OS (likely Linux/Docker).

## Engines tested

| Engine | Packages | Notes |
|--------|----------|-------|
| Tesseract | `pytesseract 0.3.13` + Tesseract **5.4.0** (UB Mannheim Windows) | Full matrix completed |
| PaddleOCR | Tried `paddleocr 2.10` + `paddlepaddle 3.3.1`, then `2.7.3` + `2.6.2` | Init/model download OK on 3.3.1; **inference RuntimeError** on Windows; 2.6.2 conflicted with NumPy 2.x stack |

### Isolation

- App/runtime venv may remain on the developer’s default Python.
- OCR evaluation used an isolated **`backend/.venv-ocr`** on **Python 3.12.10** because:
  - Project targets Python 3.12
  - PaddlePaddle has **no wheels for Python 3.14** (developer default)

## Corpus

Generated under `test-data/ocr-eval/`:

| Fixture ID | Category |
|------------|----------|
| clean_high_quality | clean |
| small_compliance_text | small_text |
| capitalization_variation | capitalization |
| punctuation_apostrophe | punctuation |
| rotated_15deg | rotated |
| perspective_moderate | perspective |
| low_contrast | low_contrast |
| mild_blur | blur |
| glare_overexposure | glare |
| cluttered_decorative | cluttered |
| partially_unreadable | difficult |

Ground truth JSON records brand, class/type, ABV (exact + semantic), net contents, government warning, category, and notes.

## Metrics

| Metric | Definition |
|--------|------------|
| Latency | Preprocess ms, OCR ms, total pipeline ms |
| CER | Character error rate vs concatenated exact field texts |
| Field recovery | Per-field fuzzy/semantic match (RapidFuzz heuristics; **not** regulatory PASS/FAIL) |
| Localization | Whether bounding boxes/polygons were returned |
| Failures | `no_text`, `engine_error`, preprocess errors, etc. |

Confidence scores are **not** compared across engines.

## Matrix

- Providers: tesseract, paddleocr  
- Profiles: **fast**, **enhanced**  
- Max edges: **1200**, **1600**, **2200**  
- Trials: **132** (11 × 2 × 2 × 3)

## Benchmark environment

- Python 3.12.10  
- Windows 11 (10.0.26200) AMD64  
- Tesseract 5.4.0.20240606  

## Results summary

### Configuration leaderboard (field recovery, then latency)

| Provider | Preprocess | Max edge | Mean fields/5 | Mean CER | Median total ms | p95 total ms | Success |
|----------|------------|----------|---------------|----------|-----------------|--------------|---------|
| tesseract | enhanced | 1200 | **4.27** | 0.224 | 750 | 1027 | 1.00 |
| tesseract | fast | 1600 | 4.18 | 0.277 | **427** | 502 | 0.91 |
| tesseract | fast | 1200 | 4.18 | 0.277 | 442 | 562 | 0.91 |
| tesseract | fast | 2200 | 4.18 | 0.277 | 449 | 554 | 0.91 |
| tesseract | enhanced | 1600 | 4.18 | 0.256 | 736 | 916 | 0.91 |
| tesseract | enhanced | 2200 | 4.18 | 0.256 | 792 | 889 | 0.91 |
| paddleocr | *all* | *all* | 0.00 | 1.000 | 24–323 | — | **0.00** |

### Field recovery (Tesseract, pooled)

| Brand | Class/Type | ABV | Net | Warning |
|------:|----------:|----:|----:|--------:|
| 0.91 | 0.73 | 0.82 | 0.83 | 0.91 |

### FAST vs ENHANCED (pooled across engines)

- **fast:** mean fields 2.09 (pulled down by Paddle zeros), Tesseract-only ~4.18; median total **168 ms** pooled / **~430 ms** Tesseract  
- **enhanced:** slightly better CER on Tesseract; median much higher (~750 ms Tesseract)

### Working resolution

On this corpus, **1200–1600 px** matched or beat **2200 px** for Tesseract field recovery. Prefer **1600** as default.

### Representative latency (Tesseract)

| Config | Median total | p95 total |
|--------|--------------|-----------|
| fast / 1600 | ~427 ms | ~502 ms |
| enhanced / 1200 | ~750 ms | ~1027 ms |

Worst-case Tesseract totals on this set remain **well under 2 s**, leaving budget for extraction, rules, optional AI, and UI.

## Failure modes observed

| Kind | Count | Notes |
|------|------:|-------|
| `engine_error` | 66 | All PaddleOCR runs (OneDNN inference failure) |
| `no_text` | 5 | Tesseract on hardest fixture(s) under some configs |

**Still hard for OCR:** heavy occlusion (`partially_unreadable`), glare covering text, strong perspective, and small warning typography (class/type recovery weakest at 0.73).

## What should trigger future AI fallback (Phase 4+)

AI should **not** replace OCR by default. Candidates for optional AI assist later:

- Multiple compliance fields missing after OCR + deterministic extraction  
- Warning text only partially recovered with low engine confidence  
- Image quality status POOR **and** field recovery incomplete  
- Explicit operator “request assist” (if product wants it)

AI must remain observable, optional, and never treated as regulatory certainty.

## How to re-run

```bash
cd backend
# Recommended: Python 3.12 isolated env
py -3.12 -m venv .venv-ocr
.\.venv-ocr\Scripts\activate   # Windows
pip install -e ".[dev,ocr-eval]"
# Ensure Tesseract binary is on PATH (or installed under Program Files)
python -m app.ocr.evaluate
```

Outputs overwrite `test-data/ocr-eval/results/`.

## Known limitations

- Synthetic corpus ≠ real bottle photography or production labels  
- Field recovery thresholds are evaluation heuristics  
- PaddleOCR not scored for accuracy on this Windows host  
- No geometric IoU benchmarking (no region ground truth)  
- Frontend bbox overlay not added (optional; deferred)

## Phase 4 wiring implication

Wire **`TesseractOcrProvider`** with **FAST / 1600** as the default OCR path behind `OcrProvider`. Keep ENHANCED selectable via config for difficult images. Revisit PaddleOCR only after a successful Linux/Docker smoke test.

---

## Phase 8.8 follow-up

Decorative-typography re-evaluation (RapidOCR, EasyOCR, Tesseract PSM, region OCR) is documented in **`docs/OCR_EVALUATION_PHASE88.md`**. Production engine remains Tesseract until a later ADR selects otherwise.
