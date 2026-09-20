"""
Spreadsheet cell sanitization for formula-injection defense.

Architectural responsibility: neutralize formula-trigger prefixes in user-controlled text.
"""

from __future__ import annotations

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_spreadsheet_value(value: object) -> str:
    """
    Return a safe literal string for Excel/CSV cells.

    Values beginning with = + - @ (or tab/CR) are prefixed with a single quote
    so spreadsheet apps treat them as text, not formulas.
    """
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text
