"""
In-memory batch job store for the local prototype.

Architectural responsibility: hold active batches without requiring SQLite.
Structured so a later persistence layer can replace this store.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.batch.models import (
    BatchItemProcessingState,
    BatchJobState,
    BatchValidationResult,
    ManifestRow,
)
from app.models.verification import SingleReviewVerificationResponse


@dataclass
class BatchItemRecord:
    """Mutable per-item state held during/after processing."""

    item_id: str
    filename: str
    row: ManifestRow
    image_bytes: bytes
    content_type: str | None
    processing_state: BatchItemProcessingState = BatchItemProcessingState.QUEUED
    overall_status: str | None = None
    ai_assisted: bool = False
    processing_time_ms: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    review_reason_codes: list[str] = field(default_factory=list)
    result: SingleReviewVerificationResponse | None = None


@dataclass
class BatchJobRecord:
    """One in-memory batch job."""

    batch_id: str
    state: BatchJobState
    concurrency: int
    ai_budget_max: int
    validation: BatchValidationResult
    items: list[BatchItemRecord]
    created_at: float = field(default_factory=time.perf_counter)
    started_at: float | None = None
    finished_at: float | None = None
    ai_calls_used: int = 0
    ai_budget_exhausted: bool = False
    message: str | None = None
    # Privacy-safe correlation for audit logs (captured at create time).
    audit_request_id: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class BatchStore:
    """Thread-safe in-memory registry of batch jobs (prototype)."""

    def __init__(self) -> None:
        self._jobs: dict[str, BatchJobRecord] = {}
        self._lock = threading.Lock()

    def put(self, job: BatchJobRecord) -> None:
        with self._lock:
            self._jobs[job.batch_id] = job

    def get(self, batch_id: str) -> BatchJobRecord | None:
        with self._lock:
            return self._jobs.get(batch_id)

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


_STORE = BatchStore()


def get_batch_store() -> BatchStore:
    """Return the process-wide batch store."""
    return _STORE
