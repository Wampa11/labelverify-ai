# Architecture

LabelVerify AI is a local-first prototype: a React frontend talks to a FastAPI backend that runs a staged verification pipeline. External AI is an optional backend capability, not the product core.

## Design goals

- **Accuracy and explainability** over opaque automation
- **Deterministic-first** processing; AI only for ambiguity
- **Graceful degradation** when OCR/AI dependencies fail or are disabled
- **Separable, testable** packages (no monolithic “god” modules)
- **Human review** as a first-class outcome (`REVIEW`)

## Planned processing pipeline

```
Image Upload
    → Image Validation
    → Image Preprocessing (+ quality assessment)
    → OCR (Tesseract FAST/1600; optional one ENHANCED/1200 retry)
    → Field Extraction (FOUND / UNCERTAIN / NOT_FOUND)   [Phase 4]
    → Normalization (ABV / net helpers for extraction)   [Phase 4 partial]
    → Deterministic Rules                                [not yet]
    → Confidence Evaluation                              [not yet]
    → Optional AI Fallback (provider abstraction)        [not yet]
    → Verification Result (with processing time)         [stub only]
    → Human Review when status is REVIEW (or agent overrides)
```

Each arrow is a module boundary. Stages communicate through typed models, not ad-hoc dicts shared across the codebase.

## Phase 2 — Image ingestion and preprocessing (implemented)

### Dual representations

Uploads are validated in memory and **never written to disk**.

| Representation | Purpose | Typical transforms |
|----------------|---------|-------------------|
| **Display** | Operator preview | EXIF orientation, RGB, optional max-edge resize for transfer, JPEG encode |
| **OCR-prepared** | Future OCR input | Oriented RGB → max-edge resize → grayscale → CLAHE → mild denoise → optional deskew → mild unsharp → PNG encode |

The display path does not receive OCR enhancements. The original upload bytes are not mutated; both outputs are derived copies for the current request only.

### Preprocessing package (`backend/app/preprocessing/`)

| Module | Responsibility |
|--------|----------------|
| `formats.py` | Magic-byte sniffing (JPEG/PNG/WebP; PDF recognized for clear rejection) |
| `validation.py` | Size, format, decode, dimension limits — does not trust client MIME |
| `orientation.py` | EXIF orientation correction |
| `transforms.py` | RGB convert, resize, grayscale, CLAHE, denoise, unsharp, encoding |
| `geometry.py` | Conservative deskew + placeholder for future perspective correction |
| `quality.py` | GOOD / WARNING / POOR heuristics (not regulatory) |
| `pipeline.py` | Orchestrates dual representations + quality |

### API

`POST /api/v1/images/analyze` (multipart field `file`)

Returns: ephemeral `analysis_id`, validation, metadata, quality assessment, preprocessing operations, base64 display/OCR images, `processing_time_ms`, stage timings. No filesystem paths.

### Frontend modes

Single application shell with:

- **Single Review** — upload + analysis preview (Phase 2)
- **Batch Review** — reserved, disabled (“Coming soon”)

## Major components

### Frontend (`frontend/`)

| Area | Responsibility |
|------|----------------|
| `components/upload` | Label image intake (`LabelImageDropzone`) |
| `components/verification` | Results display (`VerificationResultsPanel`) |
| `components/workspace` | Review Setup modals and batch results view |
| `components/common` | Shared accessible UI primitives (`AppShell`, `Modal`) |
| `pages` | Unified workspace composition (`AnalystWorkspace`) |
| `services` | HTTP client to backend only (no secrets) |
| `types` | Shared frontend TypeScript models mirroring API contracts |

Primary actions stay on the main surfaces — not hidden in nested menus.

### Backend (`backend/app/`)

