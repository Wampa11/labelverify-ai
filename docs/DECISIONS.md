# Architecture Decision Records

Running log of important technical decisions and trade-offs for LabelVerify AI.

Format per entry: context, decision, consequences.  
**Do not substantially change established architecture, schema, or patterns without adding an ADR that states the problem, why the current design is insufficient, and the proposed change.**

---

## ADR-001: Monorepo with separate `frontend/` and `backend/`

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** The prototype needs a React UI and a Python verification pipeline. Reviewers must navigate quickly.

**Decision:** Use a single repository with top-level `frontend/`, `backend/`, `docs/`, and `test-data/` rather than separate repos or a heavyweight Nx/Turborepo monorepo tool.

**Consequences:** Simple clone-and-run story; shared docs at repo root; no forced shared package for types (contracts duplicated carefully between Pydantic and TypeScript until a later ADR says otherwise).

---

## ADR-002: Pluggable OCR via interface, implementation deferred

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** OCR quality and licensing vary; stakeholder requirements forbid coupling business logic to one library before evaluation.

**Decision:** Define an OCR port/protocol in `backend/app/ocr/` with a stub adapter. Select and implement a concrete engine only after testing.

**Consequences:** Pipeline and rules depend on OCR result models, not vendor APIs. Phase 1 has no real OCR.

---

## ADR-003: AI behind a provider abstraction; disabled by default

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** OpenAI may help ambiguous cases but must not be required, and the API key must never reach the browser.

**Decision:** `backend/app/ai/` exposes a provider interface and a null/disabled provider. Configuration via `OPENAI_ENABLED` / `OPENAI_API_KEY` in server env only. No OpenAI calls in Phase 1.

**Consequences:** Verification services depend on the interface. Graceful degradation is the default path until an OpenAI adapter is added behind the same interface.

---

## ADR-004: SQLite for prototype persistence

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Local demo and take-home simplicity matter more than multi-user cloud scale.

**Decision:** Use SQLite through the `persistence` package.

**Consequences:** Easy Docker/volume story; may need a later ADR to move to Postgres if concurrent writers or hosting requirements demand it.

---

## ADR-005: Three-way status enum (PASS / REVIEW / FAIL)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Ambiguous results must not auto-fail; humans must review uncertainty.

**Decision:** All checks use exactly `PASS`, `REVIEW`, or `FAIL`. Low confidence maps to `REVIEW`.

**Consequences:** UI and exports stay simple; confidence never silently coerces to FAIL.

---

## ADR-006: pyproject.toml for backend packaging

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Need a standard Python 3.12 project with optional dev dependencies (pytest).

**Decision:** Use `backend/pyproject.toml` as the single backend dependency manifest (`pip install -e ".[dev]"`).

**Consequences:** No parallel `requirements.txt` unless an ADR introduces one for a specific deploy constraint.

---

## ADR-007: Vite + Tailwind + shadcn/ui scaffolding without full UI

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 1 must establish frontend toolchain without building the product UI.

**Decision:** Scaffold Vite React-TS, Tailwind, and shadcn-oriented config (`components.json`) with a minimal App shell and empty component folders.

**Consequences:** Later UI work installs shadcn components into `components/ui` as needed; no speculative screens in Phase 1.

---

## ADR-008: Folder layout matches stakeholder sketch with `core/` for cross-cutting concerns

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Stakeholder requested explicit packages for pipeline stages. Cross-cutting config/exceptions/timing need a home without polluting `services/`.

**Decision:** Adopt the requested layout and place config, exceptions, and timing in `backend/app/core/`.

**Consequences:** Clear ownership; documented here so the extra `core/` package is intentional, not drift.

---

## ADR-009: Docker Compose for local multi-service run

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Local run and later HTTPS tunnel exposure should not require bespoke host setup.

**Decision:** Provide root `docker-compose.yml` plus Dockerfiles for frontend and backend (minimal stubs in Phase 1).

**Consequences:** Reviewers can bring up services consistently; images will grow as implementations land.

---

## ADR-010: Dual display / OCR image representations (no disk persistence)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 2 must prepare images for future OCR without destroying the operator preview, and must not permanently store uploads.

