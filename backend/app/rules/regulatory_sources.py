"""
Centralized authoritative regulatory source metadata for Phase 5 rules.

Architectural responsibility: keep citations out of scattered business logic.
Does not invent requirements — only records documented source references.
"""

from __future__ import annotations

from typing import TypedDict


class RegulatorySource(TypedDict):
    """One authoritative citation used by rule documentation/code comments."""

    citation: str
    title: str
    url: str
    retrieved: str


RETRIEVED = "2026-09-19"

SOURCES: dict[str, RegulatorySource] = {
    "cfr_5_63": {
        "citation": "27 CFR § 5.63",
        "title": "Mandatory label information",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.63",
        "retrieved": RETRIEVED,
    },
    "cfr_5_64": {
        "citation": "27 CFR § 5.64",
        "title": "Brand name",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.64",
        "retrieved": RETRIEVED,
    },
    "cfr_5_65": {
        "citation": "27 CFR § 5.65",
        "title": "Alcohol content",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.65",
        "retrieved": RETRIEVED,
    },
    "cfr_5_70": {
        "citation": "27 CFR § 5.70",
        "title": "Net contents",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-E/section-5.70",
        "retrieved": RETRIEVED,
    },
    "cfr_5_subpart_i": {
        "citation": "27 CFR Part 5 Subpart I",
        "title": "Standards of Identity for Distilled Spirits",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-5/subpart-I",
        "retrieved": RETRIEVED,
    },
    "cfr_16_21": {
        "citation": "27 CFR § 16.21",
        "title": "Mandatory health warning statement",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.21",
        "retrieved": RETRIEVED,
    },
    "cfr_16_22": {
        "citation": "27 CFR § 16.22",
        "title": "General requirements (legibility, bold, type size)",
        "url": "https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22",
        "retrieved": RETRIEVED,
    },
    "ttb_ds_brand_label": {
        "citation": "TTB Distilled Spirits Labeling — Mandatory Label Information",
        "title": "Brand label / same field of vision guidance",
        "url": (
            "https://www.ttb.gov/regulated-commodities/beverage-alcohol/"
            "distilled-spirits/ds-labeling-home/ds-brand-label"
        ),
        "retrieved": RETRIEVED,
    },
}

# Exact statutory warning text from 27 CFR § 16.21 (whitespace may be collapsed for comparison).
STATUTORY_GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)
