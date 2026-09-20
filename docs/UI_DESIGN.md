# UI design system — Treasury-inspired institutional prototype

LabelVerify uses a restrained federal-enterprise visual language. It is **not** official Treasury software and must not use official seals.

## Tokens (summary)

| Token | Role |
|-------|------|
| `--navy` | Header / brand |
| `--primary` | Primary actions (**Analyze Label**, **Download Excel Report**) |
| `--accent-gold` | Subtle emphasis |
| `--pass` / `--review` / `--fail` | Semantic status |

## Shell

Header + prototype designation + decision-support banner + restrained utility footer. **No Single/Batch tabs** (Phase 8.6).

- **Lettermark:** geometric LV monogram (inline SVG) — product identity, not a Treasury seal
- **Footer:** `LabelVerify · Prototype Decision Support` + application version (`VITE_APP_VERSION`, default `0.8.0`)
- Full independent-prototype / non-endorsement language lives in README and Excel report context, not the shell footer

## Workspace (Phase 8.6)

Two primary panels (~30/70):

| Panel | Role |
|-------|------|
| **Review Setup** | Compact institutional tiles (Single Label / Batch Review) → accessible modals |
| **Results** | Intentional empty state (“Ready for review”) → processing → single or batch view |

### Modals

- Analyze Single Label — image upload, Analyze Label / Cancel  
- Process Batch — manifest + images, Validate, Process Batch / Cancel  
Focus trap, Escape, return focus to trigger.

### Results

- Empty: restrained prompt to begin  
- Single: overall finding, label image, extracted fields (“what was read”), checks (“what was concluded”), Excel download  
- Batch: counts, filters, table, item detail, Excel download  

Avoid repeating identical detected strings in both extracted fields and check summaries.

## Excel reports

Evaluator-facing primary export is formatted `.xlsx` (not CSV renamed). Prototype disclaimer included; no official Treasury branding.

## Do not introduce

Gradients, glass, giant rounded cards, purple AI styling, chatbot visuals, decorative AI imagery, excessive animation.
