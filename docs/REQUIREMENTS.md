# System Requirements

This document translates stakeholder goals into explicit system requirements and acceptance criteria for LabelVerify AI.

**Prototype disclaimer:** The system assists human review. It must not claim to make final regulatory determinations.

## 1. Product purpose

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| PUR-1 | Compare label image content against application data and selected regulatory checks | Each verification run produces per-check results linking application value, detected label value, status, confidence (when measured), explanation, and decision method |
| PUR-2 | Support distilled spirits as the initial product class | Initial field set is limited to Brand Name, Class/Type, Alcohol Content (ABV), Net Contents, and Government Health Warning (label-only for warning text) |
| PUR-3 | Never present outputs as final regulatory determinations | UI and API responses include clear decision-support / human-review framing; no language asserting legal finality |

## 2. Users and usability

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| UX-1 | Primary user is a compliance agent with varying technical skill | Core flows (single verify, view result, mark for review) require no technical jargon in primary copy |
| UX-2 | Important actions are obvious | Primary actions are visible on the main verification surface without being buried in menus |
| UX-3 | Interface is accessible and minimal-training | Labels, status colors/text, and explanations are readable; keyboard-reachable primary controls (to be validated in UI phase) |

## 3. Verification outcomes and explainability

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| RES-1 | Every check returns exactly one of PASS, REVIEW, or FAIL | Enum/status field is constrained to these three values in API and UI models |
| RES-2 | Ambiguous or low-confidence outcomes become REVIEW, not automatic FAIL | Confidence and ambiguity policy routes uncertain cases to REVIEW with an explanation |
| RES-3 | Each result explains why it received its status | `explanation` (or equivalent) is always present and non-empty for each check |
| RES-4 | UI can explain how a decision was reached | Result includes decision method and source/detection information sufficient for display |

## 4. Pipeline and AI philosophy

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| PIP-1 | Follow the planned verification pipeline | Stages remain separable: validation, preprocessing, OCR, extraction, normalization, rules, confidence, optional AI fallback, result |
| PIP-2 | Prefer deterministic methods when possible | Rules and comparisons that do not need AI run without calling the AI provider |
| PIP-3 | External AI is optional and backend-only | AI keyed configuration lives only on the server; browser never receives the API key |
| PIP-4 | Core verification works when AI is unavailable | With `OPENAI_ENABLED=false` or provider errors, the pipeline still returns structured results; AI skip/failure is recorded observably |
| PIP-5 | Do not silently fall back between methods | Any fallback sets observable fields (method, reason) rather than swapping silently |
| PIP-6 | Do not invent confidence values | Confidence is omitted, null, or explicitly “not measured” unless produced by a defined measurement |

## 5. Performance

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| PERF-1 | Normal single-label verification targets &lt; 5 seconds end-to-end | Measured processing time is returned with every verification result; performance testing documents against the target (see PERFORMANCE.md) |
| PERF-2 | Processing time is always returned | API result includes total (and, where useful, stage) timing fields |

## 6. Batch processing

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| BAT-1 | Architecture supports hundreds of label/application pairs | Batch module exists with concurrency controls; does not require redesign of single-verify model |
| BAT-2 | Concurrency must not compromise stability | Configurable concurrency limits and failure isolation per item |
| BAT-3 | Batch results will support filtering and CSV export | Result model and persistence shape support list/filter/export in a later phase (schema readiness, not full UI in Phase 1) |

## 7. Human-in-the-loop

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| HITL-1 | Ambiguous cases require human review | REVIEW status is first-class and surfaced prominently in UI plans |
| HITL-2 | Agents can understand disagreements | Application vs detected values and explanations are shown side by side |

## 8. Regulatory rules governance

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| REG-1 | Do not invent regulatory requirements | Rules are implemented only after documentation with authoritative sources (see RULES.md) |
| REG-2 | Government warning checks must eventually distinguish wording, capitalization, formatting (where detectable), OCR uncertainty, and other source-backed requirements | Rule docs use the RULES.md template sections before implementation |
| REG-3 | Each rule documents PASS / REVIEW / FAIL criteria and limitations | Rule module docstring/doc file includes those sections |

