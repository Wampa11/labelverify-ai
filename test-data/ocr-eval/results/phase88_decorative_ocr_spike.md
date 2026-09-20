# Phase 8.8 — Decorative Typography OCR Evaluation Spike

Generated: `2026-09-20T00:08:04.210268+00:00`

## Environment
- **python:** 3.12.10
- **platform:** Windows-11-10.0.26200-SP0
- **machine:** AMD64

## Providers
- Requested: tesseract, easyocr, rapidocr
- Available: tesseract, easyocr, rapidocr

## Init / memory
- RSS after warmup: `738.828125` MB
- `tesseract` init: `207.64010000857525` ms
- `easyocr` init: `1636.710699996911` ms
- `rapidocr` init: `334.33109999168664` ms

## Corpus FAST/1600 aggregates

| Provider | Brand exact | Brand norm | Mean fields/5 | Median ms | p95 ms | Max ms | Success |
|---|---:|---:|---:|---:|---:|---:|---:|
| tesseract | 0.69 | 0.85 | 4.08 | 445 | 567 | 570 | 0.92 |
| easyocr | 0.69 | 0.69 | 4.00 | 3791 | 5087 | 5768 | 1.00 |
| rapidocr | 0.85 | 0.85 | 4.69 | 821 | 1141 | 1416 | 1.00 |

### Per-field recovery (corpus FAST)

- **tesseract:** brand=0.85, class=0.77, abv=0.77, net=0.85, warning=0.85
- **easyocr:** brand=0.69, class=0.77, abv=0.92, net=0.92, warning=0.69
- **rapidocr:** brand=0.85, class=0.92, abv=1.00, net=1.00, warning=0.92

## Decorative label raw brand region previews

### decorative_maple_creek — corpus_fast / tesseract / production_default
- brand_exact=False brand_norm=True fields=5/5 total_ms=570
- brand_region: `APLE CREEK`

### decorative_maple_creek — corpus_fast / easyocr / production_default
- brand_exact=False brand_norm=False fields=4/5 total_ms=1851
- brand_region: `MAPLE | CREEK`

### decorative_maple_creek — corpus_fast / rapidocr / production_default
- brand_exact=True brand_norm=True fields=5/5 total_ms=821
- brand_region: `MAPLE CREEK`

### decorative_whispering_pine — corpus_fast / tesseract / production_default
- brand_exact=False brand_norm=False fields=2/5 total_ms=377
- brand_region: `BOURBON WHISKEY`

### decorative_whispering_pine — corpus_fast / easyocr / production_default
- brand_exact=False brand_norm=False fields=4/5 total_ms=2344
- brand_region: `Whisperigg | BOURBON WHISKEY | Pine`

### decorative_whispering_pine — corpus_fast / rapidocr / production_default
- brand_exact=False brand_norm=False fields=4/5 total_ms=869
- brand_region: `Whispering | Pine | BOURBON WHISKEY`

### decorative_maple_creek — decorative_enhanced / tesseract / enhanced_control
- brand_exact=False brand_norm=False fields=4/5 total_ms=662
- brand_region: `2020 EST. APLE CRE DISTILLERY KENTUCKY STRAIGHT BOURBON WHISKEY DISTILLED AND BOTTLED`

### decorative_whispering_pine — decorative_enhanced / tesseract / enhanced_control
- brand_exact=False brand_norm=False fields=1/5 total_ms=564
- brand_region: `di BOURBON WHISKEY`

### decorative_maple_creek — tesseract_psm / tesseract[default] / default
- brand_exact=False brand_norm=True fields=5/5 total_ms=566
- brand_region: `APLE CREEK`

### decorative_maple_creek — tesseract_psm / tesseract[psm3_auto] / psm3_auto
- brand_exact=False brand_norm=True fields=5/5 total_ms=614
- brand_region: `APLE CREEK`

### decorative_maple_creek — tesseract_psm / tesseract[psm6_block] / psm6_block
- brand_exact=False brand_norm=False fields=3/5 total_ms=552
- brand_region: `2020 EST. ee =i) FEA ee = DISTILLERY ———————— KENTUCKY STRAIGHT SSS`

### decorative_maple_creek — tesseract_psm / tesseract[psm7_line] / psm7_line
- brand_exact=False brand_norm=False fields=0/5 total_ms=367
- brand_region: `ms |`