**Decision:** For each successful analysis, derive (1) an orientation-corrected RGB **display** image and (2) a separate **OCR-prepared** grayscale pipeline output. Return both as base64 in the API response. Keep processing in memory for the request only; do not write uploads to `UPLOAD_DIR` in this phase.

**Consequences:** Larger HTTP payloads than path references; simpler security posture for the prototype; future persistence requires a new ADR.

---

## ADR-011: Image quality statuses GOOD / WARNING / POOR

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Operators need early feedback when a photo is unlikely to OCR well, without inventing AI confidence or regulatory grades.

**Decision:** Use `GOOD`, `WARNING`, and `POOR` from deterministic heuristics (resolution, Laplacian blur, brightness, contrast, clipping). Document thresholds as prototype engineering heuristics in `quality.py` and PERFORMANCE/ARCHITECTURE docs.

**Consequences:** Clear operator language; must never be presented as a compliance determination.

---

## ADR-012: UI shell with Single Review and Batch Review modes

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Stakeholder UX decision: one application shell, two primary modes.

**Decision:** Implement `AppShell` with **Single Review** (active) and **Batch Review** (disabled placeholder). No separate marketing homepage.

**Consequences:** Primary actions remain on the main surface; Batch work can land without navigation redesign.

---

## ADR-013: Conservative deskew only; perspective deferred

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Geometry correction helps OCR but wrong warps destroy text. Bottle curvature is hard.

**Decision:** Implement optional planar deskew when estimated angle is in ~0.5°–12° with sufficient edges; otherwise skip and record reason. Provide `PerspectiveCorrectionPlan` placeholder without auto perspective warp.

**Consequences:** Safer preprocessing; angled bottle labels may still need better capture or a later ADR.

---

## ADR-014: Government Health Warning is label-only

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Stakeholders clarified warning validation should not depend on applicant-supplied warning text.

**Decision:** Future Government Health Warning checks evaluate the label image (and OCR evidence) only. ApplicationData will not require a warning text field for that check.

**Consequences:** Simplifies application intake; rule docs must reflect label-only evaluation.

---

## ADR-015: Lightweight public access gate (deferred)

**Date:** 2026-09-19  

**Status:** Accepted (deferred implementation)  

**Context:** Public prototype will need a light gate, not a full account system.

**Decision:** Do not implement authentication in Phase 2. Preserve API/UI structure so a gate can wrap routes later.

**Consequences:** Local demo remains open; tunnel exposure must wait for the gate or equivalent control.

---

## ADR-016: OCR evaluation harness and Tesseract selection

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 3 required evidence-based OCR selection between Tesseract and PaddleOCR, comparing FAST vs ENHANCED preprocessing and multiple working resolutions, without implementing regulatory logic.

**Decision:**

1. Extend `OcrResult` with timing, warnings, geometry, and preprocessing profile metadata; keep confidence optional/never invented.
2. Add optional extras `ocr-tesseract`, `ocr-paddle`, `ocr-eval` and CLI `python -m app.ocr.evaluate`.
3. Use an isolated Python 3.12 `.venv-ocr` for evaluation (Paddle has no Python 3.14 wheels).
4. **Select Tesseract** as primary engine with default **FAST** preprocessing and **1600px** max edge; keep ENHANCED/1200 as optional harder path.
5. Document PaddleOCR as **not selected** after Windows OneDNN inference failures prevented accuracy scoring.

**Consequences:** Phase 4 can wire Tesseract behind the existing port. Paddle remains an adapter for future Linux/Docker re-evaluation. Dual-engine fallback is not introduced.

---

## ADR-017: FAST vs ENHANCED OCR preprocessing profiles

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 2 ENHANCED path (CLAHE/denoise/deskew/unsharp) can dominate latency on large images. Evaluation needed to know if it buys field recovery.

**Decision:** Introduce `OcrPreprocessProfile.FAST` and `.ENHANCED` in `preprocessing/ocr_prepare.py`. Benchmark both. Default recommendation for production OCR is FAST; ENHANCED remains available.

**Consequences:** Phase 2 display pipeline behavior unchanged; OCR prep is explicit and configurable for evaluation and future verification wiring.

---