## 9. Security and configuration

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| SEC-1 | Secrets never committed | `.env` gitignored; `.env.example` has placeholders only |
| SEC-2 | OpenAI key never exposed to frontend | No `VITE_` (or equivalent) secret for OpenAI; AI calls only from backend |
| SEC-3 | Uploaded labels are treated as sensitive local artifacts | Uploads are validated in memory and not permanently stored (Phase 2); future persistence must remain gitignored and access-gated |

## 10. Quality and maintainability

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| QUAL-1 | Separation of concerns as listed in ARCHITECTURE.md | No regulatory logic in routes; no OCR inside rules; no OpenAI SDK usage outside AI provider layer |
| QUAL-2 | Business logic testable without the web server | Service/pipeline unit tests import domain modules directly |
| QUAL-3 | Source files document responsibility | File-level docstring/comment states purpose and architectural ownership |
| QUAL-4 | Exceptions are not silently swallowed | Errors are logged/raised or converted to explicit REVIEW/FAIL with explanation |

## 11. Image ingestion and preprocessing (Phase 2)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| IMG-1 | Accept one JPEG, PNG, or WebP label image per request | `POST /api/v1/images/analyze` accepts those formats; PDF rejected with a clear message |
| IMG-2 | Validate content, not client MIME alone | Magic-byte sniff + Pillow decode; mismatch/unsupported rejected |
| IMG-3 | Reject empty, corrupt, oversized, and invalid-dimension images | User-friendly error codes/messages; no stack traces to client |
| IMG-4 | Produce non-destructive display and OCR-prepared representations | Response includes both base64 images; display path is not OCR-enhanced |
| IMG-5 | Assess image quality with GOOD/WARNING/POOR | Measurements and human-readable warnings returned; not regulatory |
| IMG-6 | Measure preprocessing time | `processing_time_ms` and stage timings present on success |
| IMG-7 | Single Review upload UX | Drag/drop + browse, processing state, preview, quality, errors |
| IMG-8 | No permanent upload storage | Analysis completes without writing upload bytes to disk |

## 12. OCR evaluation (Phase 3)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| OCR-1 | Evaluate Tesseract and PaddleOCR (or document blocker) | Harness runs both or records exact technical blocker |
| OCR-2 | Measure compliance-field recovery separately | Brand, class/type, ABV, net, warning scored independently |
| OCR-3 | Compare FAST vs ENHANCED preprocessing | Both profiles in matrix and report |
| OCR-4 | Compare working resolutions | At least 1200 / 1600 / 2200 px (or documented equivalent) |
| OCR-5 | Persist machine- and human-readable results | JSON/CSV + Markdown under `test-data/ocr-eval/results/` |
| OCR-6 | Evidence-based recommendation | `docs/OCR_EVALUATION.md` states recommendation from metrics |

## 13. Structured extraction (Phase 4)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| EXT-1 | Wire Tesseract FAST/1600 into Single Review | `POST /api/v1/labels/extract` runs production OCR path |
| EXT-2 | Extract brand, class/type, ABV, net, warning | Each field returns FOUND / UNCERTAIN / NOT_FOUND with evidence |
| EXT-3 | Preserve raw OCR text and regions | Response includes raw_text and ocr_regions when available |
| EXT-4 | Observable optional ENHANCED/1200 retry | At most one retry; reasons + both timings recorded |
| EXT-5 | Explainable pass selection | Selection reason and scores returned; no silent ENHANCED preference |
| EXT-6 | Frontend extraction review | Single Review shows Extracted Label Information |
| EXT-7 | No regulatory decisions / no OpenAI | No PASS/FAIL rules; no OpenAI calls |