### decorative_maple_creek — tesseract_psm / tesseract[psm11_sparse] / psm11_sparse
- brand_exact=False brand_norm=True fields=5/5 total_ms=527
- brand_region: `APLE CREE`

### decorative_maple_creek — tesseract_psm / tesseract[psm12_sparse_osd] / psm12_sparse_osd
- brand_exact=False brand_norm=True fields=5/5 total_ms=1094
- brand_region: `APLE CREE`

### decorative_whispering_pine — tesseract_psm / tesseract[default] / default
- brand_exact=False brand_norm=False fields=2/5 total_ms=342
- brand_region: `BOURBON WHISKEY`

### decorative_whispering_pine — tesseract_psm / tesseract[psm3_auto] / psm3_auto
- brand_exact=False brand_norm=False fields=2/5 total_ms=339
- brand_region: `BOURBON WHISKEY`

### decorative_whispering_pine — tesseract_psm / tesseract[psm6_block] / psm6_block
- brand_exact=False brand_norm=False fields=0/5 total_ms=438
- brand_region: `ead.” pen WHISKEY`

### decorative_whispering_pine — tesseract_psm / tesseract[psm7_line] / psm7_line
- brand_exact=False brand_norm=False fields=0/5 total_ms=275
- brand_region: ``

### decorative_whispering_pine — tesseract_psm / tesseract[psm11_sparse] / psm11_sparse
- brand_exact=False brand_norm=True fields=4/5 total_ms=437
- brand_region: `BOURBON WHISKEY`

### decorative_whispering_pine — tesseract_psm / tesseract[psm12_sparse_osd] / psm12_sparse_osd
- brand_exact=False brand_norm=True fields=4/5 total_ms=831
- brand_region: `BOURBON WHISKEY`

### decorative_maple_creek — region_upper45 / tesseract / upper_45pct
- brand_exact=False brand_norm=False fields=0/5 total_ms=278
- brand_region: `wae CREEK`

### decorative_maple_creek — region_prominent_band / tesseract / prominent_upper_words
- brand_exact=True brand_norm=True fields=2/5 total_ms=325
- brand_region: `MAPLE CREEK`

### decorative_maple_creek — region_upper45 / easyocr / upper_45pct
- brand_exact=False brand_norm=False fields=0/5 total_ms=487
- brand_region: `MAPLE | CREEK`

### decorative_maple_creek — region_prominent_band / easyocr / prominent_upper_words
- brand_exact=False brand_norm=False fields=1/5 total_ms=618
- brand_region: `MAPLE | CREEK`

### decorative_maple_creek — region_upper45 / rapidocr / upper_45pct
- brand_exact=True brand_norm=True fields=1/5 total_ms=452
- brand_region: `MAPLE CREEK`

### decorative_maple_creek — region_prominent_band / rapidocr / prominent_upper_words
- brand_exact=True brand_norm=True fields=2/5 total_ms=478
- brand_region: `MAPLE CREEK`

### decorative_whispering_pine — region_upper45 / tesseract / upper_45pct
- brand_exact=False brand_norm=False fields=1/5 total_ms=293
- brand_region: `we BOURBON WHISKEY`

### decorative_whispering_pine — region_prominent_band / tesseract / prominent_upper_words
- brand_exact=False brand_norm=False fields=1/5 total_ms=294
- brand_region: `ae e BOURBON WHISKEY`

### decorative_whispering_pine — region_upper45 / easyocr / upper_45pct
- brand_exact=False brand_norm=False fields=1/5 total_ms=777
- brand_region: `Whisperigg | Pine = | BOURBON WHISKEY`

### decorative_whispering_pine — region_prominent_band / easyocr / prominent_upper_words
- brand_exact=False brand_norm=False fields=1/5 total_ms=883
- brand_region: `Whisperigg | Pine | BOURBON WHISKEY`

### decorative_whispering_pine — region_upper45 / rapidocr / upper_45pct
- brand_exact=False brand_norm=False fields=1/5 total_ms=557
- brand_region: `Whispering | BOURBON WHISKEY`

### decorative_whispering_pine — region_prominent_band / rapidocr / prominent_upper_words
- brand_exact=False brand_norm=False fields=1/5 total_ms=487
- brand_region: `Whispering | BOURBON WHISKEY`

See JSON artifact for full OCR text.

