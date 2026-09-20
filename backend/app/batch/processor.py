"""
Legacy BatchProcessor stub replaced by BatchOrchestrator (Phase 7).

Architectural responsibility: keep import path for older references; prefer orchestrator.
"""

from __future__ import annotations

from app.batch.orchestrator import BatchOrchestrator

# Back-compat alias
BatchProcessor = BatchOrchestrator
