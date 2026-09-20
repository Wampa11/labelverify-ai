"""
Base contract for regulatory rule modules.

Architectural responsibility: define how rules consume evidence and return FieldCheckResult.
Implementations must cite authoritative sources in docs before coding behavior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.extraction import ExtractedField
from app.models.verification import ApplicationData, FieldCheckResult
from app.models.verification_mode import VerificationMode


@dataclass
class RuleContext:
    """
    Inputs available to a rule.

    Rules consume application data (when provided) + extraction evidence only — never OCR SDKs.
    """

    application: ApplicationData | None
    fields: dict[str, ExtractedField]
    mode: VerificationMode = VerificationMode.APPLICATION_COMPARISON
    quality_status: str | None = None
    brand_pass_ratio: float = 95.0
    brand_review_ratio: float = 85.0
    class_pass_ratio: float = 97.0
    abv_epsilon: float = 0.05
    net_ml_epsilon: float = 0.5
    extra: dict[str, object] = field(default_factory=dict)


class ComplianceRule(ABC):
    """A single deterministic compliance or consistency check."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Stable rule identifier (matches documentation)."""

    @property
    @abstractmethod
    def check_name(self) -> str:
        """Human-readable check name shown in results."""

    @abstractmethod
    def evaluate(self, context: RuleContext) -> FieldCheckResult:
        """
        Evaluate evidence and return an explainable check result.

        Must not call OCR libraries or OpenAI SDKs directly.
        """
