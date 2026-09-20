# Field Extraction

**Status:** Phase 4 implemented  
**Scope:** Structured extraction from OCR — **not** regulatory verification.

## Critical distinction

| Concern | Question answered | Phase |
|---------|-------------------|-------|
| **Extraction** | What does the label appear to say? | Phase 4 (this doc) |
| **Regulatory verification** | Does what the label says satisfy the applicable requirement? | Later |

Extraction statuses are **FOUND**, **UNCERTAIN**, and **NOT_FOUND**.  
Do **not** use PASS / REVIEW / FAIL here — those are reserved for regulatory checks.

## Pipeline

```
Upload → Validate → Display preprocess/quality
       → Preprocess FAST / 1600px → Tesseract OCR
       → Structured field extraction
       → Extraction quality evaluation
       → optional one ENHANCED / 1200px OCR retry
       → deterministic result selection
       → frontend extraction review
```

PaddleOCR remains an evaluation candidate only and is not used in this path.

## Models

Each `ExtractedField` includes:

- `raw_text` (preserved OCR wording)
- `normalized_value` / `normalized_numeric` / `normalized_unit` when useful
- `status` (FOUND / UNCERTAIN / NOT_FOUND)
- `ocr_regions` (text, confidence, bounding box, provider, preprocessing profile)
- `extraction_method`, `explanation`, `candidates`
- `ai_fallback_hints` (packaging hooks for a future AI fallback — unused in Phase 4)

## Field strategies

| Field | Strategy | Notes |
|-------|----------|-------|
| **Alcohol content** | Regex for Alc./Vol., ABV, Alcohol by Volume, Proof | Proof→ABV uses documented engineering transform `ABV = proof / 2` (US convention). Both preserved when present. |
| **Net contents** | Regex for quantity + unit | Units canonicalized to `mL` or `L`; raw text kept. |
| **Government warning** | Detect `GOVERNMENT WARNING` + following lines | Detect/extract only. No statutory wording, bold, size, or placement checks. |
| **Class / type** | Terminology phrases/keywords (isolated config) | Assistance only — not final regulatory class. Multiple hits → UNCERTAIN. |
| **Brand name** | Conservative layout heuristics (upper/larger text, exclude ABV/net/warning/class) | Does not assume first or largest line. Ambiguous scores → UNCERTAIN. |

Extractors live under `backend/app/extraction/` (`alcohol_content.py`, `net_contents.py`, `government_warning.py`, `class_type.py`, `brand_name.py`) and are coordinated by `pipeline.py`.

## Retry logic (one ENHANCED retry max)

After FAST extraction, retry with ENHANCED/1200 **only** when evidence suggests material benefit. Triggers include:

- Government warning NOT_FOUND
- Two or more critical fields NOT_FOUND
- Unusually sparse OCR text/words
- Multiple UNCERTAIN fields **and** at least one NOT_FOUND **and** image quality WARNING/POOR

**Does not** retry solely because quality is not GOOD.

Retry is observable: reasons, both pass timings, and which result was used are recorded on the response.

## Result selection

When both passes exist, score FOUND=2, UNCERTAIN=1, NOT_FOUND=0 across critical fields.

- Prefer the higher score
- On ties, prefer fewer NOT_FOUND, else prefer FAST (latency)
- Material numeric/text conflicts between passes mark the selected field UNCERTAIN

ENHANCED is never preferred blindly.

## Known weaknesses

- Brand and class/type remain the hardest fields (OCR eval + heuristics).
- Warning body may be UNCERTAIN when OCR truncates compliance text.
- Bounding boxes are in OCR working-image coordinates; display highlight scales by aspect-fit mapping.
- Decorative/cluttered/glare fixtures may correctly return UNCERTAIN or NOT_FOUND.

## Phase 8.7 integrity notes

- Normalized net/ABV values are pattern-isolated; raw OCR lines stay in `raw_text` / Technical Details.
- Noisy net matches (e.g. garbage prefix + `750mL`) are UNCERTAIN, not automatic PASS.
- Brand scoring penalizes isolated producer descriptors and treats clipped leading OCR as UNCERTAIN.
- Optional AI may recover unresolved fields; conflicts remain UNCERTAIN (`CONFLICTING_EVIDENCE`).

## OpenAI (Phase 6)

Extraction still never calls OpenAI. `ai_fallback_hints` may carry candidates for later optional vision evidence recovery during **verification** (see `docs/AI_FALLBACK.md`). Phase 4 extract API behavior is unchanged.

## API

`POST /api/v1/labels/extract` — multipart `file` → `LabelExtractionResponse` with display preview + `extraction` payload.