## ADR-018: Structured extraction statuses and observable ENHANCED retry

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 4 must answer “what does the label appear to say?” without regulatory PASS/FAIL, while using Tesseract FAST/1600 by default and ENHANCED/1200 only when extraction evidence is weak.

**Decision:**

1. Use extraction statuses **FOUND / UNCERTAIN / NOT_FOUND** (never PASS/REVIEW/FAIL for extraction).
2. Keep per-field extractors behind `extraction/` with shared OCR evidence models.
3. Trigger at most one ENHANCED retry from documented deterministic conditions; record reasons and both pass timings.
4. Select the pass with better field-completeness score; on conflict, preserve UNCERTAIN rather than inventing certainty.
5. Expose `POST /api/v1/labels/extract` and Single Review “Extracted Label Information” UI.
6. Do not call OpenAI; reserve `ai_fallback_hints` only.

**Consequences:** Regulatory rules remain Phase 5+. Brand/class extractors stay conservative. PaddleOCR stays out of production.

---

## ADR-019: Deterministic verification, fuzzy bands, and aggregation

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 5 must compare application data with extracted label fields and apply selected objective TTB/CFR requirements without inventing rules or treating uncertainty as FAIL.

**Decision:**

1. Document every implemented rule in `docs/RULES.md` with 27 CFR / TTB citations before coding.
2. Keep citations centralized in `backend/app/rules/regulatory_sources.py`.
3. Overall status aggregation: any FAIL → FAIL; else any REVIEW → REVIEW; else PASS. Prototype summary only.
4. Brand comparison: NFKC + casefold + whitespace + apostrophe normalization; RapidFuzz `token_sort_ratio` bands default **≥95 PASS**, **≥85 REVIEW**, **&lt;85 FAIL** when extraction is FOUND — configurable engineering heuristics, scores in technical details only.
5. Class/type: exact/near-exact only (≥97); partial or ambiguous → REVIEW; clear category contradiction → FAIL. No full Subpart I engine.
6. ABV: numeric compare with epsilon 0.05 pp; proof alone without % ABV statement → REVIEW (27 CFR § 5.65).
7. Net contents: compare milliliters after unit normalization.
8. Government warning: label-only wording/caps checks; bold and type-size → limitations / not machine-verifiable (never claim PASS for bold from OCR).
9. Emit `reason_code` + `ai_assist_eligible` for Phase 6 triage; OpenAI still disabled.
10. API: multipart `POST /api/v1/verify` with `file` + `application` JSON.

**Consequences:** Fuzzy thresholds are not universally validated; they must remain documented heuristics. Visual formatting requirements stay human-only. Phase 6 can target AI-eligible REVIEW codes without touching format-not-verifiable cases.

---

## ADR-020: Selective OpenAI vision evidence fallback

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 6 needs optional recovery when deterministic OCR/extraction leaves eligible fields unresolved, without making OpenAI a regulatory decision-maker or requiring network access for normal operation.

**Decision:**

1. Keep OpenAI behind `AiProvider`; implement `OpenAiProvider` with httpx Chat Completions + vision + JSON object response. No OpenAI types in rules, routes, OCR, or frontend.
2. Default `OPENAI_ENABLED=false`. Missing key with enabled=true → unavailable null provider; app starts and verifies normally.
3. Model id isolated in `OPENAI_MODEL` (default `gpt-4o-mini` — multimodal, structured JSON, cost-conscious prototype choice).
4. Invoke AI only when overall status is REVIEW and at least one check has an allowlisted reason (`BRAND_AMBIGUOUS`, `CLASS_TYPE_AMBIGUOUS`, `WARNING_PARTIAL`, `EXTRACTION_UNCERTAIN`, narrowly `ABV_FORMAT_REVIEW`). `OCR_LOW_QUALITY` alone and human-only format codes never trigger AI. PASS and FAIL make zero AI calls.
5. One combined evidence package / max one call per review; timeout and failures retain deterministic REVIEW; never HTTP 500 solely for AI failure.
6. AI returns structured evidence only (categorical HIGH/MEDIUM/LOW confidence). Validate → conservative merge → **re-run deterministic rules**. AI never sets PASS/REVIEW/FAIL.
7. Preserve deterministic evidence; conflicts → UNCERTAIN / CONFLICTING_EVIDENCE explainability.
8. Prompt-injection defense: label text is untrusted evidence; no public prompt endpoint.
9. Frontend: restrained “AI-assisted evidence” indicator only.
10. Document in `docs/AI_FALLBACK.md`. No batch implementation in Phase 6.

