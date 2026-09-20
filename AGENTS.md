# LabelVerify AI — Agent Instructions

This repository is an AI-assisted alcohol label verification **prototype** for federal regulatory workflow support.

Read and follow:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/REQUIREMENTS.md`
- `docs/RULES.md`
- `docs/FIELD_EXTRACTION.md`
- `docs/AI_FALLBACK.md`
- `docs/UI_DESIGN.md`
- `docs/BATCH_REVIEW.md`
- `docs/PERFORMANCE.md`
- `docs/DECISIONS.md`
- `.cursor/rules/*.mdc`

## Non-negotiables

- Not a final regulatory decision system
- PASS / REVIEW / FAIL only; ambiguity → REVIEW
- No invented rules, confidence, or silent fallbacks
- Architecture changes need an ADR in `docs/DECISIONS.md`
- OpenAI produces evidence only; never regulatory status
- Batch must reuse `VerificationService` — no duplicate compliance logic
- UI follows `docs/UI_DESIGN.md` (Treasury-inspired; no official seals)

## Current phase

Phase 8.9 (Selective OCR Escalation for Brand Recovery) is implemented on this branch.

- Tesseract FAST primary; brand-region retry on suspicion; optional RapidOCR behind flags
- See `docs/OCR_ESCALATION.md`, `docs/OCR_EVALUATION_PHASE88.md`
- Do **not** begin MacBook deployment until visual approval

Read also: `docs/DEPLOYMENT.md`, `docs/RELEASE_QA.md`, `docs/UI_DESIGN.md`, `docs/FIELD_EXTRACTION.md`, `docs/AI_FALLBACK.md`, `docs/OCR_EVALUATION.md`
