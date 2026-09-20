# Performance

## Target

**Normal single-label verification should complete in under 5 seconds** end-to-end (request received → verification result returned), under typical local prototype conditions with a readable label image.

This is a **target**, not a hard SLA. The architecture must make the target measurable and visible.

## Budget allocation (guidance)

| Stage | Suggested share of the 5s budget |
|-------|----------------------------------|
| Image validation + preprocessing + quality | Small fraction (aim well under ~1s for typical photos) |
| OCR (future) | Largest share |
| Extraction / rules / optional AI | Remainder |

Phase 2 instruments `processing_time_ms` and `stage_timings_ms` (`validation`, `preprocessing`) on `POST /api/v1/images/analyze`.

## What “processing time” means

| Metric | Definition |
|--------|------------|
| `processing_time_ms` (required) | Wall-clock milliseconds for the analyzed stage(s) on the server |
| `stage_timings_ms` | Named stage durations for diagnosis |

Every analysis and (later) verification result **must** include overall processing time.

## Phase 2 measurement approach

1. `PipelineTimer` wraps validation and preprocessing in `ImageAnalysisService`.
2. Soft pytest check asserts typical synthetic 1600×1200 JPEG analysis finishes in **under 2000 ms** on the developer machine (fails only if pathological — not a brittle exact-ms CI gate).
3. Representative timings should be recorded when running tests locally and noted in release notes / Phase completion reports.

## Image size controls (affect latency)

Configurable via environment (defaults):

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_UPLOAD_BYTES` | 15 MiB | Reject oversized uploads early |
| `MAX_IMAGE_DIMENSION_PX` | 8000 | Reject extreme dimensions |
| `MIN_IMAGE_DIMENSION_PX` | 100 | Reject useless tiny images |
| `DISPLAY_MAX_EDGE_PX` | 2400 | Cap display transfer size |
| `OCR_PREVIEW_MAX_EDGE_PX` | 2200 | Cap Phase 2 OCR-preview working image |
| `OCR_FAST_MAX_EDGE_PX` | 1600 | Production FAST OCR working edge |
| `OCR_ENHANCED_MAX_EDGE_PX` | 1200 | Optional ENHANCED OCR retry edge |

These are **engineering heuristics** for prototype stability and latency — not regulatory requirements.

## How performance will be measured (full pipeline — future)

1. Instrument the full verification orchestrator (including OCR).
2. Benchmark fixtures in `test-data/clean/` (baseline) and stress sets (`angled`, `glare`).
3. Record p50 / p95; compare against the 5-second target.

### Acceptance sketch (future)

- Clean, well-lit single label: aim for p95 &lt; 5000 ms on a documented reference machine.
- AI fallback must report timing honestly and is not required to meet the target for deterministic-clear cases.

## Batch considerations

Batch throughput is separate from the single-label latency target. Concurrency must be capped (future).

## Anti-patterns

- Inventing or hard-coding fake timings  
- Excluding OCR or AI time to “meet” the target  
- Optimizing by silently skipping stages  
- Brittle CI assertions on exact millisecond values  

## Phase 3 OCR latency findings

See `docs/OCR_EVALUATION.md` for full tables. On the Windows evaluation host:

| Config | Median total (preprocess + OCR) | Notes |
|--------|----------------------------------|-------|
| Tesseract FAST / 1600px | ~427 ms | Recommended default |
| Tesseract ENHANCED / 1200px | ~750 ms | Slightly better field recovery |

Both leave substantial headroom under the 5-second end-to-end target. Prefer FAST by default; do not spend nearly the full budget on OCR for marginal gains.

PaddleOCR did not complete successful inference on this Windows host (OneDNN error); latency figures for Paddle reflect failed runs and are not used for selection.

## Phase 4 extraction instrumentation

`POST /api/v1/labels/extract` reports:

| Stage key | Meaning |
|-----------|---------|
| `display_analysis` / `display_*` | Validation + display preprocess/quality |
| `fast_preprocess` | FAST/1600 OCR image prep |
| `fast_ocr` | Tesseract on FAST image |
| `fast_extraction` | Structured field extraction |
| `enhanced_*` | Present only when retry runs |
| `processing_time_ms` | End-to-end wall clock for the request |

### Corpus sample (11 synthetic fixtures, Windows eval host)

| Metric | Value |
|--------|-------|
| Median end-to-end | ~818 ms |
| Median FAST pass (preprocess+OCR+extract) | ~427 ms |
| Median ENHANCED pass (when used) | ~722 ms |
| Max end-to-end | ~1.8 s |
| ENHANCED retry rate | 3/11 (~27%); triggers were warning-missing / sparse / multi-field miss on difficult fixtures |

Default path remains FAST-only on clean fixtures. Headroom under the **&lt;5s** target is large.

## Phase 5 / 6 verification timing

`POST /api/v1/verify` reports overall `processing_time_ms` plus stage keys such as:

| Stage key | Meaning |
|-----------|---------|
| `extraction_*` | Display + FAST/ENHANCED OCR + extraction (from extraction service) |
| `verification_rules` | First deterministic rule pass |
| `ai_evidence_recovery` | Present only when AI was attempted |
| `verification_rules_after_ai` | Deterministic re-evaluation after merge |

### Budget notes

| Path | Expectation |
|------|-------------|
| Deterministic PASS / FAIL / ineligible REVIEW | **Zero** OpenAI calls; latency ≈ Phase 5 extraction + rules |
| Eligible REVIEW with AI enabled | + one vision call bounded by `OPENAI_TIMEOUT_SECONDS` (default 8s) |
| AI disabled / unavailable | Deterministic REVIEW retained; no extra network wait beyond local null provider |

Normal deterministic cases must remain within the ~5s target. AI-assisted latency is measured separately via `ai_assist.latency_ms` and must not be hidden.

Additional AI settings affecting cost/latency: `OPENAI_MAX_CALLS_PER_REVIEW=1`, `OPENAI_MAX_IMAGE_EDGE_PX=1280`.

## Phase 7 batch throughput

Batch optimizes **throughput under bounded resources**, not Single Review interactivity.

| Setting | Default | Rationale |
|---------|---------|-----------|
| `BATCH_MAX_CONCURRENCY` | 2 | Conservative for local Tesseract CPU |
| `BATCH_MAX_ITEMS` | 300 | Stakeholder peak order of magnitude |
| `BATCH_AI_MAX_CALLS` | 25 | Cost/capacity guardrail |
| `BATCH_AI_CONCURRENCY` | 1 | Avoid stampeding the provider |

### Benchmark notes (development host; not production capacity)

| Workload | Observation |
|----------|-------------|
| 300-item **scripted OCR** orchestration | Completes in CI/dev in tens of seconds (see `tests/test_batch.py`) |
| Real Tesseract | Host/image dependent; measure separately; do not claim SLA from laptop runs |

Single Review &lt;5s target remains unchanged for interactive path.