**Consequences:** Deterministic path performance unchanged when AI is unused. Eligible REVIEW cases may add bounded latency/cost when enabled. Live OpenAI remains optional for operators; CI uses mocked providers only.

---

## ADR-021: Treasury-inspired institutional UI (not official endorsement)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 6.5 must make LabelVerify feel appropriate for federal compliance personnel without implying it is an official Treasury product, and without redesigning verification behavior.

**Decision:**

1. Adopt a Treasury-**inspired** institutional palette (deep navy, restrained blues, off-white surfaces, subtle gold accent) centralized as CSS variables / Tailwind tokens.
2. Keep semantic PASS / REVIEW / FAIL colors separate from institutional blue; always pair with text and icons.
3. Build a reusable `AppShell` (header, workflow tabs, prototype designation, decision-support banner, footer) for Single Review and future Batch Review.
4. Use an independent geometric document/label mark — **never** the official Treasury seal or agency insignia.
5. Prefer borders, typography, and spacing over gradients, glass, glow, or AI novelty imagery.
6. Single Review workflow: Application → Label → explicit **Verify Label** → scannable Results; technical details remain disclosed secondary content.
7. Document the system in `docs/UI_DESIGN.md`.

**Consequences:** Frontend tests update for accessible names and explicit verify action. No backend/rule/OCR/AI logic changes. Batch UI must reuse the same shell and tokens when approved.

---

## ADR-022: Batch Review as VerificationService orchestration

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Stakeholders need a prototype path for ~200–300 applications without duplicating compliance logic or implying production capacity.

**Decision:**

1. Implement `BatchOrchestrator` that validates CSV+images and invokes existing `VerificationService` per item.
2. Bound concurrency (`BATCH_MAX_CONCURRENCY`, default **2**) and max items (**300**).
3. Wrap AI with `BudgetAwareAiProvider` (`BATCH_AI_MAX_CALLS=25`, `BATCH_AI_CONCURRENCY=1`); budget exhaustion → REVIEW, not FAIL/ERROR.
4. Keep processing state (`QUEUED`/`PROCESSING`/`COMPLETED`/`ERROR`) separate from PASS/REVIEW/FAIL.
5. Use **in-memory** job store for the local prototype; do not add SQLite/job queues in Phase 7.
6. Export CSV with formula-injection sanitization.
7. Enable Batch Review UI in the Phase 6.5 shell; reuse `VerificationResultsPanel` for item detail.
8. Document in `docs/BATCH_REVIEW.md`.

**Consequences:** Single/Batch parity is a tested invariant. CI uses scripted OCR for 300-item load; real OCR benchmarks remain host-specific and must not be over-claimed.

---

## ADR-023: Phase 8 release-candidate Docker hardening and access gate

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phases 1–7 delivered a working prototype. Phase 8 must package it for a dedicated MacBook with protected HTTPS access without adding product features, durable queues, or custom auth systems.

**Decision:**

1. **Feature freeze** except defect fixes proven by testing.
2. Ship production Docker images: backend (Python slim + **in-image Tesseract eng** + OpenCV/Pillow deps) and frontend (Vite build + nginx). Compose publishes only the frontend port; nginx same-origin proxies `/api`, `/health`, `/ready`.
3. Restart `unless-stopped`; healthchecks; no hot reload; no secrets in images; `.dockerignore` excludes venvs/node_modules/`.env`.
4. Distinguish `/health/live` (process up) from `/ready` (local deps, e.g. Tesseract). **OpenAI is never required for readiness.**
5. Access control prefers **Cloudflare Access** (or equivalent) in front of the tunnel after local validation. Optional nginx basic-auth remains a documented fallback — no general registration system in-app.
6. Version stamp via `APP_VERSION` / `VITE_APP_VERSION` (footer + `X-App-Version`).
7. Document deployment and QA in `docs/DEPLOYMENT.md` and `docs/RELEASE_QA.md`. Live OpenAI stays opt-in and out of CI.
8. Do not replace Tesseract with PaddleOCR in this phase; any Linux Paddle experiment is isolated and non-blocking.

