# Phase 8.8 — Decorative Typography OCR Evaluation Spike

**Status:** Complete (evaluation only)  
**Date:** 2026-09-19  
**Raw artifacts:** `test-data/ocr-eval/results/phase88_decorative_ocr_spike.json`, `phase88_decorative_ocr_spike.md`

Production OCR remains **Tesseract**. This spike does **not** change VerificationService, extraction heuristics, PASS/REVIEW/FAIL, or OpenAI reconciliation.

## Candidate selection

| Engine | Why selected | Why not others |
|--------|--------------|----------------|
| **RapidOCR** (`rapidocr` + `onnxruntime`) | Actively maintained; ONNX CPU path; packages Paddle-family models **without** full PaddlePaddle/OneDNN; Win/Linux/macOS; offline after model cache | — |
| **EasyOCR** | Mature PyTorch English OCR; often stronger on irregular/display fonts; CPU; cross-platform | Heavy (torch); slow |
| **PaddleOCR** | *Not re-fought* | Phase 3 Windows OneDNN `fused_conv2d` failures; no materially different install path for this spike |
| Cloud OCR | — | Violates offline / no outbound runtime requirement |

Isolation: optional extras `ocr-easyocr`, `ocr-rapidocr`, `ocr-eval-phase88` — **not** in production dependency set. Eval uses `backend/.venv-ocr` (Python 3.12). Pin `numpy<2` for OpenCV ABI compatibility with this stack.

## Versions (this Windows eval host)

| Component | Version |
|-----------|---------|
| Python | 3.12.10 |
| Tesseract binary | 5.4.0.20240606 |
| pytesseract | (ocr-tesseract extra) |
| EasyOCR | 1.7.2 |
| torch | 2.14.0+cpu |
| RapidOCR | 3.9.2 |
| onnxruntime | 1.30.0 |

## Corpus

Phase 3 synthetic fixtures **plus** manual decorative flat labels (evaluation metadata only; not hard-coded in production):

| Fixture | Brand ground truth |
|---------|-------------------|
| `decorative_maple_creek` | MAPLE CREEK |
| `decorative_whispering_pine` | WHISPERING PINE |

## How to re-run

```bash
cd backend
.\.venv-ocr\Scripts\activate
pip install -e ".[ocr-eval-phase88]"
pip install "numpy<2"   # if OpenCV ABI breaks after torch/rapidocr pull numpy 2.x
python -m app.ocr.evaluate.phase88_spike --providers tesseract easyocr rapidocr
```

## Init / memory (after warm-up)

| Provider | Approx init ms |
|----------|----------------|
| tesseract | ~208 |
| rapidocr | ~334 |
| easyocr | ~1637 |

Process RSS after warm-up ≈ **739 MB** (EasyOCR+torch loaded).

## Existing-corpus metrics (FAST / 1600 px, n=13 including decorative)

| Provider | Brand exact | Brand norm | Mean fields/5 | Median ms | p95 ms | Max ms | Success |
|----------|------------:|-----------:|--------------:|----------:|-------:|-------:|--------:|
| **rapidocr** | **0.85** | **0.85** | **4.69** | 821 | 1141 | 1416 | 1.00 |
| tesseract | 0.69 | 0.85 | 4.08 | **445** | **567** | 570 | 0.92 |
| easyocr | 0.69 | 0.69 | 4.00 | 3791 | 5087 | 5768 | 1.00 |

### Per-field recovery (corpus FAST)

| Provider | brand | class | ABV | net | warning |
|----------|------:|------:|----:|----:|--------:|
| rapidocr | 0.85 | 0.92 | 1.00 | 1.00 | 0.92 |
| tesseract | 0.85 | 0.77 | 0.77 | 0.85 | 0.85 |
| easyocr | 0.69 | 0.77 | 0.92 | 0.92 | 0.69 |

## Maple Creek — raw brand region by engine/config

| Experiment | Engine / variant | Brand exact? | Brand region / notable OCR |
|------------|------------------|-------------:|----------------------------|
| Whole-label FAST | **tesseract** | No | `APLE CREEK` |
| Whole-label FAST | easyocr | No* | `MAPLE` … later `CREEK` (not contiguous) |
| Whole-label FAST | **rapidocr** | **Yes** | `MAPLE CREEK` |
| ENHANCED | tesseract | No | Still misses leading M / loses brand line |
| PSM 3/6/7/11/12 | tesseract | No | Still `APLE CREEK` / `APLE CREE` / worse |
| Upper 45% crop | tesseract | No | `wae CREEK` |
| **Prominent-band crop** | **tesseract** | **Yes** | `MAPLE CREEK` |
| Upper / prominent | rapidocr | **Yes** | `MAPLE CREEK` |

