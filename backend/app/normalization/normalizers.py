"""
Normalizers for application and detected label values.

Architectural responsibility: deterministic canonicalization before rules/fuzzy match.
"""

from app.core.exceptions import NotImplementedStageError


class ValueNormalizer:
    """Normalizes field strings. Phase 1 exposes the seam only."""

    def normalize(self, field_name: str, value: str | None) -> str | None:
        """
        Return a normalized representation of `value` for `field_name`.

        Not implemented in Phase 1 beyond pass-through of None.
        """
        if value is None:
            return None
        raise NotImplementedStageError(
            "Normalization is not implemented in Phase 1",
            details=f"field_name={field_name!r}",
        )