**Consequences:** Evaluators can clone → configure `.env` → `docker compose up` → demo Single/Batch. MacBook architecture must be confirmed at deploy time. Compose validation on a host without Docker remains a gate for full RC sign-off.

---

## ADR-024: Label-only Single Review vs application-comparison verification

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Requiring manual application entry before Single Review weakened the prototype’s demonstration of label inspection. Batch Review and future COLA integration still need application-vs-label comparison. Duplicating OCR/rules pipelines would violate architecture boundaries.

**Decision:**

1. Introduce `VerificationMode`: `LABEL_ONLY` | `APPLICATION_COMPARISON`.
2. Single shared `VerificationService.verify(...)` path: extraction → `run_rules(mode)` → optional AI evidence → re-rules. No second pipeline.
3. **LABEL_ONLY** (Single Review default; no application JSON): run label-field evidence rules + government warning. Application-comparison rules (`RULE-DS-*-APP-COMPARE`) are **not evaluated** — absence of application data is never a regulatory FAIL/REVIEW.
4. **APPLICATION_COMPARISON** (Batch manifest today; optional API `application` form field; future COLA): existing brand/class/ABV/net compare rules + government warning.
5. Primary Single Review UI is label-first: Upload → **Analyze Label** → results (extracted fields + applicable checks). No application form in the primary workflow.
6. AI eligibility allowlist unchanged; AI still never sets PASS/FAIL.
7. Production COLA integration could supply application values without manual re-entry; that integration is not claimed to exist in this prototype.

**Consequences:** Single and Batch intentionally differ in input workflow while sharing OCR/extraction/verification services. Counts and overall status reflect only evaluated checks for the active mode.

---

## ADR-025: Unified analyst workspace and Excel primary reports

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Top-level Single/Batch tabs felt like separate apps. Evaluators need one compliance workstation and a usable Office workbook, not a CSV rename.

**Decision:**

1. Replace mode tabs with a two-panel workspace: **Review Setup** (~30%) and **Results** (~70%).
2. Single Label and Batch Review open as accessible modals; processing and results stay in the main Results panel.
3. Preserve LABEL_ONLY (Single) and APPLICATION_COMPARISON (Batch) verification semantics — no OCR/rule/AI changes.
4. Add `openpyxl`-based Excel (.xlsx) generation in `backend/app/reporting/` with formula-injection sanitization.
5. Primary UI export: **Download Excel Report**. CSV batch export remains available via API for compatibility.
6. Single workbook: `Review Summary`. Batch workbook: `Batch Summary` + `Review Results`.

**Consequences:** Cleaner evaluator UX; Docker images pick up `openpyxl` via backend dependency. Visual approval still required before MacBook deployment.

---

## ADR-026: Extraction integrity and evidence reconciliation (Phase 8.7)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Realistic flat-label OCR exposed contaminated field displays (proof glued into net contents), weak brand scoring (isolated producer descriptors competing with brands), unjustified PASS on noisy regex hits, and incomplete AI reconciliation when OCR recovered only proof or partial class/type text.

**Decision:**

1. Preserve **raw OCR** separately from **normalized** structured values for ABV/proof/net; never display surrounding OCR as the primary normalized value.
2. Strengthen deterministic parsers so ABV, proof, and net contents are isolated from recognized patterns; proof must not contaminate net contents; proof alone is not a mandatory ABV statement.
3. Improve general brand scoring (prominence, position, continuity, weak-standalone penalties, clip suspicion) without fixture-specific brand strings; material conflicts → UNCERTAIN.
4. Confidence-gate PASS: noisy/low-confidence pattern hits stay UNCERTAIN even when a regex substring exists.
5. Expand AI eligibility (including `PROOF_ONLY_NO_PERCENT_STATEMENT`, `EXTRACTION_NOT_FOUND` / `WARNING_MISSING`, `net_contents`) while keeping one-call-per-review and never letting AI set regulatory status.
6. Reconcile OCR↔AI: mutually reinforcing evidence may supplement; material conflicts → UNCERTAIN + `CONFLICTING_EVIDENCE`.
7. Keep primary reviewer explanations concise; put raw OCR, method, and reconciliation under Technical Details.

