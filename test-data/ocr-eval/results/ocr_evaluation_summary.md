# OCR Evaluation Summary

Generated: `2026-09-19T17:36:03.008228+00:00`

## Environment
- **python:** 3.12.10
- **platform:** Windows-11-10.0.26200-SP0
- **machine:** AMD64

## Providers
- Requested: tesseract, paddleocr
- Available: tesseract, paddleocr

Profiles: fast, enhanced; max edges: 1200, 1600, 2200

## Configuration leaderboard (by mean field recovery, then latency)

| Provider | Preprocess | Max edge | Mean fields/5 | Mean CER | Median total ms | p95 total ms | BBox rate | Success rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| tesseract | enhanced | 1200 | 4.27 | 0.224 | 750 | 1027 | 1.00 | 1.00 |
| tesseract | fast | 1600 | 4.18 | 0.277 | 427 | 502 | 0.91 | 0.91 |
| tesseract | fast | 1200 | 4.18 | 0.277 | 442 | 562 | 0.91 | 0.91 |
| tesseract | fast | 2200 | 4.18 | 0.277 | 449 | 554 | 0.91 | 0.91 |
| tesseract | enhanced | 1600 | 4.18 | 0.256 | 736 | 916 | 0.91 | 0.91 |
| tesseract | enhanced | 2200 | 4.18 | 0.256 | 792 | 889 | 0.91 | 0.91 |
| paddleocr | fast | 2200 | 0.00 | 1.000 | 24 | 48 | 0.00 | 0.00 |
| paddleocr | fast | 1200 | 0.00 | 1.000 | 28 | 44 | 0.00 | 0.00 |
| paddleocr | fast | 1600 | 0.00 | 1.000 | 29 | 46 | 0.00 | 0.00 |
| paddleocr | enhanced | 1600 | 0.00 | 1.000 | 321 | 442 | 0.00 | 0.00 |
| paddleocr | enhanced | 1200 | 0.00 | 1.000 | 322 | 356 | 0.00 | 0.00 |
| paddleocr | enhanced | 2200 | 0.00 | 1.000 | 323 | 433 | 0.00 | 0.00 |

## Field recovery by provider (all configs pooled)

| Provider | brand_name | class_type | alcohol_content_abv | net_contents | government_health_warning |
|---|---:|---:|---:|---:|---:|
| paddleocr | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| tesseract | 0.91 | 0.73 | 0.82 | 0.83 | 0.91 |

## FAST vs ENHANCED (pooled)

- **fast:** mean fields=2.09, median total=168 ms, mean CER=0.277
- **enhanced:** mean fields=2.11, median total=541 ms, mean CER=0.245

## Working resolution (pooled)

- **1200px:** mean fields=2.11, median total=348 ms
- **1600px:** mean fields=2.09, median total=367 ms
- **2200px:** mean fields=2.09, median total=369 ms

## Failure cases

- `engine_error`: 66
- `no_text`: 5

## Evidence-based recommendation notes

Top configuration by field recovery then latency: **tesseract / enhanced / 1200px** (mean fields 4.27/5, median 750 ms).
Best config with median total <= 2000 ms and mean fields >= 3.0: **tesseract / enhanced / 1200px** (mean fields 4.27/5, median 750 ms).

Final recommendation must weigh field recovery, latency headroom under the 5-second end-to-end target, offline practicality, and maintainability. See `docs/OCR_EVALUATION.md` after results are interpreted.

