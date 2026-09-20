"""
Ground-truth schema and loaders for the OCR evaluation corpus.

Architectural responsibility: machine-readable expected compliance-relevant text
for synthetic fixtures (not actual TTB-approved labels).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class ComplianceFieldTruth(BaseModel):
    """Expected text for one compliance-relevant field."""

    exact_text: str
    semantic_value: str | None = Field(
        default=None,
        description="Important recoverable value when exact OCR wording may vary",
    )


class FixtureGroundTruth(BaseModel):
    """Ground truth for one OCR evaluation fixture."""

    fixture_id: str
    image_file: str
    category: str
    brand_name: ComplianceFieldTruth
    class_type: ComplianceFieldTruth
    alcohol_content_abv: ComplianceFieldTruth
    net_contents: ComplianceFieldTruth
    government_health_warning: ComplianceFieldTruth
    notes: str = ""
    is_synthetic: bool = True
    disclaimer: str = (
        "Synthetic evaluation fixture only. Not an actual approved TTB label."
    )


def load_ground_truth(path: Path) -> FixtureGroundTruth:
    """Load one ground-truth JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return FixtureGroundTruth.model_validate(data)


def load_corpus_manifest(corpus_dir: Path) -> list[FixtureGroundTruth]:
    """Load all ground-truth JSON files from corpus_dir/ground-truth/."""
    gt_dir = corpus_dir / "ground-truth"
    if not gt_dir.is_dir():
        raise FileNotFoundError(f"Ground-truth directory not found: {gt_dir}")
    fixtures: list[FixtureGroundTruth] = []
    for path in sorted(gt_dir.glob("*.json")):
        fixtures.append(load_ground_truth(path))
    return fixtures
