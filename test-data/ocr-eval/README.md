# OCR evaluation corpus

Synthetic label images for OCR engine selection, plus optional manual decorative
flat-label fixtures for Phase 8.8 evaluation metadata only.

**Not actual approved TTB labels.**

Decorative fixtures (if present):

- `decorative_maple_creek.png`
- `decorative_whispering_pine.png`

Ground-truth JSON for those IDs is evaluation-only and must not be hard-coded
into production extractors or rules.

Phase 8.8 spike:

```bash
cd backend
python -m app.ocr.evaluate.phase88_spike
```
