# Regulatory Rules Documentation

**Product scope:** Distilled spirits (initial prototype only)  
**Status:** Phase 5 — selected objective checks implemented  
**Disclaimer:** LabelVerify AI is decision-support only. These checks do **not** constitute final regulatory determinations. A qualified human must review ambiguous results.

**Do not invent regulatory requirements.** Every implemented rule below cites primary TTB/CFR sources. Retrieval date for eCFR links in this file: **2026-09-19**.

---

## How to add a rule

1. Complete the template section below with authoritative sources.
2. Implement in `backend/app/rules/` only after documentation is complete.
3. Keep rule code free of OCR libraries and OpenAI SDKs; consume extraction/application evidence only.
4. Record significant design choices in `docs/DECISIONS.md`.

---

## Overall verification aggregation

| Condition | Overall status |
|-----------|----------------|
| Any applicable check is **FAIL** | **FAIL** |
| Else any applicable check is **REVIEW** | **REVIEW** |
| Else all applicable checks are **PASS** | **PASS** |

Overall status is a **prototype verification summary**, not a final regulatory determination.

**Uncertainty rule:** Extraction `UNCERTAIN` or insufficient OCR evidence → check **REVIEW**. Never convert uncertainty into **FAIL**.

---

## Authoritative source index

| Topic | Primary citation | URL |
|-------|------------------|-----|
| Mandatory label information (brand, class/type, alcohol same FOV; net contents elsewhere) | 27 CFR § 5.63 | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.63 |
| Brand name | 27 CFR § 5.64 | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.64 |
| Alcohol content (% alcohol by volume; proof optional alongside) | 27 CFR § 5.65 | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.65 |
| Net contents | 27 CFR § 5.70 | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.70 |
| Class/type designations | 27 CFR Part 5 Subpart I (standards of identity) | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-I |
| Health warning mandatory wording | 27 CFR § 16.21 | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.21 |
| Health warning legibility / bold / type size | 27 CFR § 16.22 | https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22 |
| TTB distilled spirits labeling overview | TTB DS labeling (brand label) | https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/ds-labeling-home/ds-brand-label |
| TTB mandatory checklist (guidance) | TTB DS labeling checklist PDF | https://www.ttb.gov/system/files/images/labeling-ds/ds-labeling-checklist.pdf |

Centralized machine-readable metadata: `backend/app/rules/regulatory_sources.py`.

---

### Rule ID: RULE-DS-BRAND-APP-COMPARE

**Requirement being evaluated**  
Application brand name should match the brand name appearing on the distilled spirits label (mandatory brand name per 27 CFR § 5.64 / § 5.63). This prototype check evaluates **application-vs-label consistency**, not whether a brand name is “misleading” under § 5.64(b).

**Product scope**  
Distilled spirits — initial prototype

**Fields involved**  
Brand Name (application + extracted label)

**Authoritative source(s)**  
- 27 CFR § 5.63(a)(1) — brand name required in same field of vision with class/type and alcohol content  
- 27 CFR § 5.64(a) — label must include a brand name  
- TTB Distilled Spirits Labeling: Mandatory Label Information (brand label page)

**What constitutes PASS**  
Extracted brand is FOUND; after documented comparison normalization (Unicode NFKC, casefold, whitespace collapse, and conservative apostrophe unification), strings are equal **or** RapidFuzz similarity is at/above the configured high-confidence match band (engineering heuristic; see ADR-019).

**What constitutes REVIEW**  
- Extraction UNCERTAIN or NOT_FOUND  
- Similarity in the ambiguous band  
- Conflicting extraction evidence  
- Missing application brand  

**What constitutes FAIL**  
Extraction FOUND with high confidence of mismatch (similarity below the low band) against a provided application brand.

**Decision method**  
Normalized deterministic comparison; RapidFuzz only for residual near-matches. Similarity score reported in technical details — **not** regulatory certainty.

**Inputs required**  
Application `brand_name`; extracted `brand_name` field (status, raw_text, normalized_value).

**Known limitations**  
Does not evaluate trade-name vs. bottler-name substitution nuances, misleading brand issues, or multi-brand layouts. Fuzzy bands are engineering heuristics validated on a small fixture set.

**Related tests**  
`backend/tests/test_verification_rules.py`, `test-data/verification/`

**Reason codes**  
`BRAND_MATCH`, `BRAND_MISMATCH`, `BRAND_AMBIGUOUS`, `EXTRACTION_UNCERTAIN`, `EXTRACTION_NOT_FOUND`, `APPLICATION_VALUE_MISSING`

---

### Rule ID: RULE-DS-CLASS-TYPE-APP-COMPARE

**Requirement being evaluated**  
Application class/type designation should be consistent with the class/type (or other designation) on the label (mandatory under 27 CFR § 5.63(a)(2) and Subpart I). This phase does **not** implement the full standards-of-identity framework.

**Product scope**  
Distilled spirits — initial prototype

**Fields involved**  
Class / Type (application + extracted label)

