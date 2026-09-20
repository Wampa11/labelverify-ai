"""
Synthetic OCR evaluation corpus generator.

Architectural responsibility: create purposeful synthetic label images + ground truth.
These are NOT actual approved TTB labels.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from app.ocr.evaluate.ground_truth import ComplianceFieldTruth, FixtureGroundTruth

GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

DEFAULT_BRAND = "NORTH PEAK DISTILLING"
DEFAULT_CLASS = "Straight Bourbon Whiskey"
DEFAULT_ABV = "45% Alc./Vol."
DEFAULT_ABV_VALUE = "45"
DEFAULT_NET = "750 mL"
DEFAULT_NET_VALUE = "750"


def default_corpus_root() -> Path:
    """Repository test-data/ocr-eval directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend").is_dir() and (parent / "docs").is_dir():
            return parent / "test-data" / "ocr-eval"
    return here.parents[4] / "test-data" / "ocr-eval"


def generate_corpus(corpus_dir: Path | None = None, *, overwrite: bool = True) -> Path:
    """Generate fixtures and ground-truth JSON under corpus_dir."""
    root = corpus_dir or default_corpus_root()
    fixtures_dir = root / "fixtures"
    gt_dir = root / "ground-truth"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    specs = _fixture_specs()
    for spec in specs:
        image_path = fixtures_dir / spec["image_file"]
        gt_path = gt_dir / f"{spec['fixture_id']}.json"
        if image_path.exists() and gt_path.exists() and not overwrite:
            continue
        image = spec["builder"]()
        image.save(image_path, format="PNG")
        truth: FixtureGroundTruth = spec["truth"]
        gt_path.write_text(
            json.dumps(truth.model_dump(), indent=2) + "\n",
            encoding="utf-8",
        )
    readme = root / "README.md"
    readme.write_text(
        "# OCR evaluation corpus\n\n"
        "Synthetic label images for OCR engine selection.\n\n"
        "**Not actual approved TTB labels.**\n",
        encoding="utf-8",
    )
    return root


