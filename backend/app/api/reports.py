"""
Excel report HTTP endpoints.

Architectural responsibility: accept verification/batch payloads and return .xlsx —
no OCR or rule evaluation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.batch.store import get_batch_store
from app.models.verification import SingleReviewVerificationResponse
from app.reporting.batch_report import build_batch_xlsx
from app.reporting.single_report import build_single_review_xlsx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post(
    "/single",
    summary="Generate Excel report for a Single Label review",
)
async def export_single_xlsx(payload: SingleReviewVerificationResponse) -> Response:
    """Build a formatted .xlsx from an already-completed verification response."""
    try:
        content = build_single_review_xlsx(payload)
    except Exception:
        logger.exception("single_xlsx_generation_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Unable to generate the Excel report. Please try again.",
                "code": "report_generation_failed",
            },
        ) from None
    vid = (payload.verification_id or "review")[:12]
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="labelverify-review-{vid}.xlsx"',
        },
    )


@router.get(
    "/batches/{batch_id}",
    summary="Generate Excel report for a batch job",
)
async def export_batch_xlsx(batch_id: str) -> Response:
    """Build a multi-sheet .xlsx for a batch job."""
    job = get_batch_store().get(batch_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Batch not found.", "code": "batch_not_found"},
        )
    try:
        content = build_batch_xlsx(job)
    except Exception:
        logger.exception("batch_xlsx_generation_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Unable to generate the Excel report. Please try again.",
                "code": "report_generation_failed",
            },
        ) from None
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="labelverify-batch-{batch_id[:8]}.xlsx"'
            ),
        },
    )