**Authoritative source(s)**  
- 27 CFR § 5.63(a)(2)  
- 27 CFR Part 5 Subpart I (class and type designations)  
- TTB DS mandatory label information guidance

**What constitutes PASS**  
Extraction FOUND; normalized application and label designations match exactly (case/whitespace-insensitive).

**What constitutes REVIEW**  
- Extraction UNCERTAIN or NOT_FOUND  
- Partial / truncated designation relative to application  
- Near-similar but not identical wording that could be OCR noise or a legally meaningful difference  
- Missing application class/type  

**What constitutes FAIL**  
Extraction FOUND; clear high-confidence contradiction (e.g., different spirit categories such as “Bourbon Whiskey” vs “Vodka”) after normalization.

**Decision method**  
Conservative normalized equality first; very limited fuzzy only for minor OCR character noise; otherwise REVIEW rather than aggressive equivalence.

**Inputs required**  
Application `class_type`; extracted `class_type`.

**Known limitations**  
Does not classify products under Subpart I or decide legality of a designation. Phase 4 extraction weakness for class/type intentionally biases toward REVIEW.

**Related tests**  
`backend/tests/test_verification_rules.py`

**Reason codes**  
`CLASS_TYPE_MATCH`, `CLASS_TYPE_MISMATCH`, `CLASS_TYPE_AMBIGUOUS`, `EXTRACTION_UNCERTAIN`, `EXTRACTION_NOT_FOUND`, `APPLICATION_VALUE_MISSING`

---

### Rule ID: RULE-DS-ABV-APP-COMPARE-AND-FORMAT

**Requirement being evaluated**  
(1) Application alcohol content (percent alcohol by volume) should match the alcohol content stated on the label.  
(2) The label must state alcohol content as a **percentage of alcohol by volume** (27 CFR § 5.65). Proof may appear in addition but does not replace the mandatory percentage statement.

**Product scope**  
Distilled spirits — initial prototype

**Fields involved**  
Alcohol Content / ABV (application + extracted label); optional proof evidence from extraction

**Authoritative source(s)**  
- 27 CFR § 5.65(a)–(b) — must be stated as percentage of alcohol by volume; authorized formats/abbreviations (`alc`, `%`, `vol`, slash form, etc.)  
- 27 CFR § 5.65(b)(1)(i) — proof may be stated in addition, same FOV as mandatory % ABV statement  
- 27 CFR § 5.65(c) — manufacturing tolerance ±0.3 percentage points (actual vs labeled) — used only as context; application-vs-label mismatches larger than a tiny engineering epsilon are FAIL when extraction is FOUND  
- TTB DS labeling checklist — alcohol content format notes

**What constitutes PASS**  
- Extraction FOUND with a percentage ABV statement evidence; application ABV parses; absolute difference ≤ configured epsilon (default 0.05 pp)  
- Format evidence shows an authorized % alcohol-by-volume style statement (not proof-only)

**What constitutes REVIEW**  
- Extraction UNCERTAIN / NOT_FOUND  
- Only proof recovered without clear % ABV statement on the label evidence  
- Unparseable application ABV  
- Ambiguous format after OCR  

**What constitutes FAIL**  
Extraction FOUND with clear % ABV; application ABV parses; absolute difference exceeds epsilon (e.g., 45% vs 40%).

**Decision method**  
Numeric comparison of ABV; separate format gate for mandatory % ABV statement. Proof preserved in explanation when present.

**Inputs required**  
Application `alcohol_content_abv`; extracted `alcohol_content` (raw, normalized_numeric, explanation/source).

**Known limitations**  
Does not measure type size or FOV geometrically. Does not verify actual bottled strength vs label (lab analysis). “ABV” alone as the sole mandatory statement is treated conservatively: if OCR shows only “ABV” without an authorized § 5.65 pattern, REVIEW (format not clearly satisfied).

**Related tests**  
`backend/tests/test_verification_rules.py`

**Reason codes**  
`ABV_MATCH`, `ABV_MISMATCH`, `ABV_FORMAT_REVIEW`, `PROOF_ONLY_NO_PERCENT_STATEMENT`, `EXTRACTION_UNCERTAIN`, `EXTRACTION_NOT_FOUND`, `APPLICATION_VALUE_MISSING`

---

### Rule ID: RULE-DS-NET-CONTENTS-APP-COMPARE

**Requirement being evaluated**  
Application net contents should match the net contents statement on the label/container (27 CFR § 5.70 / § 5.63(b)(2)).

**Product scope**  
Distilled spirits — initial prototype

**Fields involved**  
Net Contents (application + extracted label)

**Authoritative source(s)**  
- 27 CFR § 5.63(b)(2)  
- 27 CFR § 5.70  
- TTB DS labeling checklist (metric formats such as mL / L)

**What constitutes PASS**  
Extraction FOUND; application and label volumes are equivalent after unit normalization (e.g., 750 mL == 0.75 L).

**What constitutes REVIEW**  
Extraction UNCERTAIN / NOT_FOUND; unparseable application value; missing application net contents.

