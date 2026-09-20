# Batch Review (Phase 7)

**Status:** Implemented  
**Role:** Orchestration only — each item calls `VerificationService` in **application-comparison** mode. UI entry is the Batch Review modal in the unified workspace (ADR-025). Excel is the primary evaluator export; CSV remains at `GET /api/v1/batches/{id}/export`.

## Purpose

Demonstrate peak-workflow support (~200–300 applications) on a local prototype host.
This is a **scalability demonstration**, not a production throughput claim.

## Architecture

```
CSV manifest + label images
  → validation (association / formats / size)
  → BatchOrchestrator (bounded concurrency)
  → VerificationService per item  (identical Single Review path)
  → BudgetAwareAiProvider (batch AI caps)
  → in-memory job store (pollable)
  → summary / filter / CSV export
```

**No separate OCR, extraction, rules, or AI eligibility logic for batch.**

## Manifest schema

Required columns (header, UTF-8):

| Column | Maps to |
|--------|---------|
| `filename` | Image basename (must match upload) |
| `brand_name` | Application brand |
| `class_type` | Application class/type |
| `alcohol_content` | Application ABV (`alcohol_content_abv`) |
| `net_contents` | Application net contents |

Example: `test-data/batch-sample/sample-manifest.csv`  
API: `GET /api/v1/batches/sample-manifest`

## Validation (before process)

Blocking issues include: missing columns, empty manifest, duplicate filenames, missing images, duplicate uploads, unsupported formats, unsafe/path-like names, invalid application values, batch over `BATCH_MAX_ITEMS`.

Unreferenced images are reported; processing may proceed if every row uniquely matches.

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `BATCH_MAX_ITEMS` | 300 | Stakeholder peak order of magnitude |
| `BATCH_MAX_CONCURRENCY` | 2 | Conservative for local Tesseract CPU |
| `BATCH_AI_MAX_CALLS` | 25 | Batch-wide AI call budget |
| `BATCH_AI_CONCURRENCY` | 1 | Concurrent AI recoveries |

Concurrency default **2** was chosen over 1/4 as a balance: Tesseract is CPU-heavy; higher concurrency is not automatically faster on a laptop.

## Item lifecycle vs verification status

| Processing state | Meaning |
|------------------|---------|
| `QUEUED` / `PROCESSING` / `COMPLETED` / `ERROR` | Orchestration lifecycle |

| Overall status | Meaning |
|----------------|---------|
| `PASS` / `REVIEW` / `FAIL` | Deterministic verification (only when COMPLETED) |

**ERROR ≠ FAIL.** One item exception does not stop the batch.

## AI in batch

Same eligibility as Single Review. `BudgetAwareAiProvider` enforces batch call budget.
When exhausted: remaining eligible cases stay **REVIEW** with explainable `AI_BUDGET_EXHAUSTED` (no batch failure).

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/batches/sample-manifest` | Sample CSV |
| POST | `/api/v1/batches/validate` | Validate only |
| POST | `/api/v1/batches` | Create + start |
| GET | `/api/v1/batches/{id}` | Progress / summary |
| GET | `/api/v1/batches/{id}/items/{item_id}` | Detail |
| GET | `/api/v1/batches/{id}/export` | Results CSV |

## Persistence

**In-memory only** for this prototype (single dedicated machine). Models are structured so SQLite/job queues can be added later without changing VerificationService.

## CSV export

Includes status, application fields, per-check statuses, AI flag, timing, error text.
Cells that look like spreadsheet formulas are prefixed with `'` (injection protection).
No stack traces or secrets.

## Security

Untrusted CSV/images; basename-only filenames; size/row limits; bounded concurrency; no client path execution; AI only inside verification.

## Limitations

- Jobs lost on process restart
- No multi-user job isolation
- 300-item CI test uses mocked OCR (scripted), not 300 live Tesseract timings
- Real OCR batch timing depends on host/image complexity

## Future COLA integration

Manifest columns are the stand-in for system-supplied application data. Production could replace CSV upload with an authenticated application feed while keeping the same orchestrator → VerificationService path.
