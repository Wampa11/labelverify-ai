"""
Regulatory rule package for distilled-spirits verification.

Architectural responsibility: deterministic PASS/REVIEW/FAIL checks with
authoritative citations — not OCR engines or OpenAI SDKs.
"""

from app.rules.engine import aggregate_overall_status, default_rules, run_rules

__all__ = ["aggregate_overall_status", "default_rules", "run_rules"]
