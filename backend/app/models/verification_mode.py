"""
Verification mode: label-only vs application-comparison.

Architectural responsibility: distinguish Single Review (label-first) from Batch/COLA comparison
without duplicating OCR/extraction pipelines.
"""

from __future__ import annotations

from enum import StrEnum


class VerificationMode(StrEnum):
    """
    How verification interprets application data.

    LABEL_ONLY — evaluate label evidence and label-only regulatory checks.
      Application comparison rules are not run (no false REVIEW/FAIL for missing app data).
    APPLICATION_COMPARISON — compare extracted label fields to supplied application values
      (Batch Review today; future COLA integration).
    """

    LABEL_ONLY = "label_only"
    APPLICATION_COMPARISON = "application_comparison"
