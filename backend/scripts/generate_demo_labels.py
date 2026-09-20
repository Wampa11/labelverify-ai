"""Generate synthetic demo label JPEGs for evaluator onboarding (not official COLA art)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines: list[str] = []
    chunk: list[str] = []
    for word in words:
        trial = (" ".join(chunk + [word])).strip()
        if draw.textlength(trial, font=font) <= max_width or not chunk:
            chunk.append(word)
        else:
            lines.append(" ".join(chunk))
            chunk = [word]
    if chunk:
        lines.append(" ".join(chunk))
    return lines


def make_label(path: Path, lines: list[str], size: tuple[int, int] = (1000, 1400)) -> None:
    # Mid-tone paper avoids false POOR from washout heuristics on near-white canvases.
    img = Image.new("RGB", size, (210, 205, 195))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, size[0] - 40, size[1] - 40), outline=(30, 45, 70), width=4)

    title_font = load_font(42)
    body_font = load_font(30)
    warn_font = load_font(22)
    y = 100
    max_w = size[0] - 160

    for i, text in enumerate(lines):
        if not text:
            y += 28
            continue
        font = title_font if i == 0 else body_font
        if text.startswith("GOVERNMENT WARNING"):
            font = warn_font
        for line in wrap_text(text, font, max_w, draw):
            draw.text((80, y), line, fill=(10, 10, 10), font=font)
            y += int(font.size * 1.35) if hasattr(font, "size") else 36
        y += 18

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=93)
    print(f"wrote {path} ({path.stat().st_size} bytes)")


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "test-data"
    make_label(
        root / "demo" / "old-tom-demo.jpg",
        [
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "45% Alc./Vol.",
            "750 mL",
            "",
            WARNING,
        ],
    )
    make_label(
        root / "batch-sample" / "old-tom-001.jpg",
        [
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "45% Alc./Vol.",
            "750 mL",
            "",
            WARNING,
        ],
    )
    make_label(
        root / "batch-sample" / "stones-throw-002.jpg",
        [
            "Stone's Throw",
            "Straight Bourbon Whiskey",
            "40% Alc./Vol.",
            "750 mL",
            "",
            WARNING,
        ],
    )
    make_label(
        root / "batch-sample" / "demo-review-003.jpg",
        [
            "North Peak Distilling",
            "Bourbon Whis",
            "45% Alc./Vol.",
            "750 mL",
            "",
            WARNING,
        ],
    )


if __name__ == "__main__":
    main()
