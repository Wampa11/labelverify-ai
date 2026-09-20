# Release QA — LabelVerify AI Phase 8 / 8.5 / 8.6

Decision-support prototype QA record. Not a federal authorization package.

**Build / version:** `0.8.0` (+ Phase 8.6 workspace + Excel)  
**MacBook deployment:** not started — pending visual approval

## Phase 8.6 completion

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Two-panel Review Setup / Results workspace | PASS |
| 2 | Single/Batch tabs removed | PASS |
| 3–4 | Accessible Single & Batch modals | PASS |
| 5 | Processing/results in main Results panel | PASS |
| 6–7 | LABEL_ONLY / APPLICATION_COMPARISON unchanged | PASS |
| 8–9 | Empty state + results-weighted layout | PASS |
| 10 | Reduced extracted/check duplication | PASS |
| 11–12 | Single & Batch .xlsx downloads | PASS |
| 13 | Spreadsheet injection defense | PASS |
| 14 | Prototype disclaimer in workbooks | PASS |
| 15 | Verification behavior unchanged | PASS |
| 16–17 | Regression + Playwright | PASS |
| 18 | Ready for visual inspection | PASS |

## Automated tests (post–8.6)

| Suite | Result |
|-------|--------|
| Backend pytest | **122 passed** |
| Backend ruff | **pass** |
| Frontend vitest | **3 passed** |
| Frontend build | **pass** |
| Playwright smoke | **2 passed** |
| Excel generation tests | **4 passed** (`test_excel_reports.py`) |

## Remaining before MacBook go-live

Visual approval of workspace; Compose + in-container Tesseract; Access before public HTTPS.
