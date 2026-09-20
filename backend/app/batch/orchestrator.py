"""
Batch orchestrator: validate → schedule → VerificationService per item → summarize.

Architectural responsibility: concurrency and progress only. Regulatory verification
always comes from VerificationService (same path as Single Review).
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.ai.factory import create_ai_provider
from app.batch.budget_ai import BudgetAwareAiProvider
from app.batch.export import build_export_csv
from app.batch.manifest import parse_and_validate_manifest, sanitize_upload_filename
from app.batch.models import (
    BatchCreateResponse,
    BatchItemDetail,
    BatchItemProcessingState,
    BatchItemSummary,
    BatchJobState,
    BatchJobStatus,
    BatchSummaryCounts,
    BatchValidationResult,
)
from app.batch.store import BatchItemRecord, BatchJobRecord, BatchStore, get_batch_store
from app.core.audit import (
    BATCH_REVIEW_COMPLETED,
    BATCH_REVIEW_STARTED,
    emit_application_error,
    emit_audit_event,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import ImageValidationError
from app.core.request_context import get_request_id
from app.ocr.base import OcrProvider
from app.ocr.errors import OcrProviderError
from app.services.verification_service import VerificationService

logger = logging.getLogger(__name__)


class BatchOrchestrator:
    """Orchestrates batch validation and concurrent VerificationService calls."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        store: BatchStore | None = None,
        verification_factory: object | None = None,
        ocr_provider: OcrProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or get_batch_store()
        self._ocr_provider = ocr_provider
        # Optional injectable factory: () -> VerificationService
        self._verification_factory = verification_factory

    def validate(
        self,
        csv_bytes: bytes,
        image_filenames: list[str],
    ) -> BatchValidationResult:
        """Validate manifest against uploaded image filenames."""
        return parse_and_validate_manifest(
            csv_bytes,
            image_filenames,
            settings=self._settings,
        )

    def create_and_start(
        self,
        csv_bytes: bytes,
        images: dict[str, tuple[bytes, str | None]],
        image_filenames: list[str],
        *,
        start_background: bool = True,
    ) -> BatchCreateResponse:
        """Validate, create job, optionally start background processing."""
        validation = self.validate(csv_bytes, image_filenames)
        if not validation.valid:
            raise BatchValidationError(validation)

        batch_id = str(uuid.uuid4())
        items: list[BatchItemRecord] = []
        for row in validation.rows:
            if row.filename not in images:
                raise BatchValidationError(validation)
            data, content_type = images[row.filename]
            items.append(
                BatchItemRecord(
                    item_id=str(uuid.uuid4()),
                    filename=row.filename,
                    row=row,
                    image_bytes=data,
                    content_type=content_type,
                ),
            )

        job = BatchJobRecord(
            batch_id=batch_id,
            state=BatchJobState.QUEUED,
            concurrency=self._settings.batch_max_concurrency,
            ai_budget_max=self._settings.batch_ai_max_calls,
            validation=validation,
            items=items,
            audit_request_id=get_request_id(),
        )
        self._store.put(job)

        emit_audit_event(
            BATCH_REVIEW_STARTED,
            request_id=job.audit_request_id,
            batch_id=batch_id,
            label_count=len(items),
        )

        if start_background:
            thread = threading.Thread(
                target=self._run_job,
                args=(batch_id,),
                name=f"batch-{batch_id[:8]}",
                daemon=True,
            )
            thread.start()
        else:
            self._run_job(batch_id)

        return BatchCreateResponse(
            batch_id=batch_id,
            state=BatchJobState.QUEUED,
            summary=self._summary(job),
            concurrency=job.concurrency,
        )

    def get_status(self, batch_id: str) -> BatchJobStatus | None:
        job = self._store.get(batch_id)
        if job is None:
            return None
        with job.lock:
            return self._status_snapshot(job)

    def get_item_detail(self, batch_id: str, item_id: str) -> BatchItemDetail | None:
        job = self._store.get(batch_id)
        if job is None:
            return None
        with job.lock:
            for item in job.items:
                if item.item_id == item_id:
                    return BatchItemDetail(
                        item_id=item.item_id,
                        filename=item.filename,
                        processing_state=item.processing_state,
                        error_code=item.error_code,
                        error_message=item.error_message,
                        result=item.result,
                    )
        return None

    def export_csv(self, batch_id: str) -> str | None:
        job = self._store.get(batch_id)
        if job is None:
            return None
        with job.lock:
            return build_export_csv(job)

    def run_sync_for_tests(self, batch_id: str) -> BatchJobStatus:
        """Run (or re-run) processing synchronously — tests only."""
        self._run_job(batch_id)
        status = self.get_status(batch_id)
        assert status is not None
        return status

    def _run_job(self, batch_id: str) -> None:
        job = self._store.get(batch_id)
        if job is None:
            return
        with job.lock:
            job.state = BatchJobState.PROCESSING
            job.started_at = time.perf_counter()

        budget_ai = BudgetAwareAiProvider(
            create_ai_provider(self._settings),
            max_calls=self._settings.batch_ai_max_calls,
            ai_concurrency=self._settings.batch_ai_concurrency,
        )

        workers = max(1, job.concurrency)
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self._process_item, job, item, budget_ai): item
                    for item in job.items
                }
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        future.result()
                    except Exception as exc:  # noqa: BLE001 — never abort batch
                        logger.exception(
                            "batch_item_unhandled batch_id=%s item=%s",
                            batch_id,
                            item.filename,
                        )
                        with job.lock:
                            item.processing_state = BatchItemProcessingState.ERROR
                            item.error_code = "processing_exception"
                            item.error_message = (
                                "This label could not be processed. "
                                "Other batch items continue."
                            )
                            # Avoid leaking exception type details to clients.
                            _ = type(exc).__name__
        finally:
            with job.lock:
                job.ai_calls_used = budget_ai.calls_used
                job.ai_budget_exhausted = budget_ai.budget_exhausted
                job.finished_at = time.perf_counter()
                job.state = BatchJobState.COMPLETED
                job.message = "Batch processing finished."
                summary = self._summary(job)
                started = job.started_at
                finished = job.finished_at
                audit_request_id = job.audit_request_id
            duration_ms = None
            if started is not None and finished is not None:
                duration_ms = round((finished - started) * 1000, 1)
            emit_audit_event(
                BATCH_REVIEW_COMPLETED,
                request_id=audit_request_id,
                batch_id=batch_id,
                label_count=summary.total,
                pass_count=summary.pass_count,
                review_count=summary.review_count,
                fail_count=summary.fail_count,
                error_count=summary.error_count,
                ai_calls_used=summary.ai_calls_used,
                duration_ms=duration_ms,
            )

    def _process_item(
        self,
        job: BatchJobRecord,
        item: BatchItemRecord,
        budget_ai: BudgetAwareAiProvider,
    ) -> None:
        with job.lock:
            item.processing_state = BatchItemProcessingState.PROCESSING

        try:
            service = self._make_verification_service(budget_ai)
            result = service.verify(
                item.image_bytes,
                item.row.to_application(),
                filename=item.filename,
                declared_content_type=item.content_type,
            )
            reason_codes = [
                c.reason_code
                for c in result.verification.checks
                if c.status.value == "REVIEW" and c.reason_code
            ]
            with job.lock:
                item.processing_state = BatchItemProcessingState.COMPLETED
                item.result = result
                item.overall_status = result.verification.overall_status.value
                item.ai_assisted = result.verification.ai_used
                item.processing_time_ms = result.processing_time_ms
                item.review_reason_codes = reason_codes
                # Surface budget exhaustion on the item when relevant.
                assist = result.verification.ai_assist or {}
                if assist.get("outcome") == "provider_unavailable" and budget_ai.budget_exhausted:
                    if "AI_BUDGET_EXHAUSTED" not in item.review_reason_codes:
                        item.review_reason_codes.append("AI_BUDGET_EXHAUSTED")
        except ImageValidationError as exc:
            with job.lock:
                item.processing_state = BatchItemProcessingState.ERROR
                item.error_code = exc.code
                item.error_message = exc.message
        except OcrProviderError:
            with job.lock:
                item.processing_state = BatchItemProcessingState.ERROR
                item.error_code = "ocr_unavailable"
                item.error_message = (
                    "Text reading failed for this image. Other items continue."
                )
        except Exception as exc:
            emit_application_error(
                operation="batch_item",
                stage="process_item",
                error_type=type(exc).__name__,
                message="Batch item processing failed; other items continue.",
                request_id=job.audit_request_id,
            )
            logger.exception("batch_item_error")
            with job.lock:
                item.processing_state = BatchItemProcessingState.ERROR
                item.error_code = "processing_exception"
                item.error_message = (
                    "This label could not be processed. Other batch items continue."
                )

    def _make_verification_service(self, budget_ai: BudgetAwareAiProvider) -> VerificationService:
        if self._verification_factory is not None:
            return self._verification_factory(budget_ai)  # type: ignore[operator]
        return VerificationService(
            settings=self._settings,
            ai_provider=budget_ai,
            ocr_provider=self._ocr_provider,
        )

    def _summary(self, job: BatchJobRecord) -> BatchSummaryCounts:
        counts = BatchSummaryCounts(total=len(job.items))
        for item in job.items:
            if item.processing_state == BatchItemProcessingState.QUEUED:
                counts.queued_count += 1
            elif item.processing_state == BatchItemProcessingState.PROCESSING:
                counts.processing_count += 1
            elif item.processing_state == BatchItemProcessingState.ERROR:
                counts.error_count += 1
            elif item.processing_state == BatchItemProcessingState.COMPLETED:
                counts.completed += 1
                if item.overall_status == "PASS":
                    counts.pass_count += 1
                elif item.overall_status == "REVIEW":
                    counts.review_count += 1
                elif item.overall_status == "FAIL":
                    counts.fail_count += 1
                if item.ai_assisted:
                    counts.ai_assisted_count += 1
        counts.ai_budget_exhausted = job.ai_budget_exhausted
        counts.ai_calls_used = job.ai_calls_used
        return counts

    def _status_snapshot(self, job: BatchJobRecord) -> BatchJobStatus:
        times = [
            i.processing_time_ms
            for i in job.items
            if i.processing_time_ms is not None
        ]
        elapsed = None
        if job.started_at is not None:
            end = job.finished_at or time.perf_counter()
            elapsed = (end - job.started_at) * 1000
        median = statistics.median(times) if times else None
        p95 = None
        if times:
            ordered = sorted(times)
            idx = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
            p95 = ordered[idx]

        return BatchJobStatus(
            batch_id=job.batch_id,
            state=job.state,
            summary=self._summary(job),
            items=[
                BatchItemSummary(
                    item_id=i.item_id,
                    filename=i.filename,
                    processing_state=i.processing_state,
                    overall_status=i.overall_status,
                    brand_name=i.row.brand_name,
                    class_type=i.row.class_type,
                    alcohol_content=i.row.alcohol_content,
                    net_contents=i.row.net_contents,
                    ai_assisted=i.ai_assisted,
                    processing_time_ms=i.processing_time_ms,
                    error_code=i.error_code,
                    error_message=i.error_message,
                    review_reason_codes=list(i.review_reason_codes),
                )
                for i in job.items
            ],
            elapsed_ms=elapsed,
            median_item_ms=median,
            p95_item_ms=p95,
            concurrency=job.concurrency,
            ai_budget_max=job.ai_budget_max,
            message=job.message,
            validation=job.validation,
        )


class BatchValidationError(Exception):
    """Raised when create is attempted with an invalid association."""

    def __init__(self, validation: BatchValidationResult) -> None:
        super().__init__("Batch validation failed")
        self.validation = validation


def prepare_image_uploads(
    files: list[tuple[str | None, bytes, str | None]],
) -> tuple[list[str], dict[str, tuple[bytes, str | None]]]:
    """
    Return (all original filenames for validation, safe-name → bytes map).

    Duplicate safe names leave the last bytes in the map; validation reports duplicates
    from the filename list.
    """
    names: list[str] = []
    by_safe: dict[str, tuple[bytes, str | None]] = {}
    for raw_name, data, content_type in files:
        names.append(raw_name or "")
        safe = sanitize_upload_filename(raw_name)
        if safe is not None:
            by_safe[safe] = (data, content_type)
    return names, by_safe