## 14. Deterministic verification (Phase 5)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| VER-1 | Accept label image; optional application JSON | Multipart `POST /api/v1/verify` — label-only by default; application enables comparison mode |
| VER-1a | Label-only vs application-comparison | `VerificationMode`; APP-COMPARE rules omitted in label-only (no false REVIEW/FAIL) |
| VER-2 | Compare brand / class / ABV / net (comparison mode) | Each returns PASS/REVIEW/FAIL with explanation |
| VER-3 | Government warning label-only | Wording/caps checks; bold/size not claimed from OCR |
| VER-4 | Authoritative rule docs | `docs/RULES.md` completed before/with implementation |
| VER-5 | Uncertainty → REVIEW | Never silent FAIL on UNCERTAIN/NOT_FOUND OCR limits |
| VER-6 | Overall aggregation | FAIL > REVIEW > PASS documented |
| VER-7 | Frontend verification workspace | Overall counts + extracted fields + per-check explanations |
| VER-8 | No OpenAI / no batch | Deterministic only (superseded for OpenAI by Phase 6 AI-* requirements; batch still out of scope) |

## 15. Selective OpenAI vision fallback (Phase 6)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| AI-1 | OpenAI behind AiProvider | No OpenAI SDK/types in rules, routes, OCR, or frontend |
| AI-2 | Disabled by default | `OPENAI_ENABLED=false`; app works without API key |
| AI-3 | Deterministic PASS → zero AI calls | Instrumented `ai_assist.outcome=not_needed_pass` |
| AI-4 | Eligible REVIEW only | Allowlisted reason codes; OCR_LOW_QUALITY alone excluded |
| AI-5 | Human-only never AI→PASS | Format/bold/type-size/FOV remain human review |
| AI-6 | Evidence-only structured output | No PASS/REVIEW/FAIL from model |
| AI-7 | Validate then merge then re-verify | Deterministic rules set status after merge |
| AI-8 | Preserve deterministic evidence | Conflicts explainable; AI distinguishable in UI |
| AI-9 | Graceful provider failure | Timeout/exception/rate-limit → retain REVIEW; no 500 |
| AI-10 | Cost budget | ≤1 AI call per review; timeout; image resize |
| AI-11 | No public prompt proxy | AI only inside server verification workflow |
| AI-12 | Frontend indicator | “AI-assisted evidence” only — never “AI says PASS” |
| AI-13 | Tests mocked | CI does not require live OpenAI |

## 16. Institutional UI (Phase 6.5)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| UI-1 | Treasury-inspired institutional system | Navy/blue/gold tokens; no official seal/insignia |
| UI-2 | Prototype designation visible | Persistent prototype + decision-support messaging |
| UI-3 | Clear Single Review hierarchy | Label → Analyze → Results (no application form in primary flow) |
| UI-4 | Scannable verification results | Overall + counts + per-check app/label/explanation |
| UI-5 | Technical details secondary | Expandable disclosures |
| UI-6 | Accessible status | Text + icon + color for PASS/REVIEW/FAIL |
| UI-7 | Reusable shell | Batch Review can share AppShell/tokens later |

## 17. Batch Review (Phase 7)

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| BAT-1 | Orchestration only | Each item uses existing VerificationService |
| BAT-2 | CSV + images | Manifest columns documented; association validated |
| BAT-3 | Bounded concurrency | Configurable; default documented |
| BAT-4 | Item ERROR ≠ FAIL | Processing state separate from verification status |
| BAT-5 | Progress + summary | Actual completed counts; PASS/REVIEW/FAIL/ERROR |
| BAT-6 | Filter + detail + CSV export | Formula-injection safe export |
| BAT-7 | Batch AI budget | Exhaustion → REVIEW with explainable reason |
| BAT-8 | Single/Batch parity | Same inputs → same overall status (tested) |

## Out of scope (current)

- Public access gate / deployment hardening
- Full distilled-spirits standards-of-identity engine
- Claiming bold / type-size compliance from uncalibrated pixels
- SQLite persistence for batch/verification jobs (in-memory for prototype)
- PDF rasterization (format reserved for later; currently rejected)
- PaddleOCR in production workflow
- AI as regulatory decision-maker
- General-purpose prompt / chat endpoint