| Package | Responsibility |
|---------|----------------|
| `api` | HTTP routing, request/response mapping only |
| `models` | Pydantic domain and API models (verification + image analysis) |
| `preprocessing` | Image validation, dual-representation preprocessing, quality |
| `ocr` | OCR **interface** and adapters; no business rules |
| `extraction` | Map OCR/layout signals to labeled fields (Phase 4; not regulatory) |
| `normalization` | ABV/net parsers for extraction; comparison keys reserved for later |
| `rules` | Deterministic regulatory/compliance checks (source-documented) |
| `confidence` | Decide PASS vs REVIEW vs FAIL given evidence quality |
| `ai` | `AiProvider` + null/scripted/OpenAI vision evidence adapters |
| `services` | Orchestration (`ImageAnalysisService`, `LabelExtractionService`, `VerificationService`) |
| `persistence` | SQLite access and repositories (schema still deferred) |
| `batch` | Concurrent job scheduling with stability limits (not implemented) |
| `core` | Config, exceptions, timing utilities |

### Persistence

SQLite remains planned for verification/batch records. **Phase 2 does not persist uploads or analysis results.**

### Test data (`test-data/`)

Curated label images for later OCR evaluation. Phase 2 validation/preprocessing tests primarily use **programmatically generated** fixtures in `backend/tests/image_fixtures.py`.

## Separation of responsibilities (hard rules)

- **Do not** put regulatory logic in API route handlers.
- **Do not** put OCR logic inside regulatory rules.
- **Do not** put OpenAI-specific types or SDK calls in verification services; depend on the AI provider interface.
- **Do not** create monolithic files that mix routing, OCR, and rules.
- Business logic must be importable and testable without starting Uvicorn.

## Verification result model

A common result shape (backend Pydantic + frontend TypeScript) represents:

- Field / check name
- Application value
- Detected label value
- Normalized values (when relevant)
- Status: `PASS` | `REVIEW` | `FAIL`
- Confidence (only when actually measured; never invented)
- Explanation / reason
- Decision method (e.g. deterministic rule, fuzzy match, AI assist, human pending)
- Source / detection information
- Processing time (overall required; per-stage optional)

The UI uses these fields to explain **how** a decision was reached.

**Government Health Warning** will be **label-only** regulatory validation (no applicant-supplied warning text required). Implementation awaits rule documentation.

## External dependencies

| Dependency | Role | Failure mode |
|------------|------|--------------|
| OpenCV / Pillow | Preprocessing & quality metrics | Fail validation/preprocess with explicit user-facing error; log internals |
| OCR backend (TBD) | Text detection | Not wired yet |
| RapidFuzz | Fuzzy comparison where appropriate | Deterministic; no external network |
| OpenAI API | Optional eligible REVIEW evidence recovery | Disabled by default; graceful REVIEW retention when unavailable |
| SQLite | Persistence | Deferred for verification schema |

No new third-party packages were added in Phase 2.

## Graceful degradation strategy

1. **AI disabled** (`OPENAI_ENABLED=false`): pipeline completes using deterministic stages only; result metadata notes AI was not used.
2. **AI enabled but unavailable**: provider returns a structured failure; orchestrator does **not** invent answers; affected checks become `REVIEW` with an explicit explanation.
3. **OCR unavailable / low quality**: do not fabricate fields; prefer `REVIEW`. Image quality warnings prepare operators before OCR exists.
4. **Deskew uncertain**: skip transform; record `deskew_skipped_reason` (never silent).
5. **Partial batch failures**: one item’s failure does not abort the entire batch (future).

## Concurrency and batch

The `batch` package owns worker limits (future). Single Review remains the correctness baseline.

## Deployment shape

Docker Compose runs frontend and backend locally. Later HTTPS tunnel exposure does not change internal architecture. A lightweight public-demo access gate is planned but not implemented.

## Phase 3 — OCR evaluation (complete)

- Pluggable providers: `tesseract`, `paddleocr`, `stub`
- Evaluation harness: `python -m app.ocr.evaluate`
- Corpus + ground truth under `test-data/ocr-eval/`
- Recommendation documented in `docs/OCR_EVALUATION.md`: **Tesseract + FAST + 1600px**

### OCR package (`backend/app/ocr/`)

| Module | Responsibility |
|--------|----------------|
| `base.py` | Shared `OcrProvider` / `OcrResult` contract |
| `tesseract_provider.py` | Tesseract adapter |
| `paddle_provider.py` | PaddleOCR adapter (eval candidate; not production) |
| `factory.py` | Provider construction |
| `evaluate/` | Corpus, metrics, runner, reports |

