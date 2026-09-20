"""
Batch domain models (API + orchestration).

Architectural responsibility: batch/item lifecycle and summaries — not regulatory rules.
Processing state (QUEUED/PROCESSING/…) is separate from PASS/REVIEW/FAIL.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.verification import ApplicationData, SingleReviewVerificationResponse


class BatchItemProcessingState(StrEnum):
    """Lifecycle of one batch item (not a regulatory outcome)."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class BatchJobState(StrEnum):
    """Overall batch job lifecycle."""

    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


REQUIRED_MANIFEST_COLUMNS: tuple[str, ...] = (
    "filename",
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
)


class ManifestRow(BaseModel):
    """One validated CSV row paired with a safe basename."""

    row_number: int
    filename: str
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str

    def to_application(self) -> ApplicationData:
        """Map CSV columns onto ApplicationData (alcohol_content → alcohol_content_abv)."""
        return ApplicationData(
            brand_name=self.brand_name,
            class_type=self.class_type,
            alcohol_content_abv=self.alcohol_content,
            net_contents=self.net_contents,
        )


class BatchValidationIssue(BaseModel):
    """One explainable validation problem (never silent)."""

    code: str
    message: str
    filename: str | None = None
    row_number: int | None = None


class BatchValidationResult(BaseModel):
    """Outcome of validating a manifest against uploaded images."""

    valid: bool
    row_count: int = 0
    image_count: int = 0
    matched_count: int = 0
    missing_count: int = 0
    unreferenced_count: int = 0
    issues: list[BatchValidationIssue] = Field(default_factory=list)
    rows: list[ManifestRow] = Field(default_factory=list)


class BatchItemSummary(BaseModel):
    """Compact row for the batch results table."""

    item_id: str
    filename: str
    processing_state: BatchItemProcessingState
    overall_status: str | None = None
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    ai_assisted: bool = False
    processing_time_ms: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    review_reason_codes: list[str] = Field(default_factory=list)


class BatchSummaryCounts(BaseModel):
    """Aggregate counts for the batch (processing vs verification kept distinct)."""

    total: int = 0
    completed: int = 0
    pass_count: int = 0
    review_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    queued_count: int = 0
    processing_count: int = 0
    ai_assisted_count: int = 0
    ai_budget_exhausted: bool = False
    ai_calls_used: int = 0


class BatchJobStatus(BaseModel):
    """Pollable batch job status for the UI."""

    batch_id: str
    state: BatchJobState
    summary: BatchSummaryCounts
    items: list[BatchItemSummary] = Field(default_factory=list)
    elapsed_ms: float | None = None
    median_item_ms: float | None = None
    p95_item_ms: float | None = None
    concurrency: int
    ai_budget_max: int
    message: str | None = None
    validation: BatchValidationResult | None = None


class BatchItemDetail(BaseModel):
    """Full Single Review-equivalent payload for one completed batch item."""

    item_id: str
    filename: str
    processing_state: BatchItemProcessingState
    error_code: str | None = None
    error_message: str | None = None
    result: SingleReviewVerificationResponse | None = None


class BatchCreateResponse(BaseModel):
    """Returned when a batch is accepted and processing starts."""

    batch_id: str
    state: BatchJobState
    summary: BatchSummaryCounts
    concurrency: int
    message: str = "Batch accepted; processing started."