\*EasyOCR recovered both tokens but not as a single contiguous brand string under exact scoring.

## Whispering Pine — raw brand region by engine/config

| Experiment | Engine / variant | Brand exact? | Brand region / notable OCR |
|------------|------------------|-------------:|----------------------------|
| Whole-label FAST | tesseract | No | No brand tokens (`ie DISTILLERY` …) |
| Whole-label FAST | easyocr | No | `Whisperigg` + `Pine` |
| Whole-label FAST | **rapidocr** | No† | `Whispering` + `Pine` (separate lines; both tokens present) |
| ENHANCED / PSM variants | tesseract | No | Still no usable brand |
| Upper / prominent | tesseract | No | Still fails |
| Upper / prominent | easyocr | No | `Whisperigg` + `Pine` |
| Upper / prominent | rapidocr | No† | `Whispering` (Pine sometimes outside band) |

†Exact contiguous `WHISPERING PINE` not recovered; RapidOCR is the only engine that recovered a correct **Whispering** reading on whole-label OCR.

## Tesseract configuration experiment (conclusion)

Limited PSM variants (**3, 6, 7, 11, 12**) on decorative fixtures **did not** restore Maple’s leading **M** or Whispering’s script brand. Failure is primarily **recognition / decorative typography**, not merely default page-segmentation.

## Region-based experiment (conclusion)

General heuristics (upper 45%; band around tallest upper-half word boxes — **no fixture-specific crops**):

- **Tesseract prominent-band** recovered **`MAPLE CREEK` exactly** where whole-label FAST produced `APLE CREEK`.
- Whispering script brand remained unrecovered under Tesseract region OCR.
- RapidOCR region OCR also recovered Maple exactly; Whispering still incomplete for contiguous exact match.

## Latency comparison

| Engine | Median whole-label (corpus) | Notes |
|--------|----------------------------:|-------|
| Tesseract | ~445 ms | Best latency; fits &lt;5 s E2E budget easily |
| RapidOCR | ~821 ms | ~1.8× Tesseract; still usually &lt;1.5 s worst on this set |
| EasyOCR | ~3790 ms | Often **consumes most of** the 5 s budget alone |

## Deployment / packaging implications

| Concern | Tesseract | RapidOCR | EasyOCR |
|---------|-----------|----------|---------|
| Windows reliability | Proven | Works after adapter fix (numpy array unpack) | Works; heavy |
| Docker / Linux | Proven in image | Likely good (ONNX); needs smoke test | Large image (torch) |
| Apple Silicon | Host tesseract | ONNX wheels generally available | torch wheels available |
| Offline | Binary + tessdata | Needs **bundled ONNX models** (first-run download today) | Needs **bundled** detection/recog models |
| Prod deps | Small | Extra onnxruntime + models | Large torch stack |
| numpy/OpenCV friction | Low | Managed with `numpy<2` in eval venv | Conflicts with newer SciPy wanting numpy 2 |

## Architectural options (measured — not implemented)

| Option | Verdict |
|--------|---------|
| **A. Tesseract only** | **Keep as production default** for now. Still best latency; adequate synthetic corpus recovery; already packaged. |
| **B. Replace Tesseract** | **Not yet.** RapidOCR wins field recovery and Maple exact whole-label, but packaging (model bundling), multi-OS smoke tests, and memory must be proven before a primary swap. EasyOCR is too slow to be primary. |
| **C. Tesseract FAST → escalate** | **Most promising next experiment** (not shipped). Escalate only on evidence-quality gates — e.g. brand UNCERTAIN / integrity — to **region re-OCR (Tesseract)** and/or **RapidOCR**. Caveat: Maple `APLE CREEK` currently **PASS**es without integrity trip, so escalation would not fire unless gates improve. Do **not** weaken AI `unable_to_determine` rejection. |

## Recommendation (evidence-based)

1. **Do not change production OCR in this phase** — remain on **Tesseract FAST**.
2. Prefer future work order: (i) general **region-based Tesseract re-OCR** for prominent brand bands (Maple recovered without new engine); (ii) optional **RapidOCR escalation** behind the provider port with bundled models; (iii) do not adopt EasyOCR as primary.
3. Re-evaluate RapidOCR on Linux/Docker and Apple Silicon before any architecture selection.
4. Keep OpenAI evidence rules unchanged (`unable_to_determine=true` stays non-promotable).

## Related

- Phase 3 baseline: `docs/OCR_EVALUATION.md`
- ADR-028 in `docs/DECISIONS.md`
- Harness: `python -m app.ocr.evaluate.phase88_spike`