**Consequences:** Cleaner label-only PASS/REVIEW behavior on difficult artwork; artistic labels still tend toward REVIEW when OCR is weak unless optional AI recovers consistent evidence. No UI layout or deployment changes.

---

## ADR-027: AI fallback observability and brand integrity gate (Phase 8.7.1)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Manual flat-label reruns showed (1) malformed brand OCR such as `hispering =` receiving PASS, and (2) Whispering Pine–shaped REVIEW results with no visible AI recovery. Unit tests of merge/eligibility alone did not prove the service path was observable or that OpenAI was configured at runtime.

**Decision:**

1. Keep AI eligibility on REVIEW + allowlisted reason codes; do not invent brand corrections.
2. Add a general brand integrity gate (OCR artifacts, leading lowercase, edge clip signals, left-adjacent orphan fragments, near-tied suffix conflicts) → UNCERTAIN → REVIEW → AI-eligible when configured.
3. Expand `ai_assist` summary + structured logs (`ai_configured`, `ai_eligible`, fields, outcomes, merge results) without logging secrets or image payloads.
4. Surface evidence path under Technical Details / Timing; health exposes `openai_fallback` / model without the API key.
5. Service-level mocked integration tests cover combined AI call, disabled provider, and malformed brand.

**Consequences:** High-confidence wrong OCR without integrity signals (e.g. clean `APLE CREEK` with no alternate evidence) may still PASS until independent conflict evidence exists — documented limitation, not a dictionary fix.

---

## ADR-028: Phase 8.8 decorative typography OCR evaluation (no production swap)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Diagnostics showed first-loss on two flat labels is Tesseract (Maple → `APLE CREEK`; Whispering → missing brand tokens). Need measured evidence for local OCR alternatives before any architecture change.

**Decision:**

1. Keep **Tesseract** as the production OCR provider; no VerificationService / rules / AI merge changes in this phase.
2. Evaluate **RapidOCR** (ONNX) and **EasyOCR** behind the existing `OcrProvider` port with optional extras only (`ocr-rapidocr`, `ocr-easyocr`, `ocr-eval-phase88`). Do not re-fight Windows PaddleOCR OneDNN in this spike.
3. Add decorative fixtures + Phase 8.8 spike harness (`app.ocr.evaluate.phase88_spike`) including limited Tesseract PSM variants and general region OCR experiments.
4. Document measurements in `docs/OCR_EVALUATION_PHASE88.md`. Defer production architecture selection; measured lean is **keep A now**, explore **C** (escalation / region re-OCR) later — not a wholesale **B** replace yet.

**Consequences:** Eval venv may carry heavy optional deps; production installs stay lean. Future escalation must still not promote AI evidence marked `unable_to_determine`.

---

## ADR-029: Selective brand OCR escalation (Phase 8.9)

**Date:** 2026-09-19  

**Status:** Accepted  

**Context:** Phase 8.8 showed Tesseract prominent-band re-OCR recovers Maple-like leading-character misses, and RapidOCR improves decorative brands but is too costly to run on every label. Whole-label `APLE CREEK`-style FOUND can still PASS without integrity trips.

**Decision:**

1. Keep **Tesseract FAST** as primary whole-label OCR.
2. After pass selection, run **selective brand-region Tesseract OCR** when brand evidence is UNCERTAIN/NOT_FOUND or soft FOUND suspicions (prominent left inset / short leading token on tall glyphs) — no fixture brand strings.
3. Reconcile whole vs region evidence; stronger clean region may supersede suspicious whole-label; material conflicts → UNCERTAIN.
4. Optional **RapidOCR** (`SECONDARY_OCR_ENABLED`, default false) only if brand still unresolved after region Tesseract; prefer the same brand region crop.
5. Observe via `brand_escalation` summary + `evidence_method` suffixes; never require secondary OCR for app readiness; do not weaken AI `unable_to_determine` rejection.

**Consequences:** Slightly higher latency only on escalated labels; clean labels stay on the FAST path. Operators must explicitly enable and package RapidOCR for secondary recovery.
