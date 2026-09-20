"""
Known distilled-spirits class/type terminology for extraction assistance only.

Architectural responsibility: isolated word lists — not regulatory classification.
"""

# Lowercase tokens/phrases used to locate class/type lines in OCR text.
CLASS_TYPE_PHRASES: tuple[str, ...] = (
    "straight bourbon whiskey",
    "bourbon whiskey",
    "tennessee whiskey",
    "irish whiskey",
    "scotch whisky",
    "single malt",
    "blended whiskey",
    "blended whisky",
    "rye whiskey",
    "canadian whisky",
    "cognac",
    "armagnac",
    "brandy",
    "vodka",
    "gin",
    "rum",
    "tequila",
    "mezcal",
    "liqueur",
    "cordial",
    "neutral spirits",
    "grain spirits",
    "whiskey",
    "whisky",
)

CLASS_TYPE_KEYWORDS: tuple[str, ...] = (
    "bourbon",
    "whiskey",
    "whisky",
    "vodka",
    "gin",
    "rum",
    "tequila",
    "mezcal",
    "brandy",
    "cognac",
    "liqueur",
    "scotch",
    "rye",
)