def _base_truth(
    fixture_id: str,
    image_file: str,
    category: str,
    *,
    notes: str,
    brand: str = DEFAULT_BRAND,
    class_type: str = DEFAULT_CLASS,
    abv: str = DEFAULT_ABV,
    abv_value: str = DEFAULT_ABV_VALUE,
    net: str = DEFAULT_NET,
    net_value: str = DEFAULT_NET_VALUE,
    warning: str = GOVERNMENT_WARNING,
) -> FixtureGroundTruth:
    return FixtureGroundTruth(
        fixture_id=fixture_id,
        image_file=image_file,
        category=category,
        brand_name=ComplianceFieldTruth(exact_text=brand, semantic_value=brand),
        class_type=ComplianceFieldTruth(exact_text=class_type, semantic_value=class_type),
        alcohol_content_abv=ComplianceFieldTruth(
            exact_text=abv,
            semantic_value=abv_value,
        ),
        net_contents=ComplianceFieldTruth(exact_text=net, semantic_value=net_value),
        government_health_warning=ComplianceFieldTruth(
            exact_text=warning,
            semantic_value="GOVERNMENT WARNING",
        ),
        notes=notes,
    )


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_label(
    *,
    width: int = 900,
    height: int = 1200,
    brand: str = DEFAULT_BRAND,
    class_type: str = DEFAULT_CLASS,
    abv: str = DEFAULT_ABV,
    net: str = DEFAULT_NET,
    warning: str = GOVERNMENT_WARNING,
    brand_size: int = 42,
    body_size: int = 28,
    warning_size: int = 16,
    bg: tuple[int, int, int] = (245, 240, 230),
    fg: tuple[int, int, int] = (20, 20, 20),
    decorative: bool = False,
) -> Image.Image:
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    if decorative:
        for i in range(0, width, 40):
            draw.line((i, 0, i // 2, height), fill=(210, 200, 180), width=2)
        draw.ellipse((width - 220, 40, width - 40, 220), outline=(160, 120, 60), width=4)

    y = 80
    draw.text((60, y), brand, fill=fg, font=_font(brand_size))
    y += 70
    draw.text((60, y), class_type, fill=fg, font=_font(body_size))
    y += 50
    draw.text((60, y), abv, fill=fg, font=_font(body_size))
    y += 45
    draw.text((60, y), net, fill=fg, font=_font(body_size))
    y += 80
    # Wrap warning text
    warning_font = _font(warning_size)
    _draw_wrapped(draw, warning, (50, y), width - 100, warning_font, fg)
    return image


def _draw_wrapped(draw, text, origin, max_width, font, fill) -> None:
    x, y = origin
    words = text.split()
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            line = trial
        else:
            draw.text((x, y), line, fill=fill, font=font)
            y += (bbox[3] - bbox[1]) + 4
            line = word
    if line:
        draw.text((x, y), line, fill=fill, font=font)


def _fixture_specs() -> list[dict]:
    return [
        {
            "fixture_id": "clean_high_quality",
            "image_file": "clean_high_quality.png",
            "builder": lambda: _draw_label(),
            "truth": _base_truth(
                "clean_high_quality",
                "clean_high_quality.png",
                "clean",
                notes="Baseline clean synthetic label",
            ),
        },
        {
            "fixture_id": "small_compliance_text",
            "image_file": "small_compliance_text.png",
            "builder": lambda: _draw_label(
                brand_size=28,
                body_size=18,
                warning_size=11,
            ),
            "truth": _base_truth(
                "small_compliance_text",
                "small_compliance_text.png",
                "small_text",
                notes="Smaller compliance typography",
            ),
        },
        {
            "fixture_id": "capitalization_variation",
            "image_file": "capitalization_variation.png",
            "builder": lambda: _draw_label(
                brand="North Peak Distilling",
                class_type="straight bourbon whiskey",
            ),
            "truth": _base_truth(
                "capitalization_variation",
                "capitalization_variation.png",
                "capitalization",
                notes="Mixed/lower case class type",
                brand="North Peak Distilling",
                class_type="straight bourbon whiskey",
            ),
        },
        {
            "fixture_id": "punctuation_apostrophe",
            "image_file": "punctuation_apostrophe.png",
            "builder": lambda: _draw_label(
                brand="O'HARA'S RESERVE",
                class_type="Irish Whiskey",
            ),
            "truth": _base_truth(
                "punctuation_apostrophe",
                "punctuation_apostrophe.png",
                "punctuation",
                notes="Apostrophe in brand",
                brand="O'HARA'S RESERVE",
                class_type="Irish Whiskey",
            ),
        },
        {
            "fixture_id": "rotated_15deg",
            "image_file": "rotated_15deg.png",
            "builder": lambda: _draw_label().rotate(15, expand=True, fillcolor=(245, 240, 230)),
            "truth": _base_truth(
                "rotated_15deg",
                "rotated_15deg.png",
                "rotated",
                notes="Whole-image rotation ~15 degrees",
            ),
        },
        {
            "fixture_id": "perspective_moderate",
            "image_file": "perspective_moderate.png",
            "builder": _perspective_label,
            "truth": _base_truth(
                "perspective_moderate",
                "perspective_moderate.png",
                "perspective",
                notes="Moderate perspective warp",
            ),
        },
        {
            "fixture_id": "low_contrast",
            "image_file": "low_contrast.png",
            "builder": lambda: ImageEnhance.Contrast(_draw_label(fg=(170, 165, 155))).enhance(0.45),
            "truth": _base_truth(
                "low_contrast",
                "low_contrast.png",
                "low_contrast",
                notes="Reduced contrast text",
            ),
        },
        {
            "fixture_id": "mild_blur",
            "image_file": "mild_blur.png",
            "builder": lambda: _draw_label().filter(ImageFilter.GaussianBlur(radius=1.6)),
            "truth": _base_truth(
                "mild_blur",
                "mild_blur.png",
                "blur",
                notes="Mild Gaussian blur",
            ),
        },
        {
            "fixture_id": "glare_overexposure",
            "image_file": "glare_overexposure.png",
            "builder": _glare_label,
            "truth": _base_truth(
                "glare_overexposure",
                "glare_overexposure.png",
                "glare",
                notes="Bright glare patch over part of text",
            ),
        },
        {
            "fixture_id": "cluttered_decorative",
            "image_file": "cluttered_decorative.png",
            "builder": lambda: _draw_label(decorative=True),
            "truth": _base_truth(
                "cluttered_decorative",
                "cluttered_decorative.png",
                "cluttered",
                notes="Decorative lines/ornament behind text",
            ),
        },
        {
            "fixture_id": "partially_unreadable",
            "image_file": "partially_unreadable.png",
            "builder": _damaged_label,
            "truth": _base_truth(
                "partially_unreadable",
                "partially_unreadable.png",
                "difficult",
                notes="Heavy occlusion; expected partial OCR failure",
            ),
        },
    ]


def _perspective_label() -> Image.Image:
    base = _draw_label()
    width, height = base.size
    src = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    dst = np.float32(
        [
            [40, 30],
            [width - 10, 80],
            [width - 60, height - 20],
            [20, height - 60],
        ],
    )
    import cv2

    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        np.asarray(base),
        matrix,
        (width, height),
        borderValue=(245, 240, 230),
    )
    return Image.fromarray(warped)


def _glare_label() -> Image.Image:
    image = _draw_label()
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse((220, 120, 620, 420), fill=(255, 255, 255, 180))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _damaged_label() -> Image.Image:
    image = _draw_label().filter(ImageFilter.GaussianBlur(radius=2.5))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 60, 500, 200), fill=(245, 240, 230))
    draw.rectangle((50, 700, 850, 980), fill=(230, 230, 230))
    return ImageEnhance.Brightness(image).enhance(1.4)