OCR-oriented preprocess profiles live in `preprocessing/ocr_prepare.py` (`fast` / `enhanced`).

## Phase 4 — OCR integration + structured extraction (implemented)

Single Review runs:

`Upload → validate → display/quality → FAST/1600 Tesseract → field extraction → optional one ENHANCED/1200 retry → selection → UI`

| Concern | Implementation |
|---------|----------------|
| Extraction statuses | FOUND / UNCERTAIN / NOT_FOUND (not PASS/REVIEW/FAIL) |
| Retry | Deterministic, observable, at most one ENHANCED pass |
| Selection | Score completeness; do not blindly prefer ENHANCED |
| API | `POST /api/v1/labels/extract` |
| Docs | `docs/FIELD_EXTRACTION.md` |

**Not in Phase 4:** regulatory rules, application-vs-label comparison, OpenAI calls, batch.

### Extraction package (`backend/app/extraction/`)

Per-field extractors + `pipeline.py` + `retry_policy.py`. Terminology lists isolated in `terminology.py`.

## Phase 5–8.5 — Verification contexts (implemented)

Two modes share one pipeline (`VerificationService` → extraction → rules → optional AI → re-rules):

| Mode | Used by | Application data | Rules |
|------|---------|------------------|--------|
| **LABEL_ONLY** | Single Review (default) | Not supplied | Label-field evidence + government warning |
| **APPLICATION_COMPARISON** | Batch Review; optional API | Required brand/class/ABV/net | Compare rules + government warning |

```
Label image
  → validate / FAST OCR / extraction (+ optional ENHANCED retry)
  → rules_for_mode(mode)
  → optional AI evidence (allowlisted REVIEW only)
  → deterministic re-evaluation
  → PASS / REVIEW / FAIL (evaluated checks only)
```

| Concern | Implementation |
|---------|----------------|
| Mode | `VerificationMode` / `verification_mode` on responses |
| API | `POST /api/v1/verify` — file required; `application` JSON optional |
| Aggregation | any FAIL → FAIL; else any REVIEW → REVIEW; else PASS (among evaluated checks) |
| AI | Evidence only; never sets status (see Phase 6 / `docs/AI_FALLBACK.md`) |
| Docs | ADR-024; `docs/RULES.md` |

## Phase 6 — Selective OpenAI vision fallback (implemented)

```
Deterministic verification
  → eligible unresolved REVIEW?
        NO  → return result (PASS/FAIL/ineligible REVIEW: zero AI calls)
        YES → ≤1 OpenAI vision evidence call
  → validate structured evidence
  → merge conservatively
  → re-run deterministic rules
  → final PASS / REVIEW / FAIL
```

| Concern | Implementation |
|---------|----------------|
| Provider | `backend/app/ai/` — OpenAI via httpx; scripted/null for tests |
| Eligibility | Allowlisted reason codes only; `OCR_LOW_QUALITY` alone excluded |
| Human-only | Format/bold/type-size/FOV geometry never AI→PASS |
| Status authority | Deterministic rules only; AI never sets status |
| Cost | Max 1 call/review; resize; timeout; disabled by default |
| Docs | `docs/AI_FALLBACK.md`, ADR-020 |

**Not in Phase 6:** batch processing, public prompt endpoint, AI as compliance authority.

## Current implementation status

| Stage | Status |
|-------|--------|
| Image upload / validation / preprocessing / quality | Phase 2 implemented |
| OCR evaluation + engine selection | **Phase 3 complete** (Tesseract recommended) |
| OCR + structured extraction in Single Review | **Phase 4 complete** |
| Application comparison + selected TTB rules | **Phase 5 complete** |
| Selective OpenAI vision evidence fallback | **Phase 6 complete** |
| Treasury-inspired institutional UI | **Phase 6.5 complete** |
| Batch Review orchestration | **Phase 7 complete** |
| Public access gate / deployment hardening | Deferred |
| SQLite schema | Deferred (batch uses in-memory store) |