**What constitutes FAIL**  
Extraction FOUND; clear non-equivalent volumes (e.g., 750 mL vs 1 L).

**Decision method**  
Parse to milliliters; compare with small relative epsilon.

**Inputs required**  
Application `net_contents`; extracted `net_contents`.

**Known limitations**  
Does not verify blown-in glass markings not present in the uploaded image. Does not enforce type-size from pixels (no real-world scale).

**Related tests**  
`backend/tests/test_verification_rules.py`

**Reason codes**  
`NET_CONTENTS_MATCH`, `NET_CONTENTS_MISMATCH`, `EXTRACTION_UNCERTAIN`, `EXTRACTION_NOT_FOUND`, `APPLICATION_VALUE_MISSING`

---

### Rule ID: RULE-DS-GOVERNMENT-WARNING-LABEL

**Requirement being evaluated**  
The alcoholic beverage health warning statement must appear on the label with the exact wording prescribed in 27 CFR § 16.21, and “GOVERNMENT WARNING” must appear in capital letters and bold type per § 16.22. This check is **label-only** (no application field).

**Product scope**  
Distilled spirits — initial prototype (warning applies broadly to alcoholic beverages under Part 16)

**Fields involved**  
Government Health Warning (extracted label only)

**Authoritative source(s)**  
- 27 CFR § 16.21 — mandatory warning text (exact statement)  
- 27 CFR § 16.22(a)(2) — “GOVERNMENT WARNING” in capital letters and bold type  
- 27 CFR § 16.22(b) — minimum type sizes by container volume  
- TTB DS labeling checklist (health warning statement checklist items)

**Required statutory text (§ 16.21)**  

```
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects.
(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.
```

**What constitutes PASS**  
OCR/extraction recovers the warning with FOUND status; normalized wording matches the statutory text (allowing documented whitespace/line-break collapsing); and when OCR preserves letter case, the heading characters are uppercase `GOVERNMENT WARNING`.

**What constitutes REVIEW**  
- Extraction UNCERTAIN or NOT_FOUND (including OCR/image limitations)  
- Partial wording  
- Case of heading not reliably preserved by OCR  
- **Bold type** — not machine-verifiable from ordinary OCR → REVIEW with `FORMAT_NOT_MACHINE_VERIFIABLE`  
- **Physical type size / characters-per-inch** — not machine-verifiable without calibrated real-world scale → REVIEW / not evaluated for size  
- Contrasting background / separate-and-apart placement — not reliably measurable → REVIEW limitation note  

**What constitutes FAIL**  
Extraction FOUND (or sufficient text) and recovered warning differs **materially** from statutory wording (missing required clauses or substituted text) with high confidence.

**Decision method**  
Deterministic wording comparison + conservative capitalization check when case is available. Formatting sub-requirements that vision cannot establish remain REVIEW / not machine-verifiable.

**Inputs required**  
Extracted `government_warning` (raw_text, status, regions). Image quality flags may inform REVIEW explanations.

**Known limitations**  
Bold, type size, contrast, and placement are **honestly not verified as PASS** by this prototype. Absence of warning on a poor OCR image → REVIEW (not FAIL). Clear complete mismatch on a clean FOUND extraction → FAIL.

**Related tests**  
`backend/tests/test_verification_rules.py`

**Reason codes**  
`WARNING_PRESENT_MATCH`, `WARNING_MISSING`, `WARNING_PARTIAL`, `WARNING_WORDING_MISMATCH`, `WARNING_CAPS_REVIEW`, `FORMAT_NOT_MACHINE_VERIFIABLE`, `EXTRACTION_UNCERTAIN`, `OCR_LOW_QUALITY`

---

## Phase 6 AI eligibility (evidence recovery only)

OpenAI does **not** implement regulatory rules. When enabled, it may recover **text evidence** for allowlisted REVIEW reason codes only. Deterministic rules re-run after merge. See `docs/AI_FALLBACK.md` and ADR-020.

| AI-eligible reason codes | Human-only / never AI trigger alone |
|--------------------------|-------------------------------------|
| `BRAND_AMBIGUOUS` | `FORMAT_NOT_MACHINE_VERIFIABLE` |
| `CLASS_TYPE_AMBIGUOUS` | `NOT_MACHINE_VERIFIABLE` |
| `WARNING_PARTIAL` | `WARNING_CAPS_REVIEW` |
| `EXTRACTION_UNCERTAIN` | `OCR_LOW_QUALITY` (alone) |
| `ABV_FORMAT_REVIEW` (narrow) | Bold / type-size / FOV geometry limitations |

Overall PASS or FAIL → zero AI calls. Rules modules must not import OpenAI SDKs.

---

## Implementation checklist (per rule)

- [x] Template completed with authoritative sources  
- [x] PASS / REVIEW / FAIL criteria explicit  
- [x] Limitations documented  
- [x] Rule module file header states responsibility  
- [x] Unit tests cover PASS, REVIEW, and FAIL paths without the web server  
- [x] No silent fallbacks; explanations always populated  
